"""Estrategias de alocacao de recursos em um poligono 2D."""
import numpy as np
import shapely
from pyproj import Transformer
from shapely.geometry import Polygon

AMOSTRAS = 6000  # pontos usados para representar a area do poligono
AMOSTRAS_VERIFICACAO = 20000
ITERACOES_KMEANS = 50
ITERACOES_MINIMAX = 40


class ErroPoligono(ValueError):
    pass


def _poligono_valido(coordenadas):
    if len(coordenadas) < 3:
        raise ErroPoligono("O poligono precisa de pelo menos 3 vertices.")
    for lon, lat in coordenadas:
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise ErroPoligono(f"Coordenada fora do intervalo: {lon},{lat}")
    poligono = shapely.make_valid(Polygon(coordenadas))
    partes = [g for g in getattr(poligono, "geoms", [poligono]) if g.geom_type == "Polygon"]
    if not partes or max(p.area for p in partes) == 0:
        raise ErroPoligono("O poligono nao tem area.")
    return max(partes, key=lambda p: p.area)


def _amostrar(poligono, n, rng=None):
    """Pontos dentro do poligono: grade regular ou, com rng, aleatorios."""
    xmin, ymin, xmax, ymax = poligono.bounds
    if rng is None:
        passo = np.sqrt(poligono.area / n)
        xs = np.arange(xmin + passo / 2, xmax, passo)
        ys = np.arange(ymin + passo / 2, ymax, passo)
        x, y = (a.ravel() for a in np.meshgrid(xs, ys))
    else:
        x = rng.uniform(xmin, xmax, n * 3)
        y = rng.uniform(ymin, ymax, n * 3)
        passo = 0.0
    dentro = shapely.contains_xy(poligono, x, y)
    pts = np.column_stack([x[dentro], y[dentro]])
    if len(pts) == 0:  # poligono muito fino para a grade
        pts = np.array(poligono.representative_point().coords)
    return pts, passo


def _distancias(pts, centros):
    return np.linalg.norm(pts[:, None, :] - centros[None, :, :], axis=2)


def _kmeans(pts, k, rng):
    """k-means com inicializacao k-means++: espalha os recursos pela area."""
    centros = [pts[rng.integers(len(pts))]]
    for _ in range(1, k):
        d2 = _distancias(pts, np.array(centros)).min(axis=1) ** 2
        centros.append(pts[rng.choice(len(pts), p=d2 / d2.sum())] if d2.sum() > 0
                       else pts[rng.integers(len(pts))])
    centros = np.array(centros, dtype=float)
    for _ in range(ITERACOES_KMEANS):
        grupo = _distancias(pts, centros).argmin(axis=1)
        novos = np.array([pts[grupo == i].mean(axis=0) if np.any(grupo == i) else centros[i]
                          for i in range(k)])
        if np.allclose(novos, centros):
            break
        centros = novos
    return centros


def _minimax(pts, centros):
    """Reduz o maior raio: move cada centro para o centro do menor circulo
    que contem os pontos atendidos por ele (heuristica para o k-centro)."""
    melhor, melhor_raio = centros, _distancias(pts, centros).min(axis=1).max()
    for _ in range(ITERACOES_MINIMAX):
        grupo = _distancias(pts, centros).argmin(axis=1)
        novos = centros.copy()
        for i in range(len(centros)):
            membros = pts[grupo == i]
            if len(membros):
                circulo = shapely.minimum_bounding_circle(shapely.multipoints(membros))
                novos[i] = np.array(circulo.centroid.coords[0])
        raio = _distancias(pts, novos).min(axis=1).max()
        if raio >= melhor_raio - 1e-6:
            break
        centros, melhor, melhor_raio = novos, novos, raio
    return melhor, melhor_raio


def _projecao(centro):
    """Projecao azimutal equidistante centrada na cidade: distancias em metros."""
    proj = f"+proj=aeqd +lat_0={centro.y} +lon_0={centro.x} +datum=WGS84 +units=m"
    ida = Transformer.from_crs("EPSG:4326", proj, always_xy=True)
    volta = Transformer.from_crs(proj, "EPSG:4326", always_xy=True)
    return ida, volta


def _para_lat_lng(volta, centros):
    lon, lat = volta.transform(centros[:, 0], centros[:, 1])
    return [{"lat": round(float(la), 6), "lng": round(float(lo), 6)}
            for lo, la in zip(np.atleast_1d(lon), np.atleast_1d(lat))]


def linear_area_cidade(coordenadas, recursos, semente=0, **_):
    """Distribui `recursos` circulos de mesmo raio cobrindo toda a area do
    poligono com o menor raio que a heuristica encontrar.

    "Linear": cada ponto da area tem o mesmo peso (densidade uniforme).
    coordenadas: lista de [lon, lat] em graus.
    """
    poligono = _poligono_valido(coordenadas)
    ida, volta = _projecao(poligono.centroid)
    poligono_m = shapely.transform(poligono, ida.transform, interleaved=False)
    centros, raio, cobertura = _cobrir_uniforme(poligono_m, recursos, semente)
    return {
        "raio_m": round(float(raio), 1),
        "pontos": _para_lat_lng(volta, centros),
        "area_poligono_km2": round(poligono_m.area / 1e6, 3),
        "cobertura": round(cobertura, 4),
    }


def _cobrir_uniforme(poligono_m, recursos, semente=0):
    """Nucleo da cobertura "linear" (area uniforme) num poligono em metros:
    devolve os centros, o menor raio comum que cobre o poligono e a fracao
    da area efetivamente coberta (verificada em pontos aleatorios)."""
    rng = np.random.default_rng(semente)
    pts, passo = _amostrar(poligono_m, AMOSTRAS)
    k = min(recursos, len(pts))
    centros = _kmeans(pts, k, rng)
    centros, raio = _minimax(pts, centros)
    # Margem de meia diagonal da grade: cobre tambem a area entre os pontos
    raio += passo * np.sqrt(2) / 2

    verificacao, _ = _amostrar(poligono_m, AMOSTRAS_VERIFICACAO, rng)
    cobertura = float((_distancias(verificacao, centros).min(axis=1) <= raio).mean())
    return centros, raio, cobertura


# ---------------------------------------------------------------------------
# Drones (3D): linear - cobertura de area
# ---------------------------------------------------------------------------

def linear_area_drones(largura_m, comprimento_m, drones, altitude_m, semente=0):
    """Posiciona `drones` numa altitude fixa sobre uma area retangular
    (centrada na origem, x = largura, y = comprimento), de forma que a area
    no chao fique coberta por igual, com o menor raio de cobertura comum.

    Devolve as posicoes (x, y, z) em metros, o raio de cobertura no chao e o
    angulo de abertura que a camera/sensor de cada drone precisa ter para
    enxergar esse raio a partir da altitude.
    """
    if largura_m <= 0 or comprimento_m <= 0:
        raise ErroPoligono("A largura e o comprimento da area devem ser positivos.")
    if altitude_m <= 0:
        raise ErroPoligono("A altitude deve ser positiva.")
    area = shapely.box(-largura_m / 2, -comprimento_m / 2, largura_m / 2, comprimento_m / 2)
    centros, raio, cobertura = _cobrir_uniforme(area, drones, semente)
    return {
        "posicoes": [{"x": round(float(x), 3), "y": round(float(y), 3), "z": round(float(altitude_m), 3)}
                     for x, y in centros],
        "raio_cobertura_m": round(float(raio), 2),
        "abertura_sensor_graus": round(float(np.degrees(2 * np.arctan(raio / altitude_m))), 1),
        "area_m2": round(float(area.area), 1),
        "cobertura": round(cobertura, 4),
    }


ESTRATEGIAS_3D = {
    "linear-area-drones": {"nome": "linear - cobertura de área", "funcao": linear_area_drones},
}


# ---------------------------------------------------------------------------
# linear - densidade por bairros
# ---------------------------------------------------------------------------

AMOSTRAS_POPULACAO = 20000  # pontos que representam a distribuicao da populacao
ITERACOES_PARTICAO = 120
RODADAS_AJUSTE = 4
CANDIDATOS_POR_TERRITORIO = 200
ITERACOES_REFINO = 30
PESO_SOBREPOSICAO = 0.5
ESCALAS_RAIO = (0.8, 0.9, 1.0, 1.1)  # raios testados em volta do raio inicial
LIMITE_SALTO = 0.3  # circulo com desvio acima de 30% do alvo testa saltos
SALTOS = 24


def _areas_validas(areas):
    """[{geometria (GeoJSON), populacao, ...}] -> (geometrias, populacoes)."""
    if not areas:
        raise ErroPoligono("Esta estrategia precisa das areas (bairros) com populacao.")
    geoms, pops = [], []
    for a in areas:
        try:
            g = shapely.make_valid(shapely.geometry.shape(a["geometria"]))
        except Exception as e:
            raise ErroPoligono(f"Geometria invalida na area '{a.get('id')}': {e}")
        if g.area > 0 and a["populacao"] > 0:
            geoms.append(g)
            pops.append(float(a["populacao"]))
    if not geoms:
        raise ErroPoligono("Nenhuma area com populacao e area positivas.")
    return np.array(geoms, dtype=object), np.array(pops)


def _densidade_em_pontos(areas_m, pops):
    """Representa a populacao por pontos de uma grade regular: a populacao de
    cada area e dividida igualmente entre os pontos que caem nela
    (distribuicao linear/uniforme dentro da area)."""
    area_total = shapely.area(areas_m).sum()
    passo = np.sqrt(area_total / AMOSTRAS_POPULACAO)
    xmin, ymin, xmax, ymax = shapely.total_bounds(areas_m)
    xs = np.arange(xmin + passo / 2, xmax, passo)
    ys = np.arange(ymin + passo / 2, ymax, passo)
    pts, pesos = [], []
    for geom, pop in zip(areas_m, pops):
        bx0, by0, bx1, by1 = geom.bounds
        gx = xs[(xs >= bx0) & (xs <= bx1)]
        gy = ys[(ys >= by0) & (ys <= by1)]
        x, y = (a.ravel() for a in np.meshgrid(gx, gy))
        dentro = shapely.contains_xy(geom, x, y)
        p = np.column_stack([x[dentro], y[dentro]])
        if len(p) == 0:  # area menor que a grade: concentra num ponto interno
            p = np.array(geom.representative_point().coords)
        pts.append(p)
        pesos.append(np.full(len(p), pop / len(p)))
    return np.vstack(pts), np.concatenate(pesos)


def _particao_equilibrada(pts, pesos, k, rng):
    """Divide os pontos em k territorios com a mesma populacao (diagrama de
    potencia: cada territorio tem um deslocamento ajustado ate as cargas se
    igualarem) e devolve o territorio de cada ponto e os centroides."""
    # Inicializacao k-means++ ponderada pela populacao
    centros = [pts[rng.choice(len(pts), p=pesos / pesos.sum())]]
    for _ in range(1, k):
        d2 = _distancias(pts, np.array(centros)).min(axis=1) ** 2 * pesos
        centros.append(pts[rng.choice(len(pts), p=d2 / d2.sum())] if d2.sum() > 0
                       else pts[rng.integers(len(pts))])
    centros = np.array(centros, dtype=float)
    alvo = pesos.sum() / k
    deslocamento = np.zeros(k)
    for i in range(ITERACOES_PARTICAO):
        d2 = _distancias(pts, centros) ** 2
        territorio = (d2 - deslocamento).argmin(axis=1)
        carga = np.bincount(territorio, weights=pesos, minlength=k)
        escala = np.median(d2.min(axis=1)) + 1.0
        passo = 0.5 * (1 - i / ITERACOES_PARTICAO) + 0.05
        deslocamento += passo * escala * (alvo - carga) / alvo
        for j in range(k):
            m = territorio == j
            if m.any():
                centros[j] = np.average(pts[m], axis=0, weights=pesos[m])
    return territorio, centros


def _capturada(pts, pesos, centro, raio):
    return pesos[np.linalg.norm(pts - centro, axis=1) <= raio].sum()


def _ajustar_raio(pts, pesos, centros, alvo):
    """Raio comum para que, em media, cada circulo contenha `alvo` pessoas."""
    d = _distancias(pts, centros)
    baixo, alto = 0.0, float(d.max())
    for _ in range(50):
        meio = (baixo + alto) / 2
        media = (pesos[:, None] * (d <= meio)).sum(axis=0).mean()
        baixo, alto = (meio, alto) if media < alvo else (baixo, meio)
    return alto


def _posicionar(pts, pesos, territorio, centroides, raio, alvo, rng):
    """Dentro do seu territorio, cada circulo vai para a posicao em que contem
    a populacao mais proxima do alvo (empate: mais perto do centroide)."""
    centros = centroides.copy()
    for j in range(len(centroides)):
        candidatos = pts[territorio == j]
        if len(candidatos) == 0:
            continue
        if len(candidatos) > CANDIDATOS_POR_TERRITORIO:
            candidatos = candidatos[rng.choice(len(candidatos), CANDIDATOS_POR_TERRITORIO,
                                               replace=False)]
        candidatos = np.vstack([centroides[j], candidatos])
        # So os pontos que algum candidato pode alcancar
        xmin, ymin = candidatos.min(axis=0) - raio
        xmax, ymax = candidatos.max(axis=0) + raio
        perto = ((pts[:, 0] >= xmin) & (pts[:, 0] <= xmax) &
                 (pts[:, 1] >= ymin) & (pts[:, 1] <= ymax))
        p, w = pts[perto], pesos[perto]
        capt = np.array([w[np.linalg.norm(p - c, axis=1) <= raio].sum() for c in candidatos])
        erro = np.abs(capt - alvo) / alvo
        afastamento = np.linalg.norm(candidatos - centroides[j], axis=1) / max(raio, 1.0)
        centros[j] = candidatos[np.argmin(erro + 0.02 * afastamento)]
    return centros


def _custo(pts, pesos, centros, raio, alvo):
    """Soma dos desvios relativos ao quadrado entre a populacao de cada
    circulo e o alvo (0 = todos os circulos com exatamente o alvo)."""
    capt = pesos @ (_distancias(pts, centros) <= raio)
    return float((((capt - alvo) / alvo) ** 2).sum())


def _refinar(pts, pesos, centros, raio, alvo, regiao, rng):
    """Busca local com raio fixo: move um circulo por vez (8 direcoes, passos
    decrescentes) para aproximar a sua populacao do alvo, penalizando a
    populacao que ele divide com outros circulos (evita circulos empilhados).
    Circulos muito longe do alvo tambem testam saltos para pontos sorteados
    pela populacao. O centro deve ficar dentro da regiao (uniao das areas)."""
    prob = pesos / pesos.sum()
    angulos = np.linspace(0, 2 * np.pi, 8, endpoint=False)
    direcoes = np.column_stack([np.cos(angulos), np.sin(angulos)])
    passos = raio * np.array([1.0, 0.5, 0.25, 0.1])
    alcance = raio + passos[0]
    centros = centros.copy()
    cobre = _distancias(pts, centros) <= raio
    contagem = cobre.sum(axis=1)
    for _ in range(ITERACOES_REFINO):
        capt = pesos @ cobre
        houve_melhora = False
        for j in np.argsort(-np.abs(capt - alvo)):
            cands = np.vstack([centros[j], (centros[j] + passos[:, None, None] *
                                            direcoes[None]).reshape(-1, 2)])
            validos = shapely.contains_xy(regiao, cands[1:, 0], cands[1:, 1])
            cands = cands[np.concatenate([[True], validos])]
            if abs(capt[j] - alvo) > LIMITE_SALTO * alvo:
                saltos = pts[rng.choice(len(pts), SALTOS, p=prob)]
                cands = np.vstack([cands, saltos])
                perto = np.arange(len(pts))
            else:  # so os pontos que algum candidato pode alcancar
                perto = np.flatnonzero(np.abs(pts - centros[j]).max(axis=1) <= alcance)
            p, w = pts[perto], pesos[perto]
            outros = (contagem[perto] - cobre[perto, j]) > 0
            dentro = np.linalg.norm(p[None] - cands[:, None], axis=2) <= raio
            c_capt = dentro @ w
            c_sobre = (dentro & outros) @ w
            custo = ((c_capt - alvo) / alvo) ** 2 + PESO_SOBREPOSICAO * (c_sobre / alvo) ** 2
            melhor = int(np.argmin(custo))
            if melhor != 0 and custo[melhor] < custo[0] - 1e-9:
                centros[j] = cands[melhor]
                capt[j] = c_capt[melhor]
                contagem[perto] += dentro[melhor].astype(int) - cobre[perto, j]
                cobre[:, j] = False
                cobre[perto, j] = dentro[melhor]
                houve_melhora = True
        if not houve_melhora:
            break
    return centros


def populacao_nos_circulos(centros_m, raio, areas_m, pops):
    """Regra exata: cada area contribui com populacao * (area do circulo
    dentro dela / area dela)."""
    arvore = shapely.STRtree(areas_m)
    area_areas = shapely.area(areas_m)
    resultado = []
    for c in centros_m:
        circulo = shapely.Point(c).buffer(raio, quad_segs=32)
        idx = arvore.query(circulo, predicate="intersects")
        inter = shapely.area(shapely.intersection(areas_m[idx], circulo))
        resultado.append(float((pops[idx] * inter / area_areas[idx]).sum()))
    return np.array(resultado)


def _populacao_coberta(centros_m, raio, areas_m, pops):
    """Populacao dentro da uniao dos circulos (sem contar sobreposicao duas vezes)."""
    uniao = shapely.union_all([shapely.Point(c).buffer(raio, quad_segs=32) for c in centros_m])
    inter = shapely.area(shapely.intersection(areas_m, uniao))
    return float((pops * inter / shapely.area(areas_m)).sum())


def linear_densidade_bairros(coordenadas, recursos, areas=None, semente=0, **_):
    """Circulos de mesmo raio em que cada um contem, aproximadamente, a mesma
    populacao (populacao total / recursos).

    A populacao de cada area (bairro) e distribuida de forma uniforme dentro
    dela: um circulo que cobre metade da area de um bairro recebe metade da
    populacao do bairro.
    coordenadas: contorno do municipio [lon, lat] (usado para validacao).
    areas: [{id, nome, populacao, geometria (GeoJSON em lon/lat)}].
    """
    _poligono_valido(coordenadas)
    geoms, pops = _areas_validas(areas)
    ida, volta = _projecao(shapely.union_all(geoms).centroid)
    areas_m = np.array([shapely.transform(g, ida.transform, interleaved=False) for g in geoms])

    rng = np.random.default_rng(semente)
    pts, pesos = _densidade_em_pontos(areas_m, pops)
    k = min(recursos, len(pts))
    alvo = pops.sum() / k

    # 1) Territorios com a mesma populacao; 2) circulo posicionado dentro do
    # territorio e raio comum ajustado; 3) busca local testando alguns raios.
    territorio, centroides = _particao_equilibrada(pts, pesos, k, rng)
    centros = centroides
    for _ in range(RODADAS_AJUSTE):
        raio = _ajustar_raio(pts, pesos, centros, alvo)
        centros = _posicionar(pts, pesos, territorio, centroides, raio, alvo, rng)
    raio = _ajustar_raio(pts, pesos, centros, alvo)

    regiao = shapely.union_all(areas_m)
    shapely.prepare(regiao)
    melhor = (_custo(pts, pesos, centros, raio, alvo), centros, raio)
    for escala in ESCALAS_RAIO:
        r = raio * escala
        c = _posicionar(pts, pesos, territorio, centroides, r, alvo, rng)
        c = _refinar(pts, pesos, c, r, alvo, regiao, rng)
        custo = _custo(pts, pesos, c, r, alvo)
        if custo < melhor[0]:
            melhor = (custo, c, r)
    _, centros, raio = melhor

    populacoes = populacao_nos_circulos(centros, raio, areas_m, pops)
    pontos = _para_lat_lng(volta, centros)
    for p, pop in zip(pontos, populacoes):
        p["populacao"] = round(float(pop))
    coberta = _populacao_coberta(centros, raio, areas_m, pops)
    return {
        "raio_m": round(float(raio), 1),
        "pontos": pontos,
        "area_poligono_km2": round(float(shapely.area(areas_m).sum()) / 1e6, 3),
        "cobertura": round(coberta / pops.sum(), 4),
        "populacao": {
            "total": round(float(pops.sum())),
            "alvo_por_recurso": round(float(alvo)),
            "media_por_recurso": round(float(populacoes.mean())),
            "minimo": round(float(populacoes.min())),
            "maximo": round(float(populacoes.max())),
            "coeficiente_variacao": round(float(populacoes.std() / populacoes.mean()), 4)
            if populacoes.mean() > 0 else None,
            "coberta": round(coberta),
            "areas": len(geoms),
        },
    }


ESTRATEGIAS = {
    "linear-area-cidade": {"nome": "linear - área da cidade", "funcao": linear_area_cidade,
                           "precisa_areas": False},
    "linear-densidade-bairros": {"nome": "linear - densidade por bairros",
                                 "funcao": linear_densidade_bairros, "precisa_areas": True},
}

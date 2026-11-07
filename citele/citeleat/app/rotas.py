"""Estrategia "linear - tempo de deslocamento": posiciona os recursos na
malha viaria minimizando o tempo medio de viagem (pela rota mais rapida)
do recurso mais proximo ate qualquer ponto da cidade (p-mediana).

"Linear": todos os pontos da area do municipio tem o mesmo peso, e cada via
tem velocidade constante (sem transito).
"""
import os
from functools import lru_cache
from pathlib import Path

import numpy as np
import shapely
from scipy.sparse import csr_matrix
from scipy.optimize import linear_sum_assignment
from scipy.sparse.csgraph import dijkstra, maximum_bipartite_matching
from scipy.spatial import cKDTree

from .estrategias import (ErroPoligono, _amostrar, _distancias, _para_lat_lng, _poligono_valido,
                          _projecao)

PASTA_ROTAS = Path(os.environ.get(
    "ROTAS_DIR", Path(__file__).resolve().parents[2] / "dados" / "rotas"))
PONTOS_DEMANDA = 3000  # pontos que representam "qualquer ponto da cidade"
VELOCIDADE_ACESSO = 20 / 3.6  # m/s do ponto ate a via mais proxima (fora da malha)
CANDIDATOS = 250  # locais avaliados na primeira etapa
VIZINHOS_REFINO = 12  # locais testados em volta de cada recurso na segunda etapa


@lru_cache(maxsize=8)
def _carregar_malha(municipio):
    arquivo = PASTA_ROTAS / f"{municipio}.npz"
    if not arquivo.exists():
        raise ErroPoligono(f"Malha viaria nao disponivel para o municipio {municipio} "
                           "(a estrategia atende as capitais).")
    d = np.load(arquivo)
    n = len(d["lon"])
    # Arestas paralelas: fica a mais rapida (csr_matrix somaria os tempos)
    ordem = np.lexsort((d["tempo_s"], d["destino"], d["origem"]))
    o, t, s = d["origem"][ordem], d["destino"][ordem], d["tempo_s"][ordem]
    primeira = np.ones(len(o), dtype=bool)
    primeira[1:] = (o[1:] != o[:-1]) | (t[1:] != t[:-1])
    grafo = csr_matrix((np.maximum(s[primeira], 1e-3), (o[primeira], t[primeira])), shape=(n, n))
    # Comprimento da mesma aresta (a mais rapida), para medir as rotas
    comprimentos = csr_matrix((d["comprimento_m"][ordem][primeira], (o[primeira], t[primeira])),
                              shape=(n, n))
    return grafo, comprimentos, d["lon"].copy(), d["lat"].copy()


def _tempos(grafo, origens, destinos):
    """Tempo (s) da rota mais rapida de cada origem ate cada destino."""
    return dijkstra(grafo, directed=True, indices=origens)[:, destinos]


def _p_mediana(custos, k):
    """Escolhe k linhas (locais) minimizando a soma, por coluna (ponto), do
    menor custo entre as linhas escolhidas: guloso + trocas (Teitz-Bart)."""
    n_cand = custos.shape[0]
    escolhidos = []
    melhor = np.full(custos.shape[1], np.inf)
    for _ in range(k):
        totais = np.minimum(custos, melhor).sum(axis=1)
        totais[escolhidos] = np.inf
        c = int(np.argmin(totais))
        escolhidos.append(c)
        melhor = np.minimum(melhor, custos[c])

    while True:
        sub = custos[escolhidos]
        ordem = np.argsort(sub, axis=0)
        primeiro = sub[ordem[0], np.arange(sub.shape[1])]
        segundo = (sub[ordem[1], np.arange(sub.shape[1])] if k > 1
                   else np.full(sub.shape[1], np.inf))
        atual = primeiro.sum()
        melhor_troca = (0.0, None, None)
        for i in range(k):
            # Custo de cada ponto sem o local i
            sem_i = np.where(ordem[0] == i, segundo, primeiro)
            totais = np.minimum(custos, sem_i).sum(axis=1)
            totais[escolhidos] = np.inf
            c = int(np.argmin(totais))
            ganho = atual - totais[c]
            if ganho > melhor_troca[0] + 1e-6:
                melhor_troca = (ganho, i, c)
        if melhor_troca[1] is None:
            return escolhidos
        escolhidos[melhor_troca[1]] = melhor_troca[2]


def tempo_medio_min(coordenadas, municipio, pontos):
    """Tempo medio (min) ate qualquer ponto da cidade partindo do recurso mais
    rapido, para recursos em `pontos` [{lat, lng}] (ex.: de outra estrategia)."""
    poligono = _poligono_valido(coordenadas)
    grafo, _, lon, lat = _carregar_malha(municipio)
    ida, _ = _projecao(poligono.centroid)
    poligono_m = shapely.transform(poligono, ida.transform, interleaved=False)
    arvore = cKDTree(np.column_stack(ida.transform(lon, lat)))
    demanda, _ = _amostrar(poligono_m, PONTOS_DEMANDA)
    dist_acesso, no_demanda = arvore.query(demanda)
    origens = arvore.query(np.column_stack(ida.transform(
        [p["lng"] for p in pontos], [p["lat"] for p in pontos])))[1]
    tempos = _tempos(grafo, origens, no_demanda) + dist_acesso / VELOCIDADE_ACESSO
    return float(tempos.min(axis=0).mean()) / 60


def linear_tempo_deslocamento(coordenadas, recursos, municipio=None, semente=0, **_):
    """coordenadas: contorno do municipio [lon, lat]; municipio: CD_MUN, que
    identifica a malha viaria em dados/rotas/."""
    if not municipio:
        raise ErroPoligono("Esta estrategia precisa do codigo do municipio (malha viaria).")
    poligono = _poligono_valido(coordenadas)
    grafo, _, lon, lat = _carregar_malha(municipio)
    ida, volta = _projecao(poligono.centroid)
    poligono_m = shapely.transform(poligono, ida.transform, interleaved=False)
    nos_xy = np.column_stack(ida.transform(lon, lat))
    arvore = cKDTree(nos_xy)
    rng = np.random.default_rng(semente)

    # Demanda: pontos uniformes na area; cada um entra na malha pelo no mais proximo
    demanda, _ = _amostrar(poligono_m, PONTOS_DEMANDA)
    dist_acesso, no_demanda = arvore.query(demanda)
    tempo_acesso = dist_acesso / VELOCIDADE_ACESSO
    nos_unicos, no_para_coluna = np.unique(no_demanda, return_inverse=True)

    def custos(origens):
        return _tempos(grafo, origens, nos_unicos)[:, no_para_coluna] + tempo_acesso

    # Etapa 1: candidatos espalhados pela cidade (nos mais proximos de uma grade)
    grade, _ = _amostrar(poligono_m, CANDIDATOS)
    candidatos = np.unique(arvore.query(grade)[1])
    k = min(recursos, len(candidatos))
    matriz = custos(candidatos)
    escolhidos = candidatos[_p_mediana(matriz, k)]

    # Etapa 2: acrescenta vizinhos de cada recurso escolhido e otimiza de novo
    vizinhos = arvore.query(nos_xy[escolhidos], k=VIZINHOS_REFINO * 3)[1]
    extras = np.unique([rng.choice(v, VIZINHOS_REFINO, replace=False) for v in np.atleast_2d(vizinhos)])
    extras = np.setdiff1d(extras, candidatos)
    if len(extras):
        candidatos = np.concatenate([candidatos, extras])
        matriz = np.vstack([matriz, custos(extras)])
        escolhidos = candidatos[_p_mediana(matriz, k)]

    final = custos(escolhidos)
    atendido_por = final.argmin(axis=0)
    tempo = final.min(axis=0)  # s ate cada ponto de demanda
    centros = nos_xy[escolhidos]
    distancia = np.linalg.norm(demanda - centros[atendido_por], axis=1)

    pontos = _para_lat_lng(volta, centros)
    for j, p in enumerate(pontos):
        meus = atendido_por == j
        p["tempo_medio_min"] = round(float(tempo[meus].mean()) / 60, 2) if meus.any() else None
        p["area_atendida_pct"] = round(float(meus.mean()) * 100, 1)
    return {
        # Circulos iguais que contem 90% dos pontos atendidos por cada recurso
        # (o maximo e dominado por poucos pontos isolados)
        "raio_m": round(float(np.percentile(distancia, 90)), 1),
        "raio_maximo_m": round(float(distancia.max()), 1),
        "pontos": pontos,
        "area_poligono_km2": round(poligono_m.area / 1e6, 3),
        "cobertura": 1.0,
        "tempo": {
            "medio_min": round(float(tempo.mean()) / 60, 2),
            "mediano_min": round(float(np.median(tempo)) / 60, 2),
            "p90_min": round(float(np.percentile(tempo, 90)) / 60, 2),
            "maximo_min": round(float(tempo.max()) / 60, 2),
            "pontos_avaliados": len(demanda),
            "candidatos_avaliados": len(candidatos),
            "nos_malha": grafo.shape[0],
        },
    }


# ---------------------------------------------------------------------------
# Realocacao: rotas das posicoes atuais ate as novas
# ---------------------------------------------------------------------------

VELOCIDADE_LINHA_RETA = 30 / 3.6  # m/s, so quando nao ha malha viaria


def _caminho(predecessores, origem, destino):
    """Nos da rota mais rapida (Dijkstra com predecessores) de origem a destino."""
    nos = [destino]
    while nos[-1] != origem:
        anterior = predecessores[nos[-1]]
        if anterior < 0:
            raise ErroPoligono("Nao ha rota entre os pontos na malha viaria.")
        nos.append(anterior)
    return nos[::-1]


CRITERIOS = ("soma", "maximo")


def _tem_emparelhamento_perfeito(permitido):
    """Ha como ligar cada origem a um destino diferente so pelos pares permitidos?"""
    pares = maximum_bipartite_matching(csr_matrix(permitido.astype(np.int8)), perm_type="column")
    return bool((pares >= 0).all())


def _associar(custo, criterio):
    """Qual origem vai para qual destino.
    soma: minimiza a soma dos tempos (algoritmo hungaro).
    maximo: minimiza o maior tempo (o ultimo a chegar); entre as solucoes com
    esse maximo, minimiza a soma."""
    if criterio == "soma":
        return linear_sum_assignment(custo)
    # Menor limite L tal que existe emparelhamento so com pares de custo <= L
    valores = np.unique(custo)
    baixo, alto = 0, len(valores) - 1
    while baixo < alto:
        meio = (baixo + alto) // 2
        if _tem_emparelhamento_perfeito(custo <= valores[meio]):
            alto = meio
        else:
            baixo = meio + 1
    proibido = custo.sum() + 1  # nenhum par acima do limite entra na solucao
    return linear_sum_assignment(np.where(custo <= valores[baixo], custo, proibido))


def rotas_realocacao(origens, destinos, municipio=None, associar=True, criterio="soma"):
    """Leva cada recurso da posicao atual (origens) ate uma nova (destinos),
    pontos {lat, lng}. Com associar=True, escolhe qual recurso vai para qual
    posicao pelo criterio ("soma" ou "maximo", ver _associar); senao, i -> i.
    Usa a malha viaria do municipio; sem ela, linha reta a 30 km/h."""
    if criterio not in CRITERIOS:
        raise ErroPoligono(f"Criterio invalido: '{criterio}'. Opcoes: {', '.join(CRITERIOS)}")
    if len(origens) != len(destinos):
        raise ErroPoligono("Origens e destinos devem ter a mesma quantidade.")
    if not origens:
        return {"malha_viaria": False, "movimentos": [], "tempo_total_s": 0, "tempo_maximo_s": 0}
    o = np.array([[p["lng"], p["lat"]] for p in origens], dtype=float)
    d = np.array([[p["lng"], p["lat"]] for p in destinos], dtype=float)
    ida, _ = _projecao(shapely.Point(np.vstack([o, d]).mean(axis=0)))
    o_m = np.column_stack(ida.transform(o[:, 0], o[:, 1]))
    d_m = np.column_stack(ida.transform(d[:, 0], d[:, 1]))

    tem_malha = bool(municipio) and (PASTA_ROTAS / f"{municipio}.npz").exists()
    if tem_malha:
        grafo, comprimentos, lon, lat = _carregar_malha(municipio)
        arvore = cKDTree(np.column_stack(ida.transform(lon, lat)))
        acesso_o, no_o = arvore.query(o_m)
        acesso_d, no_d = arvore.query(d_m)
        tempos, predecessores = dijkstra(grafo, directed=True, indices=no_o,
                                         return_predecessors=True)
        custo = (tempos[:, no_d] + acesso_o[:, None] / VELOCIDADE_ACESSO
                 + acesso_d[None, :] / VELOCIDADE_ACESSO)
    else:
        custo = _distancias(o_m, d_m) / VELOCIDADE_LINHA_RETA

    if associar:
        linhas, colunas = _associar(custo, criterio)
    else:
        linhas = colunas = np.arange(len(origens))

    movimentos = []
    for i, j in zip(linhas, colunas):
        inicio = [round(o[i, 1], 6), round(o[i, 0], 6)]
        fim = [round(d[j, 1], 6), round(d[j, 0], 6)]
        if tem_malha:
            nos = _caminho(predecessores[i], no_o[i], no_d[j])
            caminho = [inicio, *([round(float(lat[n]), 6), round(float(lon[n]), 6)] for n in nos), fim]
            nas_ruas = float(np.asarray(comprimentos[nos[:-1], nos[1:]]).sum()) if len(nos) > 1 else 0.0
            distancia = acesso_o[i] + nas_ruas + acesso_d[j]
        else:
            caminho = [inicio, fim]
            distancia = float(np.linalg.norm(o_m[i] - d_m[j]))
        movimentos.append({
            "origem": int(i), "destino": int(j),
            "tempo_s": round(float(custo[i, j]), 1),
            "distancia_m": round(float(distancia), 1),
            "caminho": caminho,
        })
    tempos_mov = [m["tempo_s"] for m in movimentos]
    return {"malha_viaria": tem_malha, "criterio": criterio if associar else None,
            "movimentos": movimentos,
            "tempo_total_s": round(sum(tempos_mov), 1), "tempo_maximo_s": max(tempos_mov)}

# Citele

Sistema web para otimização da alocação de recursos em espaços geográficos.

| Módulo | Pasta | Tecnologia | Função |
|---|---|---|---|
| **Citeleat** | `citeleat/` | Python + FastAPI | Cálculos (otimização). Só backend. |
| **Citelemap** – backend | `citelemap/backend/` | Node.js + Express | Resolve cidade/estado → polígono, pré-processa e chama o Citeleat. |
| **Citelemap** – frontend | `citelemap/frontend/` | JavaScript + Google Maps (nginx) | Seções 1, 2 e 3 (localização, recursos, mapa). |
| Preparação de dados | `preparar_dados/` | Python + geopandas | Gera `dados/` a partir da Malha Municipal 2022 do IBGE. |
| **Citeledrone** | `citeledrone/` | Python (FastAPI) + ARGoS + three.js | Enxames de drones em 3D: posições pelo Citeleat, voo simulado no ARGoS e visualizado no navegador (http://localhost:8090). |

```
navegador ──► frontend (nginx :8080) ──/api──► citelemap-backend (:3000) ──GET──► citeleat (:8000)
                                                        │
                                                    dados/ (contornos dos municípios)
```


## Citeledrone (drones em 3D)

Cada drone é um recurso. O usuário informa a área (largura × comprimento, em metros), a quantidade
de drones, a altitude e a velocidade. Fluxo:

1. `POST /calc3ddrones` no Citeleat (estratégia `linear-area-drones`, "linear - cobertura de área"):
   os drones ficam numa altitude fixa e se espalham para que a área no chão fique coberta por igual,
   com o menor raio comum (mesmo núcleo da estratégia "área da cidade"). A resposta traz as
   posições `(x, y, z)`, o raio de cobertura no chão e a abertura de sensor/câmera necessária
   (`2·atan(raio/altitude)`).
2. O citeledrone gera um experimento do **ARGoS 3** (`3.0.0-beta59`, compilado sem interface no
   Docker): um `eye-bot` por drone, decolando de uma base logo abaixo da área. O controlador Lua
   (`citeledrone/argos/drone.lua`) sobe até a altitude e segue em linha reta até a posição, com
   perfil trapezoidal de velocidade (aceleração de 2 m/s²). A simulação usa 50 passos/s e
   1 iteração de física por passo: com menos passos o controlador de posição do eye-bot dá trancos
   e o drone ultrapassa o alvo.
3. As posições registradas a cada 0,2 s voltam para a página, que reproduz o voo em 3D (three.js):
   drones numerados, linha até o chão e o círculo de cobertura quando o drone chega.

**Operações nos drones (seção 3).** Cada simulação cria um *enxame* guardado em memória, com os
drones numerados e as posições atuais (`GET /api/enxames/{id}`).
`POST /api/enxames/{id}/drones/{numero}/remover` (corpo opcional `{"estrategia": "..."}`) apaga o
drone, recalcula as posições no Citeleat para os que restaram, com a estratégia selecionada, e
simula no ARGoS o voo de cada um **a partir de onde está no ar** até a nova posição. Quem vai para
onde é decidido minimizando o maior deslocamento (o último a chegar) e, em empate, a soma dos
deslocamentos. Os drones mantêm os números (apagar o 4 deixa 1, 2, 3, 5...).

Limitações desta versão: drones não desviam uns dos outros (o `pointmass3d` não trata colisões);
não há vento nem bateria; os drones aparecem ampliados na cena para serem visíveis.

Testes: `docker compose exec citeledrone python3 -m pytest -q tests` (após `pip install pytest`)
e `cd citeleat && python -m pytest`.

## Como rodar

1. Copie `.env.example` para `.env` e preencha `GOOGLE_MAPS_API_KEY`
   (chave da *Maps JavaScript API*). Sem a chave, o sistema funciona, mas o mapa não aparece.
2. `docker compose up -d --build`
3. Abra http://localhost:8080. A documentação do Citeleat fica em http://localhost:8000/docs.

## Fluxo

1. **Seção 1:** o usuário informa a cidade e o estado e clica em *Ir para a cidade*.
   O backend (`GET /api/municipio`) normaliza os nomes (aceita texto sem acento, em minúsculas
   e o estado por extenso), encontra o código IBGE e devolve o contorno do município e o seu bbox.
   O mapa enquadra a cidade e desenha o contorno. Se a cidade não for encontrada, mostra sugestões.
2. **Seção 2:** número de recursos, tipo (ambulância/polícia) e estratégia.
   *Calcular alocação* chama `POST /api/calcular`. O backend valida as entradas, simplifica o
   contorno até `MAX_VERTICES` vértices e chama
   `GET citeleat/calc2dpoligono?recursos=&estrategia=&coordenadas=lon,lat;lon,lat;...`
3. **Seção 3:** desenha um marcador para cada ponto devolvido e um círculo com o raio calculado.

## Citeleat: `calc2dpoligono`

| Parâmetro | Exemplo | |
|---|---|---|
| `recursos` | `10` | inteiro de 1 a 200 |
| `estrategia` | `linear-area-cidade` | "linear - área da cidade" (a outra estratégia exige POST, veja abaixo) |
| `coordenadas` | `-35.25,-5.85;-35.15,-5.85;-35.15,-5.75` | vértices `lon,lat` separados por `;` |

Resposta:
```json
{"estrategia": "linear-area-cidade", "recursos": 2, "vertices_recebidos": 4,
 "raio_m": 6235.0, "pontos": [{"lat": -5.775714, "lng": -35.199694}, {"lat": -5.824809, "lng": -35.199694}],
 "area_poligono_km2": 122.477, "cobertura": 1.0}
```
Também existe `POST /calc2dpoligono` com o mesmo cálculo, recebendo JSON
(`coordenadas` como lista de `[lon, lat]`), para polígonos grandes demais para uma URL.

**Estratégia "linear - área da cidade"**: todos os pontos da área têm o mesmo peso. O objetivo é
cobrir 100% do polígono com `recursos` círculos de mesmo raio, usando o menor raio que a
heurística encontrar (problema do *k-centro*):
1. projeta o polígono em metros (projeção azimutal equidistante centrada na cidade);
2. representa a área por uma grade de cerca de 6.000 pontos;
3. posiciona os recursos com k-means++ (espalhados pela área);
4. refina: move cada recurso para o centro do menor círculo que contém os pontos que ele atende,
   enquanto o maior raio diminuir;
5. o raio final é a maior distância de um ponto ao recurso mais próximo, mais meia diagonal da grade;
   a `cobertura` é verificada em 20.000 pontos aleatórios.

**Estratégia "linear - densidade por bairros"** (`linear-densidade-bairros`, só para as 27 capitais):
círculos de mesmo raio em que cada um contém aproximadamente a mesma população
(`população total ÷ recursos`). A população de cada bairro é distribuída uniformemente pela
área dele: um círculo que cobre metade da área de um bairro recebe metade da população dele.
Exige `POST /calc2dpoligono` com o campo `areas`:
```json
{"recursos": 10, "estrategia": "linear-densidade-bairros", "coordenadas": [[lon, lat], ...],
 "areas": [{"id": "2408102029", "nome": "Nossa Senhora da Apresentação", "populacao": 76177,
            "geometria": {"type": "MultiPolygon", "coordinates": [...]}}]}
```
A resposta traz a `populacao` de cada ponto e o bloco `populacao` (total, alvo por recurso,
mínimo, máximo, coeficiente de variação e população coberta). `cobertura` passa a ser a fração
da população dentro de algum círculo.
1. representa a população por cerca de 20.000 pontos de uma grade, com o peso de cada ponto igual a
   população do bairro ÷ pontos do bairro;
2. divide a cidade em `recursos` territórios com a mesma população (diagrama de potência);
3. ajusta o raio comum para que, em média, cada círculo contenha o alvo, e posiciona cada círculo
   no seu território;
4. busca local com alguns raios (0,8× a 1,1×): move os círculos, inclusive com saltos para
   áreas populosas, para aproximar cada um do alvo, penalizando sobreposição;
5. a população final de cada círculo é calculada exatamente, pela interseção dos polígonos.

Dados: `dados/areas/<CD_MUN>.json`, gerados por `preparar_dados/preparar_areas.py` a partir de
`bairros_capitais.gpkg` e `setores_capitais.gpkg` (Censo 2022). As capitais sem bairros no IBGE
usam a divisão mais próxima: São Paulo (96 distritos), Brasília (33 subdistritos, as Regiões
Administrativas), Goiânia (64 subdistritos), e Rio Branco, Palmas e São Luís (setores censitários).

**Estratégia "linear - tempo de deslocamento"** (`linear-tempo-deslocamento`, só para as 27
capitais): posiciona os recursos para minimizar o **tempo médio de viagem**, pela rota mais rápida
nas ruas, do recurso mais próximo até qualquer ponto da cidade (problema da p-mediana).
Exige o parâmetro `municipio` (código IBGE), que identifica a malha viária:
`GET /calc2dpoligono?recursos=10&estrategia=linear-tempo-deslocamento&municipio=2408102&coordenadas=...`
1. malha viária de carros do OpenStreetMap (`dados/rotas/<CD_MUN>.npz`, gerada por
   `preparar_dados/preparar_rotas.py` com o osmnx). Cada via tem velocidade constante: o `maxspeed`
   do OSM ou a velocidade típica do tipo de via (sem trânsito, por isso "linear");
2. "qualquer ponto da cidade" = cerca de 3.000 pontos uniformes na área do município. Cada ponto
   entra na malha pelo cruzamento mais próximo, a 20 km/h em linha reta;
3. tempos de rota calculados com Dijkstra a partir de cerca de 250 locais candidatos espalhados pela
   cidade; a escolha usa o algoritmo guloso seguido de trocas (Teitz-Bart); uma segunda rodada
   testa cruzamentos vizinhos aos escolhidos.

A resposta traz, em cada ponto, `tempo_medio_min` e `area_atendida_pct` (fatia da cidade que
chega mais rápido por ele) e o bloco `tempo` (médio, mediano, p90 e máximo, em minutos).
O `raio_m` é o de círculos iguais que contêm, em linha reta, 90% dos pontos atendidos por cada
recurso (`raio_maximo_m` contém 100%). É só uma referência visual: quem atende cada ponto é
decidido pelo tempo de rota.

Os marcadores usam os emojis de ambulância (U+1F691) e de viatura de polícia (U+1F694) do
[Twemoji](https://github.com/jdecked/twemoji) (licença CC-BY 4.0), em
`citelemap/frontend/public/icones/`.

## Recursos como objetos e operações (seção 4)

Ao calcular, o backend do Citelemap cria uma **alocação** (`id`) com um objeto para cada recurso
(`numero`, `tipo`, `lat`, `lng`, dados da estratégia e histórico de movimentos), guardada em
memória (`citelemap/backend/src/recursos.js`; some ao reiniciar o container).

- `GET /api/alocacoes/:id`: a alocação e os seus recursos.
- `DELETE /api/alocacoes/:id/recursos/:numero`: apaga o recurso, **recalcula** a alocação com os
  que restaram (mesma estratégia e cidade) e chama `POST /rotas2d` no Citeleat. A resposta traz,
  para cada recurso, a rota (`caminho`), a distância e o tempo da posição antiga até a nova. Os
  recursos mantêm os números (apagar o 3 deixa 1, 2, 4, 5...).

`POST /rotas2d` (Citeleat) recebe `origens`, `destinos`, `municipio` e `criterio`. Com
`associar: true`, decide qual recurso vai para qual nova posição e devolve a rota mais rápida
pelas ruas. Sem malha viária do município, a rota é em linha reta a 30 km/h. Critérios
(escolhidos na seção 4; no `DELETE`, `?criterio=`):
- `maximo` (padrão no Citelemap): menor tempo do **último a chegar**; entre as soluções empatadas,
  a de menor soma. Calculado com busca binária no limite de tempo + emparelhamento bipartido.
- `soma`: menor **tempo total** dos deslocamentos (algoritmo húngaro).

Exemplo em Natal (6 recursos, tempo de deslocamento, apagando o 3): `soma` → o último chega em
17,8 min (soma 21,7 min, um recurso atravessa a cidade); `maximo` → o último chega em 8,1 min
(soma 26,7 min, vários recursos se movem um pouco).

Novas estratégias são adicionadas no dicionário `ESTRATEGIAS` de `citeleat/app/estrategias.py`
(ou em `citeleat/app/main.py`, como a de tempo) e na lista `ESTRATEGIAS` de
`citelemap/backend/src/app.js`.

## Decisões desta versão

- **Polígono:** o contorno do município (Malha Municipal 2022 do IBGE). Em municípios com mais de
  uma parte (ilhas), é usada a maior parte.
- **Precisão:** 6 casas decimais (cerca de 0,1 m). Os contornos foram simplificados com tolerância de cerca de 33 m.
- **Vértices:** no máximo 1.000 por chamada (`MAX_VERTICES`). O Citeleat aceita URLs de até 1 MB.
- O **tipo de recurso** ainda não muda o cálculo: só define a cor dos marcadores
  (ambulância em vermelho, polícia em azul).
- Os dados de `dados/` entram na imagem do backend. Para regenerá-los:
  `docker compose --profile preparar run --rm preparar-dados`
  (requer `../malha_municipal/BR_Municipios_2022.shp`).

## Testes

```
# Citeleat
cd citeleat && python -m pytest

# Citelemap backend (rode fora do Google Drive: o npm falha em pastas sincronizadas)
cd citelemap/backend && npm install && DADOS_DIR=../../dados npm test
```

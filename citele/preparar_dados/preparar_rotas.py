"""Baixa a malha viaria (OpenStreetMap) das capitais para a estrategia
"linear - tempo de deslocamento".

Uso:
    python preparar_rotas.py <BR_Municipios_2022.shp> <pasta_saida> [CD_MUN ...]

Sem CD_MUN, processa as 27 capitais; municipios ja baixados sao pulados.

Saida: <pasta_saida>/rotas/<CD_MUN>.npz com o grafo dirigido de vias para
carros (maior componente fortemente conexo):
    lon, lat            coordenadas dos nos (graus)
    origem, destino     arestas (indices dos nos)
    tempo_s             tempo de percurso da aresta, a velocidade constante
                        por tipo de via (maxspeed do OSM ou media do tipo)
    comprimento_m       comprimento da aresta
"""
import sys
import tempfile
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import osmnx as ox

CAPITAIS = [
    "1100205", "1200401", "1302603", "1400100", "1501402", "1600303", "1721000",
    "2111300", "2211001", "2304400", "2408102", "2507507", "2611606", "2704302",
    "2800308", "2927408", "3106200", "3205309", "3304557", "3550308", "4106902",
    "4205407", "4314902", "5002704", "5103403", "5208707", "5300108",
]
# Velocidades (km/h) para vias sem maxspeed no OSM, por tipo
VELOCIDADES = {
    "motorway": 90, "trunk": 70, "primary": 50, "secondary": 40, "tertiary": 35,
    "unclassified": 30, "residential": 25, "living_street": 10, "service": 15,
    "motorway_link": 50, "trunk_link": 40, "primary_link": 35, "secondary_link": 30,
    "tertiary_link": 25, "road": 25, "track": 15,
}
MARGEM_GRAUS = 0.01  # ~1 km alem da divisa, para rotas que passam pelo vizinho
TENTATIVAS = 8
ESPERA_S = 180  # espera crescente entre tentativas (servidores Overpass publicos)
ESPERA_MAX_S = 900
# Servidores Overpass publicos, alternados a cada tentativa
SERVIDORES = [
    "https://overpass-api.de/api",
    "https://maps.mail.ru/osm/tools/overpass/api",
    "https://overpass.kumi.systems/api",
    "https://overpass.private.coffee/api",
]

ox.settings.cache_folder = str(Path(tempfile.gettempdir()) / "osmnx_cache")
ox.settings.requests_timeout = 600
ox.settings.log_console = False


def baixar(geometria):
    grafo = ox.graph_from_polygon(geometria.buffer(MARGEM_GRAUS), network_type="drive",
                                  retain_all=False, truncate_by_edge=True)
    grafo = ox.truncate.largest_component(grafo, strongly=True)
    grafo = ox.add_edge_speeds(grafo, hwy_speeds=VELOCIDADES, fallback=25)
    grafo = ox.add_edge_travel_times(grafo)
    nos = list(grafo.nodes)
    indice = {n: i for i, n in enumerate(nos)}
    arestas = list(grafo.edges(data=True))
    return {
        "lon": np.array([grafo.nodes[n]["x"] for n in nos]),
        "lat": np.array([grafo.nodes[n]["y"] for n in nos]),
        "origem": np.array([indice[u] for u, _, _ in arestas], dtype=np.int32),
        "destino": np.array([indice[v] for _, v, _ in arestas], dtype=np.int32),
        "tempo_s": np.array([d["travel_time"] for _, _, d in arestas], dtype=np.float32),
        "comprimento_m": np.array([d["length"] for _, _, d in arestas], dtype=np.float32),
    }


def main(shp, saida, codigos):
    pasta = Path(saida) / "rotas"
    pasta.mkdir(parents=True, exist_ok=True)
    mun = gpd.read_file(shp, engine="pyogrio", where="CD_MUN IN (" +
                        ",".join(f"'{c}'" for c in codigos) + ")")
    falhas = []
    # Menores primeiro: municipios enormes (Porto Velho, Rio Branco) exigem
    # muitas consultas e ficam para o fim
    mun["area"] = mun.to_crs(5880).area
    for linha in mun.sort_values("area").itertuples():
        arquivo = pasta / f"{linha.CD_MUN}.npz"
        if arquivo.exists():
            print(f"{linha.CD_MUN} {linha.NM_MUN}: ja existe")
            continue
        inicio = time.time()
        for tentativa in range(1, TENTATIVAS + 1):
            ox.settings.overpass_url = SERVIDORES[(tentativa - 1) % len(SERVIDORES)]
            try:
                dados = baixar(linha.geometry)
                break
            except Exception as e:  # Overpass fora do ar ou limitando o uso
                print(f"{linha.CD_MUN} {linha.NM_MUN}: tentativa {tentativa} falhou em "
                      f"{ox.settings.overpass_url} ({type(e).__name__})", flush=True)
                time.sleep(min(ESPERA_S * tentativa, ESPERA_MAX_S))
        else:
            falhas.append(linha.CD_MUN)
            continue
        np.savez_compressed(arquivo, **dados)
        print(f"{linha.CD_MUN} {linha.NM_MUN}/{linha.SIGLA_UF}: {len(dados['lon'])} nos, "
              f"{len(dados['origem'])} arestas, {time.time() - inicio:.0f}s", flush=True)
    if falhas:
        sys.exit(f"Falharam: {' '.join(falhas)} (rode de novo para tentar so esses)")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2], sys.argv[3:] or CAPITAIS)

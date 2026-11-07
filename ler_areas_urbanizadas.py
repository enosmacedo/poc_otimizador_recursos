"""Le o shapefile de Areas Urbanizadas 2022 (IBGE) desta pasta e cruza com
a Malha Municipal 2022 (IBGE) para obter a area urbanizada por municipio.

Requisitos:
    pip install -r requirements.txt
"""
from pathlib import Path

import geopandas as gpd
import pandas as pd

PASTA = Path(__file__).resolve().parent
ARQUIVO = PASTA / "AU_2026_AreasUrbanizadas_2022_Brasil.shp"
MALHA_MUNICIPAL = PASTA / "malha_municipal" / "BR_Municipios_2022.shp"

# Albers de area igual para o Brasil (parametros do IBGE), usada no calculo de areas
CRS_AREA = (
    "+proj=aea +lat_0=-12 +lon_0=-54 +lat_1=-2 +lat_2=-22 "
    "+ellps=GRS80 +towgs84=0,0,0 +units=m +no_defs"
)


def carregar(colunas=None, bbox=None, linhas=None, sem_geometria=False):
    """Carrega o shapefile.

    colunas: lista de colunas do .dbf a ler (None = todas)
    bbox: (xmin, ymin, xmax, ymax) em graus, para ler so uma regiao
    linhas: le apenas as N primeiras feicoes (util para testes)
    sem_geometria: True le so a tabela de atributos (bem mais rapido)
    """
    return gpd.read_file(
        ARQUIVO,
        engine="pyogrio",
        encoding="utf-8",
        columns=colunas,
        bbox=bbox,
        max_features=linhas,
        ignore_geometry=sem_geometria,
    )


def carregar_municipios(bbox=None):
    """Carrega a Malha Municipal 2022 (CD_MUN, NM_MUN, SIGLA_UF)."""
    return gpd.read_file(
        MALHA_MUNICIPAL,
        engine="pyogrio",
        encoding="utf-8",
        columns=["CD_MUN", "NM_MUN", "SIGLA_UF"],
        bbox=bbox,
    )


def recortar_por_municipio(bbox=None):
    """Divide cada area urbanizada na divisa municipal e atribui o municipio.

    Retorna um GeoDataFrame (no CRS de area igual) com os atributos originais,
    CD_MUN, NM_MUN, SIGLA_UF e area_km2_mun (area do pedaco dentro do municipio).
    """
    au = carregar(bbox=bbox).to_crs(CRS_AREA)
    mun = carregar_municipios(bbox=bbox).to_crs(CRS_AREA)
    au["geometry"] = au.make_valid()
    mun["geometry"] = mun.make_valid()

    # Descobre quais municipios cada area toca; so as que tocam mais de um
    # precisam de recorte (bem mais rapido que um overlay no Brasil todo)
    pares = gpd.sjoin(au, mun, how="inner", predicate="intersects")
    n_mun = pares.groupby(level=0)["CD_MUN"].transform("size")

    inteiras = pares[n_mun == 1].drop(columns="index_right")

    divididas = pares[n_mun > 1]
    geom_mun = gpd.GeoSeries(
        mun.geometry.loc[divididas["index_right"]].values, index=divididas.index
    )
    divididas = divididas.drop(columns="index_right")
    divididas["geometry"] = divididas.geometry.intersection(geom_mun, align=False)
    # Descarta toques so na borda (linhas/pontos, sem area)
    divididas = divididas[divididas.geometry.area > 0]

    resultado = pd.concat([inteiras, divididas])
    resultado = gpd.GeoDataFrame(resultado, geometry="geometry", crs=CRS_AREA)
    resultado["area_km2_mun"] = resultado.geometry.area / 1e6
    return resultado.reset_index(names="id_area")


def tabela_por_municipio(recorte):
    """Soma a area (km2) por municipio, total e por Tipo e Densidade."""
    chaves = ["CD_MUN", "NM_MUN", "SIGLA_UF"]
    total = recorte.groupby(chaves)["area_km2_mun"].sum().rename("area_total_km2")
    por_tipo = recorte.pivot_table(
        index=chaves, columns="Tipo", values="area_km2_mun", aggfunc="sum", fill_value=0
    ).add_prefix("Tipo: ")
    por_densidade = recorte.pivot_table(
        index=chaves, columns="Densidade", values="area_km2_mun", aggfunc="sum", fill_value=0
    ).add_prefix("Densidade: ")
    tabela = pd.concat([total, por_tipo, por_densidade], axis=1).fillna(0)
    return tabela.sort_values("area_total_km2", ascending=False).reset_index()


def poligonos_do_municipio(cd_mun=None, nome=None, uf=None, unir=False):
    """Le do GeoPackage gerado os poligonos de um municipio.

    Busca por codigo (cd_mun) ou por nome + uf. Com unir=True, junta os
    poligonos em um so por Tipo e Densidade.
    """
    if cd_mun is not None:
        filtro = f"CD_MUN = '{cd_mun}'"
    else:
        filtro = f"NM_MUN = '{nome}'" + (f" AND SIGLA_UF = '{uf}'" if uf else "")
    gdf = gpd.read_file(SAIDA_GPKG, engine="pyogrio", where=filtro)
    if unir:
        gdf = gdf.dissolve(by=["CD_MUN", "NM_MUN", "SIGLA_UF", "Tipo", "Densidade"],
                           aggfunc={"area_km2_mun": "sum"}).reset_index()
    return gdf


def pontos(gdf, id_col):
    """Lista os vertices (lon, lat) de cada poligono, em ordem.

    Uma linha por vertice: id_col, parte (para MultiPolygon), anel (0 = borda
    externa, 1+ = buracos), ordem, lon, lat. O ultimo ponto de cada anel
    repete o primeiro (o anel e fechado).
    """
    linhas = []
    for id_, geom in zip(gdf[id_col], gdf.geometry):
        partes = getattr(geom, "geoms", [geom])
        for p, poligono in enumerate(partes):
            aneis = [poligono.exterior, *poligono.interiors]
            for a, anel in enumerate(aneis):
                for o, (x, y) in enumerate(anel.coords):
                    linhas.append((id_, p, a, o, x, y))
    return pd.DataFrame(linhas, columns=[id_col, "parte", "anel", "ordem", "lon", "lat"])


MALHA_UF = PASTA / "malha_uf" / "BR_UF_2022.shp"


def poligono_estado(uf=None):
    """Limite estadual (Malha de UFs 2022 do IBGE). Sem uf, retorna todos."""
    filtro = f"SIGLA_UF = '{uf.upper()}'" if uf else None
    gdf = gpd.read_file(MALHA_UF, engine="pyogrio", encoding="utf-8", where=filtro)
    # O IBGE grava NM_REGIAO com uma quebra de linha no fim em alguns estados
    gdf["NM_REGIAO"] = gdf["NM_REGIAO"].str.strip()
    return gdf


MALHA_BAIRROS = PASTA / "malha_bairros" / "BR_bairros_CD2022.gpkg"
POPULACAO_BAIRROS = PASTA / "populacao_bairros_censo2022.csv"


def poligonos_bairros(cd_mun=None, nome=None, uf=None):
    """Bairros do Censo 2022 de um municipio, com a populacao (tabela 9923).

    Busca por codigo (cd_mun, um ou uma lista) ou por nome + uf. So 895
    municipios tem bairros no IBGE; para os demais retorna vazio. Bairros em
    varios pedacos viram um MultiPolygon; populacao_2022 vazia = bairro
    ausente na tabela do SIDRA.
    """
    if isinstance(cd_mun, (list, tuple, set)):
        filtro = "CD_MUN IN (" + ",".join(f"'{c}'" for c in cd_mun) + ")"
    elif cd_mun is not None:
        filtro = f"CD_MUN = '{cd_mun}'"
    else:
        filtro = f"NM_MUN = '{nome}'"
        if uf:  # a malha de bairros tem CD_UF, nao a sigla
            filtro += f" AND CD_UF = '{poligono_estado(uf)['CD_UF'].iloc[0]}'"
    gdf = gpd.read_file(MALHA_BAIRROS, engine="pyogrio", where=filtro,
                        columns=["CD_MUN", "NM_MUN", "CD_UF", "CD_BAIRRO", "NM_BAIRRO"])
    gdf = gdf.dissolve(by=["CD_BAIRRO", "NM_BAIRRO", "CD_MUN", "NM_MUN", "CD_UF"]).reset_index()
    pop = pd.read_csv(POPULACAO_BAIRROS, sep=";", dtype={"CD_BAIRRO": str},
                      usecols=["CD_BAIRRO", "populacao_2022"])
    gdf = gdf.merge(pop, on="CD_BAIRRO", how="left")
    gdf["area_km2"] = gdf.to_crs(CRS_AREA).area / 1e6
    return gdf


PASTA_SETORES = PASTA / "malha_setores"  # <UF>_setores_CD2022.gpkg (IBGE)
AGREGADOS_SETORES = PASTA / "agregados_setores" / "Agregados_por_setores_basico_BR.csv"


def setores_censitarios(cd_mun):
    """Setores censitarios do Censo 2022 de um ou mais municipios, com a
    populacao (v0001 dos Agregados por Setores). Requer o gpkg da UF em
    malha_setores/.
    """
    codigos = [cd_mun] if isinstance(cd_mun, str) else list(cd_mun)
    ufs = poligono_estado().set_index("CD_UF")["SIGLA_UF"]
    filtro = "CD_MUN IN (" + ",".join(f"'{c}'" for c in codigos) + ")"
    partes = []
    for cd_uf in sorted({c[:2] for c in codigos}):
        partes.append(gpd.read_file(
            PASTA_SETORES / f"{ufs[cd_uf]}_setores_CD2022.gpkg", engine="pyogrio", where=filtro,
            columns=["CD_SETOR", "SITUACAO", "CD_MUN", "NM_MUN", "NM_DIST", "NM_SUBDIST",
                     "CD_BAIRRO", "NM_BAIRRO"]))
    gdf = pd.concat(partes, ignore_index=True)

    pop = pd.read_csv(AGREGADOS_SETORES, sep=";", encoding="latin-1", dtype=str,
                      usecols=["CD_SETOR", "CD_MUN", "v0001"])
    pop = pop[pop["CD_MUN"].isin(codigos)]
    # Setores sem moradores ou com dado sigiloso vem como "." / "X"
    pop["populacao_2022"] = pd.to_numeric(pop["v0001"], errors="coerce")
    gdf = gdf.merge(pop[["CD_SETOR", "populacao_2022"]], on="CD_SETOR", how="left")
    gdf["area_km2"] = gdf.to_crs(CRS_AREA).area / 1e6
    return gdf


SAIDA_GPKG = PASTA / "areas_urbanizadas_com_municipio.gpkg"


if __name__ == "__main__":
    # Para testar numa regiao so (ex.: Joao Pessoa), passe bbox=(-35.0, -7.3, -34.75, -7.0)
    recorte = recortar_por_municipio()
    print(len(recorte), "pedacos de area urbanizada em",
          recorte["CD_MUN"].nunique(), "municipios")

    tabela = tabela_por_municipio(recorte)
    tabela.to_csv(PASTA / "area_urbanizada_por_municipio.csv",
                  index=False, sep=";", decimal=",", encoding="utf-8-sig")

    # Poligonos ja com o municipio, para abrir no QGIS
    # ("fid" e nome reservado no GeoPackage)
    recorte.rename(columns={"fid": "fid_orig"}).to_crs("EPSG:4674").to_file(
        SAIDA_GPKG, engine="pyogrio"
    )
    print(tabela.head(10).to_string())

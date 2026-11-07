"""Gera os arquivos de municipios usados pelo Citelemap a partir da
Malha Municipal 2022 do IBGE.

Uso:
    python preparar_dados.py <BR_Municipios_2022.shp> <pasta_saida>

Saida:
    <pasta_saida>/municipios.json        lista {cd_mun, nome, uf}
    <pasta_saida>/poligonos/<UF>.json    {cd_mun: {nome, uf, area_km2, partes,
                                                   bbox, coordenadas}}
As coordenadas sao o contorno externo da maior parte do municipio,
simplificado, em [lon, lat] (SIRGAS 2000, graus, 6 casas decimais).
"""
import json
import sys
from pathlib import Path

import geopandas as gpd

# Albers de area igual para o Brasil (parametros do IBGE)
CRS_AREA = (
    "+proj=aea +lat_0=-12 +lon_0=-54 +lat_1=-2 +lat_2=-22 "
    "+ellps=GRS80 +towgs84=0,0,0 +units=m +no_defs"
)
TOLERANCIA_GRAUS = 0.0003  # ~33 m; reduz o numero de vertices sem mudar a forma
CASAS_DECIMAIS = 6  # ~0,1 m
# Espelhos d'agua (Lagoa Mirim e Lagoa dos Patos, RS): nao sao municipios
NAO_MUNICIPIOS = {"4300001", "4300002"}


def poligonos(geom):
    """Lista os Polygon contidos em qualquer geometria."""
    if geom.geom_type == "Polygon":
        return [geom]
    if hasattr(geom, "geoms"):
        return [p for g in geom.geoms for p in poligonos(g)]
    return []


def main(shp, saida):
    saida = Path(saida)
    (saida / "poligonos").mkdir(parents=True, exist_ok=True)

    mun = gpd.read_file(shp, engine="pyogrio", encoding="utf-8",
                        columns=["CD_MUN", "NM_MUN", "SIGLA_UF"])
    mun = mun[~mun["CD_MUN"].isin(NAO_MUNICIPIOS)].copy()
    mun["geometry"] = mun.make_valid()
    mun["area_km2"] = mun.to_crs(CRS_AREA).area / 1e6

    indice = []
    for uf, grupo in mun.groupby("SIGLA_UF"):
        dados = {}
        for linha in grupo.itertuples():
            partes = poligonos(linha.geometry)
            maior = max(partes, key=lambda p: p.area)
            simples = maior.simplify(TOLERANCIA_GRAUS, preserve_topology=True)
            if simples.geom_type != "Polygon" or simples.is_empty:
                simples = maior
            coords = [[round(x, CASAS_DECIMAIS), round(y, CASAS_DECIMAIS)]
                      for x, y in simples.exterior.coords]
            dados[linha.CD_MUN] = {
                "nome": linha.NM_MUN,
                "uf": uf,
                "area_km2": round(linha.area_km2, 3),
                "partes": len(partes),
                "bbox": [round(v, CASAS_DECIMAIS) for v in linha.geometry.bounds],
                "coordenadas": coords,
            }
            indice.append({"cd_mun": linha.CD_MUN, "nome": linha.NM_MUN, "uf": uf})
        with open(saida / "poligonos" / f"{uf}.json", "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, separators=(",", ":"))

    with open(saida / "municipios.json", "w", encoding="utf-8") as f:
        json.dump(indice, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{len(indice)} municipios gravados em {saida}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])

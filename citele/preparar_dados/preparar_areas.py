"""Gera as areas com populacao (bairros) das capitais, usadas pela
estrategia "linear - densidade por bairros".

Uso:
    python preparar_areas.py <bairros_capitais.gpkg> <setores_capitais.gpkg> <pasta_saida>

Entrada: as planilhas geradas por bairros_capitais.py (Censo 2022).
Capitais sem bairros no IBGE usam a divisao mais proxima de bairro:
subdistritos ou distritos (se houver ao menos 20), senao setores censitarios.

Saida: <pasta_saida>/areas/<CD_MUN>.json
    {cd_mun, nome, uf, unidade, areas: [{id, nome, populacao, geometria}]}
geometria e GeoJSON (Polygon/MultiPolygon) em [lon, lat], SIRGAS 2000.
"""
import json
import sys
from pathlib import Path

import geopandas as gpd
import shapely

TOLERANCIA_GRAUS = 0.0001  # ~11 m
CASAS_DECIMAIS = 6
MIN_UNIDADES = 20


def agrupar_setores(setores):
    """Escolhe subdistrito, distrito ou setor e dissolve os setores nele."""
    for codigo, nome, unidade in (("CD_SUBDIST", "NM_SUBDIST", "subdistrito"),
                                  ("CD_DIST", "NM_DIST", "distrito")):
        if setores[nome].notna().all() and setores[codigo].nunique() >= MIN_UNIDADES:
            if unidade == "subdistrito" and (setores["NM_SUBDIST"] == setores["NM_DIST"]).all():
                unidade = "distrito"  # municipio sem subdistritos de fato
            g = setores.dissolve(by=[codigo, nome], aggfunc={"populacao_2022": "sum"})
            g = g.reset_index().rename(columns={codigo: "id", nome: "nome"})
            return g, unidade
    g = setores.rename(columns={"CD_SETOR": "id"})
    g["nome"] = "Setor " + g["id"]
    return g, "setor censitario"


def main(bairros_gpkg, setores_gpkg, saida):
    pasta = Path(saida) / "areas"
    pasta.mkdir(parents=True, exist_ok=True)
    bairros = gpd.read_file(bairros_gpkg, engine="pyogrio")
    setores = gpd.read_file(setores_gpkg, engine="pyogrio")
    # A malha de setores nao traz CD_SUBDIST/CD_DIST; os nomes servem de chave.
    # Setor sem subdistrito fica no subdistrito com o nome do seu distrito.
    setores["NM_SUBDIST"] = setores["NM_SUBDIST"].fillna(setores["NM_DIST"])
    setores["CD_SUBDIST"] = setores["NM_SUBDIST"]
    setores["CD_DIST"] = setores["NM_DIST"]

    grupos = []
    for cd_mun, g in bairros.groupby("CD_MUN"):
        grupos.append((g.iloc[0], g.rename(columns={"CD_BAIRRO": "id", "NM_BAIRRO": "nome"}), "bairro"))
    for cd_mun, g in setores.groupby("CD_MUN"):
        grupos.append((g.iloc[0], *agrupar_setores(g)))

    for municipio, g, unidade in grupos:
        g = g[g["populacao_2022"].fillna(0) > 0]
        areas = []
        for linha in g.itertuples():
            geom = shapely.make_valid(linha.geometry.simplify(TOLERANCIA_GRAUS, preserve_topology=True))
            geom = shapely.set_precision(geom, 10 ** -CASAS_DECIMAIS)
            if geom.is_empty or geom.area == 0:
                geom = linha.geometry
            areas.append({
                "id": str(linha.id),
                "nome": linha.nome,
                "populacao": int(linha.populacao_2022),
                "geometria": shapely.geometry.mapping(
                    shapely.MultiPolygon([p for p in getattr(geom, "geoms", [geom])
                                          if p.geom_type == "Polygon"])),
            })
        cd_mun = municipio["CD_MUN"]
        dados = {"cd_mun": cd_mun, "nome": municipio["NM_MUN"], "uf": municipio["SIGLA_UF"],
                 "unidade": unidade, "areas": areas}
        with open(pasta / f"{cd_mun}.json", "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, separators=(",", ":"))
        print(f"{cd_mun} {dados['nome']}/{dados['uf']}: {len(areas)} areas ({unidade}), "
              f"{sum(a['populacao'] for a in areas)} habitantes")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])

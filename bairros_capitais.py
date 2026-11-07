"""Exporta os bairros (poligono + populacao, Censo 2022) das 27 capitais.

As capitais sem bairros no IBGE (Rio Branco, Brasilia, Goiania, Sao Luis,
Sao Paulo e Palmas) recebem os setores censitarios no lugar.

Saidas na pasta do projeto:
    bairros_capitais.gpkg           um poligono por bairro, com populacao e area
    bairros_capitais_pontos.csv     vertices (lon, lat) de cada bairro
    setores_capitais.gpkg           setores censitarios das capitais sem bairros
    setores_capitais_pontos.csv     vertices (lon, lat) de cada setor
    bairros_capitais_resumo.csv     por capital: unidade usada, quantidade,
                                    populacao e area
"""
import geopandas as gpd
import pandas as pd

import ler_areas_urbanizadas as l

CAPITAIS = {
    "1100205": "RO", "1200401": "AC", "1302603": "AM", "1400100": "RR",
    "1501402": "PA", "1600303": "AP", "1721000": "TO", "2111300": "MA",
    "2211001": "PI", "2304400": "CE", "2408102": "RN", "2507507": "PB",
    "2611606": "PE", "2704302": "AL", "2800308": "SE", "2927408": "BA",
    "3106200": "MG", "3205309": "ES", "3304557": "RJ", "3550308": "SP",
    "4106902": "PR", "4205407": "SC", "4314902": "RS", "5002704": "MS",
    "5103403": "MT", "5208707": "GO", "5300108": "DF",
}

if __name__ == "__main__":
    municipios = gpd.read_file(l.MALHA_MUNICIPAL, engine="pyogrio", ignore_geometry=True,
                               columns=["CD_MUN", "NM_MUN", "SIGLA_UF"])
    capitais = municipios[municipios["CD_MUN"].isin(CAPITAIS)].copy()
    # Confere se cada codigo e mesmo da UF esperada
    assert len(capitais) == 27 and all(capitais["SIGLA_UF"] == capitais["CD_MUN"].map(CAPITAIS))

    bairros = l.poligonos_bairros(cd_mun=list(CAPITAIS))
    bairros = bairros.merge(capitais[["CD_MUN", "SIGLA_UF"]], on="CD_MUN")
    bairros.to_file(l.PASTA / "bairros_capitais.gpkg", engine="pyogrio")

    pontos = l.pontos(bairros, "CD_BAIRRO").merge(
        bairros[["CD_BAIRRO", "NM_BAIRRO", "CD_MUN", "NM_MUN", "SIGLA_UF", "populacao_2022"]],
        on="CD_BAIRRO")
    pontos.to_csv(l.PASTA / "bairros_capitais_pontos.csv", index=False, sep=";",
                  decimal=",", encoding="utf-8-sig")

    sem_bairros = sorted(set(CAPITAIS) - set(bairros["CD_MUN"]))
    setores = l.setores_censitarios(sem_bairros)
    setores = setores.merge(capitais[["CD_MUN", "SIGLA_UF"]], on="CD_MUN")
    setores.to_file(l.PASTA / "setores_capitais.gpkg", engine="pyogrio")
    pontos_setores = l.pontos(setores, "CD_SETOR").merge(
        setores[["CD_SETOR", "CD_MUN", "NM_MUN", "SIGLA_UF", "populacao_2022"]], on="CD_SETOR")
    pontos_setores.to_csv(l.PASTA / "setores_capitais_pontos.csv", index=False, sep=";",
                          decimal=",", encoding="utf-8-sig")

    def resumir(gdf, codigo, unidade):
        r = gdf.groupby("CD_MUN").agg(
            quantidade=(codigo, "size"),
            populacao=("populacao_2022", "sum"),
            sem_populacao=("populacao_2022", lambda s: s.isna().sum()),
            area_km2=("area_km2", "sum"),
        )
        r.insert(0, "unidade", unidade)
        return r

    resumo = pd.concat([resumir(bairros, "CD_BAIRRO", "bairro"),
                        resumir(setores, "CD_SETOR", "setor censitario")])
    resumo = capitais.set_index("CD_MUN").join(resumo)
    resumo = resumo.astype({"quantidade": int, "populacao": int, "sem_populacao": int})
    resumo = resumo.reset_index().sort_values("SIGLA_UF")
    resumo.to_csv(l.PASTA / "bairros_capitais_resumo.csv", index=False, sep=";",
                  decimal=",", encoding="utf-8-sig")

    print(resumo.round(1).to_string(index=False))
    print(f"\n{len(bairros)} bairros ({len(pontos)} vertices), "
          f"{len(setores)} setores ({len(pontos_setores)} vertices)")

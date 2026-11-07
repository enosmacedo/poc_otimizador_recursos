"""Citeleat: API de calculos de alocacao de recursos."""
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from .estrategias import ESTRATEGIAS as ESTRATEGIAS_GEOMETRICAS
from .estrategias import ESTRATEGIAS_3D, ErroPoligono
from .rotas import linear_tempo_deslocamento, rotas_realocacao

MAX_RECURSOS = 200

ESTRATEGIAS = {
    **ESTRATEGIAS_GEOMETRICAS,
    "linear-tempo-deslocamento": {"nome": "linear - tempo de deslocamento",
                                  "funcao": linear_tempo_deslocamento,
                                  "precisa_areas": False, "precisa_municipio": True},
}
for _e in ESTRATEGIAS.values():
    _e.setdefault("precisa_municipio", False)

app = FastAPI(title="Citeleat", version="0.1.0")


class Area(BaseModel):
    id: str
    nome: str | None = None
    populacao: float = Field(ge=0)
    geometria: dict = Field(description="Polygon/MultiPolygon GeoJSON em [lon, lat]")


class Calc2dPoligono(BaseModel):
    recursos: int = Field(ge=1, le=MAX_RECURSOS)
    estrategia: str
    coordenadas: list[tuple[float, float]] = Field(
        min_length=3, description="Vertices do poligono como [lon, lat]")
    areas: list[Area] | None = Field(
        None, description="Areas (bairros) com populacao; exigidas por "
                          "'linear-densidade-bairros'")
    municipio: str | None = Field(
        None, description="Codigo IBGE do municipio (malha viaria); exigido por "
                          "'linear-tempo-deslocamento'")


class Ponto(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class Rotas2d(BaseModel):
    origens: list[Ponto] = Field(max_length=MAX_RECURSOS, description="Posicoes atuais")
    destinos: list[Ponto] = Field(max_length=MAX_RECURSOS, description="Novas posicoes")
    municipio: str | None = Field(None, description="Codigo IBGE (malha viaria)")
    associar: bool = Field(True, description="Escolher qual origem vai para qual destino "
                                             "pelo criterio; senao, i -> i")
    criterio: Literal["soma", "maximo"] = Field(
        "soma", description="soma: menor tempo total; maximo: menor tempo do ultimo a chegar")


def _calcular(recursos, estrategia, coordenadas, areas=None, municipio=None):
    if estrategia not in ESTRATEGIAS:
        raise HTTPException(422, f"Estrategia desconhecida: '{estrategia}'. "
                                 f"Opcoes: {', '.join(ESTRATEGIAS)}")
    definicao = ESTRATEGIAS[estrategia]
    if definicao["precisa_areas"] and not areas:
        raise HTTPException(422, f"A estrategia '{estrategia}' precisa das areas com "
                                 "populacao: use POST /calc2dpoligono com o campo 'areas'.")
    if definicao["precisa_municipio"] and not municipio:
        raise HTTPException(422, f"A estrategia '{estrategia}' precisa do parametro "
                                 "'municipio' (codigo IBGE).")
    try:
        resultado = definicao["funcao"](coordenadas, recursos, areas=areas, municipio=municipio)
    except ErroPoligono as e:
        raise HTTPException(422, str(e))
    return {"estrategia": estrategia, "recursos": recursos,
            "vertices_recebidos": len(coordenadas), **resultado}


def _ler_coordenadas(texto):
    """'lon,lat;lon,lat;...' -> [(lon, lat), ...]"""
    try:
        coords = [tuple(float(v) for v in par.split(","))
                  for par in texto.strip().strip(";").split(";")]
    except ValueError:
        raise HTTPException(422, "Coordenadas invalidas. Use 'lon,lat;lon,lat;...'.")
    if any(len(c) != 2 for c in coords):
        raise HTTPException(422, "Cada vertice deve ter exatamente 'lon,lat'.")
    return coords


@app.get("/saude")
def saude():
    return {"status": "ok"}


@app.get("/estrategias")
def estrategias():
    return [{"id": k, "nome": v["nome"], "precisa_areas": v["precisa_areas"],
             "precisa_municipio": v["precisa_municipio"]} for k, v in ESTRATEGIAS.items()]


@app.get("/calc2dpoligono")
def calc2dpoligono_get(
    recursos: Annotated[int, Query(ge=1, le=MAX_RECURSOS)],
    estrategia: str,
    coordenadas: Annotated[str, Query(description="Vertices 'lon,lat;lon,lat;...'")],
    municipio: Annotated[str | None, Query(description="Codigo IBGE (malha viaria)")] = None,
):
    return _calcular(recursos, estrategia, _ler_coordenadas(coordenadas), municipio=municipio)


@app.post("/calc2dpoligono")
def calc2dpoligono_post(corpo: Calc2dPoligono):
    """Mesmo calculo do GET, para poligonos grandes demais para a URL e para
    estrategias que precisam das areas com populacao."""
    areas = [a.model_dump() for a in corpo.areas] if corpo.areas else None
    return _calcular(corpo.recursos, corpo.estrategia, corpo.coordenadas, areas, corpo.municipio)


@app.post("/rotas2d")
def rotas2d(corpo: Rotas2d):
    """Rotas para levar recursos das posicoes atuais ate novas posicoes (pelas
    ruas, se houver malha viaria do municipio; senao em linha reta)."""
    try:
        return rotas_realocacao([p.model_dump() for p in corpo.origens],
                                [p.model_dump() for p in corpo.destinos],
                                corpo.municipio, corpo.associar, corpo.criterio)
    except ErroPoligono as e:
        raise HTTPException(422, str(e))


MAX_DRONES = 100


class Calc3dDrones(BaseModel):
    drones: int = Field(ge=1, le=MAX_DRONES, description="Quantidade de drones (cada drone e um recurso)")
    estrategia: str = "linear-area-drones"
    largura_m: float = Field(gt=0, le=10000, description="Largura da area (eixo x), em metros")
    comprimento_m: float = Field(gt=0, le=10000, description="Comprimento da area (eixo y), em metros")
    altitude_m: float = Field(gt=0, le=500, description="Altitude de voo dos drones, em metros")


@app.get("/estrategias3d")
def estrategias3d():
    return [{"id": k, "nome": v["nome"]} for k, v in ESTRATEGIAS_3D.items()]


@app.post("/calc3ddrones")
def calc3ddrones(corpo: Calc3dDrones):
    """Posicoes 3D (x, y, z em metros) de um enxame de drones sobre uma area
    retangular centrada na origem."""
    if corpo.estrategia not in ESTRATEGIAS_3D:
        raise HTTPException(422, f"Estrategia desconhecida: '{corpo.estrategia}'. "
                                 f"Opcoes: {', '.join(ESTRATEGIAS_3D)}")
    try:
        resultado = ESTRATEGIAS_3D[corpo.estrategia]["funcao"](
            corpo.largura_m, corpo.comprimento_m, corpo.drones, corpo.altitude_m)
    except ErroPoligono as e:
        raise HTTPException(422, str(e))
    return {"estrategia": corpo.estrategia, "drones": corpo.drones, **resultado}

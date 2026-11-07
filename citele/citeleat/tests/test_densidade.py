import json
from pathlib import Path

import numpy as np
import shapely
from fastapi.testclient import TestClient

from app.estrategias import populacao_nos_circulos
from app.main import app

cliente = TestClient(app)
DADOS = Path(__file__).resolve().parents[2] / "dados"
ESTRATEGIA = "linear-densidade-bairros"


def _quadrado(lon, lat, lado):
    return {"type": "Polygon", "coordinates": [[
        [lon, lat], [lon + lado, lat], [lon + lado, lat + lado], [lon, lat + lado], [lon, lat]]]}


# Um bairro pequeno e denso ao lado de um grande e pouco populoso
AREAS = [
    {"id": "denso", "nome": "Denso", "populacao": 90000, "geometria": _quadrado(-35.20, -5.80, 0.02)},
    {"id": "esparso", "nome": "Esparso", "populacao": 30000, "geometria": _quadrado(-35.18, -5.80, 0.06)},
]
CONTORNO = [[-35.20, -5.80], [-35.12, -5.80], [-35.12, -5.74], [-35.20, -5.74], [-35.20, -5.80]]


def _post(recursos, areas=AREAS, contorno=CONTORNO):
    return cliente.post("/calc2dpoligono", json={
        "recursos": recursos, "estrategia": ESTRATEGIA, "coordenadas": contorno, "areas": areas})


def test_regra_metade_do_bairro_metade_da_populacao():
    # Faixa fina de 2000 m: um circulo de raio 1000 m centrado na ponta
    # cobre (quase exatamente) metade da faixa
    faixa = shapely.box(0, 0, 2000, 1)
    pop = populacao_nos_circulos(np.array([[0.0, 0.5]]), 1000.0,
                                 np.array([faixa], dtype=object), np.array([1000.0]))
    assert abs(pop[0] - 500) < 2


def test_circulo_cobrindo_o_bairro_inteiro_recebe_toda_a_populacao():
    bairro = shapely.box(0, 0, 100, 100)
    pop = populacao_nos_circulos(np.array([[50.0, 50.0]]), 1000.0,
                                 np.array([bairro], dtype=object), np.array([777.0]))
    assert abs(pop[0] - 777) < 1e-6


def test_populacao_equilibrada_entre_recursos():
    r = _post(4)
    assert r.status_code == 200, r.text
    corpo = r.json()
    p = corpo["populacao"]
    assert p["total"] == 120000 and p["alvo_por_recurso"] == 30000
    assert len(corpo["pontos"]) == 4
    assert all("populacao" in ponto for ponto in corpo["pontos"])
    assert p["coeficiente_variacao"] < 0.15
    # O bairro denso (1/4 da area, 3/4 da populacao) deve concentrar recursos
    no_denso = sum(-35.20 <= pt["lng"] <= -35.18 for pt in corpo["pontos"])
    assert no_denso >= 2


def test_natal_bairros_reais():
    areas = json.loads((DADOS / "areas" / "2408102.json").read_text(encoding="utf-8"))["areas"]
    contorno = json.loads((DADOS / "poligonos" / "RN.json").read_text(encoding="utf-8"))["2408102"]["coordenadas"]
    corpo = _post(10, areas, contorno).json()
    assert corpo["populacao"]["total"] == 751300
    assert corpo["populacao"]["coeficiente_variacao"] < 0.10
    assert corpo["populacao"]["areas"] == 36


def test_exige_areas_e_post():
    assert _post(3, areas=None).status_code == 422
    r = cliente.get("/calc2dpoligono", params={
        "recursos": 3, "estrategia": ESTRATEGIA,
        "coordenadas": ";".join(f"{lon},{lat}" for lon, lat in CONTORNO)})
    assert r.status_code == 422
    assert "areas" in r.json()["detail"]


def test_area_invalida():
    ruim = [{"id": "x", "populacao": 10, "geometria": {"type": "Polygon", "coordinates": [[[0, 0]]]}}]
    assert _post(2, areas=ruim).status_code == 422

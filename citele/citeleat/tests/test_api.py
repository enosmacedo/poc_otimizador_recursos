import json
import math
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

cliente = TestClient(app)

# Quadrado de ~11 km x 11 km perto de Natal
QUADRADO = [[-35.25, -5.85], [-35.15, -5.85], [-35.15, -5.75], [-35.25, -5.75], [-35.25, -5.85]]
DADOS = Path(__file__).resolve().parents[2] / "dados" / "poligonos" / "RN.json"


def _texto(coords):
    return ";".join(f"{lon},{lat}" for lon, lat in coords)


def _get(recursos, coords, estrategia="linear-area-cidade"):
    return cliente.get("/calc2dpoligono", params={
        "recursos": recursos, "estrategia": estrategia, "coordenadas": _texto(coords)})


def test_um_recurso_fica_no_centro_e_cobre_tudo():
    r = _get(1, QUADRADO)
    assert r.status_code == 200
    corpo = r.json()
    assert len(corpo["pontos"]) == 1
    p = corpo["pontos"][0]
    assert abs(p["lng"] + 35.20) < 0.002 and abs(p["lat"] + 5.80) < 0.002
    # Raio minimo = meia diagonal do quadrado (~7,8 km)
    meia_diagonal = math.hypot(11070, 11060) / 2
    assert meia_diagonal * 0.98 < corpo["raio_m"] < meia_diagonal * 1.03
    assert corpo["cobertura"] == 1.0


def test_mais_recursos_raio_menor():
    raios = [_get(k, QUADRADO).json()["raio_m"] for k in (1, 4, 16)]
    assert raios[0] > raios[1] > raios[2]
    # 4 recursos num quadrado: cada um cobre um quadrante (raio ~ metade)
    assert raios[1] < raios[0] * 0.56


def test_resposta_tem_um_ponto_por_recurso_dentro_do_bbox():
    corpo = _get(7, QUADRADO).json()
    assert len(corpo["pontos"]) == 7
    for p in corpo["pontos"]:
        assert -35.25 <= p["lng"] <= -35.15 and -5.85 <= p["lat"] <= -5.75


def test_post_igual_ao_get():
    g = _get(5, QUADRADO).json()
    p = cliente.post("/calc2dpoligono", json={
        "recursos": 5, "estrategia": "linear-area-cidade", "coordenadas": QUADRADO}).json()
    assert g == p


def test_natal():
    coords = json.loads(DADOS.read_text(encoding="utf-8"))["2408102"]["coordenadas"]
    corpo = _get(10, coords).json()
    assert len(corpo["pontos"]) == 10
    assert corpo["cobertura"] >= 0.999
    assert abs(corpo["area_poligono_km2"] - 167.4) < 2


def test_erros():
    assert _get(3, QUADRADO, estrategia="nao-existe").status_code == 422
    assert _get(0, QUADRADO).status_code == 422
    assert _get(3, QUADRADO[:2]).status_code == 422
    r = cliente.get("/calc2dpoligono", params={
        "recursos": 2, "estrategia": "linear-area-cidade", "coordenadas": "abc"})
    assert r.status_code == 422

import math

from fastapi.testclient import TestClient

from app.main import app

cliente = TestClient(app)


def _calc(drones, largura=200, comprimento=100, altitude=30, **extra):
    return cliente.post("/calc3ddrones", json={"drones": drones, "largura_m": largura,
                                               "comprimento_m": comprimento, "altitude_m": altitude, **extra})


def test_um_drone_no_centro_cobre_tudo():
    corpo = _calc(1).json()
    p = corpo["posicoes"][0]
    assert abs(p["x"]) < 2 and abs(p["y"]) < 2 and p["z"] == 30
    meia_diagonal = math.hypot(200, 100) / 2
    assert meia_diagonal * 0.98 < corpo["raio_cobertura_m"] < meia_diagonal * 1.05
    assert corpo["cobertura"] == 1.0


def test_posicoes_dentro_da_area_e_na_altitude():
    corpo = _calc(12, altitude=45).json()
    assert len(corpo["posicoes"]) == 12
    for p in corpo["posicoes"]:
        assert -100 <= p["x"] <= 100 and -50 <= p["y"] <= 50 and p["z"] == 45
    assert corpo["cobertura"] >= 0.999
    assert corpo["area_m2"] == 20000


def test_mais_drones_raio_menor_e_abertura_coerente():
    r4, r16 = _calc(4).json(), _calc(16).json()
    assert r16["raio_cobertura_m"] < r4["raio_cobertura_m"]
    # Abertura = 2 * atan(raio / altitude)
    esperado = math.degrees(2 * math.atan(r4["raio_cobertura_m"] / 30))
    assert abs(r4["abertura_sensor_graus"] - esperado) < 0.2


def test_validacoes():
    assert _calc(0).status_code == 422
    assert _calc(3, altitude=0).status_code == 422
    assert _calc(3, largura=-5).status_code == 422
    assert _calc(3, estrategia="outra").status_code == 422
    estr = cliente.get("/estrategias3d").json()
    assert estr == [{"id": "linear-area-drones", "nome": "linear - cobertura de área"}]

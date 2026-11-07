"""API do citeledrone com o Citeleat simulado (o ARGoS roda de verdade)."""
import shutil

import pytest
from fastapi.testclient import TestClient

from app import main

pytestmark = pytest.mark.skipif(shutil.which("argos3") is None, reason="ARGoS nao instalado")
cliente = TestClient(main.app)
chamadas = []


def _citeleat_falso(parametros, drones):
    """Posicoes em linha, espacadas na largura, na altitude pedida."""
    chamadas.append((parametros["estrategia"], drones))
    passo = parametros["largura_m"] / drones
    return {"drones": drones, "raio_cobertura_m": passo, "abertura_sensor_graus": 90.0,
            "area_m2": parametros["largura_m"] * parametros["comprimento_m"], "cobertura": 1.0,
            "posicoes": [{"x": -parametros["largura_m"] / 2 + passo * (i + 0.5), "y": 0.0,
                          "z": parametros["altitude_m"]} for i in range(drones)]}


@pytest.fixture(autouse=True)
def citeleat_falso(monkeypatch):
    chamadas.clear()
    monkeypatch.setattr(main, "_calcular", _citeleat_falso)


def _simular(n=4):
    r = cliente.post("/api/simular", json={"drones": n, "largura_m": 80, "comprimento_m": 40, "altitude_m": 20})
    assert r.status_code == 200, r.text
    return r.json()


def test_simular_cria_enxame_numerado():
    corpo = _simular(4)
    assert [d["numero"] for d in corpo["enxame"]["drones"]] == [1, 2, 3, 4]
    assert [d["numero"] for d in corpo["simulacao"]["drones"]] == [1, 2, 3, 4]
    assert len(corpo["simulacao"]["base"]) == 4


def test_remover_drone_reposiciona_os_demais_a_partir_do_ar():
    corpo = _simular(4)
    eid = corpo["enxame"]["id"]
    antes = {d["numero"]: d for d in corpo["enxame"]["drones"]}
    r = cliente.post(f"/api/enxames/{eid}/drones/2/remover", json={"estrategia": "linear-area-drones"})
    assert r.status_code == 200, r.text
    novo = r.json()
    assert novo["removido"] == 2
    assert chamadas[-1] == ("linear-area-drones", 3)
    assert [d["numero"] for d in novo["enxame"]["drones"]] == [1, 3, 4]
    for d in novo["simulacao"]["drones"]:
        a = antes[d["numero"]]
        assert d["inicio"] == {"x": round(a["x"], 3), "y": round(a["y"], 3), "z": round(a["z"], 3)}
        assert d["chegada_s"] is not None
    # O enxame guardado ja esta nas novas posicoes
    salvo = cliente.get(f"/api/enxames/{eid}").json()
    assert salvo["drones"] == novo["enxame"]["drones"]


def test_remover_erros():
    eid = _simular(2)["enxame"]["id"]
    assert cliente.post(f"/api/enxames/{eid}/drones/9/remover").status_code == 404
    assert cliente.post("/api/enxames/nao-existe/drones/1/remover").status_code == 404
    assert cliente.post(f"/api/enxames/{eid}/drones/1/remover").status_code == 200
    assert cliente.post(f"/api/enxames/{eid}/drones/2/remover").status_code == 400  # ultimo drone

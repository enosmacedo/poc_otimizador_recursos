import json
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.estrategias import linear_area_cidade
from app.main import app
from app.rotas import _p_mediana, tempo_medio_min

cliente = TestClient(app)
DADOS = Path(__file__).resolve().parents[2] / "dados"
NATAL = "2408102"
CONTORNO = json.loads((DADOS / "poligonos" / "RN.json").read_text(encoding="utf-8"))[NATAL]["coordenadas"]
ESTRATEGIA = "linear-tempo-deslocamento"


def _get(recursos, municipio=NATAL):
    params = {"recursos": recursos, "estrategia": ESTRATEGIA,
              "coordenadas": ";".join(f"{lon},{lat}" for lon, lat in CONTORNO)}
    if municipio:
        params["municipio"] = municipio
    return cliente.get("/calc2dpoligono", params=params)


def test_p_mediana_encontra_o_otimo_em_caso_pequeno():
    # 3 grupos de pontos; cada candidato atende bem um grupo
    custos = np.array([
        [0, 0, 9, 9, 9, 9],
        [9, 9, 0, 0, 9, 9],
        [9, 9, 9, 9, 0, 0],
        [5, 5, 5, 5, 5, 5],
    ], dtype=float)
    assert sorted(_p_mediana(custos, 3)) == [0, 1, 2]
    assert _p_mediana(custos, 1) == [3]


def test_natal_tempo_cai_com_mais_recursos():
    tempos = []
    for k in (1, 5, 10):
        r = _get(k)
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert len(corpo["pontos"]) == k
        assert all("tempo_medio_min" in p for p in corpo["pontos"])
        assert sum(p["area_atendida_pct"] for p in corpo["pontos"]) == pytest.approx(100, abs=0.5)
        tempos.append(corpo["tempo"]["medio_min"])
    assert tempos[0] > tempos[1] > tempos[2]
    assert 3 < tempos[0] < 30  # Natal inteira a partir de um ponto, sem transito


def test_melhor_que_a_estrategia_de_area():
    k = 8
    rota = _get(k).json()
    area = linear_area_cidade(CONTORNO, k)
    tempo_area = tempo_medio_min(CONTORNO, NATAL, area["pontos"])
    tempo_rota = tempo_medio_min(CONTORNO, NATAL, rota["pontos"])
    assert tempo_rota == pytest.approx(rota["tempo"]["medio_min"], abs=0.01)
    assert tempo_rota <= tempo_area


def test_exige_municipio_com_malha():
    assert _get(3, municipio=None).status_code == 422
    r = _get(3, municipio="9999999")
    assert r.status_code == 422
    assert "Malha viaria" in r.json()["detail"]

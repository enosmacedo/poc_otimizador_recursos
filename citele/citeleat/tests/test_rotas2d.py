import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.rotas import _associar

cliente = TestClient(app)
NATAL = "2408102"
# Pontos em Natal: Ponta Negra, Alecrim, Lagoa Nova
PONTA_NEGRA = {"lat": -5.876, "lng": -35.178}
ALECRIM = {"lat": -5.797, "lng": -35.214}
LAGOA_NOVA = {"lat": -5.828, "lng": -35.206}


def _rotas(origens, destinos, municipio=NATAL, associar=True):
    r = cliente.post("/rotas2d", json={"origens": origens, "destinos": destinos,
                                        "municipio": municipio, "associar": associar})
    assert r.status_code == 200, r.text
    return r.json()


def test_rota_pelas_ruas_comeca_e_termina_nos_pontos():
    corpo = _rotas([PONTA_NEGRA], [ALECRIM])
    assert corpo["malha_viaria"] is True
    m = corpo["movimentos"][0]
    assert m["caminho"][0] == [PONTA_NEGRA["lat"], PONTA_NEGRA["lng"]]
    assert m["caminho"][-1] == [ALECRIM["lat"], ALECRIM["lng"]]
    assert len(m["caminho"]) > 10  # segue as ruas, nao e linha reta
    # ~9,6 km em linha reta; pelas ruas e mais longo, mas nao absurdamente
    assert 9000 < m["distancia_m"] < 20000
    assert 5 * 60 < m["tempo_s"] < 40 * 60


def test_associacao_minimiza_o_tempo_total():
    # Os destinos estao na ordem "errada": o hungaro deve trocar os pares
    corpo = _rotas([PONTA_NEGRA, ALECRIM], [ALECRIM, PONTA_NEGRA])
    pares = {(m["origem"], m["destino"]) for m in corpo["movimentos"]}
    assert pares == {(0, 1), (1, 0)}
    assert all(m["tempo_s"] < 60 for m in corpo["movimentos"])  # ninguem se move


def test_sem_associacao_mantem_a_ordem():
    corpo = _rotas([PONTA_NEGRA, ALECRIM], [ALECRIM, PONTA_NEGRA], associar=False)
    assert {(m["origem"], m["destino"]) for m in corpo["movimentos"]} == {(0, 0), (1, 1)}
    assert corpo["tempo_maximo_s"] > 5 * 60


def test_sem_malha_usa_linha_reta():
    corpo = _rotas([PONTA_NEGRA], [LAGOA_NOVA], municipio="9999999")
    assert corpo["malha_viaria"] is False
    m = corpo["movimentos"][0]
    assert len(m["caminho"]) == 2
    assert m["tempo_s"] == pytest.approx(m["distancia_m"] / (30 / 3.6), rel=1e-3)


def test_quantidades_diferentes():
    r = cliente.post("/rotas2d", json={"origens": [PONTA_NEGRA], "destinos": [], "municipio": NATAL})
    assert r.status_code == 422


def test_criterios_soma_e_maximo_divergem():
    # Pareamento direto: soma 0+10=10, maior 10. Cruzado: soma 6+6=12, maior 6.
    custo = np.array([[0.0, 6.0], [6.0, 10.0]])
    assert list(_associar(custo, "soma")[1]) == [0, 1]
    assert list(_associar(custo, "maximo")[1]) == [1, 0]


def test_maximo_desempata_pela_soma():
    # Todas as solucoes tem maior custo 5; a de menor soma e a diagonal (1+1+5)
    custo = np.array([[1.0, 5.0, 5.0], [5.0, 1.0, 5.0], [5.0, 5.0, 5.0]])
    assert list(_associar(custo, "maximo")[1]) == [0, 1, 2]


def test_criterio_maximo_em_natal_nao_piora_o_ultimo():
    origens = [PONTA_NEGRA, ALECRIM, LAGOA_NOVA]
    destinos = [ALECRIM, LAGOA_NOVA, {"lat": -5.84, "lng": -35.19}]
    soma = cliente.post("/rotas2d", json={"origens": origens, "destinos": destinos,
                                           "municipio": NATAL, "criterio": "soma"}).json()
    maximo = cliente.post("/rotas2d", json={"origens": origens, "destinos": destinos,
                                             "municipio": NATAL, "criterio": "maximo"}).json()
    assert maximo["criterio"] == "maximo"
    assert maximo["tempo_maximo_s"] <= soma["tempo_maximo_s"]
    assert soma["tempo_total_s"] <= maximo["tempo_total_s"]


def test_criterio_invalido():
    r = cliente.post("/rotas2d", json={"origens": [PONTA_NEGRA], "destinos": [ALECRIM],
                                        "municipio": NATAL, "criterio": "outro"})
    assert r.status_code == 422

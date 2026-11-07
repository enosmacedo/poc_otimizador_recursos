"""Testes do citeledrone. Os que executam o ARGoS rodam dentro do container:
    docker compose exec citeledrone python3 -m pytest -q tests
"""
import math
import shutil

import pytest

from app.simulacao import (TOLERANCIA_M, associar_alvos, decolar, gerar_experimento,
                           interpretar_log, posicoes_base, reposicionar)

ARGOS = shutil.which("argos3")
precisa_argos = pytest.mark.skipif(ARGOS is None, reason="ARGoS nao instalado (rode no container)")
QUADRADO = [{"x": -30.0, "y": -20.0, "z": 30.0}, {"x": 30.0, "y": 20.0, "z": 30.0},
            {"x": 30.0, "y": -20.0, "z": 30.0}, {"x": -30.0, "y": 20.0, "z": 30.0}]
xyz = lambda p: (p["x"], p["y"], p["z"])  # noqa: E731


def test_base_sem_drones_sobrepostos():
    base = posicoes_base(10, -60)
    assert len(base) == 10 and all(p["z"] == 0 for p in base)
    menor = min(math.dist(xyz(a), xyz(b)) for i, a in enumerate(base) for b in base[i + 1:])
    assert menor >= 1.5 - 1e-9


def test_associacao_minimiza_o_maior_deslocamento():
    inicios = [{"x": 0.0, "y": 0.0, "z": 30.0}, {"x": 10.0, "y": 0.0, "z": 30.0}]
    # Direto: 0 e 10 (maior 10). Cruzado: 20 e 10 (maior 20) -> direto
    alvos = [{"x": 0.0, "y": 0.0, "z": 30.0}, {"x": 20.0, "y": 0.0, "z": 30.0}]
    assert associar_alvos(inicios, alvos) == [0, 1]
    # Direto: 10 e 20 (maior 20). Cruzado: 10 e 0 (maior 10) -> cruzado
    alvos = [{"x": 10.0, "y": 0.0, "z": 30.0}, {"x": -10.0, "y": 0.0, "z": 30.0}]
    assert associar_alvos(inicios, alvos) == [1, 0]
    assert sorted(associar_alvos(posicoes_base(4, -50), QUADRADO)) == [0, 1, 2, 3]


def test_experimento_inclui_posicao_inicial_no_ar():
    inicios = [{"x": 5.0, "y": 6.0, "z": 30.0}]
    xml, lua, dur = gerar_experimento(inicios, [QUADRADO[0]], 120, 80, 8, 3)
    assert 'position="5.000,6.000,30.000"' in xml
    assert 'ticks_per_second="50"' in xml and "quadrotor_position" in xml
    assert '["d0"]' in lua and "TPS = 50" in lua and dur > 8


def test_interpretar_log():
    texto = ("[INFO] x\nPOS d0 0 0.000 -44.000 0.000 subindo\n"
             "POS d1 50 1.000 2.000 10.000 posicionado\n")
    traj = interpretar_log(texto)
    assert traj[0] == [[0.0, 0.0, -44.0, 0.0]] and traj[1] == [[1.0, 1.0, 2.0, 10.0]]


def _confere_chegadas(sim, velocidade=8):
    assert sim["tempo_formacao_s"] is not None and sim["tempo_formacao_s"] < sim["duracao_s"]
    for d in sim["drones"]:
        dist = [math.dist(p[1:], xyz(d["alvo"])) for p in d["trajetoria"]]
        assert dist[-1] <= TOLERANCIA_M
        k = next(i for i, x in enumerate(dist) if x <= TOLERANCIA_M)
        assert max(dist[k:]) <= 1.0  # nao passa do alvo e volta
        pts = d["trajetoria"]
        vel = [math.dist(pts[i][1:], pts[i + 1][1:]) / 0.2 for i in range(len(pts) - 1)]
        assert max(vel) <= velocidade * 1.1


@precisa_argos
def test_decolagem_leva_todos_ate_o_alvo():
    sim = decolar(QUADRADO, 120, 80)
    assert len(sim["base"]) == 4 and all(d["inicio"]["z"] == 0 for d in sim["drones"])
    _confere_chegadas(sim)


@precisa_argos
def test_reposicionamento_parte_do_ar():
    inicios = QUADRADO[:3]
    alvos = [{"x": -20.0, "y": 0.0, "z": 30.0}, {"x": 20.0, "y": 10.0, "z": 30.0}, {"x": 20.0, "y": -10.0, "z": 30.0}]
    sim = reposicionar(inicios, alvos, 120, 80)
    for d in sim["drones"]:
        assert d["trajetoria"][0][3] > 29  # comeca no ar, nao no chao
    assert sorted(xyz(d["alvo"]) for d in sim["drones"]) == sorted(xyz(a) for a in alvos)
    _confere_chegadas(sim)

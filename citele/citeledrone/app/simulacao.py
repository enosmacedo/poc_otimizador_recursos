"""Gera e executa simulacoes do enxame de drones no ARGoS (sem interface).

- decolar: drones saem de uma base no chao e voam ate as posicoes calculadas;
- reposicionar: drones que ja estao no ar voam ate novas posicoes.
"""
import math
import re
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

CONTROLADOR = Path(__file__).resolve().parents[1] / "argos" / "drone.lua"
# 50 passos de controle por segundo e 1 iteracao de fisica por passo: o
# comando do drone avanca em degraus pequenos e ele para no alvo sem
# ultrapassar (com 10 passos/s o termo derivativo do eye-bot da trancos)
TICKS_POR_SEGUNDO = 50
ITERACOES_FISICA = 1
PASSOS_LOG = 10  # registra a posicao a cada 0,2 s
ESPACAMENTO_BASE = 1.5  # m entre drones na base de decolagem
FOLGA_S = 8  # segundos de simulacao depois do ultimo drone chegar
TOLERANCIA_M = 0.5  # distancia ao alvo para considerar o drone posicionado
ACELERACAO = 2.0  # m/s^2, a mesma do drone.lua
MARGEM_ARENA_M = 10

LINHA_POS = re.compile(
    r"POS d(\d+) (\d+) (-?[\d.]+) (-?[\d.]+) (-?[\d.]+) (\w+)")


class ErroSimulacao(RuntimeError):
    pass


def posicoes_base(n, base_y):
    """Drones lado a lado numa base retangular centrada em (0, base_y), no chao."""
    colunas = math.ceil(math.sqrt(n))
    linhas = math.ceil(n / colunas)
    pos = []
    for i in range(n):
        lin, col = divmod(i, colunas)
        pos.append({"x": (col - (colunas - 1) / 2) * ESPACAMENTO_BASE,
                    "y": base_y + (lin - (linhas - 1) / 2) * ESPACAMENTO_BASE, "z": 0.0})
    return pos


def _xyz(p):
    return (p["x"], p["y"], p["z"])


def associar_alvos(inicios, alvos):
    """Indice do alvo de cada drone: minimiza o maior deslocamento (o ultimo a
    chegar) e, entre as solucoes com esse maximo, a soma dos deslocamentos."""
    custo = np.array([[math.dist(_xyz(i), _xyz(a)) for a in alvos] for i in inicios])
    valores = np.unique(custo)
    baixo, alto = 0, len(valores) - 1
    while baixo < alto:  # menor limite que ainda permite ligar todos os pares
        meio = (baixo + alto) // 2
        linhas, colunas = linear_sum_assignment(custo > valores[meio])
        if (custo[linhas, colunas] > valores[meio]).any():
            baixo = meio + 1
        else:
            alto = meio
    proibido = custo.sum() + 1
    _, colunas = linear_sum_assignment(np.where(custo <= valores[baixo], custo, proibido))
    return [int(j) for j in colunas]


def _tempo_trecho(distancia, velocidade):
    """Tempo para percorrer a distancia com perfil trapezoidal (parte e para em repouso)."""
    d_acel = velocidade ** 2 / ACELERACAO  # acelerar + frear ate a velocidade maxima
    if distancia <= d_acel:
        return 2 * math.sqrt(distancia / ACELERACAO)
    return 2 * velocidade / ACELERACAO + (distancia - d_acel) / velocidade


def duracao_s(inicios, alvos, velocidade, subida):
    pior = max(_tempo_trecho(abs(a["z"] - i["z"]), subida)
               + _tempo_trecho(math.hypot(a["x"] - i["x"], a["y"] - i["y"]), velocidade)
               for i, a in zip(inicios, alvos))
    return math.ceil(pior + FOLGA_S)


def gerar_experimento(inicios, alvos, largura_m, comprimento_m, velocidade_ms, subida_ms):
    """Experimento do ARGoS com o drone i saindo de inicios[i] ate alvos[i].
    Devolve (xml_argos, script_lua, duracao_s)."""
    duracao = duracao_s(inicios, alvos, velocidade_ms, subida_ms)
    tabela = ",\n".join(f'  ["d{i}"] = {{{a["x"]:.3f}, {a["y"]:.3f}, {a["z"]:.3f}}}'
                        for i, a in enumerate(alvos))
    lua = (f"ALVOS = {{\n{tabela}\n}}\nVELOCIDADE = {velocidade_ms}\nSUBIDA = {subida_ms}\n"
           f"TPS = {TICKS_POR_SEGUNDO}\nPASSOS_LOG = {PASSOS_LOG}\n\n" + CONTROLADOR.read_text(encoding="utf-8"))

    # Arena centrada na origem, cobrindo a area, os pontos de partida e os alvos
    pontos = inicios + alvos
    meia_x = max(largura_m / 2, *(abs(p["x"]) for p in pontos)) + MARGEM_ARENA_M
    meia_y = max(comprimento_m / 2, *(abs(p["y"]) for p in pontos)) + MARGEM_ARENA_M
    tam_z = max(p["z"] for p in pontos) + 10
    drones_xml = "\n".join(
        f'    <eye-bot id="d{i}"><body position="{p["x"]:.3f},{p["y"]:.3f},{p["z"]:.3f}" '
        f'orientation="0,0,0"/><controller config="drone"/></eye-bot>' for i, p in enumerate(inicios))
    xml = f"""<?xml version="1.0" ?>
<argos-configuration>
  <framework>
    <system threads="0" />
    <experiment length="{duracao}" ticks_per_second="{TICKS_POR_SEGUNDO}" random_seed="1" />
  </framework>
  <controllers>
    <lua_controller id="drone">
      <actuators><quadrotor_position implementation="default" /></actuators>
      <sensors><positioning implementation="default" /></sensors>
      <params script="drone.lua" />
    </lua_controller>
  </controllers>
  <arena size="{2 * meia_x:.1f}, {2 * meia_y:.1f}, {tam_z:.1f}" center="0,0,{tam_z / 2:.1f}">
{drones_xml}
  </arena>
  <physics_engines><pointmass3d id="pm3d" iterations="{ITERACOES_FISICA}" /></physics_engines>
  <media />
</argos-configuration>
"""
    return xml, lua, duracao


def interpretar_log(texto):
    """Linhas 'POS d<i> passo x y z fase' -> {i: [[t, x, y, z], ...]}."""
    trajetorias = {}
    for m in LINHA_POS.finditer(texto):
        drone, passo = int(m.group(1)), int(m.group(2))
        x, y, z = (float(m.group(k)) for k in (3, 4, 5))
        trajetorias.setdefault(drone, []).append(
            [round(passo / TICKS_POR_SEGUNDO, 2), round(x, 3), round(y, 3), round(z, 3)])
    return trajetorias


def chegada_s(pontos, alvo):
    """Instante em que a trajetoria chega a menos de TOLERANCIA_M do alvo."""
    return next((t for t, x, y, z in pontos if math.dist((x, y, z), _xyz(alvo)) <= TOLERANCIA_M), None)


def _rodar(inicios, alvos, largura_m, comprimento_m, velocidade_ms, subida_ms, argos):
    xml, lua, duracao = gerar_experimento(inicios, alvos, largura_m, comprimento_m, velocidade_ms, subida_ms)
    with tempfile.TemporaryDirectory() as pasta:
        (Path(pasta) / "experimento.argos").write_text(xml, encoding="utf-8")
        (Path(pasta) / "drone.lua").write_text(lua, encoding="utf-8")
        try:
            r = subprocess.run([argos, "-n", "-c", "experimento.argos"], cwd=pasta, capture_output=True,
                               text=True, timeout=300)
        except FileNotFoundError:
            raise ErroSimulacao("ARGoS (argos3) nao encontrado.")
        except subprocess.TimeoutExpired:
            raise ErroSimulacao("A simulacao passou do tempo limite (5 min).")
    trajetorias = interpretar_log(r.stdout)
    if r.returncode != 0 or len(trajetorias) != len(alvos):
        raise ErroSimulacao(f"ARGoS falhou (codigo {r.returncode}): {(r.stderr or r.stdout)[-800:]}")
    drones = []
    for i, (inicio, alvo) in enumerate(zip(inicios, alvos)):
        pontos = trajetorias[i]
        drones.append({"inicio": {k: round(v, 3) for k, v in inicio.items()}, "alvo": alvo,
                       "trajetoria": pontos, "chegada_s": chegada_s(pontos, alvo),
                       "distancia_m": round(math.dist(_xyz(inicio), _xyz(alvo)), 2)})
    chegadas = [d["chegada_s"] for d in drones]
    return {"duracao_s": duracao, "drones": drones,
            "tempo_formacao_s": None if None in chegadas else max(chegadas)}


def decolar(alvos, largura_m, comprimento_m, velocidade_ms=8.0, subida_ms=3.0, argos="argos3"):
    """Drones decolam de uma base logo abaixo da area ate os alvos."""
    base = posicoes_base(len(alvos), -comprimento_m / 2 - 4)
    ordem = associar_alvos(base, alvos)
    sim = _rodar(base, [alvos[j] for j in ordem], largura_m, comprimento_m, velocidade_ms, subida_ms, argos)
    return {**sim, "base": base}


def reposicionar(inicios, alvos, largura_m, comprimento_m, velocidade_ms=8.0, subida_ms=3.0, argos="argos3"):
    """Drones ja no ar (inicios[i]) voam ate novos alvos; quem vai para onde
    e decidido por associar_alvos."""
    ordem = associar_alvos(inicios, alvos)
    return _rodar(inicios, [alvos[j] for j in ordem], largura_m, comprimento_m, velocidade_ms, subida_ms, argos)

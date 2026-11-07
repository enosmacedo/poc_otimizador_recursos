"""citeledrone: simulacao 3D de enxames de drones (ARGoS) integrada ao Citeleat."""
import os
import time
import uuid
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .simulacao import ErroSimulacao, decolar, reposicionar

CITELEAT_URL = os.environ.get("CITELEAT_URL", "http://localhost:8000")
PUBLICO = Path(__file__).resolve().parents[1] / "public"
MAX_ENXAMES = 50

app = FastAPI(title="citeledrone", version="0.2.0")

# Enxames simulados, em memoria: id -> {parametros, base, drones: [{numero, x, y, z}]}
enxames = {}


class Simulacao(BaseModel):
    drones: int = Field(ge=1, le=100, description="Quantidade de drones (cada drone e um recurso)")
    estrategia: str = "linear-area-drones"
    largura_m: float = Field(gt=0, le=2000)
    comprimento_m: float = Field(gt=0, le=2000)
    altitude_m: float = Field(gt=0, le=120, description="Altitude de voo (limite usual da ANAC/DECEA: 120 m)")
    velocidade_ms: float = Field(8.0, gt=0, le=25, description="Velocidade horizontal maxima")
    subida_ms: float = Field(3.0, gt=0, le=10, description="Velocidade de subida")


class Remocao(BaseModel):
    estrategia: str | None = Field(None, description="Estrategia do reposicionamento (padrao: a do enxame)")


def _citeleat(metodo, caminho, **kwargs):
    try:
        r = httpx.request(metodo, f"{CITELEAT_URL}{caminho}", timeout=120, **kwargs)
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Citeleat indisponível: {e}")
    if r.status_code == 422:
        detalhe = r.json().get("detail")
        raise HTTPException(400, detalhe if isinstance(detalhe, str) else str(detalhe))
    if r.status_code >= 400:
        raise HTTPException(502, f"Citeleat respondeu {r.status_code}: {r.text[:300]}")
    return r.json()


def _calcular(parametros, drones):
    return _citeleat("POST", "/calc3ddrones", json={
        "drones": drones, "estrategia": parametros["estrategia"], "largura_m": parametros["largura_m"],
        "comprimento_m": parametros["comprimento_m"], "altitude_m": parametros["altitude_m"]})


def _resposta(enxame_id, enxame, calculo, sim, numeros):
    """Monta a resposta e atualiza as posicoes atuais dos drones do enxame."""
    for d, numero in zip(sim["drones"], numeros):
        d["numero"] = numero
    enxame["drones"] = [{"numero": d["numero"], **d["alvo"]} for d in sim["drones"]]
    return {"enxame": {"id": enxame_id, "drones": enxame["drones"]}, "parametros": enxame["parametros"],
            "calculo": calculo, "simulacao": {**sim, "base": enxame["base"]}}


@app.get("/api/saude")
def saude():
    return {"status": "ok"}


@app.get("/api/config")
def config():
    return {"estrategias": _citeleat("GET", "/estrategias3d"), "max_drones": 100,
            "max_area_m": 2000, "max_altitude_m": 120}


@app.post("/api/simular")
def simular(corpo: Simulacao):
    """1) Citeleat calcula as posicoes 3D; 2) ARGoS simula o enxame decolando
    da base e voando ate elas; 3) guarda o enxame e devolve as trajetorias."""
    parametros = corpo.model_dump()
    calculo = _calcular(parametros, corpo.drones)
    inicio = time.time()
    try:
        sim = decolar(calculo["posicoes"], corpo.largura_m, corpo.comprimento_m,
                      corpo.velocidade_ms, corpo.subida_ms)
    except ErroSimulacao as e:
        raise HTTPException(500, str(e))
    print(f"[simular] drones={corpo.drones} area={corpo.largura_m}x{corpo.comprimento_m} "
          f"alt={corpo.altitude_m} formacao={sim['tempo_formacao_s']}s argos={time.time() - inicio:.1f}s",
          flush=True)
    enxame_id = uuid.uuid4().hex
    enxames[enxame_id] = {"parametros": parametros, "base": sim.pop("base"), "drones": []}
    while len(enxames) > MAX_ENXAMES:
        enxames.pop(next(iter(enxames)))
    return _resposta(enxame_id, enxames[enxame_id], calculo, sim, list(range(1, corpo.drones + 1)))


@app.get("/api/enxames/{enxame_id}")
def obter_enxame(enxame_id: str):
    enxame = _enxame(enxame_id)
    return {"id": enxame_id, "parametros": enxame["parametros"], "drones": enxame["drones"]}


def _enxame(enxame_id):
    if enxame_id not in enxames:
        raise HTTPException(404, "Enxame não encontrado (o servidor pode ter reiniciado). Simule de novo.")
    return enxames[enxame_id]


@app.post("/api/enxames/{enxame_id}/drones/{numero}/remover")
def remover_drone(enxame_id: str, numero: int, corpo: Remocao | None = None):
    """Apaga um drone e reposiciona os demais: a estrategia recalcula as
    posicoes para os drones restantes e o ARGoS simula o voo de cada um, a
    partir de onde esta, ate a nova posicao."""
    enxame = _enxame(enxame_id)
    atuais = enxame["drones"]
    if not any(d["numero"] == numero for d in atuais):
        raise HTTPException(404, f"Drone {numero} não existe. Drones atuais: "
                                 f"{', '.join(str(d['numero']) for d in atuais)}.")
    if len(atuais) == 1:
        raise HTTPException(400, "Não é possível apagar o último drone do enxame.")
    if corpo and corpo.estrategia:
        enxame["parametros"]["estrategia"] = corpo.estrategia
    p = enxame["parametros"]

    restantes = [d for d in atuais if d["numero"] != numero]
    calculo = _calcular(p, len(restantes))
    inicios = [{"x": d["x"], "y": d["y"], "z": d["z"]} for d in restantes]
    try:
        sim = reposicionar(inicios, calculo["posicoes"], p["largura_m"], p["comprimento_m"],
                           p["velocidade_ms"], p["subida_ms"])
    except ErroSimulacao as e:
        raise HTTPException(500, str(e))
    resposta = _resposta(enxame_id, enxame, calculo, sim, [d["numero"] for d in restantes])
    print(f"[remover] enxame={enxame_id} drone={numero} restantes={len(restantes)} "
          f"formacao={sim['tempo_formacao_s']}s", flush=True)
    return {"removido": numero, **resposta}


app.mount("/", StaticFiles(directory=PUBLICO, html=True), name="publico")

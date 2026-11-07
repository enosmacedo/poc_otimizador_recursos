// Cliente do Citeleat (/calc2dpoligono e /rotas2d).

export class ErroCiteleat extends Error {
  constructor(mensagem, status) {
    super(mensagem);
    this.status = status;
  }
}

const espera = (ms) => new Promise((r) => setTimeout(r, ms));

/** fetch com timeout e novas tentativas em erros temporarios. */
async function requisitar(url, opcoes, { timeoutMs = 120000, tentativas = 3 } = {}) {
  for (let tentativa = 1; ; tentativa++) {
    let resposta;
    try {
      resposta = await fetch(url, { ...opcoes, signal: AbortSignal.timeout(timeoutMs) });
    } catch (e) {
      if (tentativa < tentativas) { await espera(500 * tentativa); continue; }
      throw new ErroCiteleat(`Citeleat indisponível: ${e.message}`, 502);
    }
    const temporario = resposta.status === 429 || resposta.status >= 500;
    if (temporario && tentativa < tentativas) { await espera(500 * tentativa); continue; }

    const corpo = await resposta.json().catch(() => ({}));
    if (!resposta.ok) {
      const detalhe = typeof corpo.detail === "string" ? corpo.detail : JSON.stringify(corpo.detail ?? corpo);
      // 422: o Citeleat recusou os dados (ex.: municipio sem malha viaria)
      if (resposta.status === 422) throw new ErroCiteleat(detalhe, 400);
      throw new ErroCiteleat(`Citeleat respondeu ${resposta.status}: ${detalhe}`, 502);
    }
    return corpo;
  }
}

const postJson = (corpo) => ({
  method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(corpo),
});

/**
 * Sem `areas`: GET com o poligono na URL. Com `areas` (bairros com
 * populacao): POST com JSON, porque os poligonos nao cabem numa URL.
 */
export async function calc2dPoligono(urlBase,
  { recursos, estrategia, coordenadas, areas, municipio }, opcoes) {
  const url = new URL("/calc2dpoligono", urlBase);
  if (areas) {
    return requisitar(url, postJson({ recursos, estrategia, coordenadas, areas, municipio }), opcoes);
  }
  url.searchParams.set("recursos", recursos);
  url.searchParams.set("estrategia", estrategia);
  url.searchParams.set("coordenadas", coordenadas.map(([lon, lat]) => `${lon},${lat}`).join(";"));
  if (municipio) url.searchParams.set("municipio", municipio);
  return requisitar(url, {}, opcoes);
}

/** Rotas das posicoes atuais (origens) ate as novas (destinos), pontos {lat, lng}. */
export async function rotas2d(urlBase,
  { origens, destinos, municipio, associar = true, criterio = "soma" }, opcoes) {
  return requisitar(new URL("/rotas2d", urlBase),
    postJson({ origens, destinos, municipio, associar, criterio }), opcoes);
}

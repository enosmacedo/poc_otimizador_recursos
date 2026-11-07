// Douglas-Peucker: reduz o numero de vertices de um anel [[lon, lat], ...].

function distanciaSegmento([px, py], [ax, ay], [bx, by]) {
  const dx = bx - ax;
  const dy = by - ay;
  const comprimento2 = dx * dx + dy * dy;
  let t = comprimento2 ? ((px - ax) * dx + (py - ay) * dy) / comprimento2 : 0;
  t = Math.max(0, Math.min(1, t));
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
}

function douglasPeucker(pontos, tolerancia) {
  const manter = new Uint8Array(pontos.length);
  manter[0] = manter[pontos.length - 1] = 1;
  const pilha = [[0, pontos.length - 1]];
  while (pilha.length) {
    const [ini, fim] = pilha.pop();
    let maior = 0;
    let indice = -1;
    for (let i = ini + 1; i < fim; i++) {
      const d = distanciaSegmento(pontos[i], pontos[ini], pontos[fim]);
      if (d > maior) { maior = d; indice = i; }
    }
    if (indice !== -1 && maior > tolerancia) {
      manter[indice] = 1;
      pilha.push([ini, indice], [indice, fim]);
    }
  }
  return pontos.filter((_, i) => manter[i]);
}

/**
 * Simplifica o anel (fechado) ate ter no maximo `maxVertices`,
 * aumentando a tolerancia em 50% a cada tentativa.
 */
export function simplificarAnel(anel, maxVertices) {
  if (anel.length <= maxVertices) return anel;
  // Divide o anel em duas metades para o DP nao colapsar o primeiro/ultimo ponto
  const meio = Math.floor(anel.length / 2);
  let tolerancia = 1e-5;
  let resultado = anel;
  while (resultado.length > maxVertices) {
    const a = douglasPeucker(anel.slice(0, meio + 1), tolerancia);
    const b = douglasPeucker(anel.slice(meio), tolerancia);
    resultado = [...a, ...b.slice(1)];
    tolerancia *= 1.5;
  }
  return resultado.length >= 4 ? resultado : anel.slice(0, maxVertices);
}

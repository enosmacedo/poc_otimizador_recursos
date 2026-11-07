import assert from "node:assert/strict";
import { after, before, describe, test } from "node:test";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { criarApp } from "../src/app.js";
import { Municipios, normalizar, resolverUf } from "../src/municipios.js";
import { simplificarAnel } from "../src/simplificar.js";

const pastaDados = process.env.DADOS_DIR ??
  path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../dados");
const municipios = new Municipios(pastaDados);

describe("resolucao de municipios", () => {
  const casos = [
    ["Natal", "RN", "2408102"],
    ["natal", "rio grande do norte", "2408102"],
    ["  NATAL ", "rn", "2408102"],
    ["Ourilandia do Norte", "PA", "1505437"],
    ["Lagoa dos Patos", "MG", "3137304"],
    ["Sao Paulo", "SP", "3550308"],
    ["Alta Floresta DOeste", "RO", undefined], // sem apostrofo nao casa
    ["Alta Floresta D Oeste", "RO", "1100015"],
    ["alta floresta d'oeste", "Rondônia", "1100015"],
  ];
  for (const [cidade, estado, esperado] of casos) {
    test(`${cidade}/${estado}`, () => {
      if (esperado) assert.equal(municipios.resolver(cidade, estado).cd_mun, esperado);
      else assert.throws(() => municipios.resolver(cidade, estado));
    });
  }

  test("Lagoa dos Patos/RS nao e municipio", () => {
    assert.throws(() => municipios.resolver("Lagoa dos Patos", "RS"), { status: 404 });
  });

  test("Natal/PB sugere nomes parecidos", () => {
    try {
      municipios.resolver("Natal", "PB");
      assert.fail("deveria lancar");
    } catch (e) {
      assert.equal(e.status, 404);
      assert.ok(e.extras.sugestoes.length > 0 && e.extras.sugestoes.length <= 5);
    }
  });

  test("estado invalido", () => {
    assert.throws(() => resolverUf("XX"), /não reconhecido/);
  });

  test("normalizar", () => {
    assert.equal(normalizar("  São  João-del-Rei "), "sao joao del rei");
  });
});

describe("simplificacao", () => {
  test("respeita o maximo de vertices e mantem o anel fechado", () => {
    const anel = Array.from({ length: 5001 }, (_, i) => {
      const a = (2 * Math.PI * i) / 5000;
      return [Math.cos(a) + 0.001 * Math.sin(50 * a), Math.sin(a)];
    });
    anel[anel.length - 1] = anel[0];
    const s = simplificarAnel(anel, 1000);
    assert.ok(s.length <= 1000 && s.length >= 4);
    assert.deepEqual(s[0], s[s.length - 1]);
  });
});

describe("API", () => {
  let servidor;
  let base;
  let chamadas = [];
  let chamadasRotas = [];
  const citeleatFalso = async (_url, args) => {
    chamadas.push(args);
    const pontos = Array.from({ length: args.recursos }, (_, i) =>
      ({ lat: -5.8 - i / 1000, lng: -35.2 - args.recursos / 1000 }));
    return { raio_m: 1234.5, pontos, cobertura: 1 };
  };
  // Associa em ordem inversa, para conferir que o backend respeita o pareamento
  const rotasFalsas = async (_url, args) => {
    chamadasRotas.push(args);
    const n = args.origens.length;
    return { malha_viaria: true, tempo_total_s: 60 * n, tempo_maximo_s: 60,
      movimentos: args.origens.map((o, i) => ({ origem: i, destino: n - 1 - i, tempo_s: 60,
        distancia_m: 500, caminho: [[o.lat, o.lng], [args.destinos[n - 1 - i].lat, args.destinos[n - 1 - i].lng]] })) };
  };

  before(async () => {
    const app = criarApp({ municipios, citeleatUrl: "http://x", googleMapsApiKey: "k",
      googleMapsMapId: "m", maxVertices: 100, chamarCiteleat: citeleatFalso,
      chamarRotas: rotasFalsas });
    await new Promise((r) => { servidor = app.listen(0, r); });
    base = `http://localhost:${servidor.address().port}`;
  });
  after(() => servidor.close());

  const post = (corpo) => fetch(`${base}/api/calcular`, {
    method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(corpo),
  });

  test("GET /api/municipio", async () => {
    const r = await fetch(`${base}/api/municipio?cidade=natal&estado=RN`);
    assert.equal(r.status, 200);
    const m = await r.json();
    assert.equal(m.cd_mun, "2408102");
    assert.equal(m.bbox.length, 4);
    assert.ok(m.coordenadas.length > 3);
  });

  test("GET /api/municipio nao encontrado", async () => {
    const r = await fetch(`${base}/api/municipio?cidade=Natal&estado=PB`);
    assert.equal(r.status, 404);
    assert.ok((await r.json()).sugestoes.length > 0);
  });

  test("POST /api/calcular simplifica e repassa ao Citeleat", async () => {
    chamadas = [];
    // Sao Paulo tem mais de 100 vertices nos dados
    const r = await post({ cidade: "São Paulo", estado: "SP", recursos: 5,
      tipo: "ambulancia", estrategia: "linear-area-cidade" });
    assert.equal(r.status, 200);
    const corpo = await r.json();
    assert.equal(corpo.municipio.cd_mun, "3550308");
    assert.equal(corpo.resultado.raio_m, 1234.5);
    assert.equal(chamadas[0].recursos, 5);
    assert.ok(chamadas[0].coordenadas.length <= 100);
    assert.equal(corpo.municipio.coordenadas, undefined);
  });

  test("densidade por bairros envia as areas da capital", async () => {
    chamadas = [];
    const r = await post({ cidade: "Natal", estado: "RN", recursos: 4, tipo: "policia",
      estrategia: "linear-densidade-bairros" });
    assert.equal(r.status, 200);
    const corpo = await r.json();
    assert.deepEqual(corpo.areas, { unidade: "bairro", quantidade: 36 });
    assert.equal(chamadas[0].areas.length, 36);
    const total = chamadas[0].areas.reduce((s, a) => s + a.populacao, 0);
    assert.equal(total, 751300);
    assert.ok(chamadas[0].areas[0].geometria.type);
  });

  test("densidade por bairros em cidade que nao e capital", async () => {
    const r = await post({ cidade: "Mossoró", estado: "RN", recursos: 4, tipo: "policia",
      estrategia: "linear-densidade-bairros" });
    assert.equal(r.status, 400);
    assert.match((await r.json()).erro, /capitais/);
  });

  test("tempo de deslocamento envia o codigo do municipio", async () => {
    chamadas = [];
    const r = await post({ cidade: "Natal", estado: "RN", recursos: 4, tipo: "ambulancia",
      estrategia: "linear-tempo-deslocamento" });
    assert.equal(r.status, 200);
    assert.equal(chamadas[0].municipio, "2408102");
    assert.equal(chamadas[0].areas, undefined);
  });

  test("area da cidade nao envia areas", async () => {
    chamadas = [];
    await post({ cidade: "Natal", estado: "RN", recursos: 4, tipo: "policia",
      estrategia: "linear-area-cidade" });
    assert.equal(chamadas[0].areas, undefined);
  });

  test("calcular cria um objeto numerado para cada recurso", async () => {
    const r = await post({ cidade: "Natal", estado: "RN", recursos: 3, tipo: "policia",
      estrategia: "linear-area-cidade" });
    const { alocacao } = await r.json();
    assert.ok(alocacao.id);
    assert.deepEqual(alocacao.recursos.map((x) => x.numero), [1, 2, 3]);
    assert.ok(alocacao.recursos.every((x) => x.tipo === "policia" && x.lat && x.lng));
    const obtida = await (await fetch(`${base}/api/alocacoes/${alocacao.id}`)).json();
    assert.equal(obtida.recursos.length, 3);
  });

  test("apagar recurso recalcula e devolve as rotas dos restantes", async () => {
    const r = await post({ cidade: "Natal", estado: "RN", recursos: 4, tipo: "ambulancia",
      estrategia: "linear-tempo-deslocamento" });
    const { alocacao } = await r.json();
    chamadas = [];
    chamadasRotas = [];
    const d = await fetch(`${base}/api/alocacoes/${alocacao.id}/recursos/2`, { method: "DELETE" });
    assert.equal(d.status, 200);
    const corpo = await d.json();

    // Recalculou com 3 recursos, na mesma estrategia e municipio
    assert.equal(chamadas[0].recursos, 3);
    assert.equal(chamadas[0].estrategia, "linear-tempo-deslocamento");
    assert.equal(chamadas[0].municipio, "2408102");
    // Rotas pedidas das posicoes atuais dos recursos 1, 3 e 4
    assert.equal(chamadasRotas[0].origens.length, 3);
    assert.equal(chamadasRotas[0].municipio, "2408102");

    assert.equal(corpo.removido, 2);
    assert.deepEqual(corpo.alocacao.recursos.map((x) => x.numero), [1, 3, 4]);
    assert.deepEqual(corpo.movimentos.map((m) => m.numero), [1, 3, 4]);
    // O recurso 1 (origem 0) foi para o destino 2 (pareamento invertido)
    const novos = corpo.alocacao.recursos;
    const m1 = corpo.movimentos.find((m) => m.numero === 1);
    assert.deepEqual(m1.para, { lat: novos[0].lat, lng: novos[0].lng });
    assert.equal(m1.para.lat, -5.8 - 2 / 1000);
    assert.deepEqual(m1.de, { lat: alocacao.recursos[0].lat, lng: alocacao.recursos[0].lng });
    assert.equal(novos[0].movimentos, 1);
  });

  test("apagar repassa o criterio de deslocamento (padrao: maximo)", async () => {
    const criar = async () => (await (await post({ cidade: "Natal", estado: "RN", recursos: 3,
      tipo: "ambulancia", estrategia: "linear-area-cidade" })).json()).alocacao;
    const apagar = (id, q = "") => fetch(`${base}/api/alocacoes/${id}/recursos/1${q}`, { method: "DELETE" });

    chamadasRotas = [];
    let r = await apagar((await criar()).id);
    assert.equal(chamadasRotas[0].criterio, "maximo");
    assert.equal((await r.json()).rotas.criterio, "maximo");

    chamadasRotas = [];
    r = await apagar((await criar()).id, "?criterio=soma");
    assert.equal(chamadasRotas[0].criterio, "soma");

    const a = await criar();
    assert.equal((await apagar(a.id, "?criterio=outro")).status, 400);
    // O criterio invalido nao pode ter apagado nada
    const atual = await (await fetch(`${base}/api/alocacoes/${a.id}`)).json();
    assert.equal(atual.recursos.length, 3);
  });

  test("apagar recurso inexistente, ultimo recurso ou alocacao desconhecida", async () => {
    const r = await post({ cidade: "Natal", estado: "RN", recursos: 1, tipo: "ambulancia",
      estrategia: "linear-area-cidade" });
    const { alocacao } = await r.json();
    const apagar = (id, n) => fetch(`${base}/api/alocacoes/${id}/recursos/${n}`, { method: "DELETE" });
    assert.equal((await apagar(alocacao.id, 9)).status, 404);
    assert.equal((await apagar(alocacao.id, 1)).status, 400);
    assert.equal((await apagar("nao-existe", 1)).status, 404);
  });

  test("POST /api/calcular valida entradas", async () => {
    const valido = { cidade: "Natal", estado: "RN", recursos: 3, tipo: "policia",
      estrategia: "linear-area-cidade" };
    assert.equal((await post({ ...valido, recursos: 0 })).status, 400);
    assert.equal((await post({ ...valido, recursos: 2.5 })).status, 400);
    assert.equal((await post({ ...valido, tipo: "bombeiro" })).status, 400);
    assert.equal((await post({ ...valido, estrategia: "x" })).status, 400);
    assert.equal((await post({ ...valido, estado: "ZZ" })).status, 400);
    assert.equal((await post(valido)).status, 200);
  });
});

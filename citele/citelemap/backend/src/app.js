// API do Citelemap: pre-processa a requisicao do frontend e chama o Citeleat.
import express from "express";

import { calc2dPoligono, ErroCiteleat, rotas2d } from "./citeleat.js";
import { ErroMunicipio, LISTA_UFS } from "./municipios.js";
import { Alocacao, RepositorioAlocacoes } from "./recursos.js";
import { simplificarAnel } from "./simplificar.js";

export const TIPOS_RECURSO = [
  { id: "ambulancia", nome: "Ambulância" },
  { id: "policia", nome: "Polícia" },
];
export const ESTRATEGIAS = [
  { id: "linear-area-cidade", nome: "linear - área da cidade" },
  { id: "linear-densidade-bairros", nome: "linear - densidade por bairros", precisaAreas: true },
  { id: "linear-tempo-deslocamento", nome: "linear - tempo de deslocamento", precisaMunicipio: true },
];
// Como escolher qual recurso vai para qual nova posicao ao realocar
export const CRITERIOS_REALOCACAO = [
  { id: "maximo", nome: "Menor tempo do último a chegar" },
  { id: "soma", nome: "Menor tempo total dos deslocamentos" },
];
const MAX_RECURSOS = 200;

function dadosMunicipio(municipios, cidade, estado) {
  const m = municipios.resolver(cidade, estado);
  const p = municipios.poligono(m.cd_mun, m.uf);
  return { ...m, area_km2: p.area_km2, partes: p.partes, bbox: p.bbox, coordenadas: p.coordenadas };
}

export function criarApp({ municipios, citeleatUrl, googleMapsApiKey, googleMapsMapId,
  maxVertices = 1000, chamarCiteleat = calc2dPoligono, chamarRotas = rotas2d,
  alocacoes = new RepositorioAlocacoes() }) {
  const app = express();
  app.use(express.json({ limit: "100kb" }));

  /** Executa a estrategia no Citeleat para `recursos` recursos no municipio. */
  async function executarEstrategia(municipio, coordenadas, estrategia, recursos) {
    const definicao = ESTRATEGIAS.find((e) => e.id === estrategia);
    let dadosAreas = null;
    if (definicao.precisaAreas) {
      dadosAreas = municipios.areas(municipio.cd_mun);
      if (!dadosAreas) {
        throw new ErroMunicipio(`A estratégia '${definicao.nome}' só está disponível para as ` +
          `capitais; não há dados de bairros para ${municipio.nome}/${municipio.uf}.`, 400);
      }
    }
    const inicio = Date.now();
    const resultado = await chamarCiteleat(citeleatUrl, {
      recursos, estrategia, coordenadas, areas: dadosAreas?.areas,
      municipio: definicao.precisaMunicipio ? municipio.cd_mun : undefined,
    });
    console.log(`[calcular] ${municipio.cd_mun} ${municipio.nome}/${municipio.uf} ${estrategia} ` +
      `recursos=${recursos} vertices=${coordenadas.length} areas=${dadosAreas?.areas.length ?? 0} ` +
      `raio=${resultado.raio_m}m ${Date.now() - inicio}ms`);
    const areas = dadosAreas && { unidade: dadosAreas.unidade, quantidade: dadosAreas.areas.length };
    return { resultado, areas };
  }

  app.get("/api/saude", (_req, res) => res.json({ status: "ok" }));

  app.get("/api/config", (_req, res) => res.json({
    googleMapsApiKey, googleMapsMapId, ufs: LISTA_UFS,
    tiposRecurso: TIPOS_RECURSO, estrategias: ESTRATEGIAS, maxRecursos: MAX_RECURSOS,
    criteriosRealocacao: CRITERIOS_REALOCACAO,
  }));

  // Secao 1: localiza o municipio e devolve o contorno para o mapa
  app.get("/api/municipio", (req, res) => {
    const m = dadosMunicipio(municipios, req.query.cidade, req.query.estado);
    res.json(m);
  });

  // Secao 2: calcula a alocacao e cria um objeto para cada recurso
  app.post("/api/calcular", async (req, res) => {
    const { cidade, estado, tipo, estrategia } = req.body ?? {};
    const recursos = Number(req.body?.recursos);
    if (!Number.isInteger(recursos) || recursos < 1 || recursos > MAX_RECURSOS) {
      throw new ErroMunicipio(`O número de recursos deve ser um inteiro entre 1 e ${MAX_RECURSOS}.`, 400);
    }
    if (!TIPOS_RECURSO.some((t) => t.id === tipo)) {
      throw new ErroMunicipio(`Tipo de recurso inválido: '${tipo}'.`, 400);
    }
    if (!ESTRATEGIAS.some((e) => e.id === estrategia)) {
      throw new ErroMunicipio(`Estratégia inválida: '${estrategia}'.`, 400);
    }

    const { coordenadas: contorno, ...municipio } = dadosMunicipio(municipios, cidade, estado);
    const coordenadas = simplificarAnel(contorno, maxVertices);
    const { resultado, areas } = await executarEstrategia(municipio, coordenadas, estrategia, recursos);
    const alocacao = alocacoes.adicionar(
      new Alocacao({ municipio, coordenadas, tipo, estrategia, resultado }));
    res.json({ municipio, tipo, estrategia, vertices_enviados: coordenadas.length, areas, resultado,
      alocacao });
  });

  app.get("/api/alocacoes/:id", (req, res) => res.json(alocacoes.obter(req.params.id)));

  // Secao de operacoes: apaga um recurso, recalcula a alocacao com os que
  // restaram e devolve a rota de cada recurso ate a sua nova posicao.
  // ?criterio=maximo|soma define o pareamento (padrao: maximo)
  app.delete("/api/alocacoes/:id/recursos/:numero", async (req, res) => {
    const criterio = req.query.criterio ?? CRITERIOS_REALOCACAO[0].id;
    if (!CRITERIOS_REALOCACAO.some((c) => c.id === criterio)) {
      throw new ErroMunicipio(`Critério inválido: '${criterio}'.`, 400);
    }
    const alocacao = alocacoes.obter(req.params.id);
    const numero = Number(req.params.numero);
    alocacao.recurso(numero); // 404 se nao existir
    if (alocacao.recursos.length === 1) {
      throw new ErroMunicipio("Não é possível apagar o último recurso da alocação.", 400);
    }

    const restantes = alocacao.recursos.filter((r) => r.numero !== numero);
    const { resultado, areas } = await executarEstrategia(alocacao.municipio, alocacao.coordenadas,
      alocacao.estrategia, restantes.length);
    const rotas = await chamarRotas(citeleatUrl, {
      origens: restantes.map((r) => r.posicao), destinos: resultado.pontos.map(({ lat, lng }) => ({ lat, lng })),
      municipio: alocacao.municipio.cd_mun, associar: true, criterio,
    });

    const movimentos = rotas.movimentos.map((m) => {
      const recurso = restantes[m.origem];
      const de = recurso.posicao;
      recurso.moverPara(resultado.pontos[m.destino], `recurso ${numero} apagado`);
      return { numero: recurso.numero, de, para: recurso.posicao, tempo_s: m.tempo_s,
        distancia_m: m.distancia_m, caminho: m.caminho };
    }).sort((a, b) => a.numero - b.numero);
    alocacao.remover(numero);
    alocacao.resultado = resultado;
    console.log(`[apagar] alocacao=${alocacao.id} recurso=${numero} restantes=${restantes.length} ` +
      `criterio=${criterio} ` +
      `malha=${rotas.malha_viaria} tempo_max=${rotas.tempo_maximo_s}s`);

    res.json({ removido: numero, alocacao, areas, movimentos,
      rotas: { malha_viaria: rotas.malha_viaria, criterio, tempo_total_s: rotas.tempo_total_s,
        tempo_maximo_s: rotas.tempo_maximo_s } });
  });

  app.use("/api", (_req, res) => res.status(404).json({ erro: "Rota não encontrada." }));

  app.use((err, _req, res, _next) => {
    if (err instanceof ErroMunicipio || err instanceof ErroCiteleat) {
      return res.status(err.status).json({ erro: err.message, ...(err.extras ?? {}) });
    }
    console.error(err);
    res.status(500).json({ erro: "Erro interno no Citelemap." });
  });

  return app;
}

// Resolve cidade + estado -> municipio do IBGE e carrega o seu poligono.
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

const UFS = {
  AC: "Acre", AL: "Alagoas", AP: "Amapá", AM: "Amazonas", BA: "Bahia",
  CE: "Ceará", DF: "Distrito Federal", ES: "Espírito Santo", GO: "Goiás",
  MA: "Maranhão", MT: "Mato Grosso", MS: "Mato Grosso do Sul",
  MG: "Minas Gerais", PA: "Pará", PB: "Paraíba", PR: "Paraná",
  PE: "Pernambuco", PI: "Piauí", RJ: "Rio de Janeiro",
  RN: "Rio Grande do Norte", RS: "Rio Grande do Sul", RO: "Rondônia",
  RR: "Roraima", SC: "Santa Catarina", SP: "São Paulo", SE: "Sergipe",
  TO: "Tocantins",
};

export class ErroMunicipio extends Error {
  constructor(mensagem, status = 400, extras = {}) {
    super(mensagem);
    this.status = status;
    this.extras = extras;
  }
}

/** Sem acento, minusculo, apostrofo/hifen viram espaco, espacos unicos. */
export function normalizar(texto) {
  return String(texto ?? "")
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase()
    .replace(/[''`´\-]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

const UF_POR_NOME = Object.fromEntries(
  Object.entries(UFS).map(([sigla, nome]) => [normalizar(nome), sigla]),
);

/** "rn", "RN" ou "Rio Grande do Norte" -> "RN" */
export function resolverUf(estado) {
  const n = normalizar(estado);
  const sigla = n.toUpperCase();
  if (UFS[sigla]) return sigla;
  if (UF_POR_NOME[n]) return UF_POR_NOME[n];
  throw new ErroMunicipio(`Estado '${estado}' não reconhecido.`, 400);
}

function levenshtein(a, b) {
  const linha = Array.from({ length: b.length + 1 }, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    let anterior = linha[0];
    linha[0] = i;
    for (let j = 1; j <= b.length; j++) {
      const atual = linha[j];
      linha[j] = Math.min(linha[j] + 1, linha[j - 1] + 1,
        anterior + (a[i - 1] === b[j - 1] ? 0 : 1));
      anterior = atual;
    }
  }
  return linha[b.length];
}

export class Municipios {
  constructor(pastaDados) {
    this.pasta = pastaDados;
    const lista = JSON.parse(readFileSync(path.join(pastaDados, "municipios.json"), "utf8"));
    this.porChave = new Map();
    this.porUf = new Map();
    for (const m of lista) {
      const item = { ...m, chave: normalizar(m.nome) };
      this.porChave.set(`${item.chave}|${m.uf}`, item);
      if (!this.porUf.has(m.uf)) this.porUf.set(m.uf, []);
      this.porUf.get(m.uf).push(item);
    }
    this.cachePoligonos = new Map();
  }

  /** Retorna {cd_mun, nome, uf} ou lanca ErroMunicipio com sugestoes. */
  resolver(cidade, estado) {
    if (!normalizar(cidade)) throw new ErroMunicipio("Informe a cidade.", 400);
    if (!normalizar(estado)) throw new ErroMunicipio("Informe o estado.", 400);
    const uf = resolverUf(estado);
    const chave = normalizar(cidade);
    const achado = this.porChave.get(`${chave}|${uf}`);
    if (achado) return { cd_mun: achado.cd_mun, nome: achado.nome, uf };

    const sugestoes = this.porUf.get(uf)
      .map((m) => ({ nome: m.nome, d: levenshtein(chave, m.chave), contem: m.chave.includes(chave) }))
      .sort((a, b) => (b.contem - a.contem) || (a.d - b.d))
      .slice(0, 5)
      .map((m) => m.nome);
    throw new ErroMunicipio(
      `Cidade '${cidade}' não encontrada em ${uf}.`, 404, { sugestoes },
    );
  }

  /** Dados do poligono do municipio (carrega o arquivo da UF uma vez). */
  poligono(cdMun, uf) {
    if (!this.cachePoligonos.has(uf)) {
      const arquivo = path.join(this.pasta, "poligonos", `${uf}.json`);
      this.cachePoligonos.set(uf, JSON.parse(readFileSync(arquivo, "utf8")));
    }
    return this.cachePoligonos.get(uf)[cdMun];
  }

  /** Areas (bairros) com populacao do municipio, ou null se nao houver. */
  areas(cdMun) {
    const arquivo = path.join(this.pasta, "areas", `${cdMun}.json`);
    if (!existsSync(arquivo)) return null;
    return JSON.parse(readFileSync(arquivo, "utf8"));
  }
}

export const LISTA_UFS = Object.entries(UFS).map(([sigla, nome]) => ({ sigla, nome }));

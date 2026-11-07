// Objetos de recursos e alocacoes mantidos em memoria pelo backend.
import { randomUUID } from "node:crypto";

import { ErroMunicipio } from "./municipios.js";

/** Um recurso alocado (ex.: ambulancia 3), com posicao e historico. */
export class Recurso {
  constructor({ numero, tipo, lat, lng, detalhes = {} }) {
    this.numero = numero;
    this.tipo = tipo;
    this.lat = lat;
    this.lng = lng;
    this.detalhes = detalhes; // populacao, tempo_medio_min... vindos da estrategia
    this.historico = [];
  }

  get posicao() {
    return { lat: this.lat, lng: this.lng };
  }

  moverPara({ lat, lng, ...detalhes }, motivo) {
    this.historico.push({ lat: this.lat, lng: this.lng, motivo, em: new Date().toISOString() });
    this.lat = lat;
    this.lng = lng;
    this.detalhes = detalhes;
  }

  toJSON() {
    return { numero: this.numero, tipo: this.tipo, lat: this.lat, lng: this.lng,
      ...this.detalhes, movimentos: this.historico.length };
  }
}

/** Resultado de um calculo: municipio, estrategia e os recursos criados. */
export class Alocacao {
  constructor({ municipio, coordenadas, tipo, estrategia, resultado }) {
    this.id = randomUUID();
    this.criadaEm = new Date().toISOString();
    this.municipio = municipio; // {cd_mun, nome, uf, ...} sem o contorno
    this.coordenadas = coordenadas; // contorno simplificado, para recalcular
    this.tipo = tipo;
    this.estrategia = estrategia;
    this.recursos = resultado.pontos.map(({ lat, lng, ...detalhes }, i) =>
      new Recurso({ numero: i + 1, tipo, lat, lng, detalhes }));
    this.resultado = resultado;
  }

  recurso(numero) {
    const r = this.recursos.find((x) => x.numero === numero);
    if (!r) {
      throw new ErroMunicipio(`Recurso ${numero} não existe. Recursos atuais: ` +
        `${this.recursos.map((x) => x.numero).join(", ")}.`, 404);
    }
    return r;
  }

  remover(numero) {
    const r = this.recurso(numero);
    this.recursos = this.recursos.filter((x) => x !== r);
    return r;
  }

  toJSON() {
    const { pontos: _, ...resumo } = this.resultado;
    return { id: this.id, criadaEm: this.criadaEm, municipio: this.municipio, tipo: this.tipo,
      estrategia: this.estrategia, recursos: this.recursos, resultado: resumo };
  }
}

/** Guarda as alocacoes em memoria (as mais antigas saem quando passa do limite). */
export class RepositorioAlocacoes {
  constructor(limite = 100) {
    this.limite = limite;
    this.alocacoes = new Map();
  }

  adicionar(alocacao) {
    this.alocacoes.set(alocacao.id, alocacao);
    while (this.alocacoes.size > this.limite) {
      this.alocacoes.delete(this.alocacoes.keys().next().value);
    }
    return alocacao;
  }

  obter(id) {
    const a = this.alocacoes.get(id);
    if (!a) throw new ErroMunicipio("Alocação não encontrada (o servidor pode ter reiniciado).", 404);
    return a;
  }
}

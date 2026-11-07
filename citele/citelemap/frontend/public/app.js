// Citelemap - frontend 2D (Google Maps)

const CORES = { ambulancia: "#d92d20", policia: "#1a5fd0" };
// Cores das rotas de realocacao (uma por recurso, em ciclo)
const CORES_ROTAS = ["#6d28d9", "#047857", "#c2410c", "#be185d", "#ca8a04", "#0891b2",
  "#334155", "#65a30d"];
const BRASIL = { center: { lat: -14.2, lng: -51.9 }, zoom: 4 };

const $ = (id) => document.getElementById(id);
const estado = {
  mapa: null,
  libs: null,
  contorno: null,
  recursos: [], // marcadores e circulos desenhados
  rotas: [], // linhas das rotas de realocacao
  alocacao: null, // alocacao atual criada pelo backend (id e recursos)
};

// ---------- API ----------

async function api(caminho, opcoes) {
  const resposta = await fetch(`/api${caminho}`, opcoes);
  const corpo = await resposta.json().catch(() => ({}));
  if (!resposta.ok) {
    const erro = new Error(corpo.erro ?? `Erro ${resposta.status}`);
    erro.sugestoes = corpo.sugestoes ?? [];
    throw erro;
  }
  return corpo;
}

// ---------- Mensagens ----------

function mensagem(id, texto, tipo = "", sugestoes = []) {
  const el = $(id);
  el.className = `mensagem ${tipo}`;
  el.textContent = texto;
  if (sugestoes.length) {
    el.append(" Você quis dizer: ");
    sugestoes.forEach((nome, i) => {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = nome;
      b.addEventListener("click", () => {
        $("cidade").value = nome;
        $("form-local").requestSubmit();
      });
      el.append(b, i < sugestoes.length - 1 ? ", " : "?");
    });
  }
}

// ---------- Google Maps ----------

function carregarGoogleMaps(chave) {
  return new Promise((resolve, reject) => {
    window.__citeleMapsPronto = resolve;
    window.gm_authFailure = () => reject(new Error("Chave do Google Maps inválida ou sem permissão."));
    const s = document.createElement("script");
    s.src = "https://maps.googleapis.com/maps/api/js?" + new URLSearchParams({
      key: chave, v: "weekly", loading: "async", libraries: "marker",
      language: "pt-BR", region: "BR", callback: "__citeleMapsPronto",
    });
    s.async = true;
    s.onerror = () => reject(new Error("Não foi possível carregar o Google Maps."));
    document.head.append(s);
  });
}

function avisoMapa(texto) {
  $("aviso-mapa").textContent = texto;
  $("aviso-mapa").hidden = false;
}

async function iniciarMapa(config) {
  if (!config.googleMapsApiKey) {
    avisoMapa("Defina GOOGLE_MAPS_API_KEY no arquivo .env para exibir o mapa.");
    return;
  }
  try {
    await carregarGoogleMaps(config.googleMapsApiKey);
    const [{ Map, Polygon, Circle }, { AdvancedMarkerElement }, { LatLngBounds }] =
      await Promise.all([
        google.maps.importLibrary("maps"),
        google.maps.importLibrary("marker"),
        google.maps.importLibrary("core"),
      ]);
    estado.libs = { Polygon, Circle, AdvancedMarkerElement, LatLngBounds };
    estado.mapa = new Map($("mapa"), {
      ...BRASIL, mapId: config.googleMapsMapId, streetViewControl: false,
    });
  } catch (e) {
    avisoMapa(e.message);
  }
}

const paraLatLng = (coordenadas) => coordenadas.map(([lng, lat]) => ({ lat, lng }));

function focarMunicipio(m) {
  if (!estado.mapa) return;
  const { Polygon, LatLngBounds } = estado.libs;
  estado.contorno?.setMap(null);
  estado.contorno = new Polygon({
    map: estado.mapa, paths: paraLatLng(m.coordenadas), clickable: false,
    strokeColor: "#1d2330", strokeWeight: 2, fillColor: "#1d2330", fillOpacity: 0.05,
  });
  const [oeste, sul, leste, norte] = m.bbox;
  estado.mapa.fitBounds(new LatLngBounds({ lat: sul, lng: oeste }, { lat: norte, lng: leste }), 24);
}

function limparRecursos() {
  for (const { marcador, circulo } of estado.recursos) {
    marcador.map = null;
    circulo.setMap(null);
  }
  estado.recursos = [];
}

// Icones dos veiculos: emojis do Twemoji (CC-BY 4.0), em icones/
const ICONES = { ambulancia: "icones/ambulancia.svg", policia: "icones/policia.svg" };

/** Marcador: selo branco com o veiculo, numero na cor do tipo e ponta embaixo. */
function iconeRecurso(tipo, numero, cor) {
  const el = document.createElement("div");
  el.className = "marcador-recurso";
  el.style.setProperty("--cor", cor);
  const img = document.createElement("img");
  img.src = ICONES[tipo] ?? ICONES.ambulancia;
  img.alt = "";
  const n = document.createElement("span");
  n.className = "numero";
  n.textContent = numero;
  el.append(img, n);
  return el;
}

/** recursos: objetos do backend {numero, lat, lng, populacao?, tempo_medio_min?...} */
function desenharRecursos(recursos, raio, tipo) {
  if (!estado.mapa) return;
  const { Circle, AdvancedMarkerElement } = estado.libs;
  const cor = CORES[tipo] ?? "#444";
  limparRecursos();
  for (const p of recursos) {
    const pin = iconeRecurso(tipo, p.numero, cor);
    const pessoas = p.populacao != null ? ` · ${fmt(p.populacao, 0)} pessoas`
      : p.tempo_medio_min != null ? ` · ${fmt(p.tempo_medio_min, 1)} min em média, ` +
        `${fmt(p.area_atendida_pct, 1)}% da área` : "";
    const marcador = new AdvancedMarkerElement({
      map: estado.mapa, position: { lat: p.lat, lng: p.lng }, content: pin, zIndex: 10,
      title: `Recurso ${p.numero}${pessoas} (${p.lat}, ${p.lng})`,
    });
    const circulo = new Circle({
      map: estado.mapa, center: { lat: p.lat, lng: p.lng }, radius: raio, clickable: false,
      strokeColor: cor, strokeOpacity: 0.8, strokeWeight: 1.5, fillColor: cor, fillOpacity: 0.12,
    });
    estado.recursos.push({ marcador, circulo });
  }
}

function limparRotas() {
  for (const linha of estado.rotas) linha.setMap(null);
  estado.rotas = [];
  $("movimentos").hidden = true;
}

/** Linha de cada recurso da posicao antiga ate a nova, pelo caminho recebido. */
function desenharRotas(movimentos) {
  limparRotas();
  if (!estado.mapa) return;
  const inicio = { path: google.maps.SymbolPath.CIRCLE, scale: 4, fillOpacity: 1, strokeWeight: 2 };
  const seta = { path: google.maps.SymbolPath.FORWARD_CLOSED_ARROW, scale: 3, fillOpacity: 1 };
  movimentos.forEach((m, i) => {
    const cor = CORES_ROTAS[i % CORES_ROTAS.length];
    estado.rotas.push(new google.maps.Polyline({
      map: estado.mapa, path: m.caminho.map(([lat, lng]) => ({ lat, lng })), zIndex: 5,
      strokeColor: cor, strokeOpacity: 0.9, strokeWeight: 4,
      icons: [{ icon: { ...inicio, fillColor: "#fff", strokeColor: cor }, offset: "0%" },
        { icon: { ...seta, fillColor: cor, strokeColor: cor }, offset: "100%" }],
    }));
  });
}

function listarMovimentos(movimentos) {
  const lista = $("movimentos");
  lista.replaceChildren(...movimentos.map((m, i) => {
    const li = document.createElement("li");
    const cor = document.createElement("span");
    cor.className = "cor";
    cor.style.background = CORES_ROTAS[i % CORES_ROTAS.length];
    const valor = document.createElement("span");
    valor.className = "valor";
    valor.textContent = m.distancia_m < 1
      ? "fica no lugar" : `${fmt(m.distancia_m / 1000, 1)} km · ${fmt(m.tempo_s / 60, 1)} min`;
    li.append(cor, `Recurso ${m.numero}`, valor);
    return li;
  }));
  lista.hidden = false;
}

// ---------- Secao 1 ----------

async function buscarMunicipio() {
  const params = new URLSearchParams({ cidade: $("cidade").value, estado: $("estado").value });
  return api(`/municipio?${params}`);
}

async function aoLocalizar(evento) {
  evento.preventDefault();
  const botao = evento.submitter ?? evento.target.querySelector("button");
  botao.disabled = true;
  mensagem("msg-local", "Buscando…");
  try {
    const m = await buscarMunicipio();
    $("cidade").value = m.nome;
    focarMunicipio(m);
    limparRecursos();
    limparRotas();
    definirAlocacao(null);
    $("resultado").hidden = true;
    const ilhas = m.partes > 1 ? ` · ${m.partes} partes (usando a maior)` : "";
    mensagem("msg-local", `${m.nome}/${m.uf} · IBGE ${m.cd_mun} · ${fmt(m.area_km2)} km²${ilhas}`, "ok");
  } catch (e) {
    mensagem("msg-local", e.message, "erro", e.sugestoes);
  } finally {
    botao.disabled = false;
  }
}

// ---------- Secao 2 ----------

const fmt = (n, casas = 1) => Number(n).toLocaleString("pt-BR", { maximumFractionDigits: casas });

function mostrarResultado(r) {
  const pop = r.resultado.populacao;
  const tempo = r.resultado.tempo;
  const linhas = [
    ["Município", `${r.municipio.nome}/${r.municipio.uf}`],
    ["Recursos", r.alocacao.recursos.length],
    ["Raio", `${fmt(r.resultado.raio_m / 1000, 2)} km`],
  ];
  if (tempo) {
    linhas.push(
      ["Tempo médio", `${fmt(tempo.medio_min, 1)} min`],
      ["Tempo mediano", `${fmt(tempo.mediano_min, 1)} min`],
      ["90% chegam em", `${fmt(tempo.p90_min, 1)} min`],
      ["Tempo máximo", `${fmt(tempo.maximo_min, 1)} min`],
      ["Área", `${fmt(r.resultado.area_poligono_km2)} km²`],
    );
  } else if (pop) {
    linhas.push(
      ["Áreas", `${r.areas.quantidade} (${r.areas.unidade})`],
      ["População", fmt(pop.total, 0)],
      ["Alvo por recurso", `${fmt(pop.alvo_por_recurso, 0)} pessoas`],
      ["Por recurso", `${fmt(pop.minimo, 0)} a ${fmt(pop.maximo, 0)}`],
      ["Variação (CV)", `${fmt(pop.coeficiente_variacao * 100, 1)}%`],
      ["População coberta", `${fmt(r.resultado.cobertura * 100, 1)}%`],
    );
  } else {
    linhas.push(
      ["Área", `${fmt(r.resultado.area_poligono_km2)} km²`],
      ["Cobertura", `${fmt(r.resultado.cobertura * 100, 1)}%`],
      ["Vértices enviados", r.vertices_enviados],
    );
  }
  const dl = $("resultado");
  dl.replaceChildren(...linhas.filter(([, v]) => v != null).flatMap(([k, v]) => {
    const dt = document.createElement("dt");
    const dd = document.createElement("dd");
    dt.textContent = k;
    dd.textContent = v;
    return [dt, dd];
  }));
  dl.hidden = false;
}

async function aoCalcular(evento) {
  evento.preventDefault();
  if (!$("cidade").value.trim() || !$("estado").value) {
    mensagem("msg-recursos", "Preencha a cidade e o estado na seção 1.", "erro");
    return;
  }
  const botao = evento.submitter ?? evento.target.querySelector("button");
  botao.disabled = true;
  mensagem("msg-recursos", "Calculando… (pode levar alguns segundos)");
  try {
    const corpo = {
      cidade: $("cidade").value, estado: $("estado").value,
      recursos: Number($("recursos").value), tipo: $("tipo").value, estrategia: $("estrategia").value,
    };
    const [r, m] = await Promise.all([
      api("/calcular", { method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify(corpo) }),
      buscarMunicipio(),
    ]);
    focarMunicipio(m);
    limparRotas();
    desenharRecursos(r.alocacao.recursos, r.resultado.raio_m, r.tipo);
    mostrarResultado(r);
    definirAlocacao(r.alocacao);
    mensagem("msg-recursos", "Alocação calculada.", "ok");
    mensagem("msg-operacoes", "");
  } catch (e) {
    mensagem("msg-recursos", e.message, "erro", e.sugestoes);
  } finally {
    botao.disabled = false;
  }
}

// ---------- Secao 4: operacoes nos recursos ----------

function definirAlocacao(alocacao) {
  estado.alocacao = alocacao;
  $("operacoes").disabled = !alocacao;
  $("recurso-apagar").value = "";
  if (!alocacao) {
    $("recursos-atuais").textContent = "Calcule uma alocação na seção 2 para operar nos recursos.";
    return;
  }
  const numeros = alocacao.recursos.map((r) => r.numero);
  $("recursos-atuais").textContent = `Recursos atuais: ${numeros.join(", ")}`;
  $("recurso-apagar").max = Math.max(...numeros);
}

async function aoApagar(evento) {
  evento.preventDefault();
  const numero = Number($("recurso-apagar").value);
  const alocacao = estado.alocacao;
  if (!alocacao) return;
  if (!alocacao.recursos.some((r) => r.numero === numero)) {
    mensagem("msg-operacoes", `Informe um dos recursos atuais: ` +
      `${alocacao.recursos.map((r) => r.numero).join(", ")}.`, "erro");
    return;
  }
  $("operacoes").disabled = true;
  mensagem("msg-operacoes", `Apagando o recurso ${numero} e recalculando… (pode levar alguns segundos)`);
  try {
    const params = new URLSearchParams({ criterio: $("criterio").value });
    const r = await api(`/alocacoes/${alocacao.id}/recursos/${numero}?${params}`, { method: "DELETE" });
    desenharRecursos(r.alocacao.recursos, r.alocacao.resultado.raio_m, r.alocacao.tipo);
    desenharRotas(r.movimentos);
    listarMovimentos(r.movimentos);
    mostrarResultado({ municipio: r.alocacao.municipio, resultado: r.alocacao.resultado,
      areas: r.areas, alocacao: r.alocacao });
    definirAlocacao(r.alocacao);
    const via = r.rotas.malha_viaria ? "pelas ruas" : "em linha reta (sem malha viária)";
    mensagem("msg-operacoes", `Recurso ${numero} apagado. Rotas ${via}; o último chega em ` +
      `${fmt(r.rotas.tempo_maximo_s / 60, 1)} min; soma dos deslocamentos ` +
      `${fmt(r.rotas.tempo_total_s / 60, 1)} min.`, "ok");
  } catch (e) {
    mensagem("msg-operacoes", e.message, "erro");
    $("operacoes").disabled = false;
  }
}

// ---------- Inicio ----------

function preencherSelect(id, itens, valor, texto) {
  $(id).append(...itens.map((i) => new Option(texto(i), valor(i))));
}

async function iniciar() {
  let config;
  try {
    config = await api("/config");
  } catch (e) {
    mensagem("msg-local", `Backend indisponível: ${e.message}`, "erro");
    return;
  }
  preencherSelect("estado", config.ufs, (u) => u.sigla, (u) => `${u.sigla} – ${u.nome}`);
  preencherSelect("tipo", config.tiposRecurso, (t) => t.id, (t) => t.nome);
  preencherSelect("estrategia", config.estrategias, (e) => e.id, (e) => e.nome);
  preencherSelect("criterio", config.criteriosRealocacao, (c) => c.id, (c) => c.nome);
  $("recursos").max = config.maxRecursos;

  $("form-local").addEventListener("submit", aoLocalizar);
  $("form-recursos").addEventListener("submit", aoCalcular);
  $("form-apagar").addEventListener("submit", aoApagar);
  await iniciarMapa(config);
}

iniciar();

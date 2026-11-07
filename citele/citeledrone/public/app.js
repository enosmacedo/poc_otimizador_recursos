// Citeledrone - visualizacao 3D do enxame simulado no ARGoS (three.js)
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const $ = (id) => document.getElementById(id);
const fmt = (n, casas = 1) => Number(n).toLocaleString("pt-BR", { maximumFractionDigits: casas });
const COR_DRONE = 0xd92d20;
const COR_COBERTURA = 0x1a5fd0;

// ARGoS usa z para cima; o three.js usa y para cima: (x, y, z) -> (x, z, -y)
const paraCena = (x, y, z) => new THREE.Vector3(x, z, -y);

// ---------- Cena ----------

const recipiente = $("cena");
const renderizador = new THREE.WebGLRenderer({ antialias: true });
renderizador.setPixelRatio(window.devicePixelRatio);
recipiente.append(renderizador.domElement);
const cena = new THREE.Scene();
cena.background = new THREE.Color(0xdfe8ef);
cena.fog = new THREE.Fog(0xdfe8ef, 800, 3000);
const camera = new THREE.PerspectiveCamera(45, 1, 0.5, 10000);
camera.position.set(220, 220, 260);
const controles = new OrbitControls(camera, renderizador.domElement);
controles.enableDamping = true;
controles.maxPolarAngle = Math.PI / 2 - 0.02;
cena.add(new THREE.HemisphereLight(0xffffff, 0x8899aa, 1.6));
const sol = new THREE.DirectionalLight(0xffffff, 1.4);
sol.position.set(200, 400, 150);
cena.add(sol);

let mundo = null; // grupo com a simulacao atual
const estado = { drones: [], duracao: 0, tempo: 0, tocando: false, ultimo: 0, enxame: null };

function redimensionar() {
  const { clientWidth: l, clientHeight: a } = recipiente;
  renderizador.setSize(l, a);
  camera.aspect = l / a;
  camera.updateProjectionMatrix();
}
new ResizeObserver(redimensionar).observe(recipiente);

// ---------- Objetos ----------

function rotulo(texto, tamanho) {
  const tela = document.createElement("canvas");
  tela.width = tela.height = 128;
  const c = tela.getContext("2d");
  c.fillStyle = "#ffffff";
  c.beginPath(); c.arc(64, 64, 54, 0, Math.PI * 2); c.fill();
  c.lineWidth = 10; c.strokeStyle = "#d92d20"; c.stroke();
  c.fillStyle = "#1d2330";
  c.font = `bold ${texto.length > 2 ? 46 : 58}px system-ui, sans-serif`;
  c.textAlign = "center"; c.textBaseline = "middle";
  c.fillText(texto, 64, 68);
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(tela), depthTest: false }));
  sprite.scale.set(tamanho, tamanho, 1);
  sprite.renderOrder = 10;
  return sprite;
}

/** Quadricoptero estilizado; escala para ficar visivel na area. */
function modeloDrone(escala) {
  const g = new THREE.Group();
  const corpo = new THREE.MeshStandardMaterial({ color: COR_DRONE, roughness: 0.5 });
  const escuro = new THREE.MeshStandardMaterial({ color: 0x1d2330, roughness: 0.6 });
  g.add(new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.18, 0.5), corpo));
  for (const ang of [45, 135, 225, 315]) {
    const r = THREE.MathUtils.degToRad(ang);
    const braco = new THREE.Mesh(new THREE.BoxGeometry(0.7, 0.05, 0.08), escuro);
    braco.position.set(Math.cos(r) * 0.35, 0, Math.sin(r) * 0.35);
    braco.rotation.y = -r;
    g.add(braco);
    const helice = new THREE.Mesh(new THREE.CylinderGeometry(0.22, 0.22, 0.03, 20), escuro);
    helice.position.set(Math.cos(r) * 0.68, 0.06, Math.sin(r) * 0.68);
    g.add(helice);
  }
  g.scale.setScalar(escala);
  return g;
}

/** manterCamera: no reposicionamento, a camera fica onde o usuario deixou. */
function montarMundo(r, manterCamera = false) {
  if (mundo) { cena.remove(mundo); mundo.traverse((o) => { o.geometry?.dispose(); o.material?.dispose?.(); }); }
  mundo = new THREE.Group();
  cena.add(mundo);
  const { largura_m: L, comprimento_m: C, altitude_m: H } = r.parametros;
  const maior = Math.max(L, C);
  // Drones de verdade tem ~0,5 m: ampliados para serem vistos na area inteira
  const escala = Math.max(1, maior / 70);
  $("escala").textContent = escala > 1.05 ? `drones ampliados ${fmt(escala, 0)}× para visualização` : "";

  // Chao em volta e area de interesse (com grade de 10 m)
  cena.fog = new THREE.Fog(0xdfe8ef, maior * 1.5, maior * 4);
  const chao = new THREE.Mesh(new THREE.PlaneGeometry(maior * 8, maior * 8),
    new THREE.MeshStandardMaterial({ color: 0xc9d6c0, roughness: 1 }));
  chao.rotation.x = -Math.PI / 2;
  chao.position.y = -0.05;
  mundo.add(chao);
  const area = new THREE.Mesh(new THREE.PlaneGeometry(L, C), new THREE.MeshStandardMaterial({ color: 0xa8c79a, roughness: 1 }));
  area.rotation.x = -Math.PI / 2;
  mundo.add(area);
  const passoGrade = maior > 600 ? 50 : 10;
  const linhas = [];
  for (let x = -L / 2; x <= L / 2 + 1e-6; x += passoGrade) linhas.push(x, 0.02, -C / 2, x, 0.02, C / 2);
  for (let y = -C / 2; y <= C / 2 + 1e-6; y += passoGrade) linhas.push(-L / 2, 0.02, y, L / 2, 0.02, y);
  const geoGrade = new THREE.BufferGeometry();
  geoGrade.setAttribute("position", new THREE.Float32BufferAttribute(linhas, 3));
  mundo.add(new THREE.LineSegments(geoGrade, new THREE.LineBasicMaterial({ color: 0x7f9c72, transparent: true, opacity: 0.5 })));
  const borda = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints([
    new THREE.Vector3(-L / 2, 0.05, -C / 2), new THREE.Vector3(L / 2, 0.05, -C / 2),
    new THREE.Vector3(L / 2, 0.05, C / 2), new THREE.Vector3(-L / 2, 0.05, C / 2)]),
  new THREE.LineBasicMaterial({ color: 0x1d2330 }));
  mundo.add(borda);

  // Base de decolagem
  const xs = r.simulacao.base.map((b) => b.x), ys = r.simulacao.base.map((b) => b.y);
  const larguraBase = Math.max(...xs) - Math.min(...xs) + 3, compBase = Math.max(...ys) - Math.min(...ys) + 3;
  const base = new THREE.Mesh(new THREE.PlaneGeometry(larguraBase, compBase),
    new THREE.MeshStandardMaterial({ color: 0x6b7280, roughness: 0.9 }));
  base.rotation.x = -Math.PI / 2;
  base.position.copy(paraCena((Math.max(...xs) + Math.min(...xs)) / 2, (Math.max(...ys) + Math.min(...ys)) / 2, 0.03));
  mundo.add(base);

  // Drones, area coberta (circulo no chao), linha vertical e numero
  const raio = r.calculo.raio_cobertura_m;
  estado.drones = r.simulacao.drones.map(({ numero, trajetoria: pontos, alvo }) => {
      const modelo = modeloDrone(escala);
      const cobertura = new THREE.Mesh(new THREE.CircleGeometry(raio, 64),
        new THREE.MeshBasicMaterial({ color: COR_COBERTURA, transparent: true, opacity: 0.0, depthWrite: false }));
      cobertura.rotation.x = -Math.PI / 2;
      const contorno = new THREE.LineLoop(
        new THREE.BufferGeometry().setFromPoints(Array.from({ length: 65 }, (_, k) => {
          const a = (k / 64) * Math.PI * 2;
          return new THREE.Vector3(Math.cos(a) * raio, 0, Math.sin(a) * raio);
        })),
        new THREE.LineBasicMaterial({ color: COR_COBERTURA, transparent: true, opacity: 0 }));
      const prumo = new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), new THREE.Vector3()]),
        new THREE.LineDashedMaterial({ color: 0x1d2330, dashSize: 1.5 * escala, gapSize: 1 * escala, transparent: true, opacity: 0.6 }));
      const etiqueta = rotulo(String(numero), 1.6 * escala);
      mundo.add(modelo, cobertura, contorno, prumo, etiqueta);
      return { numero, pontos, modelo, cobertura, contorno, prumo, numero3d: etiqueta, alvo };
    });

  estado.duracao = Math.max(...estado.drones.map((d) => d.pontos.at(-1)[0]));
  $("tempo").max = estado.duracao;
  if (manterCamera) return;
  // Camera enquadra a area
  controles.target.set(0, H * 0.25, -C * 0.05);
  camera.position.set(maior * 0.55, Math.max(H * 2.5, maior * 0.6), maior * 0.85);
  camera.far = maior * 20;
  camera.updateProjectionMatrix();
}

// ---------- Reproducao ----------

function posicaoNoTempo(pontos, t) {
  // Interpolacao linear entre as amostras [t, x, y, z] (a cada 0,2 s)
  if (t <= pontos[0][0]) return pontos[0];
  const i = pontos.findIndex((p) => p[0] >= t);
  if (i < 0) return pontos.at(-1);
  const [t0, x0, y0, z0] = pontos[i - 1], [t1, x1, y1, z1] = pontos[i];
  const f = (t - t0) / (t1 - t0);
  return [t, x0 + (x1 - x0) * f, y0 + (y1 - y0) * f, z0 + (z1 - z0) * f];
}

function atualizarDrones(t) {
  for (const d of estado.drones) {
    const [, x, y, z] = posicaoNoTempo(d.pontos, t);
    const p = paraCena(x, y, z);
    d.modelo.position.copy(p);
    d.numero3d.position.set(p.x, p.y + d.modelo.scale.x * 1.2, p.z);
    d.cobertura.position.set(p.x, 0.08, p.z);
    d.contorno.position.set(p.x, 0.1, p.z);
    d.prumo.geometry.setFromPoints([p, new THREE.Vector3(p.x, 0.1, p.z)]);
    d.prumo.computeLineDistances();
    // A area coberta so aparece nos ultimos metros ate o alvo (durante a
    // decolagem os circulos se sobreporiam na base e poluiriam a cena)
    const distAlvo = Math.hypot(x - d.alvo.x, y - d.alvo.y, z - d.alvo.z);
    const chegou = Math.max(0, 1 - distAlvo / 8);
    d.cobertura.material.opacity = 0.22 * chegou;
    d.contorno.material.opacity = 0.9 * chegou;
  }
  $("tempo").value = t;
  $("relogio").textContent = `${fmt(t, 1)} s`;
}

function quadro(agora) {
  requestAnimationFrame(quadro);
  if (estado.tocando && estado.drones.length) {
    const dt = (agora - estado.ultimo) / 1000;
    estado.tempo = Math.min(estado.duracao, estado.tempo + dt * Number($("ritmo").value));
    atualizarDrones(estado.tempo);
    if (estado.tempo >= estado.duracao) definirTocando(false);
  }
  estado.ultimo = agora;
  controles.update();
  renderizador.render(cena, camera);
}

function definirTocando(sim) {
  estado.tocando = sim;
  $("tocar").textContent = sim ? "❚❚" : "▶";
  $("tocar").setAttribute("aria-label", sim ? "Pausar" : "Reproduzir");
}

// ---------- Simulacao ----------

async function api(caminho, opcoes) {
  const r = await fetch(`/api${caminho}`, opcoes);
  const corpo = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof corpo.detail === "string" ? corpo.detail : `Erro ${r.status}`);
  return corpo;
}

function mensagem(texto, tipo = "") {
  $("msg").className = `mensagem ${tipo}`;
  $("msg").textContent = texto;
}

function mostrarResultado(r) {
  const c = r.calculo, s = r.simulacao;
  const linhas = [
    ["Drones", c.drones],
    ["Área", `${fmt(c.area_m2 / 10000, 2)} ha`],
    ["Raio de cobertura", `${fmt(c.raio_cobertura_m, 1)} m`],
    ["Abertura do sensor", `${fmt(c.abertura_sensor_graus, 0)}°`],
    ["Cobertura da área", `${fmt(c.cobertura * 100, 1)}%`],
    ["Formação completa", s.tempo_formacao_s == null ? "não concluída" : `${fmt(s.tempo_formacao_s, 1)} s`],
  ];
  $("resultado").replaceChildren(...linhas.flatMap(([k, v]) => {
    const dt = document.createElement("dt"), dd = document.createElement("dd");
    dt.textContent = k; dd.textContent = v;
    return [dt, dd];
  }));
  $("resultado").hidden = false;
}

async function simular(evento) {
  evento.preventDefault();
  const botao = document.querySelector("button[form=form-simular]");
  botao.disabled = true;
  mensagem("Calculando posições no Citeleat e simulando no ARGoS…");
  try {
    const corpo = {
      drones: Number($("drones").value), estrategia: $("estrategia").value,
      largura_m: Number($("largura").value), comprimento_m: Number($("comprimento").value),
      altitude_m: Number($("altitude").value), velocidade_ms: Number($("velocidade").value),
    };
    const r = await api("/simular", { method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify(corpo) });
    montarMundo(r);
    estado.tempo = 0;
    atualizarDrones(0);
    definirTocando(true);
    $("controles").hidden = false;
    $("aviso").hidden = true;
    mostrarResultado(r);
    definirEnxame(r.enxame);
    $("movimentos").hidden = true;
    $("msg-operacoes").textContent = "";
    mensagem(`Simulação concluída: ${r.calculo.drones} drones a ${fmt(r.parametros.altitude_m, 0)} m.`, "ok");
  } catch (e) {
    mensagem(e.message, "erro");
  } finally {
    botao.disabled = false;
  }
}

// ---------- Secao 3: operacoes nos drones ----------

function definirEnxame(enxame) {
  estado.enxame = enxame;
  $("operacoes").disabled = !enxame;
  $("drone-apagar").value = "";
  const numeros = enxame.drones.map((d) => d.numero);
  $("drones-atuais").textContent = `Drones atuais: ${numeros.join(", ")}`;
  $("drone-apagar").max = Math.max(...numeros);
}

function listarMovimentos(drones) {
  const itens = [...drones].sort((a, b) => a.numero - b.numero).map((d) => {
    const li = document.createElement("li");
    const valor = document.createElement("span");
    valor.textContent = d.distancia_m < 0.5 ? "fica no lugar"
      : `${fmt(d.distancia_m, 1)} m · chega em ${fmt(d.chegada_s, 1)} s`;
    li.append(`Drone ${d.numero}`, valor);
    return li;
  });
  $("movimentos").replaceChildren(...itens);
  $("movimentos").hidden = false;
}

async function apagar(evento) {
  evento.preventDefault();
  const enxame = estado.enxame;
  const numero = Number($("drone-apagar").value);
  if (!enxame) return;
  if (!enxame.drones.some((d) => d.numero === numero)) {
    $("msg-operacoes").className = "mensagem erro";
    $("msg-operacoes").textContent = `Informe um dos drones atuais: ${enxame.drones.map((d) => d.numero).join(", ")}.`;
    return;
  }
  $("operacoes").disabled = true;
  $("msg-operacoes").className = "mensagem";
  $("msg-operacoes").textContent = `Apagando o drone ${numero} e reposicionando os demais…`;
  try {
    const r = await api(`/enxames/${enxame.id}/drones/${numero}/remover`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ estrategia: $("estrategia").value }),
    });
    montarMundo(r, true);
    estado.tempo = 0;
    atualizarDrones(0);
    definirTocando(true);
    mostrarResultado(r);
    definirEnxame(r.enxame);
    listarMovimentos(r.simulacao.drones);
    $("msg-operacoes").className = "mensagem ok";
    $("msg-operacoes").textContent = `Drone ${numero} apagado. Nova formação com ` +
      `${r.enxame.drones.length} drones completa em ${fmt(r.simulacao.tempo_formacao_s, 1)} s.`;
  } catch (e) {
    $("msg-operacoes").className = "mensagem erro";
    $("msg-operacoes").textContent = e.message;
    $("operacoes").disabled = false;
  }
}

async function iniciar() {
  redimensionar();
  requestAnimationFrame(quadro);
  $("form-simular").addEventListener("submit", simular);
  $("form-apagar").addEventListener("submit", apagar);
  $("tocar").addEventListener("click", () => {
    if (estado.tempo >= estado.duracao) estado.tempo = 0;
    definirTocando(!estado.tocando);
  });
  $("tempo").addEventListener("input", () => {
    definirTocando(false);
    estado.tempo = Number($("tempo").value);
    atualizarDrones(estado.tempo);
  });
  try {
    const config = await api("/config");
    $("estrategia").append(...config.estrategias.map((e) => new Option(e.nome, e.id)));
  } catch (e) {
    mensagem(`Citeleat indisponível: ${e.message}`, "erro");
  }
}

iniciar();

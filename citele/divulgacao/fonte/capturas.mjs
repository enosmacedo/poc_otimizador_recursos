// Captura telas do Citelemap (http://localhost:8080) para o material de divulgacao.
// Uso: node capturas.mjs [pasta_saida]   (o sistema precisa estar rodando no Docker)
import { spawn } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

const CHROME = ["C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"].find(existsSync);
const BASE = "http://localhost:8080/";
const SAIDA = process.argv[2] ?? "capturas";
mkdirSync(SAIDA, { recursive: true });
const espera = (ms) => new Promise((r) => setTimeout(r, ms));

const proc = spawn(CHROME, ["--headless=new", "--remote-debugging-port=9555",
  `--user-data-dir=${mkdtempSync(path.join(tmpdir(), "cap-"))}`, "--hide-scrollbars", "about:blank"],
{ stdio: "ignore" });
let alvos;
for (let i = 0; i < 60 && !alvos; i++) {
  try { alvos = await (await fetch("http://127.0.0.1:9555/json")).json(); } catch { await espera(250); }
}
const ws = new WebSocket(alvos.find((t) => t.type === "page").webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener("open", r));
let id = 0;
const pend = new Map();
ws.addEventListener("message", (ev) => {
  const m = JSON.parse(ev.data);
  if (m.id && pend.has(m.id)) { pend.get(m.id)(m.result ?? m); pend.delete(m.id); }
});
const cmd = (method, params = {}) => new Promise((r) => { const i = ++id; pend.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const js = async (expr) => (await cmd("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true })).result?.value;
const valor = (campo, v) => js(`document.getElementById('${campo}').value = ${JSON.stringify(v)}; 1`);
const enviar = (form) => js(`document.getElementById('${form}').requestSubmit(); 1`);
// Espera a mensagem de status ficar verde (ok) ou vermelha (erro)
async function aguardar(msg, limiteMs = 90000) {
  for (let t = 0; t < limiteMs; t += 500) {
    await espera(500);
    const classe = await js(`document.getElementById('${msg}').className`);
    if (/\b(ok|erro)\b/.test(classe)) {
      await espera(2500); // tiles e marcadores do mapa
      return js(`document.getElementById('${msg}').textContent`);
    }
  }
  throw new Error(`tempo esgotado esperando ${msg}`);
}
async function foto(nome) {
  const r = await cmd("Page.captureScreenshot", { format: "png" });
  writeFileSync(path.join(SAIDA, `${nome}.png`), Buffer.from(r.data, "base64"));
  console.log("capturada:", nome);
}
async function abrir() {
  await cmd("Page.navigate", { url: BASE });
  await espera(4000);
}
async function cidade(nome, uf) {
  await valor("cidade", nome);
  await valor("estado", uf);
  await js("document.getElementById('msg-local').className = 'mensagem'; 1");
  await enviar("form-local");
  await aguardar("msg-local");
}
async function calcular(recursos, tipo, estrategia) {
  await valor("recursos", String(recursos));
  await valor("tipo", tipo);
  await valor("estrategia", estrategia);
  await js("document.getElementById('msg-recursos').className = 'mensagem'; 1");
  await enviar("form-recursos");
  console.log("  ", await aguardar("msg-recursos"));
}

await cmd("Runtime.enable");
await cmd("Emulation.setDeviceMetricsOverride", { width: 1600, height: 900, deviceScaleFactor: 2, mobile: false });

await abrir();
await foto("00-inicio");
await cidade("Natal", "RN");
await foto("01-cidade");
await calcular(8, "ambulancia", "linear-area-cidade");
await foto("02-area");
await calcular(10, "ambulancia", "linear-densidade-bairros");
await js("document.querySelector('.painel').scrollTop = 300; 1");
await foto("03-densidade");
await js("document.querySelector('.painel').scrollTop = 0; 1");
await calcular(8, "policia", "linear-tempo-deslocamento");
await js("document.querySelector('.painel').scrollTop = 300; 1");
await foto("04-tempo");

await abrir();
await cidade("Natal", "RN");
await calcular(6, "ambulancia", "linear-tempo-deslocamento");
await valor("recurso-apagar", "3");
await valor("criterio", "maximo");
await js("document.getElementById('msg-operacoes').className = 'mensagem'; 1");
await enviar("form-apagar");
console.log("  ", await aguardar("msg-operacoes"));
await js("document.querySelector('.painel').scrollTop = 99999; 1");
await foto("05-realocacao");

ws.close();
proc.kill();
process.exit(0);

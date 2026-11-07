// Renderiza uma pagina (HTML local ou URL) com o Chrome headless em PNG ou PDF.
// Uso: node render.mjs <url-ou-arquivo> <saida.png|saida.pdf> [largura] [altura] [escala] [espera_ms]
// Requer Node 22+ (WebSocket global) e o Google Chrome instalado.
import { spawn } from "node:child_process";
import { existsSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";

const CHROMES = [
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
  "/usr/bin/google-chrome", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
];
const [alvo, saida, largura = "1600", altura = "900", escala = "1", esperaMs = "800"] = process.argv.slice(2);
if (!alvo || !saida) {
  console.error("Uso: node render.mjs <url-ou-arquivo> <saida.png|pdf> [largura] [altura] [escala] [espera_ms]");
  process.exit(1);
}
const url = /^[a-z]+:\/\//i.test(alvo) ? alvo : pathToFileURL(path.resolve(alvo)).href;
const chrome = CHROMES.find(existsSync);
const perfil = mkdtempSync(path.join(tmpdir(), "render-"));
const porta = 9400 + Math.floor(Math.random() * 400);
const proc = spawn(chrome, ["--headless=new", `--remote-debugging-port=${porta}`, `--user-data-dir=${perfil}`,
  "--hide-scrollbars", "--allow-file-access-from-files", "about:blank"], { stdio: "ignore" });
const espera = (ms) => new Promise((r) => setTimeout(r, ms));

let alvos;
for (let i = 0; i < 60 && !alvos; i++) {
  try { alvos = await (await fetch(`http://127.0.0.1:${porta}/json`)).json(); } catch { await espera(250); }
}
const ws = new WebSocket(alvos.find((t) => t.type === "page").webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener("open", r));
let id = 0;
const pendentes = new Map();
ws.addEventListener("message", (ev) => {
  const m = JSON.parse(ev.data);
  if (m.id && pendentes.has(m.id)) { pendentes.get(m.id)(m.result ?? m); pendentes.delete(m.id); }
  if (m.method === "Runtime.exceptionThrown") console.error("[erro na pagina]", m.params.exceptionDetails.text);
});
const cmd = (method, params = {}) => new Promise((r) => { const i = ++id; pendentes.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });

await cmd("Runtime.enable");
await cmd("Emulation.setDeviceMetricsOverride", { width: +largura, height: +altura, deviceScaleFactor: +escala, mobile: false });
await cmd("Page.navigate", { url });
await espera(+esperaMs);
await cmd("Runtime.evaluate", { expression: "document.fonts.ready", awaitPromise: true });

if (saida.toLowerCase().endsWith(".pdf")) {
  const r = await cmd("Page.printToPDF", { printBackground: true, preferCSSPageSize: true,
    marginTop: 0, marginBottom: 0, marginLeft: 0, marginRight: 0 });
  writeFileSync(saida, Buffer.from(r.data, "base64"));
} else {
  const r = await cmd("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
  writeFileSync(saida, Buffer.from(r.data, "base64"));
}
ws.close();
proc.kill();
await espera(300);
try { rmSync(perfil, { recursive: true, force: true }); } catch { /* o Chrome pode segurar o perfil */ }
console.log(`ok: ${saida}`);
process.exit(0);

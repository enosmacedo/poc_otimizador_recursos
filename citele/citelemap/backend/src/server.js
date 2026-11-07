import { criarApp } from "./app.js";
import { Municipios } from "./municipios.js";

const porta = Number(process.env.PORTA ?? 3000);
const app = criarApp({
  municipios: new Municipios(process.env.DADOS_DIR ?? "dados"),
  citeleatUrl: process.env.CITELEAT_URL ?? "http://localhost:8000",
  googleMapsApiKey: process.env.GOOGLE_MAPS_API_KEY ?? "",
  googleMapsMapId: process.env.GOOGLE_MAPS_MAP_ID || "DEMO_MAP_ID",
  maxVertices: Number(process.env.MAX_VERTICES ?? 1000),
});

app.listen(porta, () => console.log(`Citelemap backend na porta ${porta}`));

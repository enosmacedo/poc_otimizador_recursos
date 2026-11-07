# Material de divulgação do Citele

Público: gestores públicos (saúde, segurança, defesa civil e planejamento).

| Arquivo | O que é |
|---|---|
| `logo/citele-simbolo.svg` | Símbolo (pino de localização com área de cobertura e o recurso no centro). Bom para ícone e favicon. |
| `logo/citele-logo.svg` | Logomarca horizontal para fundo claro. |
| `logo/citele-logo-negativo.svg` | Logomarca para fundo escuro. |
| `folder-citele.pdf` | Folder A4 paisagem, três dobras, frente e verso (pronto para impressão). |
| `folder-citele-frente.png`, `folder-citele-verso.png` | Pré-visualização das duas faces do folder. |
| `fluxo-uso-citele.png` | Imagem 1920×1080 com o fluxo de uso em cinco passos (exemplo em Natal). |
| `video-citele-gestores.mp4` | Vídeo de apresentação (1080p, narrado). |
| `video-citele-gestores.srt` | Legendas do vídeo, para quem assiste sem som. |

**Cores**: azul `#1A5FD0`, azul-escuro `#13254A`, vermelho `#D92D20`, texto `#1D2330`.
**Fonte**: Segoe UI (Windows), com Roboto/Helvetica/Arial como alternativas. Nos SVG da logomarca o
nome "Citele" é texto; para uso em gráfica, converta-o em curvas (Inkscape: *Caminho → Objeto
para caminho*) para não depender da fonte instalada.

**Antes de distribuir**: preencha o contato da equipe, hoje marcado como
`[preencher com e-mail ou site da equipe]`, em `fonte/folder.html` e em `fonte/video/cenas.json`,
e gere de novo os arquivos.

Os números citados (cerca de 75 mil pessoas por ambulância, tempo médio de 4,6 min, nova
configuração em 8,1 min) são resultados reais do sistema em Natal (RN), com tempos sem trânsito.

## Como gerar de novo

Requer o sistema rodando (`docker compose up -d` em `citele/`), Node 22+, Google Chrome e o
`.venv` do projeto (com `imageio-ffmpeg`). Na pasta `fonte/`:

```
node capturas.mjs capturas                                   # telas do sistema
node render.mjs folder.html ../folder-citele.pdf 1123 794    # folder (PDF)
node render.mjs folder.html#p1 ../folder-citele-frente.png 1123 794 2
node render.mjs folder.html#p2 ../folder-citele-verso.png 1123 794 2
node render.mjs fluxo.html ../fluxo-uso-citele.png 1920 1080
cd video && python montar_video.py                           # vídeo + legendas
```

O roteiro do vídeo (textos na tela e narração) fica em `fonte/video/cenas.json`. A narração usa a
voz "Microsoft Maria" do Windows. Para um resultado mais natural, grave uma locução humana de cada
cena (mesmo texto de `narracao`) e salve como `fonte/video/locucao/cena_N.wav` (N = 0 a 8): o
script usa a gravação no lugar da voz sintética e ajusta a duração da cena e das legendas.

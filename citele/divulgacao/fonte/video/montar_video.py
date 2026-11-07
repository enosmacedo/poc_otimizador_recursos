"""Monta o video de apresentacao do Citele a partir de cenas.json.

Etapas: narracao (voz pt-BR do Windows) -> quadros (Chrome headless, via
../render.mjs) -> um clipe por cena (zoom leve + fade, ffmpeg) -> video final
e legendas .srt.

Uso (na pasta divulgacao/fonte/video):
    python montar_video.py [saida.mp4]
Requer: Node 22+, Google Chrome, Windows (voz "Microsoft Maria Desktop") e
o pacote imageio-ffmpeg (traz o executavel do ffmpeg).
"""
import json
import re
import subprocess
import sys
import wave
from pathlib import Path

import imageio_ffmpeg

AQUI = Path(__file__).resolve().parent
TRABALHO = AQUI / "build"
SAIDA = Path(sys.argv[1]) if len(sys.argv) > 1 else AQUI.parents[1] / "video-citele-gestores.mp4"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
ANTES_S = 0.6  # silencio antes da fala
DEPOIS_S = 1.0  # respiro depois da fala
FPS = 30
VELOCIDADE_VOZ = "2"  # -10 a 10 (System.Speech); 2 = um pouco mais rapido que o normal


def executar(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise SystemExit(f"Falhou: {' '.join(map(str, cmd))[:300]}\n{r.stderr[-2000:]}")


def duracao_wav(arquivo):
    with wave.open(str(arquivo)) as w:
        return w.getnframes() / w.getframerate()


def trechos_legenda(texto, maximo=84):
    """Divide a fala em frases; frases longas sao quebradas na virgula ou,
    sem virgula, no ultimo espaco (no maximo duas linhas de legenda)."""
    frases = re.findall(r"[^.?!]+[.?!]?", texto)
    trechos = []
    for f in (f.strip() for f in frases if f.strip()):
        while len(f) > maximo:
            corte = f[:maximo].rfind(",") + 1 or f[:maximo].rfind(" ")
            trechos.append(f[:corte].strip())
            f = f[corte:].strip()
        trechos.append(f)
    return trechos


def quebrar_linhas(texto, largura=44):
    palavras, linhas, atual = texto.split(), [], ""
    for p in palavras:
        if len(atual) + len(p) + 1 > largura and atual:
            linhas.append(atual)
            atual = p
        else:
            atual = f"{atual} {p}".strip()
    linhas.append(atual)
    return "\n".join(linhas)


def tempo_srt(s):
    ms = round(s * 1000)
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def main():
    TRABALHO.mkdir(exist_ok=True)
    cenas = json.loads((AQUI / "cenas.json").read_text(encoding="utf-8"))
    (AQUI / "cenas.js").write_text("window.CENAS = " + json.dumps(cenas, ensure_ascii=False) + ";\n",
                                   encoding="utf-8")
    clipes, legendas, inicio_video = [], [], 0.0
    for i, cena in enumerate(cenas):
        fala_txt, fala_wav = TRABALHO / f"fala_{i}.txt", TRABALHO / f"fala_{i}.wav"
        quadro, clipe = TRABALHO / f"cena_{i}.png", TRABALHO / f"clipe_{i}.mp4"
        gravada = AQUI / "locucao" / f"cena_{i}.wav"
        if gravada.exists():  # locucao humana tem prioridade sobre a voz sintetica
            fala_wav = gravada
        else:
            fala_txt.write_text(cena["narracao"], encoding="utf-8")
            executar(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                      str(AQUI / "narrar.ps1"), "-Texto", str(fala_txt), "-Saida", str(fala_wav),
                      "-Velocidade", VELOCIDADE_VOZ])
        executar(["node", str(AQUI.parent / "render.mjs"), f"{(AQUI / 'video.html').as_uri()}#{i}",
                  str(quadro), "1920", "1080", "2", "1500"])

        fala = duracao_wav(fala_wav)
        dur = round(ANTES_S + fala + DEPOIS_S, 2)
        quadros = int(dur * FPS)
        filtro = (
            f"[0:v]scale=3840:2160,zoompan=z='1+0.05*on/{quadros}':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1920x1080:fps={FPS},"
            f"fade=t=in:st=0:d=0.45,fade=t=out:st={dur - 0.45}:d=0.45,format=yuv420p[v];"
            f"[1:a]aresample=48000,loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000,"
            f"adelay={int(ANTES_S * 1000)}:all=1,apad,atrim=0:{dur},"
            f"afade=t=out:st={dur - 0.3}:d=0.3[a]"
        )
        executar([FFMPEG, "-y", "-loop", "1", "-framerate", str(FPS), "-t", str(dur), "-i", str(quadro),
                  "-i", str(fala_wav), "-filter_complex", filtro, "-map", "[v]", "-map", "[a]",
                  "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-r", str(FPS),
                  "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2", str(clipe)])
        clipes.append(clipe)

        # Legendas: cada trecho dura proporcionalmente ao seu tamanho
        trechos = trechos_legenda(cena["narracao"])
        total = sum(len(t) for t in trechos)
        t0 = inicio_video + ANTES_S
        for t in trechos:
            t1 = t0 + fala * len(t) / total
            legendas.append((t0, t1, quebrar_linhas(t)))
            t0 = t1
        inicio_video += dur
        print(f"cena {i}: {dur:.1f}s ({cena['tipo']})", flush=True)

    lista = TRABALHO / "clipes.txt"
    lista.write_text("".join(f"file '{c.as_posix()}'\n" for c in clipes), encoding="utf-8")
    executar([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(lista), "-c", "copy",
              "-movflags", "+faststart", str(SAIDA)])
    srt = SAIDA.with_suffix(".srt")
    srt.write_text("\n".join(f"{n}\n{tempo_srt(a)} --> {tempo_srt(b)}\n{txt}\n"
                             for n, (a, b, txt) in enumerate(legendas, 1)), encoding="utf-8")
    print(f"video: {SAIDA} ({inicio_video:.1f}s)\nlegendas: {srt}")


if __name__ == "__main__":
    main()

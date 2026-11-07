# Gera a narracao (WAV) de um texto com a voz pt-BR do Windows.
# Uso: powershell -File narrar.ps1 -Texto fala.txt -Saida fala.wav [-Velocidade 1]
param([string]$Texto, [string]$Saida, [int]$Velocidade = 1)
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.SelectVoice("Microsoft Maria Desktop")
$s.Rate = $Velocidade
$s.SetOutputToWaveFile($Saida)
$s.Speak((Get-Content -Raw -Encoding UTF8 $Texto))
$s.Dispose()

-- Controlador dos drones (eye-bot) no ARGoS.
-- O citeledrone coloca antes deste codigo valores gerados a cada simulacao:
--   ALVOS = { ["d0"] = {x, y, z}, ... }   posicao final de cada drone (m)
--   VELOCIDADE = 8        velocidade horizontal maxima (m/s)
--   SUBIDA = 3            velocidade de subida (m/s)
--   TPS = 50              passos de controle por segundo (ticks_per_second)
--   PASSOS_LOG = 10       registra a posicao a cada N passos
-- O drone sobe na vertical ate a altitude do alvo e depois segue em linha
-- reta ate ele.
--
-- O alvo nao e entregue direto ao controlador de posicao do eye-bot (ele e
-- muito agressivo e o drone "saltaria" dezenas de metros). Um ponto de
-- comando anda ate o alvo com perfil trapezoidal de velocidade (acelera,
-- cruza e freia a tempo de parar no alvo) e o drone o acompanha. Com 50
-- passos por segundo (e 1 iteracao de fisica por passo) os degraus do
-- comando sao pequenos e o drone para no alvo sem ultrapassar.

local DT = 1 / TPS
local ACELERACAO = 2.0 -- m/s^2 (a mesma de simulacao.py)
local passo, alvo, comando, fase, vel

local function registrar()
  local p = robot.positioning.position
  log(string.format("POS %s %d %.3f %.3f %.3f %s", robot.id, passo, p.x, p.y, p.z, fase))
end

local function avancar(destino, velocidade_max)
  -- Move o ponto de comando ate o destino; devolve true quando chega
  local dx, dy, dz = destino[1] - comando[1], destino[2] - comando[2], destino[3] - comando[3]
  local d = math.sqrt(dx * dx + dy * dy + dz * dz)
  vel = math.min(velocidade_max, vel + ACELERACAO * DT, math.sqrt(2 * ACELERACAO * d))
  local s = vel * DT
  if d <= s or d < 1e-3 then
    comando = {destino[1], destino[2], destino[3]}
    vel = 0
    return true
  end
  comando = {comando[1] + dx / d * s, comando[2] + dy / d * s, comando[3] + dz / d * s}
  return false
end

function init()
  passo = 0
  vel = 0
  alvo = ALVOS[robot.id]
  local p = robot.positioning.position
  comando = {p.x, p.y, p.z}
  fase = "subindo"
end

function step()
  if fase == "subindo" then
    if avancar({comando[1], comando[2], alvo[3]}, SUBIDA) then fase = "deslocando" end
  elseif fase == "deslocando" then
    if avancar(alvo, VELOCIDADE) then fase = "posicionado" end
  end
  robot.quadrotor.set_absolute_position(comando[1], comando[2], comando[3])
  if passo % PASSOS_LOG == 0 then registrar() end
  passo = passo + 1
end

function reset()
  init()
end

function destroy()
end

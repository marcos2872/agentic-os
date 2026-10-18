---
name: agenticos-rotinas
description: Criar, listar, executar e remover rotinas agendadas (timers systemd --user) pelo chat. Use para "todo dia/semana faça X", "agende a atualização dos flatpaks", "me avise tal hora" ou "lista minhas rotinas".
license: MIT
---

# Rotinas agendadas (systemd --user)

## Quando usar

- Lembretes via notificação (`notify-send`).
- Atualização periódica dos Flatpaks (`flatpak update`).
- Reconstruir cache do menu (`kbuildsycoca6`).

Comandos permitidos nas rotinas: **`flatpak [--user] update [-y]`**, **`notify-send`** e
**`kbuildsycoca6`**. Qualquer outro comando é recusado por design — explique o limite.

## Criar

`os_routine_create name=<slug> calendar="<expressão>" argv=[...]`

Exemplos de calendário (formato `OnCalendar` do systemd):

| calendário | quando roda |
|---|---|
| `daily` | todo dia à meia-noite |
| `*-*-* 10:00` | todo dia às 10h |
| `Sun *-*-* 10:00` | domingos às 10h |
| `Mon-Fri 09:00` | dias úteis às 9h |
| `weekly` | uma vez por semana |

Exemplos de comando (`argv`):

- `["flatpak", "--user", "update", "-y"]`
- `["notify-send", "Hidratação", "Beba água!"]` — sem `$` nem `\` na mensagem
- `["kbuildsycoca6"]`

## Listar, rodar agora, remover

- `os_routine_list` — nome, calendário e próxima execução.
- `os_routine_run name=...` — dispara uma vez, sem esperar o horário.
- `os_routine_remove name=...` — desabilita e remove (undo recria).

## Detalhes para explicar ao usuário

- Cada rotina vira `agenticos-<nome>.service` + `.timer` em `~/.config/systemd/user`.
- `Persistent=true`: se a máquina estava desligada na hora, roda na próxima oportunidade.
- O serviço roda na sessão do usuário (sem root).
- `notify-send` só aparece se houver servidor de notificações (o KDE tem).

## Cuidados

- Nome: `a-z`, `0-9` e hífen (até 31 caracteres).
- Liste as rotinas antes de criar para não duplicar.
- Confirme com o usuário a frequência quando o pedido for vago ("de vez em quando").

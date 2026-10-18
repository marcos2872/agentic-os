#!/usr/bin/env bash
# uninstall.sh — remove o Agentic OS instalado no escopo do usuário.
#
# Uso: setup/uninstall.sh [--keep-config] [-h|--help]
set -euo pipefail

KEEP_CONFIG=0

log_ok()   { printf '[ok] %s\n' "$*"; }
log_warn() { printf '[aviso] %s\n' "$*"; }
log_err()  { printf '[erro] %s\n' "$*" >&2; }
have()     { command -v "$1" >/dev/null 2>&1; }

usage() {
  cat <<'EOF'
Uso: setup/uninstall.sh [opções]

Remove daemon, wrappers, serviço systemd, launcher e atalho do Agentic OS.
Não remove o pi, as configs do pi nem os plasmoids (veja o aviso no final).

Opções:
  --keep-config   preserva ~/.config/agenticos e ~/.local/share/agenticos
                  (system prompt, assets, audit, backups e undo)
  -h, --help      mostra esta ajuda
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --keep-config) KEEP_CONFIG=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) log_err "opção desconhecida: $1"; usage; exit 2 ;;
  esac
done

BIN_DIR="$HOME/.local/bin"
KCTL="$BIN_DIR/agenticctl"

# 1) Regra KWin — via agenticctl, ANTES de derrubar o daemon.
RULE_PARAMS='{"description":"Transparência Global"}'
if [[ -x $KCTL ]]; then
  if "$KCTL" call kwin.remove_rule --yes --json --params-json "$RULE_PARAMS" >/dev/null 2>&1; then
    log_ok "regra KWin 'Transparência Global' removida"
  else
    log_warn "não consegui remover a regra KWin via agenticctl; remova manualmente em Configurações do Sistema → Janelas → Regras"
  fi
else
  log_warn "agenticctl não encontrado; se existir a regra KWin 'Transparência Global', remova manualmente"
fi

# 2) Serviço systemd: parar, desabilitar e remover a unit.
if have systemctl; then
  systemctl --user disable --now agenticd.service >/dev/null 2>&1 \
    || log_warn "agenticd.service já estava parado/ausente"
fi
rm -f "$HOME/.config/systemd/user/agenticd.service"
if have systemctl; then
  systemctl --user daemon-reload >/dev/null 2>&1 || true
fi
log_ok "serviço agenticd.service removido"

# 3) Daemon e wrappers.
rm -rf "$HOME/.local/lib/agenticos"
rm -f "$BIN_DIR/agenticd" "$BIN_DIR/agenticctl" "$BIN_DIR/agentic-os-chat"
log_ok "daemon e wrappers removidos"

# 4) Extension e skills do pi.
rm -f "$HOME/.pi/agent/extensions/agentic-os.ts"
rm -rf "$HOME/.pi/agent/skills"/agenticos-*
log_ok "extension e skills do pi removidas (~/.pi/agent)"

# 5) Atalho de menu.
rm -f "$HOME/.local/share/applications/agentic-os.desktop"
if have kbuildsycoca6; then
  kbuildsycoca6 >/dev/null 2>&1 || log_warn "kbuildsycoca6 falhou (sem sessão gráfica?)"
fi
log_ok "atalho removido do menu"

# 6) Config e dados.
if (( KEEP_CONFIG == 1 )); then
  log_ok "config e dados preservados: ~/.config/agenticos e ~/.local/share/agenticos"
else
  log_warn "apagando ~/.config/agenticos e ~/.local/share/agenticos (inclui audit.jsonl, backups e undo)"
  rm -rf "$HOME/.config/agenticos" "$HOME/.local/share/agenticos"
fi

cat <<'EOF'

O seguinte NÃO foi removido (faça manualmente se quiser):

  - pi (o harness do chat):
        npm uninstall -g @earendil-works/pi-coding-agent
    (se instalado pelo instalador curl, remova o binário 'pi' correspondente)
  - configs do pi:
        rm -rf ~/.pi
  - plasmoids do Agentic OS:
        kpackagetool6 -t Plasma/Applet --remove com.agenticos.inlineconfirm
        kpackagetool6 -t Plasma/Applet --remove com.agenticos.appcarousel
EOF

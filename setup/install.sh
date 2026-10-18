#!/usr/bin/env bash
# install.sh — instala o Agentic OS no escopo do usuário (sem root, idempotente).
#
# Uso: setup/install.sh [--dry-run] [--no-ui] [--skip-pi] [-h|--help]
#
# Alvos:
#   ~/.local/lib/agenticos/     código do daemon (pacote Python)
#   ~/.local/bin/               wrappers (agenticd, agenticctl, agentic-os-chat)
#   ~/.config/agenticos/        system prompt do chat
#   ~/.local/share/agenticos/   assets do daemon (regra KWin, undo, audit, backups)
#   ~/.config/systemd/user/     unit agenticd.service
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

DRY_RUN=0
WITH_UI=1
SKIP_PI=0

# ---------------------------------------------------------------- utilidades
log_ok()   { printf '[ok] %s\n' "$*"; }
log_warn() { printf '[aviso] %s\n' "$*"; }
log_err()  { printf '[erro] %s\n' "$*" >&2; }
have()     { command -v "$1" >/dev/null 2>&1; }

# Registra sucesso só quando algo foi realmente feito (evita "ok" em dry-run).
log_done() { if [[ $DRY_RUN -eq 0 ]]; then log_ok "$@"; fi; }

# Executa um comando — ou apenas imprime, em --dry-run.
run() {
  if [[ $DRY_RUN -eq 1 ]]; then
    printf '  [dry-run] %s\n' "$*"
    return 0
  fi
  "$@"
}

# Executa uma linha de shell (para pipes, ex.: instalador do pi).
run_sh() {
  if [[ $DRY_RUN -eq 1 ]]; then
    printf '  [dry-run] (sh) %s\n' "$*"
    return 0
  fi
  bash -c "$*"
}

usage() {
  cat <<'EOF'
Uso: setup/install.sh [opções]

Instala o Agentic OS (daemon, CLI, chat do pi, assets e serviço systemd de
usuário). É idempotente: rode de novo para atualizar.

Opções:
  --dry-run    apenas mostra o que seria feito, sem executar nada
  --no-ui      pula tema (BreezeDark) e regra de transparência do KWin
  --skip-pi    não tenta instalar o pi
  -h, --help   mostra esta ajuda
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --no-ui)   WITH_UI=0; shift ;;
    --skip-pi) SKIP_PI=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) log_err "opção desconhecida: $1"; usage; exit 2 ;;
  esac
done

# ---------------------------------------------------------------- pré-checagem
if [[ ! -d "$REPO_DIR/daemon/agenticos" ]]; then
  log_err "não encontrei daemon/agenticos em $REPO_DIR — rode este script dentro do repositório"
  exit 1
fi
if [[ ! -f "$REPO_DIR/assets/system-prompt.md" ]]; then
  log_err "não encontrei assets/system-prompt.md em $REPO_DIR"
  exit 1
fi

if ! have python3; then
  log_err "python3 não encontrado; instale o Python 3 (ex.: sudo dnf install python3)"
  exit 1
fi
log_ok "python3: $(python3 --version 2>&1)"

for tool in konsole kpackagetool6 kwriteconfig6 kreadconfig6; do
  if have "$tool"; then
    log_ok "$tool encontrado"
  else
    log_warn "$tool ausente; a funcionalidade correspondente ficará limitada"
  fi
done

if have rpm-ostree; then
  log_ok "sistema imutável detectado (rpm-ostree); a instalação continua user-scope"
else
  log_ok "sem rpm-ostree (Fedora KDE tradicional ou outro sistema)"
fi

if [[ $DRY_RUN -eq 1 ]]; then
  printf '\n== SIMULAÇÃO (--dry-run): nada será alterado ==\n\n'
fi

# ---------------------------------------------------------------- pi (harness)
install_pi() {
  local node_version="" node_major="" node_minor="" use_npm=0

  if have pi; then
    log_ok "pi já instalado: $(command -v pi)"
    return 0
  fi

  if have node; then
    node_version="$(node --version 2>/dev/null || true)"   # ex.: v24.22.0
    if [[ $node_version =~ ^v([0-9]+)\.([0-9]+) ]]; then
      node_major="${BASH_REMATCH[1]}"
      node_minor="${BASH_REMATCH[2]}"
      if (( node_major > 22 || (node_major == 22 && node_minor >= 19) )); then
        use_npm=1
      fi
    fi
  fi

  if (( use_npm == 1 )); then
    log_ok "instalando pi via npm (node $node_version)"
    if ! run npm install -g --ignore-scripts @earendil-works/pi-coding-agent; then
      log_warn "npm install falhou; instale manualmente: https://pi.dev"
    fi
  else
    if have node; then
      log_warn "node ${node_version:-?} abaixo de 22.19; usando o instalador oficial do pi"
    else
      log_warn "node não encontrado; usando o instalador oficial do pi"
    fi
    if ! run_sh 'curl -fsSL https://pi.dev/install.sh | sh'; then
      log_warn "instalador do pi falhou (sem rede?); instale manualmente: https://pi.dev"
    fi
  fi

  if [[ $DRY_RUN -eq 0 ]]; then
    if have pi; then
      log_ok "pi instalado: $(command -v pi)"
    else
      log_warn "pi ainda não está no PATH; reabra o terminal ou instale manualmente: https://pi.dev"
    fi
  fi
}

if [[ $SKIP_PI -eq 1 ]]; then
  log_ok "instalação do pi pulada (--skip-pi)"
else
  install_pi
fi

# ---------------------------------------------------------------- daemon + wrappers
LIB_DIR="$HOME/.local/lib/agenticos"
BIN_DIR="$HOME/.local/bin"
CFG_DIR="$HOME/.config/agenticos"
DATA_DIR="$HOME/.local/share/agenticos"
ASSETS_DIR="$DATA_DIR/assets"
UNIT_DIR="$HOME/.config/systemd/user"

run mkdir -p "$LIB_DIR" "$BIN_DIR" "$CFG_DIR" "$ASSETS_DIR" "$UNIT_DIR"
run rm -rf "$LIB_DIR/agenticos"
run cp -r "$REPO_DIR/daemon/agenticos" "$LIB_DIR/agenticos"
if [[ $DRY_RUN -eq 1 ]]; then
  printf '  [dry-run] remover __pycache__ de %s/agenticos\n' "$LIB_DIR"
else
  find "$LIB_DIR/agenticos" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
fi
log_done "daemon copiado para $LIB_DIR/agenticos"

write_module_wrapper() {
  local dest="$1" module="$2"
  if [[ $DRY_RUN -eq 1 ]]; then
    printf '  [dry-run] criar wrapper %s (python3 -m %s)\n' "$dest" "$module"
    return 0
  fi
  cat >"$dest" <<EOF
#!/usr/bin/env bash
export PYTHONPATH="\$HOME/.local/lib/agenticos\${PYTHONPATH:+:\$PYTHONPATH}"
exec python3 -m $module "\$@"
EOF
  chmod +x "$dest"
}

write_module_wrapper "$BIN_DIR/agenticd" agenticos.daemon
write_module_wrapper "$BIN_DIR/agenticctl" agenticos.cli
log_done "wrappers criados: $BIN_DIR/agenticd, $BIN_DIR/agenticctl"

# ---------------------------------------------------------------- serviço systemd
write_unit() {
  if [[ $DRY_RUN -eq 1 ]]; then
    printf '  [dry-run] escrever %s\n' "$UNIT_DIR/agenticd.service"
    return 0
  fi
  cat >"$UNIT_DIR/agenticd.service" <<'EOF'
[Unit]
Description=Agentic OS policy daemon
After=graphical-session.target
PartOf=graphical-session.target

[Service]
Type=simple
ExecStart=%h/.local/bin/agenticd
Restart=on-failure

[Install]
WantedBy=default.target
EOF
}

write_unit
log_done "unit systemd escrita em $UNIT_DIR/agenticd.service"

if have systemctl; then
  run systemctl --user daemon-reload
  run systemctl --user enable agenticd.service
  # restart (e não enable --now) garante que o daemon antigo em memória
  # seja substituído pelo código recém-instalado.
  if run systemctl --user restart agenticd.service; then
    log_done "agenticd.service habilitado e (re)iniciado"
  else
    log_warn "não foi possível iniciar agenticd.service; rode: systemctl --user enable --now agenticd.service"
  fi
else
  log_warn "systemctl ausente; sem serviço de usuário (rode 'agenticd' manualmente, se preciso)"
fi

RUNTIME_BASE="${XDG_RUNTIME_DIR:-/tmp/agenticos-$(id -u)}"
SOCK="$RUNTIME_BASE/agenticos/agenticd.sock"

if [[ $DRY_RUN -eq 1 ]]; then
  printf '  [dry-run] aguardar o socket %s (até 5s)\n' "$SOCK"
else
  for _ in {1..50}; do
    if [[ -S $SOCK ]]; then break; fi
    sleep 0.1
  done
  if [[ -S $SOCK ]]; then
    log_ok "daemon escutando em $SOCK"
  else
    log_warn "socket não apareceu em 5s ($SOCK); veja: systemctl --user status agenticd"
  fi
fi

if [[ $DRY_RUN -eq 1 ]]; then
  printf '  [dry-run] %s tools\n' "$BIN_DIR/agenticctl"
elif "$BIN_DIR/agenticctl" tools >/dev/null 2>&1; then
  log_ok "sanity check: agenticctl respondeu a 'tools'"
else
  log_warn "sanity check falhou ($BIN_DIR/agenticctl tools); veja: journalctl --user -u agenticd -n 50"
fi

# ---------------------------------------------------------------- extension do pi
EXT_SRC="$REPO_DIR/pi-package/extensions/agentic-os.ts"
EXT_DST="$HOME/.pi/agent/extensions/agentic-os.ts"
if [[ -f $EXT_SRC ]]; then
  run mkdir -p "$(dirname "$EXT_DST")"
  run cp "$EXT_SRC" "$EXT_DST"
  log_done "extension do pi instalada em $EXT_DST"
else
  log_warn "extension não encontrada ($EXT_SRC); pulando (gere pi-package/ e rode de novo)"
fi

# ---------------------------------------------------------------- assets
run cp "$REPO_DIR/assets/system-prompt.md" "$CFG_DIR/system-prompt.md"
log_done "system prompt copiado para $CFG_DIR/system-prompt.md"

run cp -r "$REPO_DIR/assets/kwin/." "$ASSETS_DIR/"
log_done "assets do daemon copiados para $ASSETS_DIR"

# ---------------------------------------------------------------- launcher
run cp "$REPO_DIR/assets/launcher/agentic-os-chat" "$BIN_DIR/agentic-os-chat"
run chmod +x "$BIN_DIR/agentic-os-chat"
run mkdir -p "$HOME/.local/share/applications"
run cp "$REPO_DIR/assets/launcher/agentic-os.desktop" "$HOME/.local/share/applications/agentic-os.desktop"
log_done "launcher instalado: $BIN_DIR/agentic-os-chat + atalho no menu"

if have kbuildsycoca6; then
  if [[ $DRY_RUN -eq 1 ]]; then
    printf '  [dry-run] kbuildsycoca6\n'
  elif kbuildsycoca6 >/dev/null 2>&1; then
    log_ok "cache do menu atualizado (kbuildsycoca6)"
  else
    log_warn "kbuildsycoca6 falhou (sem sessão gráfica?); o atalho aparece no próximo login"
  fi
else
  log_warn "kbuildsycoca6 ausente; rode-o depois para atualizar o menu"
fi

# ---------------------------------------------------------------- plasmoids
install_plasmoids() {
  if ! have kpackagetool6; then
    log_warn "kpackagetool6 ausente; instale os plasmoids manualmente: kpackagetool6 -t Plasma/Applet -i <dir>"
    return 0
  fi

  local installed_list="" dir metadata id
  installed_list="$(kpackagetool6 -t Plasma/Applet --list 2>/dev/null || true)"

  for dir in "$REPO_DIR"/prototypes/plasmoids/*/; do
    [[ -d $dir ]] || continue
    metadata="$dir/metadata.json"
    if [[ ! -f $metadata ]]; then
      log_warn "$dir sem metadata.json; pulando"
      continue
    fi
    id="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["KPlugin"]["Id"])' "$metadata" 2>/dev/null || true)"
    if [[ -z $id ]]; then
      log_warn "não consegui ler KPlugin.Id de $metadata; pulando"
      continue
    fi
    if grep -qF "$id" <<<"$installed_list"; then
      run kpackagetool6 -t Plasma/Applet -u "$dir"
      log_done "plasmoid $id atualizado"
    else
      run kpackagetool6 -t Plasma/Applet -i "$dir"
      log_done "plasmoid $id instalado"
    fi
  done
}
install_plasmoids

# ---------------------------------------------------------------- UI (tema + KWin)
if [[ $WITH_UI -eq 0 ]]; then
  log_ok "etapa de UI pulada (--no-ui)"
else
  if have plasma-apply-colorscheme; then
    if [[ $DRY_RUN -eq 1 ]]; then
      printf '  [dry-run] plasma-apply-colorscheme BreezeDark\n'
    elif plasma-apply-colorscheme BreezeDark >/dev/null 2>&1; then
      log_ok "tema BreezeDark aplicado"
    else
      log_warn "plasma-apply-colorscheme falhou; aplique o tema manualmente"
    fi
  elif have kwriteconfig6; then
    if [[ $DRY_RUN -eq 1 ]]; then
      printf '  [dry-run] kwriteconfig6 --file kdeglobals --group General --key ColorScheme BreezeDark\n'
    elif kwriteconfig6 --file kdeglobals --group General --key ColorScheme BreezeDark; then
      log_ok "ColorScheme=BreezeDark gravado (aplica no próximo login / reabertura do Plasma)"
    else
      log_warn "kwriteconfig6 falhou; aplique o tema manualmente"
    fi
  else
    log_warn "sem plasma-apply-colorscheme/kwriteconfig6; aplique BreezeDark manualmente (Configurações do Sistema → Aparência)"
  fi

  RULE_FILE="$ASSETS_DIR/Transparencia-Global.kwinrule"
  KCTL="$BIN_DIR/agenticctl"
  RULE_PARAMS="$(printf '{"file":"%s"}' "$RULE_FILE")"
  if [[ $DRY_RUN -eq 1 ]]; then
    printf '  [dry-run] %s call kwin.add_rule --yes --json --params-json %s\n' "$KCTL" "$RULE_PARAMS"
  elif [[ ! -x $KCTL ]]; then
    log_warn "agenticctl indisponível; regra de transparência do KWin não aplicada"
  elif "$KCTL" call kwin.add_rule --yes --json --params-json "$RULE_PARAMS" >/dev/null 2>&1; then
    log_ok "regra de transparência do KWin aplicada"
  else
    log_warn "kwin.add_rule falhou; aplique manualmente (Configurações do Sistema → Janelas → Regras)"
  fi
fi

# ---------------------------------------------------------------- resumo
if [[ $DRY_RUN -eq 1 ]]; then
  log_ok "simulação concluída (nada foi alterado)"
else
  log_ok "instalação concluída"
fi

cat <<'EOF'

Próximos passos:
  1. Abra "Agentic OS" no menu de aplicativos (ou rode: agentic-os-chat).
  2. Dentro do pi, rode /login para autenticar o modelo.
  3. Teste com frases como:
       - "como está o sistema?"
       - "instale o Brave via flatpak"
       - "deixe o tema escuro com transparência"
       - "desfaça a última ação"
  4. Diagnóstico: systemctl --user status agenticd | journalctl --user -u agenticd -n 50
  5. Para remover: setup/uninstall.sh [--keep-config]
EOF

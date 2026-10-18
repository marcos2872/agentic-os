#!/usr/bin/env bash
# vm-create.sh — cria uma VM descartável (libvirt/KVM) para testar o Agentic OS.
#
# Uso: setup/vm-create.sh --iso PATH [opções]
#
# O ISO NÃO é baixado automaticamente; passe o caminho de um Fedora Kinoite
# ou Fedora KDE Spin já baixado.
#
# Por padrão usa qemu:///system (é onde a rede 'default' vive). Se o usuário
# não tiver acesso, cai para qemu:///session com rede em modo user (SLIRP).
set -euo pipefail

NAME="agentic-os-vm"
RAM=8192
VCPUS=4
DISK=60
ISO=""
CONNECT=""
CONNECT_EXPLICIT=0
NETWORK="auto"
DRY_RUN=0

log_ok()   { printf '[ok] %s\n' "$*"; }
log_warn() { printf '[aviso] %s\n' "$*"; }
log_err()  { printf '[erro] %s\n' "$*" >&2; }

usage() {
  cat <<'EOF'
Uso: setup/vm-create.sh --iso PATH [opções]

Cria uma VM no libvirt (KVM) para instalar o Fedora Kinoite ou Fedora KDE
Spin e testar o Agentic OS.

Opções:
  --iso PATH        (obrigatório) caminho do ISO do Fedora
  --name NOME       nome da VM (default: agentic-os-vm)
  --ram MB          memória em MB (default: 8192)
  --vcpus N         vCPUs (default: 4)
  --disk GB         disco em GB (default: 60)
  --connect URI     conexão libvirt (default: qemu:///system; aceita
                    qemu:///session com rede user automaticamente)
  --network MODO    auto | default | user (default: auto)
  --dry-run         apenas mostra o virt-install que seria executado
  -h, --help        mostra esta ajuda

Pré-requisitos (Fedora):
  sudo dnf install virt-install qemu-kvm libvirt-daemon-config-network
  sudo systemctl enable --now virtqemud.socket libvirtd 2>/dev/null || true
  sudo usermod -aG libvirt <seu-usuario>   # e faça login de novo
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --iso)     ISO="${2:-}"; shift 2 ;;
    --name)    NAME="${2:-}"; shift 2 ;;
    --ram)     RAM="${2:-}"; shift 2 ;;
    --vcpus)   VCPUS="${2:-}"; shift 2 ;;
    --disk)    DISK="${2:-}"; shift 2 ;;
    --connect) CONNECT="${2:-}"; CONNECT_EXPLICIT=1; shift 2 ;;
    --network) NETWORK="${2:-}"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) log_err "opção desconhecida: $1"; usage; exit 2 ;;
  esac
done

if [[ -z $ISO ]]; then
  log_err "--iso é obrigatório (ex.: --iso ~/Downloads/Fedora-Kinoite-44.iso)"
  usage
  exit 2
fi
if [[ ! -f $ISO ]]; then
  log_err "ISO não encontrado: $ISO"
  exit 1
fi

if ! command -v virt-install >/dev/null 2>&1; then
  log_err "virt-install não encontrado. Instale as dependências com:"
  printf '  sudo dnf install virt-install qemu-kvm libvirt-daemon-config-network\n' >&2
  printf '  sudo systemctl enable --now virtqemud.socket\n' >&2
  printf '  sudo usermod -aG libvirt <seu-usuario>   # depois faça login de novo\n' >&2
  exit 1
fi

virsh_for() {
  local uri="$1"
  shift
  virsh --connect "$uri" "$@"
}

# -------------------------------------------------- conexão libvirt
if [[ -z $CONNECT ]]; then
  CONNECT="qemu:///system"
fi
if ! virsh_for "$CONNECT" version >/dev/null 2>&1; then
  if [[ $CONNECT_EXPLICIT -eq 1 ]]; then
    log_err "não consegui falar com $CONNECT (permissão? serviço ligado?)"
    exit 1
  fi
  log_warn "sem acesso ao qemu:///system (usuário fora do grupo libvirt?)"
  log_warn "caindo para qemu:///session com rede em modo user (SLIRP)"
  CONNECT="qemu:///session"
  NETWORK="user"
fi

# -------------------------------------------------- rede
case "$NETWORK" in
  auto)
    if [[ $CONNECT == *"//system"* ]]; then NETWORK="default"; else NETWORK="user"; fi
    ;;
  default|user) ;;
  *) log_err "--network aceita auto, default ou user"; exit 2 ;;
esac

if [[ $NETWORK == "default" ]]; then
  if ! virsh_for "$CONNECT" net-info default >/dev/null 2>&1; then
    log_warn "rede 'default' não existe em $CONNECT; tentando criá-la"
    DEFAULT_XML="/usr/share/libvirt/networks/default.xml"
    if [[ -f $DEFAULT_XML ]] \
      && virsh_for "$CONNECT" net-define "$DEFAULT_XML" >/dev/null 2>&1 \
      && virsh_for "$CONNECT" net-start default >/dev/null 2>&1 \
      && virsh_for "$CONNECT" net-autostart default >/dev/null 2>&1; then
      log_ok "rede 'default' criada e ativa"
    else
      log_warn "não consegui criar a rede 'default'; usando rede user (SLIRP)"
      log_warn "para a rede default: sudo virsh -c qemu:///system net-start default"
      NETWORK="user"
    fi
  fi
fi

if [[ $NETWORK == "default" ]]; then
  NET_ARG="network=default"
else
  NET_ARG="user"
fi

# -------------------------------------------------- UEFI (com fallback BIOS)
BOOT_ARGS=()
if [[ -e /usr/share/edk2/ovmf/OVMF_CODE.fd || -e /usr/share/edk2/ovmf/OVMF_CODE.cc.fd ]]; then
  BOOT_ARGS=(--boot uefi)
else
  log_warn "firmware UEFI (edk2-ovmf) não encontrado; usando BIOS"
  log_warn "recomendado: sudo dnf install edk2-ovmf"
fi

# -------------------------------------------------- VM já existe?
if virsh_for "$CONNECT" dominfo "$NAME" >/dev/null 2>&1; then
  log_err "já existe uma VM chamada '$NAME' em $CONNECT"
  printf '  remova com:\n' >&2
  printf '    virsh -c %s destroy %s 2>/dev/null; virsh -c %s undefine --remove-all-storage %s\n' \
    "$CONNECT" "$NAME" "$CONNECT" "$NAME" >&2
  exit 1
fi

log_ok "criando a VM '$NAME' ($RAM MB, $VCPUS vCPUs, ${DISK}G) via $CONNECT"
log_ok "rede: $NET_ARG"

# shellcheck disable=SC2054  # 'size=..,format=qcow2' é um único valor
CMD=(
  virt-install
  --connect "$CONNECT"
  --name "$NAME"
  --osinfo detect=on,require=off
  "${BOOT_ARGS[@]+"${BOOT_ARGS[@]}"}"
  --machine q35
  --cpu host-passthrough
  --graphics spice
  --video virtio
  --network "$NET_ARG"
  --memory "$RAM"
  --vcpus "$VCPUS"
  --disk "size=$DISK,format=qcow2"
  --cdrom "$ISO"
  --noautoconsole
)

if [[ $DRY_RUN -eq 1 ]]; then
  printf '  [dry-run]'
  printf ' %q' "${CMD[@]}"
  printf '\n'
  exit 0
fi

"${CMD[@]}"

log_ok "VM '$NAME' criada; a instalação do Fedora já começou no console"

cat <<EOF

Abrir a VM:
  virt-manager -c $CONNECT                        # interface gráfica
  virt-viewer -c $CONNECT $NAME                   # console direto

Passos pós-instalação:
  1. Instale o Fedora Kinoite ou o Fedora KDE Spin normalmente na VM.
  2. Dentro da VM, clone o repositório do Agentic OS e rode o instalador:
       git clone <URL do repositório do Agentic OS>
       cd agentic_os && ./setup/install.sh
  3. Abra o chat pelo menu ("Agentic OS") e rode /login no pi.

A VM é descartável. Para removê-la depois:
  virsh -c $CONNECT destroy $NAME
  virsh -c $CONNECT undefine --remove-all-storage $NAME
EOF

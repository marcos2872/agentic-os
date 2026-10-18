#!/usr/bin/env bash
# vm-create.sh — cria uma VM descartável (libvirt/KVM) para testar o Agentic OS.
#
# Uso: setup/vm-create.sh --iso PATH [--name NOME] [--ram MB] [--vcpus N] [--disk GB]
#
# O ISO NÃO é baixado automaticamente; passe o caminho de um Fedora Kinoite
# ou Fedora KDE Spin já baixado.
set -euo pipefail

NAME="agentic-os-vm"
RAM=8192
VCPUS=4
DISK=60
ISO=""

log_ok()   { printf '[ok] %s\n' "$*"; }
log_warn() { printf '[aviso] %s\n' "$*"; }
log_err()  { printf '[erro] %s\n' "$*" >&2; }

usage() {
  cat <<'EOF'
Uso: setup/vm-create.sh --iso PATH [opções]

Cria uma VM no libvirt (qemu:///system) para instalar o Fedora Kinoite ou
Fedora KDE Spin e testar o Agentic OS.

Opções:
  --iso PATH     (obrigatório) caminho do ISO do Fedora
  --name NOME    nome da VM (default: agentic-os-vm)
  --ram MB       memória em MB (default: 8192)
  --vcpus N      vCPUs (default: 4)
  --disk GB      disco em GB (default: 60)
  -h, --help     mostra esta ajuda
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --iso)   ISO="${2:-}"; shift 2 ;;
    --name)  NAME="${2:-}"; shift 2 ;;
    --ram)   RAM="${2:-}"; shift 2 ;;
    --vcpus) VCPUS="${2:-}"; shift 2 ;;
    --disk)  DISK="${2:-}"; shift 2 ;;
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
  printf '  sudo systemctl enable --now libvirtd\n' >&2
  exit 1
fi

log_ok "criando a VM '$NAME' ($RAM MB, $VCPUS vCPUs, ${DISK}G) a partir de $ISO"
virt-install \
  --name "$NAME" \
  --osinfo detect=on,require=off \
  --boot uefi \
  --machine q35 \
  --cpu host-passthrough \
  --graphics spice \
  --video virtio \
  --network network=default \
  --memory "$RAM" \
  --vcpus "$VCPUS" \
  --disk size="$DISK",format=qcow2 \
  --cdrom "$ISO" \
  --noautoconsole \
  --wait 0

log_ok "VM '$NAME' criada; a instalação do Fedora já começou no console"

cat <<EOF

Abrir a VM:
  virt-manager                                  # interface gráfica
  virt-viewer -c qemu:///system $NAME           # console direto

Passos pós-instalação:
  1. Instale o Fedora Kinoite ou o Fedora KDE Spin normalmente na VM.
  2. Dentro da VM, clone o repositório do Agentic OS e rode o instalador:
       git clone <URL do repositório do Agentic OS>
       cd agentic_os && ./setup/install.sh
  3. Abra o chat pelo menu ("Agentic OS") e rode /login no pi.

A VM é descartável. Para removê-la depois:
  virsh -c qemu:///system destroy $NAME
  virsh -c qemu:///system undefine --remove-all-storage $NAME
EOF

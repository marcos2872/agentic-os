# Agentic OS — MVP

Chat de IA que controla o sistema com guardrails: o agente não tem shell — ele
emite ações estruturadas que um daemon de políticas valida, audita e torna
reversíveis. O harness do chat é o [pi](https://pi.dev); o desktop é o KDE Plasma
(cara padrão, por enquanto).

## Como funciona

```
Chat (pi, TUI)  ──tools os_*──▶  agenticctl ──socket Unix──▶  agenticd
                                                               │
                    ┌──────────────┬──────────────┬────────────┴───────────┐
                    ▼              ▼              ▼                        ▼
                 flatpak      Plasma/KWin     widgets/rotinas       configs (~/.config)
```

- **Verde** executa direto (com auditoria e undo). **Amarela** exige confirmação
  do usuário (`needs_confirmation` + `plan_id`). **Vermelho** é bloqueado
  (base imutável, PAM/SELinux, drivers, chaves SSH).
- Toda ação mutável registra **undo** (`os_undo`) e vai para a **auditoria**
  (`~/.local/share/agenticos/audit.jsonl`).
- Instalação 100% user-scope (`$HOME` + `systemctl --user`), sem root.

## Estrutura

| Caminho | O que é |
|---|---|
| `daemon/` | pacote Python do daemon (`agenticd`) e do CLI (`agenticctl`) + testes |
| `pi-package/` | extensão do pi com as tools `os_*` (+ teste funcional) |
| `assets/` | system prompt do chat, regra KWin de transparência, launcher |
| `setup/` | `install.sh`, `uninstall.sh` e `vm-create.sh` |
| `prototypes/` | plasmoids de protótipo (inline confirm, app carousel) |

## Testar numa VM (fluxo rápido)

Recomendado: **Fedora Kinoite** (base imutável, alinhado ao roadmap), mas o
instalador também funciona no **Fedora KDE Spin**. VM descartável:

```bash
# no host (opcional; também vale criar a VM pelo virt-manager)
setup/vm-create.sh --iso ~/Downloads/Fedora-Kinoite-44-*.iso
```

Dentro da VM, depois de instalar o Fedora normalmente:

```bash
git clone <url-deste-repo> && cd agentic_os
./setup/install.sh            # idempotente; --dry-run para simular, --no-ui para pular tema/KWin
```

> **Sem remote no Git?** Para levar este repositório para dentro da VM, publique-o
> num remote e clone, use `scp -r` (com o `sshd` da VM habilitado) ou, com a VM
> desligada, `sudo virt-copy-in -a /var/lib/libvirt/images/agentic-os-vm.qcow2 \
> /tmp/agentic_os.tar.gz /home/<usuario-na-vm>/` e extraia dentro da VM.

Depois:

1. Abra **Agentic OS** no menu (roda `pi -nbt -t 'os_*'` no Konsole, com o
   system prompt do Agentic OS).
2. Dentro do pi, rode `/login` e escolha o provider/modelo.
3. Frases de teste:
   - “como está o sistema?”
   - “instale o Brave via flatpak”
   - “deixe o tema escuro com transparência” *(ação amarela: confirme no chat)*
   - “crie uma rotina para atualizar os flatpaks todo domingo às 10h”
   - “liste as regras do KWin” / “desfaça a última ação”

Para remover: `setup/uninstall.sh [--keep-config]`.

## CLI (sem o chat)

O mesmo daemon pode ser usado direto:

```bash
agenticctl tools                          # lista ações, risco e parâmetros
agenticctl system.info
agenticctl call theme.apply_preset        # amarela: devolve plan_id
agenticctl call theme.apply_preset --confirm <plan_id>
agenticctl undo.last                      # desfaz a última ação reversível
agenticctl audit.tail n=10                # histórico
```

## Desenvolvimento e testes

```bash
./daemon/run-tests.sh        # unidade + integração (daemon isolado, ferramentas stubbadas)
./pi-package/test/run.sh     # extensão do pi: registro das tools, fluxo amarelo, guardrail

# rodar o chat sem instalar:
pi -nbt -t 'os_*' --append-system-prompt assets/system-prompt.md
```

O contrato tool↔ação é verificado por teste (`daemon/tests/test_policy.py`):
os nomes em `pi-package/extensions/agentic-os.ts` têm que bater com
`TOOL_NAMES` em `daemon/agenticos/policy.py`.

## Limites deste MVP

- Transporte é socket Unix; o contrato já está pronto para virar D-Bus + polkit depois.
- Sem root: ações que exigem privilégio (escopo `system` do Flatpak) pedem
  confirmação e podem falhar sem agente polkit.
- Chat = TUI do pi no Konsole; web UI/chat QML nativo e tema “glass” ficam para as
  próximas fases.
- `plasma.set_wallpaper` não tem undo; `widget.install` que atualiza um plasmoid
  existente não é reversível.

## Segurança

- O launcher restringe o agente a `os_*` (`-nbt -t 'os_*'`) e a extensão ainda
  bloqueia `bash`/`edit`/`write` como defesa em profundidade
  (`AGENTICOS_ALLOW_BUILTIN=1` libera).
- O daemon só executa binários de uma allowlist, com argv explícito (sem shell),
  validação de parâmetros, backup antes de alterar arquivos e limites de caminho
  (`~/.config`, `$HOME`, `/etc`, `/var/log`; segredos bloqueados).
- Auditoria completa em JSONL; planos amarelos expiram em 10 minutos.

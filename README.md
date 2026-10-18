# Agentic OS — MVP

Chat de IA que controla o sistema com guardrails: o caminho principal são ações
estruturadas (`os_*`) que um daemon de políticas valida, audita e torna reversíveis.
Terminal e escrita de arquivos também existem, mas cada uso passa por **confirmação
no chat** (e há um modo confiança). O harness do chat é o [pi](https://pi.dev); o
desktop é o KDE Plasma (cara padrão, por enquanto).

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
- **Terminal e escrita** (`bash`, `write`, `edit`, `read`, `grep`, `find`, `ls`)
  estão ativos, mas cada uso de terminal/escrita pede confirmação no chat; comandos
  catastróficos e escritas fora de `$HOME`/`/tmp` são bloqueados. O atalho
  **Agentic OS (modo confiança)** no menu desliga as confirmações.
- Toda ação mutável registra **undo** (`os_undo`) e vai para a **auditoria**
  (`~/.local/share/agenticos/audit.jsonl`).
- Instalação 100% user-scope (`$HOME` + `systemctl --user`), sem root.

## Estrutura

| Caminho | O que é |
|---|---|
| `daemon/` | pacote Python do daemon (`agenticd`) e do CLI (`agenticctl`) + testes |
| `pi-package/` | extensão do pi com as tools `os_*` e as skills `agenticos-*` |
| `assets/` | system prompt do chat, regra KWin de transparência, launcher |
| `setup/` | `install.sh`, `uninstall.sh` e `vm-create.sh` |
| `prototypes/` | plasmoids de protótipo (inline confirm, app carousel) |

## Skills e system prompt

O pacote do pi traz **skills** (formato Agent Skills) que o modelo carrega sob demanda —
cada uma ensina um fluxo completo com as ferramentas `os_*`:

| Skill | Para quê |
|---|---|
| `agenticos-operacao` | roteamento geral, risco, confirmação, undo e auditoria |
| `agenticos-apps` | instalar/remover/abrir aplicativos (Flatpak, .desktop) |
| `agenticos-temas` | tema, cores, papel de parede, transparência e regras do KWin |
| `agenticos-widgets` | criar/editar/validar/instalar widgets (plasmoids) pelo chat |
| `agenticos-rotinas` | rotinas agendadas (timers systemd --user) |
| `agenticos-configs` | configurações em `~/.config` com backup e undo |

Elas são instaladas em `~/.pi/agent/skills/` e anunciadas automaticamente; o usuário
também pode forçar uma com `/skill:agenticos-widgets`. O system prompt
(`assets/system-prompt.md`) é injetado pelo launcher em todo chat do Agentic OS.

## Testar numa VM (fluxo rápido)

Recomendado: **Fedora Kinoite** (base imutável, alinhado ao roadmap), mas o
instalador também funciona no **Fedora KDE Spin**. VM descartável:

```bash
# no host (opcional; também vale criar a VM pelo virt-manager)
setup/vm-create.sh --iso ~/Downloads/Fedora-Kinoite-44-*.iso
```

Dentro da VM, depois de instalar o Fedora normalmente:

```bash
git clone https://github.com/marcos2872/agentic-os.git && cd agentic-os
./setup/install.sh            # idempotente; --dry-run para simular, --no-ui para pular tema/KWin
```

> **Alternativas** (fork offline, VM sem rede): use `scp -r` com o `sshd` da VM
> habilitado ou, com a VM desligada, `sudo virt-copy-in -a /var/lib/libvirt/images/agentic-os-vm.qcow2 \
> /tmp/agentic_os.tar.gz /home/<usuario-na-vm>/` e extraia dentro dela.

Depois:

1. Abra **Agentic OS** no menu (roda o pi no Konsole com as tools `os_*` + builtins
   guardados e o system prompt do Agentic OS). Há também **Agentic OS (modo confiança)**,
   sem confirmações.
2. Dentro do pi, rode `/login` e escolha o provider/modelo.
3. Frases de teste:
   - “como está o sistema?”
   - “instale o Brave via flatpak”
   - “deixe o tema escuro com transparência” *(ação amarela: confirme no chat)*
   - “crie um widget que mostra a hora atual e instale” *(o agente escreve o QML direto)*
   - “cria uma pasta ~/projetos/teste com um README e lista o conteúdo” *(bash: confirmação por uso)*
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
pi -t 'os_*,read,bash,edit,write,grep,find,ls' --append-system-prompt assets/system-prompt.md
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
- O agente cria e instala widgets, mas ainda não os adiciona à área de trabalho
  sozinho (o usuário adiciona pelo Plasma após a instalação).
- `plasma.set_wallpaper` não tem undo; `widget.install` que atualiza um plasmoid
  existente não é reversível.

## Segurança

- Três camadas: (1) `os_*` passa pelo daemon com allowlist, argv explícito (sem
  shell), validação de parâmetros, backup, undo e auditoria; (2) `bash`/`write`/`edit`
  builtin pedem confirmação por uso, com padrões catastróficos bloqueados e escrita
  limitada a `$HOME`/`/tmp`/`/var/tmp`; (3) modo confiança
  (`agentic-os-chat --trust` ou `AGENTICOS_ALLOW_BUILTIN=1`) libera tudo — decisão
  explícita do usuário.
- No fluxo guardado, sem UI para confirmar, a ação é bloqueada (falha segura).
- O daemon limita caminhos (`~/.config`, `$HOME`, `/etc`, `/var/log`; segredos
  bloqueados) e roda apenas na sessão do usuário.
- Auditoria completa em JSONL; planos amarelos expiram em 10 minutos.

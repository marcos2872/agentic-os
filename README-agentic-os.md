# Agentic OS — Sistema operacional com UI de chat controlada por IA

> Documento de ideia e direção técnica. Não é o MyOS atual (rota C com scripts bash), mas uma
> variante/evolução: um OS onde o chat de IA é a interface central e controla o sistema com
> guardrails, sem sacrificar o uso "normal" de um desktop.

## 1. Visão

Um sistema GNU/Linux completo e usável no dia a dia (apps, jogos, multimídia, dev), mas cuja
interface primária é um **chat de IA** capaz de:

- instalar e desinstalar aplicativos;
- alterar configurações do sistema e da UI;
- criar e gerenciar rotinas (tarefas agendadas, automações);
- criar widgets e personalizações na interface via plugins.

O diferencial não é "um OS com um chatbot". É um OS onde **o estado desejado é descrito em
linguagem natural** e um agente traduz isso em ações seguras, verificáveis e reversíveis — com
guardrails que impedem que o agente ou o usuário matem o sistema.

## 2. Princípios de design

1. **Base imutável, camadas mutáveis.** O sistema base é uma imagem OCI com atualização
   transacional e rollback. Tudo que muda com frequência fica em camadas acima da base:
   Flatpak, containers (Distrobox), configs em `$HOME`, serviços de usuário.
2. **Privilégio mínimo para o agente.** O agente nunca tem shell root livre. Ele opera via um
   daemon com API restrita (D-Bus + polkit), allowlist de operações e auditoria.
3. **Toda mudança é reversível.** Antes de aplicar, gera plano + diff; guarda backup; oferece
   undo no chat e rollback de boot para mudanças de base.
4. **UI plugável.** Widgets e rotinas são plugins instaláveis/atualizáveis sem tocar no core.
5. **Usável sem o agente.** Se a IA falhar, estiver offline ou o usuário quiser, o desktop
   continua 100% funcional como um OS normal.
6. **O sistema se adapta ao usuário no primeiro boot.** Onboarding guiado por perguntas monta
   um sistema já personalizado, eliminando a instalação manual de apps e ajustes.

## 3. Base Linux — pesquisa e decisão

| Opção | Estável para agente? | Facilitada? | Observações |
|---|---|---|---|
| **Fedora bootc / Atomic** (Silverblue, Kinoite, uBlue) | Sim | Sim | `/usr` somente leitura, updates transacionais + rollback, Flatpak e Toolbx/Distrobox nativos, SELinux, build de imagem via OCI | 
| NixOS | Sim (rollback e declarativo excelentes) | Não | Curva alta, ecossistema Flatpak fraco, IA gera Nix com erro com frequência |
| openSUSE Aeon / Vanilla OS | Médio | Médio | Conceito similar, ecossistema menor, menos imagens prontas e menos documentação |
| Arch / Fedora Workstation tradicional | Não | Sim (para dev) | `dnf` direto na base + agente = boot quebrado sem rollback |

**Decisão: Fedora bootc** (sucessor do rpm-ostree):

- imagem própria com `FROM quay.io/fedora/fedora-bootc`;
- o agente nunca roda `dnf` na base. Ações permitidas: `flatpak`, `distrobox`, `bootc upgrade`,
  configs de usuário e `systemctl --user`;
- operações privilegiadas via daemon com allowlist + polkit + confirmação no chat;
- rollback no boot resolve o pior caso ("agente quebrou o sistema").

O MyOS atual (scripts bash idempotentes) vira a **base da imagem bootc**: o que hoje é
`10-gpu.sh`…`50-configs.sh` passa a ser construído na imagem, e o que é personalização vira
camada de runtime.

## 4. Ambiente gráfico — pesquisa e decisão

| Opção | Estável? | Widget/plugin por IA? | Observações |
|---|---|---|---|
| **KDE Plasma 6 (Kinoite)** | Sim | Sim (Plasmoids em QML/JS, KRunner, D-Bus) | Melhor custo-benefício para MVP; Wayland maduro; IA gera QML com facilidade |
| **Niri + Noctalia/Quickshell** | Médio | Sim (plugins Noctalia em QML/JS) | Leve (<600 MB idle, alvo do MyOS), mas nicho: todo bug do compositor é seu |
| COSMIC (System76) | Alpha | Médio (applets em Rust) | Promissor, sem base Fedora oficial e toolchain mais dura para IA |
| GNOME Shell | Sim | Não | Extensions quebram a cada versão; inviável para widgets gerados por IA |
| Hyprland | Não | Não | Quebra com updates, config manual, portais/polkit imaturos |

**Decisão em duas fases:**

- **Fase 1 (MVP estável): Fedora Kinoite bootc + Plasma 6**
  - chat como app/painel lateral sempre visível em QML nativo (Kirigami);
  - sem Tauri/webview: blur, translucidez e integração Wayland são nativos no QML;
  - widgets = Plasmoids; rotinas = systemd `--user` timers + D-Bus;
  - onboarding = `plasma-welcome` customizado com as perguntas;
  - valida agente, permissões e guardrails sem brigar com o compositor.
- **Fase 2 (porta leve): Fedora bootc minimal + Niri + Noctalia**
  - reaproveita o daemon do agente e o modelo de permissões do MVP;
  - reutiliza os mesmos tokens de glass e o mesmo contrato D-Bus da Fase 1;
  - busca o alvo de baixo uso de RAM e a shell chat-first 100% custom.

Regra: **não fazer agente + compositor custom + imutabilidade ao mesmo tempo**. Primeiro o
agente seguro no Plasma; depois a shell leve.

## 5. Arquitetura do agente e guardrails

```
Usuário ⇄ UI de chat (QML)
              │  intenção em linguagem natural
              ▼
      Orquestrador LLM (intenção → plano de ações)
              │  ações estruturadas (não shell)
              ▼
   Daemon de políticas (D-Bus) ──── polkit / auditoria / backup
              │
   ┌──────────┼──────────────┬───────────────┐
   ▼          ▼              ▼               ▼
 Flatpak   Distrobox   systemctl --user   $HOME/.config
 (apps)    (dev/CLI)   (rotinas/serviços) (configs, plugins)
```

- O LLM **não executa shell**. Ele emite um plano de ações estruturadas que o daemon valida.
- Toda ação tem: validação de sintaxe/tipo, dry-run quando possível, backup e registro de undo.
- Separação data vs render (padrão MCP Apps): data tools buscam/mutam e retornam
  `structuredContent` encadeável; render tools só apresentam. Ex: `flatpak_search`
  (dados) → `render_app_card` (UI). Só a render tool referencia `resourceUri`.
- Toda render tool declara `resourceUri` versionado (ex: `ui://app-card/v1.qml`).
  Mudança quebradiça = nova URI. Tools precisam ser úteis sem UI (fallback texto no chat).

### Matriz de permissões (exemplo)

| Nível | Exemplos | Comportamento |
|---|---|---|
| Verde | `flatpak install/remove`, criar widget, editar `~/.config`, cron `--user` | Executa direto, com log |
| Amarelo | `bootc upgrade`, habilitar serviço de sistema, mudar tema/portais globalmente | Confirmação no chat com diff + explicação |
| Vermelho | Comandos na base (`rpm-ostree`/`dnf` em `/usr`), `rm -rf` fora de `$HOME`, alterar PAM/SELinux/kernel, drivers | Bloqueado; no máximo sugere procedimento manual documentado |

## 6. Apps: como instalar sem quebrar a base

- **GUI**: Flatpak (containerizado, permissões por app via `flatpak override` — o agente pode
  ajustar as permissões e explicar o que está concedendo).
- **Dev/CLI/stack**: Distrobox (ou Toolbx), com `.desktop` exportado.
- **Drivers/hardware**: por perfil na imagem (Intel/AMD/NVIDIA/hybrid), como o `10-gpu.sh` do
  MyOS já faz; mudança de driver = nova imagem + rollback.

## 7. Onboarding no primeiro boot

Wizard com perguntas que geram um **manifesto de personalização** (declarativo), aplicado pelo
mesmo daemon do agente:

- idioma, layout de teclado, fuso, wifi;
- perfil: dev / design / escritório / gaming / estudo / multiuso;
- apps que já usa (checklist agrupado por categoria) e stack de desenvolvimento;
- estética: tema, ícones, wallpapers, accent color, densidade;
- rotinas iniciais: backup, atualizações, limpeza, notificações;
- confirmação final com "plano de instalação" revisável antes de aplicar.

Resultado: sistema já com a cara, os apps e as ferramentas do usuário — e o manifesto fica salvo
para reinstalação/migração idêntica.

## 8. UI: chat + widgets como plugins

Direção visual: **Liquid Glass adaptado** (Apple HIG: material translúcido dinâmico,
blur + refração sutil, adaptação light/dark, hierarquia por elevação). Não é clone
pixel-perfect — é o mesmo vocabulário implementado em QML nativo.

Direção de interação: **MCP Apps / ChatGPT UI** (OpenAI Apps SDK): UI opcional,
data tools separadas de render tools, bridge `ui/*` sobre D-Bus, apresentações
mínimas, CSP estrito.

### 8.1 Tokens de glass (Fase 1 Plasma, reutilizados na Fase 2)

- Material: fundo translúcido (60–70% opacidade em dark, 50–60% em light) + `Blur`/`MultiEffect`;
  borda 1px semi-transparente; sombra suave por elevação; highlight especular sutil no topo.
- Chat = painel flutuante sempre visível (lateral direita ou overlay central), não janela opaca.
- Widgets = glass cards com 3 elevações (flat / raised / overlay). Raio e blur constantes
  via tema para IA gerar QML consistente a partir de templates.
- Acessibilidade obrigatória: toggle reduzir-transparência, modo alto-contraste e fallback
  100% opaco quando o compositor não oferece blur. Contraste mínimo WCAG AA para texto
  sobre vidro.
- Performance: blur só no chrome (chat, cards); conteúdo interno sem blur recursivo;
  respeitar `prefers-reduced-motion` para animações físicas.

### 8.2 Apresentações (escolher a menor que resolve)

| Tipo | Uso no Agentic OS | Exemplo |
|---|---|---|
| `inline card` | Resultado focado, confirmação amarela | "Instalar o Brave? [Confirmar] [Ver diff]" |
| `carousel` | Scan de opções similares | Lista de apps Flatpak, wallpapers, temas |
| `fullscreen` | Tarefa rica que precisa de espaço | Onboarding, log de auditoria, editor de rotina |
| `pip` | Atividade contínua visível durante o chat | Backup/upgrade em progresso, timer de rotina |

### 8.3 Bridge D-Bus (equivalente ao `postMessage` `ui/*`)

- `ui/initialize` + `tool-input`: UI recebe args validados da ação.
- `tool-result`: UI recebe `structuredContent` autoritativo e renderiza. Tratar como input não confiável.
- `tools/call`: UI pode chamar data tools (ex: "re-buscar", "re-tentar") sem remontar o widget.
- `ui/message` / `update-model-context`: seleção ou draft na UI que o modelo precisa ver
  (ex: app selecionado no carousel) é enviado como contexto, não como verdade.
- Compat: manter nomes/parâmetros idênticos nas Fases 1 e 2 para o daemon não mudar.

### 8.4 Estado

- **Autoritativo no daemon:** apps, configs, rotinas, resultados. UI chama tool → daemon
  valida, persiste, retorna snapshot → UI renderiza snapshot.
- **Efêmero na UI:** item selecionado, painel aberto, ordenação, draft de filtro.
- **Durável no servidor:** preferências cross-sessão (view mode, filtros salvos) em storage
  próprio, nunca só em `localStorage`/iframe.

### 8.5 Plugins

- Instalação/atualização não altera a base: fica em `$HOME` (`~/.local/share/plasma/plasmoids`
  na Fase 1, `~/.config/noctalia/plugins` na Fase 2) e é gerenciável/removível.
- Cada plugin: `resourceUri` versionado + manifesto (nome, versão, permissões D-Bus,
  `connectDomains`/`resourceDomains` se acessar rede) + assinatura (Sigstore/cosign).
  Sem assinatura válida, instala como não-confiável e sem acesso a data tools.
- Fase 1: Plasmoids (QML/JS) gerados a partir de templates validados com os tokens de glass.
  Fase 2: mesmos templates portados para plugins Noctalia (QML/JS).

## 9. Deploy e segurança

- Imagem bootc (OCI) construída em CI (GitHub Actions) e publicada em registry.
- `bootc upgrade` transacional + rollback no boot; kernel e drivers só mudam com a imagem.
- SELinux enforcing; política polkit dedicada para o daemon do agente.
- Sandbox do agente: acesso limitado por allowlist de D-Bus; nunca root direto.
- Plugins de UI: assinatura obrigatória para data tools; CSP declarado no manifesto
  (`connectDomains`, `resourceDomains` mínimos; sem `frame` aninhado por padrão).
- Auditoria: toda ação (prompt, plano, resultado, undo) registrada em log consultável no chat.

## 10. Desenvolvimento e testes

- `bootc-image-builder` gera QCOW2 para VM (KVM/QEMU) — ciclos de teste sem máquina física.
- Provar o protótipo em VM descartável (mesmo fluxo do `--dry-run`/`--yes` do MyOS atual).
- "Kanban" de confiabilidade: cada ação do agente precisa de teste de undo/rollback antes de
  virar ação "verde".

## 11. Roadmap por fases

| Fase | Escopo | Entrega |
|---|---|---|
| 0 | Decisões e protótipo do daemon de políticas (D-Bus + polkit + allowlist) | Prova de ações seguras de flatpak/config |
| 1 | Imagem Fedora Kinoite bootc com stack do MyOS + onboarding | VM instalável e usável |
| 2 | UI de chat integrada (painel glass sempre visível) + ações verdes/amarelas | Chat controla apps/config/rotinas com cards inline/carousel |
| 3 | Widgets plugináveis assinados (Plasmoids) + undo no chat | Personalização por IA a partir de templates |
| 4 | Porta leve: base bootc minimal + Niri + Noctalia | Mesmo contrato D-Bus e mesmos tokens de glass, alvo de RAM |

## 12. Riscos e mitigação

| Risco | Mitigação |
|---|---|
| LLM gera ação inválida ou nociva | Ações estruturadas (nunca shell), dry-run, backup, undo, rollback de boot |
| Flatpak quebra por permissions/parental controls | Manter pacotes protegidos (caso `malcontent`, já tratado no MyOS) |
| Update da base quebra plugins da UI | Plugins em `$HOME`; pinagem/calendário de upgrade; testar em VM antes |
| Custo de LLM | Provider escolhido pelo usuário; agente degrada para modo "sugerir script" |
| Escopo grande demais | Fases: Plasma antes de Niri; daemon antes de UI; VM antes de bare metal |

## 13. Relação com o MyOS atual

- **MyOS (hoje)**: rota C — scripts bash idempotentes sobre Fedora Workstation. Serve como
  fonte dos perfis de GPU, tuning, serviços e configs.
- **Agentic OS (ideia)**: evolução possível — empacotar o MyOS como imagem bootc, adicionar o
  daemon de agente e o chat. O noção de "plugáveis" e "reversível" já está no DNA dos scripts;
  a mudança principal é sair da base mutável e pôr o agente atrás de guardrails.

## 14. Questões abertas

- Provedor de LLM: local (privacidade, custo de hardware) vs nuvem (qualidade) — ou híbrido?
- Quanto de autonomia "verde" é aceitável no primeiro uso? Auto-confirmar rotinas de backup?
- UI do chat: decidido como painel QML nativo com glass (app separado vs embutido ainda
  a validar em protótipo); contrato D-Bus espelha MCP Apps `ui/*`.
- Supply chain de plugins: Sigstore/cosign + `resourceUri` versionado; definir UX de
  plugin não-confiável.
- Nome do projeto (Agentic OS é uma descrição, não um nome).

## Referências de UI

- Apple HIG — Liquid Glass / Materials: material translúcido dinâmico, blur, elevação,
  adaptação light/dark e acessibilidade.
- OpenAI Apps SDK — Build ChatGPT UI: UI opcional, separação data vs render tools,
  bridge `ui/*`, apresentações inline/carousel/fullscreen/PiP, CSP e `window.openai`.


kpackagetool6 -t Plasma/Applet -u prototypes/plasmoids/com.agenticos.inlineconfirm
kpackagetool6 -t Plasma/Applet -u prototypes/plasmoids/com.agenticos.appcarousel
kbuildsycoca6
plasmoidviewer -a com.agenticos.inlineconfirm

---
name: agenticos-widgets
description: Criar, editar, validar, instalar e remover widgets (plasmoids) do Plasma pelo chat. Use quando o usuário pedir um widget novo ("um widget que mostra X"), quiser mudar um widget do Agentic OS ou instalar/remover plasmoids.
license: MIT
---

# Widgets (plasmoids) do Plasma

Um widget é um pacote com `metadata.json` + `contents/ui/main.qml` (QML puro). O
Agentic OS mantém os widgets em criação em `~/.local/share/agenticos/workspace/<nome>/`
e instala em `~/.local/share/plasma/plasmoids` (camada do usuário, sem root).

## Criar um widget novo

1. **Entenda o pedido**: o que mostra, tamanho aproximado e de onde vêm os dados.
   O widget em si roda QML/JavaScript puro (sem shell e sem rede no runtime), mas
   você pode usar `bash` para testar/empacotar (cada comando pede confirmação).
2. **Esqueleto**: `os_widget_create name=<slug> description="<descrição curta>"`
   → cria `metadata.json` e `contents/ui/main.qml` e devolve o `path`.
3. **Edite o QML**: prefira `os_widget_write_file name=<slug>
   path=contents/ui/main.qml content=<arquivo COMPLETO>` (tem undo). Alternativamente,
   `write`/`edit` direto no arquivo do workspace (confirmação por uso, sem undo).
   Consulte `references/plasmoid-anatomy.md` (estrutura mínima, imports, dicas).
4. **Valide**: `os_widget_lint name=<slug>` (ou `qmllint` via bash); corrija e repita.
   Use `os_widget_read_file` para conferir o conteúdo atual.
5. **Instale**: `os_widget_install path=<path devolvido no passo 2>` (verde; undo remove).
6. **Teste com o usuário**: `plasmoidviewer -a com.agenticos.<slug>` abre uma
   pré-visualização na sessão (peça para ele olhar), ou oriente: botão direito na área
   de trabalho → "Adicionar widgets" → buscar pelo nome. (O agente ainda não adiciona
   o widget à área de trabalho sozinho.)

## Atualizar um widget que já existe

- Feito pelo Agentic OS (está no workspace e no `os_widget_list`): edite com
  `os_widget_write_file` → `os_widget_lint` → `os_widget_install` de novo (atualiza).
- De origem desconhecida: crie uma cópia no workspace, ajuste, instale a cópia; depois
  remova a original com `os_widget_remove` (pergunte antes).

## Remover / listar

- `os_widget_list` mostra instalados **e** o que está em criação no workspace.
- `os_widget_remove id=...` — undo reinstala quando a origem é conhecida.

## Limites e cuidados

- Sem shell/rede no widget; não prometa dados que ele não tem como obter.
- `qmllint` pega sintaxe/estrutura, mas o teste visual é manual
  (`plasmoidviewer -a com.agenticos.<nome>` ou adicionando na área de trabalho).
- Evite imports de módulos opcionais (Kirigami, PlasmaComponents) sem necessidade —
  o básico é `QtQuick`, `QtQuick.Layouts` e `org.kde.plasma.plasmoid`.
- Sempre relate o nome final e como testar.

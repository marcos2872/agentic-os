# Campos de regras do KWin (`~/.config/kwinrulesrc`)

Uma regra é um grupo cujo nome é um UUID, mais a lista `rules=` no `[General]`.
O Agentic OS cria regras por `os_kwin_rule_add` (parâmetro `fields`) e por arquivo
`.kwinrule` exportado pelo System Settings → Janelas → Regras → Exportar.

## Campos usados pelo preset (os mais confiáveis)

| campo | significado | valores |
|---|---|---|
| `Description` | nome da regra | texto livre |
| `Enabled` | regra ativa | `true` / `false` |
| `opacityactive` / `opacityinactive` | opacidade da janela ativa / inativa | `0`–`100` |
| `opacityactiverule` / `opacityinactiverule` | como aplicar a opacidade | `2` = forçar (é o que o preset usa) |
| `wmclassmatch` | como casar a janela | `0` = ignorar, `1` = exato, `2` = substring, `3` = regex |
| `wmclass` | classe da janela | ex.: `firefox`, `org.kde.konsole` |
| `wmclasscomplete` | usar classe completa | `true` / `false` |

> Deixando `wmclass` vazio com `wmclassmatch=2`, a regra vale para **todas** as janelas
> (é assim que a regra de transparência global funciona).

## Outros comportamentos comuns

| campo | efeito | valores |
|---|---|---|
| `above` / `below` | sempre na frente / atrás | `true` / `false` |
| `skiptaskbar` | não mostrar na barra de tarefas | `true` / `false` |
| `noborder` | sem moldura | `true` / `false` |
| `fullscreen` | abrir em tela cheia | `true` / `false` |
| `placement` | posicionamento | `1` = padrão do sistema (mantenha este quando em dúvida) |

## Boas práticas

- Para comportamentos simples use `fields`; para regras complexas (múltiplas condições,
  regex), peça ao usuário para exportar a regra do System Settings e instale com `file=`.
- Regras se acumulam: sempre `os_kwin_rules` antes de criar, e remova as antigas com
  `os_kwin_rule_remove` para não duplicar.
- Toda regra criada tem undo (`os_undo` restaura o estado anterior do arquivo).

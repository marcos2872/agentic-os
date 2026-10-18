---
name: agenticos-configs
description: Ler e escrever configurações de usuário em ~/.config (INIs como kdeglobals, kwinrc, dolphinrc) com backup e undo. Use para ajustes finos que não têm ferramenta própria (cor de destaque, preferências de apps) ou para conferir o valor de uma chave.
license: MIT
---

# Configurações de usuário (~/.config)

## Ferramentas

- `os_config_get file= group= key=` — lê uma chave (erro se não existir).
- `os_config_set file= group= key= value=` — grava com backup automático; o undo
  restaura o valor anterior (ou remove a chave, se ela não existia).
- `os_config_unset` — remove a chave (também com undo).

Só aceita caminhos **dentro de `~/.config`**; valores não podem ter quebra de linha.

## Fluxo

1. `os_config_get` para conhecer o valor atual (se não existir, siga — o undo remove).
2. `os_config_set` com o novo valor.
3. Explique **quando** o efeito aparece: aplicativos leem a config ao iniciar; mudanças
   globais do Plasma podem exigir reabrir o app ou a sessão.

## Exemplos úteis (referência, valores variam por versão)

| objetivo | file | group | key | valor |
|---|---|---|---|---|
| esquema de cores | `kdeglobals` | `General` | `ColorScheme` | `BreezeDark` |
| cor de destaque (accent) | `kdeglobals` | `General` | `AccentColor` | `61,174,233` |
| clique único no Dolphin | `dolphinrc` | `General` | `SingleClick` | `true` |
| desligar animações do Plasma | `kdeglobals` | `KDE` | `AnimationDurationFactor` | `0` |

## Cuidados

- Nunca edite arquivos de sistema (`/etc`) — só `~/.config`.
- Prefira as ferramentas específicas quando existirem (`os_plasma_color_scheme`,
  `os_theme_preset`, `os_kwin_rule_add`).
- Antes de mexer em chaves que afetam o desktop inteiro, avise e lembre do `os_undo`.
- Se a chave que o usuário citar não existir, diga isso em vez de inventar outra.

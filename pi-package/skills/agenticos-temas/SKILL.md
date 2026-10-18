---
name: agenticos-temas
description: Mudar a aparência do KDE Plasma — tema escuro/claro, esquema de cores, papel de parede, transparência global e regras de janela do KWin. Use para "deixe escuro", "janelas translúcidas", "muda o papel de parede", "sempre na frente", "tira a transparência".
license: MIT
---

# Tema e aparência (Plasma 6 + KWin)

## Preset pronto: escuro + transparência

- `os_theme_preset` (amarela) aplica: esquema **BreezeDark** + regra KWin
  "Transparência Global" (94% na janela ativa e inativa, todas as janelas).
- Explique o efeito e deixe a UI confirmar. O KWin recarrega a regra na hora; sem KWin
  rodando, ela vale no próximo login.

## Só as cores

- `os_plasma_color_scheme scheme=BreezeDark` (ou `BreezeLight`; amarela).
- Esquemas instalados: os mais comuns são BreezeDark/BreezeLight; se o usuário citar um
  esquema próprio, use o nome exato que ele informar.

## Papel de parede

- `os_plasma_wallpaper path=/caminho/imagem.png` (amarela; png/jpg/webp).
- **Sem undo** — avise o usuário antes de trocar.

## Transparência e regras de janela (KWin)

- Listar: `os_kwin_rules`.
- Instalar a partir de arquivo `.kwinrule`: `os_kwin_rule_add file=...` (amarela).
- Instalar por campos diretos: `os_kwin_rule_add fields={...}` — veja
  `references/kwin-rule-fields.md` para o dicionário de campos.
- Remover: `os_kwin_rule_remove id=<uuid>` ou `description="<nome>"` (amarela).
- Exemplo — 70% de opacidade em todas as janelas:

  ```json
  {"Description": "Transparência 70", "opacityactive": "70", "opacityactiverule": "2",
   "opacityinactive": "70", "opacityinactiverule": "2", "wmclasscomplete": "true",
   "wmclassmatch": "2"}
  ```

## Ajustes finos

- Preferências sem ferramenta própria (accent color, animações) vão por
  `os_config_set` em `~/.config` — ver skill `agenticos-configs`.

## Limites

- Papel de parede não tem undo; regras do KWin têm.
- Sem sessão gráfica, mudanças de Plasma/KWin ficam para o próximo login.
- Não invente nomes de esquema nem IDs de regra: liste antes.

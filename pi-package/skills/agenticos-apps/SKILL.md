---
name: agenticos-apps
description: Instalar, remover, listar e abrir aplicativos (Flatpak e entradas .desktop) pelas ferramentas os_apps_*. Use para "instala tal app", "o que está instalado", "abre o navegador" ou "remove isso".
license: MIT
---

# Aplicativos (Flatpak e .desktop)

## Instalar

1. `os_apps_search` com o nome pedido — **sempre busque antes de instalar**.
2. Mostre ao usuário o nome, o ID e a descrição do candidato; se houver mais de um
   plausível, pergunte qual (texto simples já basta).
3. `os_apps_install app_id=...` — verde, instala no escopo `user` (sem root).
   `scope=system` existe, mas escala para confirmação (amarela) — explique que pede
   autenticação de administrador.
4. Depois de instalar, diga que o app já está no menu e pode ser aberto com
   `os_app_launch`.

## Remover

1. `os_apps_installed` — use o ID **exato** (ex.: `com.brave.Browser`).
2. `os_apps_remove app_id=...` — verde (`system` vira amarela).
3. Avise: o undo reinstala o pacote, mas **configurações/dados do app podem se perder**.

## Abrir

- `os_app_launch app="firefox"` ou o ID completo (`org.mozilla.firefox`,
  `org.kde.konsole`). Aceita nome parcial se não houver ambiguidade.

## Catálogo do menu

- `os_apps_list query=...` — tudo que tem `.desktop`: apps do sistema e Flatpaks
  exportados. Use para responder "qual o nome do programa X?".

## Limites e cuidados

- `install` pode demorar (download); espere — não repita a chamada.
- IDs são sensíveis a maiúsculas: copie do resultado da busca.
- Não prometa versões nem tamanhos que a busca não retornou.
- Flatpak do sistema e do usuário coexistem; use `os_apps_installed` para ver origem.

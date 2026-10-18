#!/usr/bin/env bash
# Testa a extensão do pi fora do TUI (usa jiti + pacote real do pi).
# Requer node >= 22.19 e acesso ao npm na primeira execução (cache local).
set -euo pipefail
cd "$(dirname "$0")"

PKGS="${PI_EXT_TEST_DIR:-/tmp/opencode/pi-ext-test}"
mkdir -p "$PKGS"

if [ ! -d "$PKGS/node_modules/jiti" ] || [ ! -d "$PKGS/node_modules/@earendil-works/pi-coding-agent" ]; then
  echo "[test] instalando @earendil-works/pi-coding-agent em $PKGS (primeira vez)"
  (cd "$PKGS" && npm install --no-save --no-audit --no-fund @earendil-works/pi-coding-agent@latest >/dev/null)
fi

cp -f extension.test.mjs "$PKGS/extension.test.mjs"
cp -f ../extensions/agentic-os.ts "$PKGS/agentic-os.ts"
[ -f "$PKGS/package.json" ] || echo '{"name":"pi-ext-test","private":true,"type":"module"}' > "$PKGS/package.json"

cd "$PKGS"
exec node extension.test.mjs

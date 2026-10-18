#!/usr/bin/env bash
# Roda a suíte de testes do daemon (unidade + integração com stubs).
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m unittest discover -s tests -v "$@"

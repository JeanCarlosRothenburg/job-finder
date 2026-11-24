#!/usr/bin/env bash
# Instalação no macOS (Apple Silicon), sem Docker. Rode na pasta do projeto: ./scripts/instalar_mac.sh
set -euo pipefail

if ! command -v brew >/dev/null; then
  echo "Instale o Homebrew primeiro: https://brew.sh" && exit 1
fi
command -v uv >/dev/null || brew install uv
command -v ollama >/dev/null || brew install ollama

echo "→ Dependências Python"
uv sync --extra dev

[ -f .env ] || cp .env.example .env
[ -f perfil.yaml ] || { cp perfil.exemplo.yaml perfil.yaml; echo "→ Criei perfil.yaml a partir do exemplo: preencha com o seu currículo."; }

echo "→ Ollama (modelo de ~4B para extrair requisitos)"
pgrep -x ollama >/dev/null || (brew services start ollama || (ollama serve >/dev/null 2>&1 &))
sleep 2
MODELO=$(grep -E '^OLLAMA_MODELO=' .env | cut -d= -f2)
ollama pull "${MODELO:-qwen3:4b}"

echo "→ Testes"
uv run pytest -q

echo
echo "Pronto. Para usar:"
echo "  uv run job-finder testar-fontes   # confere Gupy e GitHub"
echo "  uv run job-finder serve           # abre em http://127.0.0.1:8000"

#!/usr/bin/env bash
cd "$(dirname "$0")"
[ -f .env ] || cp .env.example .env
if [ ! -x venv/bin/python ]; then
  rm -rf venv
  echo "Creando el entorno por primera vez..."
  python3 -m venv venv || { echo "Instala Python 3"; exit 1; }
fi
if ! cmp -s requirements.txt venv/requisitos.txt; then
  echo "Instalando librerias, puede tardar unos minutos..."
  venv/bin/python -m pip install -U -r requirements.txt || { echo "Fallo la instalacion"; exit 1; }
  cp requirements.txt venv/requisitos.txt
fi
venv/bin/python app.py

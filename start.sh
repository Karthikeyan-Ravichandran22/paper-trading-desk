#!/usr/bin/env bash
set -euo pipefail
cd backend
mkdir -p data
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"

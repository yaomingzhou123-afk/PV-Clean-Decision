#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
python3 -m pip install -q -r requirements.txt
cd backend
python3 -m uvicorn main:app --host 0.0.0.0 --port 8001
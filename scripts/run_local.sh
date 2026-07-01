#!/usr/bin/env bash
set -e
# Port 8000 is the shared backend port (matches the n8n nodes, app config, and the Vite proxy).
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

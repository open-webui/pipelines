#!/usr/bin/env bash
PORT="${PORT:-9099}"
HOST="${HOST:-0.0.0.0}"

# Start the server
uvicorn main:app --host "$HOST" --port "$PORT" --forwarded-allow-ips '*'

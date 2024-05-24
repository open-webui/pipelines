#!/usr/bin/env bash
PORT="${PORT:-9099}"
HOST="${HOST:-0.0.0.0}"

python -m open_webui.pipeline --pipelines ${1:-pipelines} serve --host $HOST --port $PORT

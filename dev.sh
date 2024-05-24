PORT="${PORT:-9099}"
python -m open_webui.pipeline --pipelines ${1:-pipelines} serve --host 0.0.0.0 --port $PORT

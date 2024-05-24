PORT="${PORT:-9099}"
uvicorn open_webui.pipeline:app --port $PORT --host 0.0.0.0 --forwarded-allow-ips '*' --reload
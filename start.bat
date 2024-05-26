@echo off
set PORT=9099
set HOST=0.0.0.0

uvicorn main:app --host %HOST% --port %PORT% --forwarded-allow-ips '*'
import logging
from pathlib import Path
from typing import Optional

import typer


import subprocess
import time


def start_process(app: str, host: str, port: int, reload: bool = False):
    # Start the FastAPI application
    command = [
        "uvicorn",
        app,
        "--host",
        host,
        "--port",
        str(port),
        "--forwarded-allow-ips",
        "*",
    ]

    if reload:
        command.append("--reload")

    process = subprocess.Popen(command)
    return process


main = typer.Typer()


@main.command()
def serve(
    host: str = "0.0.0.0",
    port: int = 9099,
):
    while True:
        process = start_process("main:app", host, port, reload=False)
        process.wait()

        if process.returncode == 42:
            print("Restarting due to restart request")
            time.sleep(2)  # optional delay to prevent tight restart loops
        else:
            print("Normal exit, stopping the manager")
            break


@main.command()
def dev(
    host: str = "0.0.0.0",
    port: int = 9099,
):
    while True:
        process = start_process("main:app", host, port, reload=True)
        process.wait()

        if process.returncode == 42:
            print("Restarting due to restart request")
            time.sleep(2)  # optional delay to prevent tight restart loops
        else:
            print("Normal exit, stopping the manager")
            break


if __name__ == "__main__":
    main()

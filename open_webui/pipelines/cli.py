import logging
from pathlib import Path
from typing import Optional

import typer

from .main import PIPELINES, load_modules_from_directory, app

def callback(
    pipelines: Optional[Path] = None
):
    for loaded_module in load_modules_from_directory(pipelines):
        # Do something with the loaded module
        logging.info("Loaded:", loaded_module.__name__)

        pipeline = loaded_module.Pipeline()

        PIPELINES[loaded_module.__name__] = {
            "module": pipeline,
            "id": pipeline.id if hasattr(pipeline, "id") else loaded_module.__name__,
            "name": pipeline.name if hasattr(pipeline, "name") else loaded_module.__name__,
        }


main = typer.Typer(callback=callback)


@main.command()
def serve(
    host: str = "0.0.0.0",
    port: int = 9099,
):
    import uvicorn

    uvicorn.run(app, host=host, port=port, forwarded_allow_ips="*")


@main.command()
def dev(
    host: str = "0.0.0.0",
    port: int = 9099,
):
    import uvicorn

    uvicorn.run("open_webui.pipeline.main:app", host=host, port=port, reload=True, forwarded_allow_ips="*")

if __name__ == "__main__":
    main()

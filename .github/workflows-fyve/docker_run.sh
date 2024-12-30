#!/bin/bash

# Navigate to the root of the project
PROJECT_DIR=$(dirname $(dirname "$(dirname "$0")"))
IMAGE_NAME=$(basename "$PWD")
cd "$PROJECT_DIR"

# use the data path to mount the data directory
DATA_PATH="$(pwd)/data"
KEY_PATH="/data"
PORT_EXPOSE=9099

# if there is an `env.sh` file, load it
if [ -f "env.sh" ]; then
    source env.sh
    echo $OPENAI_API_KEY
fi

# make temp directory for local openweb instance mount
mkdir -p data/openwebui

# Check if the '--cli' or '--skip' option is passed
SKIP_MODE=false

# Check for an input argument to skip the Docker rebuild
if [ "$SKIP_MODE" == true ]; then
    echo "Skipping Docker build as per the input argument, patching existing code directory."
    echo "Running PATCHED Docker image... with DATA_PATH='$DATA_PATH' (from directory $(pwd))"

    # Run the Docker container with the required environment variables
    PATCH_PATH="$(pwd)"
    # echo "Exposing port $PORT_EXPOSE for the server."
    # docker run --rm -t -p $PORT_EXPOSE:$PORT_EXPOSE $IMAGE_NAME:latest
    docker compose --file .github/workflows-fyve/docker-compose-local.yaml up 
    docker compose --file .github/workflows-fyve/docker-compose-local.yaml rm -f 

else
    # Build the Docker image
    ./.github/workflows-fyve/docker_build.sh

    # Check if the Docker build was successful
    if [ $? -ne 0 ]; then
        echo "Docker build failed. Exiting."
        exit 1
    fi

    echo "Running the Docker image... with DATA_PATH='$DATA_PATH' (from directory $(pwd))"

    # Run the Docker container with the required environment variables
    # echo "Exposing port $PORT_EXPOSE for the server."
    # docker run --rm -t -p $PORT_EXPOSE:8000 -e KEY_PATH="$KEY_PATH" -e DATA_PATH="/data" -v "$DATA_PATH":/data $IMAGE_NAME:latest
    # docker run --rm -t -p $PORT_EXPOSE:$PORT_EXPOSE $IMAGE_NAME:latest
    docker compose --file .github/workflows-fyve/docker-compose-local.yaml up 
    docker compose --file .github/workflows-fyve/docker-compose-local.yaml rm -f 

fi

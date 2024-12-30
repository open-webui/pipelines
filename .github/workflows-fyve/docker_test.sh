#!/bin/bash

# Navigate to the root of the project
PROJECT_DIR=$(dirname $(dirname "$(dirname "$0")"))
IMAGE_NAME=$(basename "$PWD")
cd "$PROJECT_DIR"

# Exit immediately if a command exits with a non-zero status
set -e
# Build the Docker image
USE_TEST=true ./.github/workflows-fyve/docker_build.sh dev

# Generate a temporary directory name
DATA_PATH="$(mktemp -d)/data"
mkdir -p $DATA_PATH
echo "Temporary directory created at '$DATA_PATH'..."

# use the test config script for testing
WORKING_PATH="$(pwd)"
KEY_PATH="/data"

echo "Testing the image... with DATA_PATH='$DATA_PATH', IMAGE_NAME=$IMAGE_NAME (from directory $(pwd))"

# start clean!
rm -rf $WORKING_PATH/coverage
mkdir -p $WORKING_PATH/coverage

# Run the Docker container with the required environment variables
# docker run --rm -t -e KEY_PATH="$KEY_PATH" -v "$DATA_PATH":/data -v "$WORKING_PATH/coverage:/coverage" -v "$WORKING_PATH/tests:/app/tests" $IMAGE_NAME:dev pytest --cov=$IMAGE_NAME --cov-report html:/coverage/coverage.html --cov-report=xml:/coverage/coverage.xml tests
docker run --rm -t -e KEY_PATH="$KEY_PATH" -v "$DATA_PATH":/data -v "$WORKING_PATH/coverage:/coverage" -v "$WORKING_PATH/tests:/app/tests" $IMAGE_NAME:dev pytest --cov=/app  --cov-report html:/coverage/coverage.html --cov-report=xml:/coverage/coverage.xml tests

# stop the build if there are Python syntax errors or undefined names
SELECT_CLAUSE="--ignore=E501,E121,E128,E124,E123"
# SELECT_CLAUSE=--select=E9,F63,F7,F82   # limit errors?
# docker run --rm -t -e KEY_PATH="$KEY_PATH" -v "$DATA_PATH":/data -v "$WORKING_PATH/coverage:/coverage" $IMAGE_NAME:dev flake8 /app/$IMAGE_NAME --exclude .venv --count $SELECT_CLAUSE --show-source --statistics --output-file=/coverage/flake8.txt --color=never --exit-zero
docker run --rm -t -e KEY_PATH="$KEY_PATH" -v "$DATA_PATH":/data -v "$WORKING_PATH/coverage:/coverage" $IMAGE_NAME:dev flake8 /app --exclude .venv --count $SELECT_CLAUSE --show-source --statistics --output-file=/coverage/flake8.txt --color=never --exit-zero


# final coverage report available
echo "Coverage report generated at $DATA_PATH/coverage.xml, $DATA_PATH/coverage.html"
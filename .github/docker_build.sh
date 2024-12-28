#!/bin/bash

# you can specify a unique tag for the image instead of "latest" with an argument to this script
# you can specify to build a "development" image by setting the DEV environment variable to anything (1, true, etc)

# Check for an input argument
if [ -n "$1" ]; then
    TAG=$1
else
    TAG="latest"
fi

# Navigate to the root of the project
PROJECT_DIR=$(dirname "$(dirname "$0")")
IMAGE_NAME=$(basename "$PWD")
cd "$PROJECT_DIR"

# build the image as required 
echo "Building the Docker image (tagged $TAG)... (from directory $(pwd)) (DEV TAG: $DEV)"

# Build the Docker image with the DEV environment variable
# buildkit and special mount from this tip -- https://stackoverflow.com/a/55761914
SSH_KEY_PATH="$(dirname ~/.ssh/id_rsa)/id_rsa"
if [ ! -f "$SSH_KEY_PATH" ]; then
    if [ -n "$GITHUB_ACTION" ]; then        # detected running in github
        echo "Running in GitHub Actions environment"
        
        # https://blog.oddbit.com/post/2019-02-24-docker-build-learns-about-secr/
        SSH_KEY_PATH="$HOME/.ssh/id_rsa"
    fi
fi
# if [ ! -f "$SSH_KEY_PATH/id_rsa" ] && [ ! -f "$SSH_KEY_PATH/.git-credentials" ]; then
if [ ! -f "$SSH_KEY_PATH" ] ; then
    echo "No SSH key (e.g. 'id_rsa') found in '$SSH_KEY_PATH'"
    echo "Please ensure you have an SSH path for the build.  It's required to get to the private repo for the Fyve API library."
    exit 1
fi

echo "SSH Key Path: $SSH_KEY_PATH"
DOCKER_BUILDKIT=1 docker build -t $IMAGE_NAME:$TAG --build-arg DEV=$DEV --build-arg MINIMUM_BUILD=True --ssh github_ssh_key=$SSH_KEY_PATH -f Dockerfile .
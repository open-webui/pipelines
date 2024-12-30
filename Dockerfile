FROM python:3.11-slim-bookworm AS base

# Use args
ARG MINIMUM_BUILD
ARG USE_CUDA
ARG USE_CUDA_VER
ARG USE_TEST=false
ARG PIPELINES_URLS=
ARG PIPELINES_REQUIREMENTS_PATH=

## Basis ##
ENV ENV=prod \
    PORT=9099 \
    # pass build args to the build
    USE_TEST=${USE_TEST} \
    MINIMUM_BUILD=${MINIMUM_BUILD} \
    USE_CUDA_DOCKER=${USE_CUDA} \
    USE_CUDA_DOCKER_VER=${USE_CUDA_VER}

# Install GCC and build tools. 
# These are kept in the final image to enable installing packages on the fly.
RUN apt-get update && \
    apt-get install -y gcc build-essential curl git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY ./requirements.txt .
COPY ./requirements-minimum.txt .
COPY ./requirements-test.txt .
RUN pip3 install uv
RUN if [ "$MINIMUM_BUILD" != "true" ]; then \
        if [ "$USE_CUDA_DOCKER" = "true" ]; then \
            pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/$USE_CUDA_DOCKER_VER --no-cache-dir; \
        else \
            pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu --no-cache-dir; \    
        fi \
    fi
RUN if [ "$MINIMUM_BUILD" = "true" ]; then \
        uv pip install --system -r requirements-minimum.txt --no-cache-dir; \
    else \
        uv pip install --system -r requirements.txt --no-cache-dir; \
    fi
RUN if [ "$USE_TEST" != "false" ]; then \
    uv pip install --system -r requirements-test.txt --no-cache-dir; \
fi

# Layer on for other components
FROM base AS app

ENV PIPELINES_URLS=${PIPELINES_URLS} \
    PIPELINES_REQUIREMENTS_PATH=${PIPELINES_REQUIREMENTS_PATH}

# Copy the application code
COPY . .

# Expose the port
ENV HOST="0.0.0.0"
ENV PORT="9099"

# we use a CMD so that it can be overriden by other tests on the container
CMD [ "bash", "start.sh" ]

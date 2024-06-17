FROM python:3.11-slim-bookworm as base

# Use args
ARG USE_CUDA
ARG USE_CUDA_VER

## Basis ##
ENV ENV=prod \
    PORT=9099 \
    # pass build args to the build
    USE_CUDA_DOCKER=${USE_CUDA} \
    USE_CUDA_DOCKER_VER=${USE_CUDA_VER}


# Install GCC and build tools
RUN apt-get update && \
    apt-get install -y gcc build-essential curl git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY ./requirements.txt .
RUN pip3 install uv && \
    if [ "$USE_CUDA" = "true" ]; then \
    pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/$USE_CUDA_DOCKER_VER --no-cache-dir; \
    else \
    pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu --no-cache-dir; \    
    fi
RUN uv pip install --system -r requirements.txt --no-cache-dir

# Copy the application code
COPY . .

# Expose the port
ENV HOST="0.0.0.0"
ENV PORT="9099"

ENTRYPOINT [ "bash", "start.sh" ]
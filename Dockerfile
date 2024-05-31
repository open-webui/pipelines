FROM python:3.11-slim-bookworm as base

# Install GCC and build tools
RUN apt-get update && \
    apt-get install -y gcc build-essential && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy the application code
COPY . /app
WORKDIR /app

# Install Python dependencies
RUN pip3 install --no-cache-dir -r requirements.txt

ENV HOST="0.0.0.0"
ENV PORT="9099"

ENTRYPOINT [ "bash", "start.sh" ]
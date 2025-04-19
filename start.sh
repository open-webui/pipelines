#!/usr/bin/env bash
PORT="${PORT:-9099}"
HOST="${HOST:-0.0.0.0}"
# Default value for PIPELINES_DIR
PIPELINES_DIR=${PIPELINES_DIR:-./pipelines}

UVICORN_LOOP="${UVICORN_LOOP:-auto}"

# Function to reset pipelines
reset_pipelines_dir() {
  if [ "$RESET_PIPELINES_DIR" = true ]; then
    echo "Resetting pipelines directory: $PIPELINES_DIR"

    # Check if the directory exists
    if [ -d "$PIPELINES_DIR" ]; then
      # Remove all contents of the directory
      rm -rf "${PIPELINES_DIR:?}"/*
      echo "All contents in $PIPELINES_DIR have been removed."

      # Optionally recreate the directory if needed
      mkdir -p "$PIPELINES_DIR"
      echo "$PIPELINES_DIR has been recreated."
    else
      echo "Directory $PIPELINES_DIR does not exist. No action taken."
    fi
  else
    echo "RESET_PIPELINES_DIR is not set to true. No action taken."
  fi
}

# Function to install requirements if requirements.txt is provided
install_requirements() {
  if [[ -f "$1" ]]; then
    echo "requirements.txt found at $1. Installing requirements..."
    pip install -r "$1"
  else
    echo "requirements.txt not found at $1. Skipping installation of requirements."
  fi
}

# Check if the PIPELINES_REQUIREMENTS_PATH environment variable is set and non-empty
if [[ -n "$PIPELINES_REQUIREMENTS_PATH" ]]; then
  # Install requirements from the specified requirements.txt
  install_requirements "$PIPELINES_REQUIREMENTS_PATH"
else
  echo "PIPELINES_REQUIREMENTS_PATH not specified. Skipping installation of requirements."
fi


# Function to download the pipeline files
download_pipelines() {
  local path=$1
  local destination=$2

  # Remove any surrounding quotes from the path
  path=$(echo "$path" | sed 's/^"//;s/"$//')

  echo "Downloading pipeline files from $path to $destination..."

  if [[ "$path" =~ ^https://github.com/.*/.*/blob/.* ]]; then
    # It's a single file
    dest_file=$(basename "$path")
    curl -L "$path?raw=true" -o "$destination/$dest_file"
  elif [[ "$path" =~ ^https://github.com/.*/.*/tree/.* ]]; then
    # It's a folder
    git_repo=$(echo "$path" | awk -F '/tree/' '{print $1}')
    subdir=$(echo "$path" | awk -F '/tree/' '{print $2}')
    git clone --depth 1 --filter=blob:none --sparse "$git_repo" "$destination"
    (
      cd "$destination" || exit
      git sparse-checkout set "$subdir"
    )
  elif [[ "$path" =~ \.py$ ]]; then
    # It's a single .py file (but not from GitHub)
    dest_file=$(basename "$path")
    curl -L "$path" -o "$destination/$dest_file"
  else
    echo "Invalid URL format: $path"
    exit 1
  fi
}

# Function to parse and install requirements from frontmatter
install_frontmatter_requirements() {
  local file=$1
  local file_content=$(cat "$1")
  # Extract the first triple-quoted block
  local first_block=$(echo "$file_content" | awk '/"""/{flag=!flag; if(flag) count++; if(count == 2) {exit}} flag' )

  # Check if the block contains requirements
  local requirements=$(echo "$first_block" | grep -i 'requirements:')

  if [ -n "$requirements" ]; then
    # Extract the requirements list
    requirements=$(echo "$requirements" | awk -F': ' '{print $2}' | tr ',' ' ' | tr -d '\r')

    # Construct and echo the pip install command
    local pip_command="pip install $requirements"
    echo "$pip_command"
    pip install $requirements
  else
    echo "No requirements found in frontmatter of $file."
  fi
}


# Parse command line arguments for mode
MODE="full"   # select a runmode ("setup", "run", "full" (setup + run))
while [[ "$#" -gt 0 ]]; do
  case $1 in
    --mode) MODE="$2"; shift ;;
    *) echo "Unknown parameter passed: $1"; exit 1 ;;
  esac
  shift
done
if [[ "$MODE" != "setup" && "$MODE" != "run" && "$MODE" != "full" ]]; then
  echo "Invalid script mode: $MODE"
  echo "  Example usage: './start.sh --mode [setup|run|full]' "
  exit 1
fi

# Function to handle different modes, added 1/29/24
if [[ "$MODE" == "setup" || "$MODE" == "full" ]]; then
  echo "Download + install Executed in mode: $MODE"

  reset_pipelines_dir
  if [[ -n "$PIPELINES_REQUIREMENTS_PATH" ]]; then
    install_requirements "$PIPELINES_REQUIREMENTS_PATH"
  else
    echo "PIPELINES_REQUIREMENTS_PATH not specified. Skipping installation of requirements."
  fi

  if [[ -n "$PIPELINES_URLS" ]]; then
    if [ ! -d "$PIPELINES_DIR" ]; then
      mkdir -p "$PIPELINES_DIR"
    fi

    IFS=';' read -ra ADDR <<< "$PIPELINES_URLS"
    for path in "${ADDR[@]}"; do
      download_pipelines "$path" "$PIPELINES_DIR"
    done

    for file in "$PIPELINES_DIR"/*; do
      if [[ -f "$file" ]]; then
        install_frontmatter_requirements "$file"
      fi
    done
  else
    echo "PIPELINES_URLS not specified. Skipping pipelines download and installation."
  fi
fi

if [[ "$MODE" == "run" || "$MODE" == "full" ]]; then
  echo "Running via Mode: $MODE"
  uvicorn main:app --host "$HOST" --port "$PORT" --forwarded-allow-ips '*' --loop "$UVICORN_LOOP"
fi


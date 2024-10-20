#!/usr/bin/env bash

# Check for required commands
command -v git >/dev/null 2>&1 || { echo >&2 "git is not installed. Aborting."; exit 1; }
command -v curl >/dev/null 2>&1 || { echo >&2 "curl is not installed. Aborting."; exit 1; }
command -v pip >/dev/null 2>&1 || { echo >&2 "pip is not installed. Aborting."; exit 1; }

PORT="${PORT:-9099}"
HOST="${HOST:-0.0.0.0}"
# Default value for PIPELINES_DIR
PIPELINES_DIR=${PIPELINES_DIR:-./pipelines}
# Default value for DEBUG_PIP
DEBUG_PIP=${DEBUG_PIP:-false}

# Function to reset pipelines
reset_pipelines_dir() {
  if [ "$RESET_PIPELINES_DIR" = true ]; then
    echo "Resetting pipelines directory: $PIPELINES_DIR"

    # Safety checks to prevent accidental deletion
    if [ -z "$PIPELINES_DIR" ] || [ "$PIPELINES_DIR" = "/" ]; then
      echo "Error: PIPELINES_DIR is not set correctly."
      exit 1
    fi

    # Check if the directory exists
    if [ -d "$PIPELINES_DIR" ]; then
      # Remove the directory completely
      rm -rf "$PIPELINES_DIR"
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
    if [ "$DEBUG_PIP" = true ]; then
      pip install -r "$1" || { echo "Failed to install requirements from $1"; exit 1; }
    else
      pip install -r "$1" >/dev/null 2>&1 || { echo "Failed to install requirements from $1"; exit 1; }
    fi
  else
    echo "requirements.txt not found at $1. Skipping installation of requirements."
  fi
}

# Function to download the pipeline files
download_pipelines() {
  local path="$1"
  local destination="$2"

  # Remove any surrounding quotes from the path
  path=$(echo "$path" | sed 's/^"//;s/"$//')

  echo "Downloading pipeline files from '$path' to '$destination'..."

  if [[ "$path" =~ ^https://github.com/.*/.*/blob/.* ]]; then
    # It's a single file
    dest_file=$(basename "$path")
    curl -L "$path?raw=true" -o "$destination/$dest_file" || { echo "Failed to download $path"; exit 1; }
  elif [[ "$path" =~ ^https://github.com/.*/.*/tree/.* ]]; then
    # It's a folder
    git_repo=$(echo "$path" | awk -F '/tree/' '{print $1}')
    subdir=$(echo "$path" | awk -F '/tree/' '{print $2}')
    git clone --depth 1 --filter=blob:none --sparse "$git_repo" "$destination" || { echo "Failed to clone $git_repo"; exit 1; }
    (
      cd "$destination" || exit
      git sparse-checkout set "$subdir"
    )
  elif [[ "$path" =~ ^https://github.com/.*/.*/archive/.*\.zip$ ]]; then
    curl -L "$path" -o "$destination/archive.zip" || { echo "Failed to download $path"; exit 1; }
    unzip "$destination/archive.zip" -d "$destination" || { echo "Failed to unzip archive.zip"; exit 1; }
    rm "$destination/archive.zip"
  elif [[ "$path" =~ \.py$ ]]; then
    # It's a single .py file (but not from GitHub)
    dest_file=$(basename "$path")
    curl -L "$path" -o "$destination/$dest_file" || { echo "Failed to download $path"; exit 1; }
  elif [[ "$path" =~ ^https://github.com/.*/.*$ ]]; then
    # Handle general GitHub repository URL
    git clone "$path" "$destination" || { echo "Failed to clone $path"; exit 1; }
  else
    echo "Invalid URL format: $path"
    exit 
  fi
}

# Function to parse and install requirements from frontmatter
install_frontmatter_requirements() {
  local file="$1"
  local file_content=$(cat "$file")
  # Extract the first triple-quoted block
  local first_block=$(echo "$file_content" | awk '/"""/{flag=!flag; if(flag) count++; if(count == 2) {exit}} flag' )

  # Check if the block contains requirements
  local requirements=$(echo "$first_block" | grep -i 'requirements:')

  if [ -n "$requirements" ]; then
    # Extract the requirements list
    requirements=$(echo "$requirements" | awk -F': ' '{print $2}' | tr ',' ' ' | tr -d '\r')

    # Split the requirements into an array
    IFS=' ' read -r -a requirements_array <<< "$requirements"

    # Install each requirement individually
    for requirement in "${requirements_array[@]}"; do
      echo "Installing $requirement"
      if [ "$DEBUG_PIP" = true ]; then
        pip install "$requirement" || { echo "Failed to install requirement: $requirement"; exit 1; }
      else
        pip install "$requirement" >/dev/null 2>&1 || { echo "Failed to install requirement: $requirement"; exit 1; }
      fi
    done
  else
    echo "No requirements found in frontmatter of $file."
  fi
}

# Check if the PIPELINES_REQUIREMENTS_PATH environment variable is set and non-empty
if [[ -n "$PIPELINES_REQUIREMENTS_PATH" ]]; then
  # Install requirements from the specified requirements.txt
  install_requirements "$PIPELINES_REQUIREMENTS_PATH"
else
  echo "PIPELINES_REQUIREMENTS_PATH not specified. Skipping installation of requirements."
fi

# Reset pipelines directory before any download or cloning operations
reset_pipelines_dir

# Check if the PIPELINES_URLS environment variable is set and non-empty
if [[ -n "$PIPELINES_URLS" ]]; then
  # Check if RESET_PIPELINES_DIR is not true and pipelines directory exists and is not empty
  if [ "$RESET_PIPELINES_DIR" != true ] && [ -d "$PIPELINES_DIR" ] && [ "$(ls -A "$PIPELINES_DIR")" ]; then
    echo "Pipelines directory $PIPELINES_DIR already exists and is not empty. Skipping download."
  else
    # Split PIPELINES_URLS by ';' and iterate over each path
    IFS=';' read -ra ADDR <<< "$PIPELINES_URLS"
    for path in "${ADDR[@]}"; do
      download_pipelines "$path" "$PIPELINES_DIR"
    done
  fi

  for file in "$PIPELINES_DIR"/*; do
    if [[ -f "$file" ]]; then
      install_frontmatter_requirements "$file"
    fi
  done
else
  echo "PIPELINES_URLS not specified. Skipping pipelines download and installation."
fi

exec uvicorn main:app --host "$HOST" --port "$PORT" --forwarded-allow-ips '*'
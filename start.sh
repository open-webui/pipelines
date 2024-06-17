#!/usr/bin/env bash
PORT="${PORT:-9099}"
HOST="${HOST:-0.0.0.0}"
# Default value for PIPELINES_DIR
PIPELINES_DIR=${PIPELINES_DIR:-./pipelines}

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

# Example usage of the function
reset_pipelines_dir

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



# Check if PIPELINES_URLS environment variable is set and non-empty
if [[ -n "$PIPELINES_URLS" ]]; then
  pipelines_dir="./pipelines"
  mkdir -p "$pipelines_dir"

  # Split PIPELINES_URLS by ';' and iterate over each path
  IFS=';' read -ra ADDR <<< "$PIPELINES_URLS"
  for path in "${ADDR[@]}"; do
    download_pipelines "$path" "$pipelines_dir"
  done

  for file in "$pipelines_dir"/*; do
    if [[ -f "$file" ]]; then
      install_frontmatter_requirements "$file"
    fi
  done
else
  echo "PIPELINES_URLS not specified. Skipping pipelines download and installation."
fi



# Start the server
uvicorn main:app --host "$HOST" --port "$PORT" --forwarded-allow-ips '*'

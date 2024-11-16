import aiohttp
import git
import os
import re
import sys
import subprocess
import shutil
import tempfile
import time
import zipfile

from fastapi import status, HTTPException
from urllib.parse import urlparse


from config import SUPPRESS_PIP_OUTPUT
from .logger import setup_logger

logger = setup_logger(__name__)


def parse_frontmatter(content):
    frontmatter = {}
    for line in content.split("\n"):
        if ":" in line:
            key, value = line.split(":", 1)
            frontmatter[key.strip().lower()] = value.strip()
    return frontmatter


async def reset_pipelines_dir(PIPELINES_DIR, RESET_PIPELINES_DIR):
    if RESET_PIPELINES_DIR:
        logger.info(f"Resetting pipelines directory: {PIPELINES_DIR}")
        if os.path.isdir(PIPELINES_DIR):
            max_retries = 3
            retry_delay = 1  # seconds

            for attempt in range(max_retries):
                try:
                    # First try to remove all contents inside the directory
                    for root, dirs, files in os.walk(PIPELINES_DIR, topdown=False):
                        for name in files:
                            file_path = os.path.join(root, name)
                            try:
                                os.remove(file_path)
                            except OSError:
                                continue
                        for name in dirs:
                            dir_path = os.path.join(root, name)
                            try:
                                os.rmdir(dir_path)
                            except OSError:
                                continue

                    # Then try to remove the main directory
                    try:
                        os.rmdir(PIPELINES_DIR)
                    except OSError:
                        pass

                    logger.debug(f"All contents in {PIPELINES_DIR} have been removed.")
                    break
                except Exception as e:
                    if attempt < max_retries - 1:
                        logger.warning(
                            f"Attempt {attempt + 1} failed, retrying in {retry_delay} seconds..."
                        )
                        time.sleep(retry_delay)
                        retry_delay *= 2  # exponential backoff
                    else:
                        logger.warning(
                            f"Warning: Could not fully remove directory: {e}"
                        )

        os.makedirs(PIPELINES_DIR, exist_ok=True)
        logger.info(f"{PIPELINES_DIR} has been recreated.")
    else:
        logger.debug("RESET_PIPELINES_DIR is not set to true. No action taken.")


def install_pip_packages(packages):
    """Install packages using pip.
    Args:
        packages: A list of packages or pip arguments.
    """
    if not packages:
        return
    logger.info(f"Installing packages: {packages}")
    cmd = [sys.executable, "-m", "pip", "install"] + packages
    subprocess.check_call(
        cmd,
        stdout=subprocess.DEVNULL if SUPPRESS_PIP_OUTPUT else None,
        stderr=subprocess.DEVNULL if SUPPRESS_PIP_OUTPUT else None,
    )


async def install_requirements(PIPELINES_REQUIREMENTS_PATH):
    if PIPELINES_REQUIREMENTS_PATH and os.path.isfile(PIPELINES_REQUIREMENTS_PATH):
        logger.info(f"Installing requirements from {PIPELINES_REQUIREMENTS_PATH}")
        install_pip_packages(["-r", PIPELINES_REQUIREMENTS_PATH])
    else:
        logger.debug(
            "PIPELINES_REQUIREMENTS_PATH not specified or file not found. Skipping installation of requirements."
        )


async def download_pipelines(PIPELINES_URLS, PIPELINES_DIR):
    if not PIPELINES_URLS or not PIPELINES_URLS.strip():
        logger.debug(
            "PIPELINES_URLS not specified. Skipping pipelines download and installation."
        )
        return

    if not os.path.exists(PIPELINES_DIR):
        os.makedirs(PIPELINES_DIR)

    # Split and clean URLs, filtering out empty strings
    pipeline_urls = [
        url.strip().strip('"')
        for url in PIPELINES_URLS.split(";")
        if url.strip().strip('"')
    ]

    if not pipeline_urls:
        logger.warning("No valid URLs found in PIPELINES_URLS. Skipping download.")
        return

    for url in pipeline_urls:
        await download_pipeline(url, PIPELINES_DIR)


async def download_pipeline(url, destination):
    url = url.strip('"')
    logger.info(f"Downloading pipeline files from {url} to {destination}...")

    if "github.com" in url:
        if re.match(r"^https://github\.com/.+/.+/blob/.+", url):
            logger.debug("Found single file from GitHub...")
            # It's a single file from GitHub
            raw_url = url.replace("/blob/", "/raw/")
            filename = os.path.basename(url)
            filepath = os.path.join(destination, filename)
            logger.debug(f"Downloading {raw_url} to {filepath}")
            await download_file(raw_url, filepath)
            await install_frontmatter_requirements(filepath)
        elif re.match(r"^https://github\.com/.+/.+/tree/.+", url):
            # It's a folder from GitHub
            logger.debug("Found folder from GitHub...")
            await download_github_folder(url, destination)
        elif re.match(r"^https://github\.com/.+/.+/archive/.+\.zip$", url):
            # Download and extract the zip archive
            logger.debug("Found zip archive from GitHub...")
            await download_and_extract_zip(url, destination)
        elif re.match(r"^https://github\.com/.+/.+$", url):
            # General GitHub repository URL
            logger.debug("Found GitHub repository...")
            await clone_github_repo(url, destination)
        else:
            logger.error(f"Invalid GitHub URL format: {url}")
    elif url.endswith(".py"):
        # Download single .py file (not from GitHub)
        filename = os.path.basename(url)
        filepath = os.path.join(destination, filename)
        await download_file(url, filepath)
        await install_frontmatter_requirements(filepath)
    else:
        logger.error(f"Invalid URL format: {url}")


async def download_file(url, filepath):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status != 200:
                logger.error(f"Failed to download file: {url}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to download file",
                )

            data = await response.read()
            with open(filepath, "wb") as f:
                f.write(data)
            logger.debug(f"Downloaded {filepath}")


async def download_file_to_folder(url: str, dest_folder: str):
    filename = os.path.basename(urlparse(url).path)
    if not filename.endswith(".py"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="URL must point to a Python file",
        )

    file_path = os.path.join(dest_folder, filename)
    await download_file(url, file_path)
    return file_path


async def download_and_extract_zip(url, destination):
    zip_path = os.path.join(destination, "archive.zip")
    await download_file(url, zip_path)
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(destination)
    os.remove(zip_path)
    logger.debug(f"Extracted archive to {destination}")


async def clone_github_repo(url, destination):
    try:
        logger.debug(f"Cloning repository {url} to {destination}...")
        git.Repo.clone_from(url, destination)
        logger.debug(f"Cloned repository {url} to {destination}")
    except Exception as e:
        logger.error(f"Failed to clone repository: {e}")


async def download_github_folder(url, destination):
    logger.debug(f"Downloading folder from GitHub: {url}")
    match = re.match(
        r"^https://github\.com/(?P<owner>.+)/(?P<repo>.+)/tree/(?P<branch>[^/]+)/(?P<subdir>.+)",
        url,
    )
    if not match:
        logger.warning(f"Invalid GitHub tree URL: {url}")
        return
    owner = match.group("owner")
    repo_name = match.group("repo")
    branch = match.group("branch")
    subdir = match.group("subdir")
    git_url = f"https://github.com/{owner}/{repo_name}.git"
    temp_dir = tempfile.mkdtemp()
    try:
        repo = git.Repo.clone_from(
            git_url,
            temp_dir,
            no_checkout=True,
            depth=1,
        )
        # Enable sparse checkout
        repo.git.config("core.sparseCheckout", "true")
        sparse_checkout_path = os.path.join(temp_dir, ".git", "info", "sparse-checkout")
        with open(sparse_checkout_path, "w") as f:
            f.write(f"{subdir}/*\n")
        # Checkout the branch
        repo.git.checkout(branch)
        src_path = os.path.join(temp_dir, subdir)
        if os.path.exists(src_path):
            for item in os.listdir(src_path):
                s = os.path.join(src_path, item)
                d = os.path.join(destination, item)
                if os.path.isdir(s):
                    shutil.copytree(s, d, dirs_exist_ok=True)
                else:
                    shutil.copy2(s, d)
            logger.debug(f"Downloaded folder {subdir} from {url}")
        else:
            logger.error(f"Subdirectory {subdir} not found in repository.")
    except Exception as e:
        logger.error(f"Failed to download folder: {e}")
    finally:
        shutil.rmtree(temp_dir)


async def install_frontmatter_requirements(file_path):
    with open(file_path, "r") as f:
        content = f.read()
    # Extract the first triple-quoted block
    if content.startswith('"""'):
        end = content.find('"""', 3)
        if end != -1:
            frontmatter_content = content[3:end]
            frontmatter = parse_frontmatter(frontmatter_content)
            requirements = frontmatter.get("requirements")
            if requirements:
                req_list = [req.strip() for req in requirements.split(",")]
                if req_list:
                    install_pip_packages(req_list)
                else:
                    logger.info(
                        f"No valid requirements found in frontmatter of {file_path}."
                    )
            else:
                logger.info(f"No requirements found in frontmatter of {file_path}.")
        else:
            logger.info(f"No frontmatter block closure in {file_path}.")
    else:
        logger.info(f"No frontmatter found in {file_path}.")


# Add a function to handle requirements installation from a file
async def install_requirements_from_file(module_path):  # Changed to async
    with open(module_path, "r") as f:
        content = f.read()
    if content.startswith('"""'):
        end = content.find('"""', 3)
        if end != -1:
            frontmatter_content = content[3:end]
            frontmatter = parse_frontmatter(frontmatter_content)
            requirements = frontmatter.get("requirements")
            if requirements:
                req_list = [req.strip() for req in requirements.split(",")]
                install_pip_packages(req_list)
            else:
                logger.info(f"No requirements found in frontmatter of {module_path}.")
        else:
            logger.info(f"No closing triple quotes for frontmatter in {module_path}.")
    else:
        logger.info(f"No frontmatter found in {module_path}.")

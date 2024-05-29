import re


def convert_to_raw_url(github_url):
    """
    Converts a GitHub URL to a raw URL.

    Example:
    https://github.com/user/repo/blob/branch/path/to/file.ext
    becomes
    https://raw.githubusercontent.com/user/repo/branch/path/to/file.ext

    Parameters:
    github_url (str): The GitHub URL to convert.

    Returns:
    str: The converted raw URL.
    """
    # Define the regular expression pattern
    pattern = r"https://github\.com/(.+?)/(.+?)/blob/(.+?)/(.+)"

    # Use the pattern to match and extract parts of the URL
    match = re.match(pattern, github_url)

    if match:
        user_repo = match.group(1) + "/" + match.group(2)
        branch = match.group(3)
        file_path = match.group(4)

        # Construct the raw URL
        raw_url = f"https://raw.githubusercontent.com/{user_repo}/{branch}/{file_path}"
        return raw_url

    # If the URL does not match the expected pattern, return the original URL or raise an error
    return github_url

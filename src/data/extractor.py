import re
import logging

logger = logging.getLogger(__name__)


def extract_set_urls(yaml_data):
    """
    Extract Mediux set URLs from YAML data.

    Args:
        yaml_data (str): YAML data string containing set URLs in comments

    Returns:
        set: Set of unique Mediux set URLs
    """
    set_urls = set()
    if not yaml_data:
        return set_urls

    lines = yaml_data.split("\n")
    for line in lines:
        match = re.search(r"#.*(https://mediux.pro/sets/\d+)", line)
        if match:
            set_urls.add(match.group(1))
    return set_urls

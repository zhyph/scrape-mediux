import os
import logging

logger = logging.getLogger(__name__)

# Determine the project root directory
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))

# Define common paths relative to project root
CACHE_DIR = os.path.join(PROJECT_ROOT, "out")
CACHE_FILE = os.path.join(CACHE_DIR, "tmdb_cache.pkl")
KOMETA_DIR = os.path.join(CACHE_DIR, "kometa")
BULK_FILE = os.path.join(CACHE_DIR, "ppsh-bulk.txt")
LOG_FILE = os.path.join(PROJECT_ROOT, "scrape-mediux.log")


def ensure_dir(path):
    """Ensure directory exists"""
    if not os.path.exists(path):
        try:
            os.makedirs(path)
            logger.debug(f"Created directory: {path}")
        except Exception as e:
            logger.error(f"Failed to create directory {path}: {e}")
    return path


# Ensure necessary directories exist
ensure_dir(CACHE_DIR)
ensure_dir(KOMETA_DIR)


def get_kometa_file(folder):
    """Get path for a kometa data file with given folder name"""
    return os.path.join(KOMETA_DIR, f"{folder}_data.yml")


def get_screenshot_dir(config_path=None):
    """Get screenshot directory path"""
    base_path = config_path if config_path else PROJECT_ROOT
    return ensure_dir(os.path.join(base_path, "screenshots"))


def get_config_file(config_path):
    """Get config file path"""
    return os.path.join(config_path, "config.json")

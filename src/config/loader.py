import os
import json
import logging
from .paths import get_config_file

logger = logging.getLogger(__name__)


def _validate_single_path(path, description="Path"):
    """
    Validate that a single path exists and is a directory.

    Args:
        path (str): Path to validate
        description (str): Description for error messages

    Raises:
        ValueError: If path is empty
        FileNotFoundError: If path does not exist
        NotADirectoryError: If path is not a directory
    """
    if not path:
        raise ValueError(f"{description} is not set. Please check your configuration.")
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{description} '{path}' does not exist. Please check your configuration."
        )
    if not os.path.isdir(path):
        raise NotADirectoryError(
            f"{description} '{path}' is not a directory. Please check your configuration."
        )


def validate_path(path, description="Path"):
    """
    Validate that a path or list of paths exist and are directories.

    Args:
        path (str or list): Path(s) to validate
        description (str): Description for error messages

    Raises:
        ValueError: If path is empty
        FileNotFoundError: If path does not exist
        NotADirectoryError: If path is not a directory
    """
    if isinstance(path, list):
        for p in path:
            _validate_single_path(p, f"{description} entry")
    else:
        _validate_single_path(path, description)


def load_config(config_path):
    """
    Load configuration from a JSON file.

    Args:
        config_path (str): Path to the directory containing config.json

    Returns:
        dict: Configuration options

    Raises:
        SystemExit: If config file is not found
    """
    full_config_path = get_config_file(config_path)
    if os.path.exists(full_config_path):
        logger.info(f"Loading configuration from {full_config_path}...")
        with open(full_config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        sanitized_config = {
            k: (
                "[REDACTED]"
                if k
                in [
                    "api_key",
                    "password",
                    "sonarr_api_key",
                    "username",
                    "nickname",
                    "sonarr_endpoint",
                ]
                else v
            )
            for k, v in config.items()
        }
        logger.debug(f"Configuration loaded: {sanitized_config}")
        return config
    logger.error(f"Configuration file not found at {full_config_path}.")
    exit(1)

"""
Base classes and utilities for Mediux Scraper.

This module provides common base classes and utilities used across the scraper.
"""

import logging
from collections import defaultdict
from typing import Optional, TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from modules.intelligent_cache import CacheManager


class CachedService:
    """Base class for services that need cache access.

    This class provides a standardized way to access the intelligent cache
    manager across all service classes, reducing code duplication.
    """

    def __init__(self, cache_manager: Optional["CacheManager"] = None):
        """Initialize cached service.

        Args:
            cache_manager: Optional cache manager to use. If None, gets global instance.
        """
        if cache_manager is not None:
            self.cache_manager = cache_manager
        else:
            from modules.intelligent_cache import get_cache_manager

            self.cache_manager = get_cache_manager()

        self.logger = logging.getLogger(self.__class__.__module__)


class ScraperContext:
    """Centralized context class for managing scraper state.

    This class encapsulates all global state variables and provides centralized
    access and management for the scraper components, eliminating scattered
    global variables across modules.
    """

    def __init__(self):
        """Initialize scraper context with default empty state."""
        self.new_data = defaultdict(dict)  # Stores new data collected during scraping
        self.cache = {}  # TMDB cache for API responses
        self.folder_bulk_data = {}  # Bulk data loaded from YAML files
        self.updated_titles_list = []  # List of titles that were updated
        self.fixed_titles_list = []  # List of titles that were fixed
        self.driver = None  # WebDriver instance

    def clear_new_data(self) -> None:
        """Clear all new data."""
        self.new_data.clear()

    def clear_cache(self) -> None:
        """Clear all cache data."""
        self.cache.clear()

    def clear_folder_bulk_data(self) -> None:
        """Clear all folder bulk data."""
        self.folder_bulk_data.clear()

    def set_driver(self, driver) -> None:
        """Set the WebDriver instance."""
        self.driver = driver

    def clear_driver(self) -> None:
        """Clear the WebDriver instance."""
        self.driver = None

    def clear_all(self) -> None:
        """Clear all state data."""
        self.clear_new_data()
        self.clear_cache()
        self.clear_folder_bulk_data()
        self.updated_titles_list.clear()
        self.fixed_titles_list.clear()
        self.clear_driver()

    def get_state_summary(self) -> dict:
        """Get summary of current state for logging."""
        return {
            "new_data_keys": list(self.new_data.keys()) if self.new_data else [],
            "cache_entries": len(self.cache),
            "folder_bulk_data_keys": (
                list(self.folder_bulk_data.keys()) if self.folder_bulk_data else []
            ),
            "updated_titles": len(self.updated_titles_list),
            "fixed_titles": len(self.fixed_titles_list),
        }


class YAMLService:
    """Centralized service for YAML operations.

    This class provides a unified interface for all YAML operations across the scraper,
    replacing scattered yaml_parser.load/dump calls with consistent service methods.
    """

    def __init__(self, yaml_parser=None):
        """Initialize YAML service.

        Args:
            yaml_parser: Optional YAML parser instance. If None, imports from config.
        """
        if yaml_parser is not None:
            self.yaml_parser = yaml_parser
        else:
            from modules.config import yaml_parser

            self.yaml_parser = yaml_parser

    def load_from_string(self, yaml_string: str) -> Optional[dict]:
        """Load YAML from string.

        Args:
            yaml_string: YAML content as string

        Returns:
            Parsed YAML as dictionary or None if parsing fails
        """
        try:
            return self.yaml_parser.load(yaml_string)
        except Exception as e:
            logger.error(f"Failed to parse YAML string: {e}")
            return None

    def load_from_file(self, file_path: str) -> Optional[dict]:
        """Load YAML from file.

        Args:
            file_path: Path to YAML file

        Returns:
            Parsed YAML as dictionary or None if loading fails
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            return self.load_from_string(content)
        except Exception as e:
            logger.error(f"Failed to load YAML from file {file_path}: {e}")
            return None

    def dump_to_string(self, data: dict) -> Optional[str]:
        """Dump data to YAML string.

        Args:
            data: Data to serialize

        Returns:
            YAML string or None if serialization fails
        """
        try:
            from io import StringIO

            string_stream = StringIO()
            self.yaml_parser.dump(data, string_stream)
            return string_stream.getvalue()
        except Exception as e:
            logger.error(f"Failed to dump data to YAML string: {e}")
            return None

    def dump_to_file(self, data: dict, file_path: str) -> bool:
        """Dump data to YAML file.

        Args:
            data: Data to serialize
            file_path: Path to output file

        Returns:
            True if successful, False otherwise
        """
        try:
            yaml_string = self.dump_to_string(data)
            if yaml_string is not None:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(yaml_string)
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to dump data to YAML file {file_path}: {e}")
            return False

    def format_yaml_string(self, data: dict) -> Optional[str]:
        """Format data to properly formatted YAML string with consistent formatting.

        Args:
            data: Data to format

        Returns:
            Formatted YAML string or None if formatting fails
        """
        try:
            yaml_string = self.dump_to_string(data)
            if yaml_string:
                # Apply additional formatting rules
                import re

                # Remove trailing spaces and normalize line endings
                yaml_string = re.sub(r"[ \t]+$", "", yaml_string, flags=re.MULTILINE)
                return yaml_string
            return None
        except Exception as e:
            logger.error(f"Failed to format YAML string: {e}")
            return None


class WebAutomationConstants:
    """Centralized constants for web automation operations.

    This class consolidates all magic numbers and constants used in web scraping
    operations, making them centralized and easily configurable.
    """

    # Timeout constants (in seconds)
    PAGE_LOAD_TIMEOUT = 300  # 5 minutes
    SCRIPT_TIMEOUT = 60  # Script execution timeout
    IMPLICIT_WAIT_TIMEOUT = 5  # Implicit element wait timeout
    ELEMENT_WAIT_TIMEOUT_SHORT = 5  # Quick element checks
    ELEMENT_WAIT_TIMEOUT_MEDIUM = 10  # Standard interactions
    ELEMENT_WAIT_TIMEOUT_LONG = 20  # Complex operations
    PROCESS_WAIT_TIMEOUT = 30  # Long-running processes

    # Sleep delays (in seconds)
    BRIEF_DELAY = 1  # Brief pauses between operations
    STANDARD_DELAY = 5  # Standard delays (page loads, refreshes)

    # Chrome options
    CHROME_REMOTE_DEBUGGING_PORT = 9222


class MediuxConfig:
    """Configuration constants for Mediux interactions.

    Centralizes all Mediux-specific URLs, API endpoints, and configuration values.
    """

    BASE_URL = "https://mediux.pro"

    @classmethod
    def get_movie_url(cls, tmdb_id: str) -> str:
        """Get movie URL for given TMDB ID."""
        return f"{cls.BASE_URL}/movies/{tmdb_id}"

    @classmethod
    def get_show_url(cls, tmdb_id: str) -> str:
        """Get TV show URL for given TMDB ID."""
        return f"{cls.BASE_URL}/shows/{tmdb_id}"

    @classmethod
    def get_set_url_pattern(cls) -> str:
        """Get regex pattern for Mediux set URLs."""
        return r"https://mediux\.pro/sets/\d+"

    # UI Text constants for status messages
    MOVIE_UPDATING_TEXT = "Updating movie data"
    MOVIE_UPDATE_SUCCESS = "Movie updated successfully"
    SHOW_UPDATING_TEXT = "Updating show data"
    SHOW_UPDATE_SUCCESS = "Show updated successfully"


class FileSystemConstants:
    """File system related constants and default paths.

    Centralizes common file system paths and directories used across the project.
    """

    # Output directories
    OUTPUT_DIR_DEFAULT = "./out"
    KOMETA_DIR = "./out/kometa"
    CONFIG_FILE_DEFAULT = "./config.json"

    # File extensions and patterns
    DATA_FILE_SUFFIX = "_data.yml"
    BULK_FILE_PATH = "./out/ppsh-bulk.txt"

    # Cache filenames
    INTELLIGENT_CACHE_FILENAME = "intelligent_cache.pkl"


class WebSelectors:
    """Centralized XPath and CSS selectors for web elements.

    This class organizes all XPath patterns and selectors used in web scraping,
    making them easy to find, update, and maintain.
    """

    # Button selectors
    SIGN_IN_BUTTON = "//button[contains(text(), 'Sign In')]"
    USER_BUTTON = "//button[contains(text(), '{nickname}')]"

    # Form selectors
    LOGIN_USERNAME_FIELD = "//*[@id=':r0:-form-item']"
    LOGIN_PASSWORD_FIELD = "//*[@id=':r1:-form-item']"
    LOGIN_FORM_SUBMIT = "//form/button"

    # Content and data selectors
    YAML_BUTTON = "//button[span[contains(text(), 'YAML')]]"
    YAML_CONTENT = "//code"
    REFRESH_SPINNER = "//svg[contains(@class, 'lucide-refresh-cw') and contains(@class, 'animate-spin')]"

    # Toast notification selectors
    UPDATE_TOAST = (
        "//li[contains(@class, 'toast')]//div[contains(text(), '{updating_text}')]"
    )
    SUCCESS_TOAST = (
        "//li[contains(@class, 'toast')]//div[contains(text(), '{success_text}')]"
    )

    # User and link selectors
    USER_LINK_PATTERN = "/user/{username}"

    @classmethod
    def get_user_button(cls, nickname: str) -> str:
        """Get XPath for user button with specific nickname."""
        return cls.USER_BUTTON.format(nickname=nickname)

    @classmethod
    def get_update_toast(cls, updating_text: str) -> str:
        """Get XPath for update toast with specific text."""
        return cls.UPDATE_TOAST.format(updating_text=updating_text)

    @classmethod
    def get_success_toast(cls, success_text: str) -> str:
        """Get XPath for success toast with specific text."""
        return cls.SUCCESS_TOAST.format(success_text=success_text)


class BaseService:
    """Base class for all service classes.

    Provides common functionality like logging that all services need.
    """

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__module__)


class MediaProcessingConfig:
    """Configuration class for media processing parameters.

    This class encapsulates all configuration parameters needed for processing
    individual media items, reducing the number of parameters passed to functions.
    """

    def __init__(
        self,
        api_key: str,
        sonarr_api_key: Optional[str] = None,
        sonarr_endpoint: Optional[str] = None,
        process_all: bool = False,
        retry_on_yaml_failure: bool = True,
        preferred_users: Optional[list] = None,
        excluded_users: Optional[list] = None,
        disable_season_fix: bool = False,
        remove_paths: Optional[list] = None,
    ):
        """Initialize media processing configuration.

        Args:
            api_key: TMDB API key
            sonarr_api_key: Sonarr API key (optional)
            sonarr_endpoint: Sonarr endpoint URL (optional)
            process_all: Whether to process all items regardless of existing YAML
            retry_on_yaml_failure: Whether to retry on YAML parsing failures
            preferred_users: List of preferred user names
            excluded_users: List of excluded user names
            disable_season_fix: Whether to disable automatic season fix
            remove_paths: List of YAML paths to remove during filtering
        """
        self.api_key = api_key
        self.sonarr_api_key = sonarr_api_key
        self.sonarr_endpoint = sonarr_endpoint
        self.process_all = process_all
        self.retry_on_yaml_failure = retry_on_yaml_failure
        self.preferred_users = preferred_users or []
        self.excluded_users = excluded_users or []
        self.disable_season_fix = disable_season_fix
        self.remove_paths = remove_paths or []
        self.logger = logging.getLogger(self.__class__.__module__)

"""
Configuration management module for Mediux Scraper.

This module handles all configuration loading, validation, and argument parsing
for the Mediux scraper application.
"""

import os
import argparse
import json
import logging
from typing import Dict, List, Any, Optional, Union

logger = logging.getLogger(__name__)


class ConfigManager:
    """Manages configuration loading from multiple sources with priority."""

    def __init__(self):
        self.config_path = "./config.json"
        self.logger = logging.getLogger(__name__)

    def load_config_file(self, config_path: str) -> Dict[str, Any]:
        """
        Load configuration from JSON file.

        Args:
            config_path: Path to the configuration file

        Returns:
            Dictionary containing configuration values

        Raises:
            FileNotFoundError: If config file doesn't exist
            json.JSONDecodeError: If config file is invalid JSON
        """
        full_config_path = os.path.join(config_path, "config.json")

        if not os.path.exists(full_config_path):
            raise FileNotFoundError(
                f"Configuration file not found at {full_config_path}"
            )

        self.logger.info(f"Loading configuration from {full_config_path}")

        with open(full_config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        # Sanitize sensitive information for logging
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
                    "discord_webhook_url",
                ]
                else v
            )
            for k, v in config.items()
        }

        self.logger.debug(f"Configuration loaded: {sanitized_config}")
        return config

    def _resolve_config_value(
        self,
        arg_val: Any,
        env_var_name: str,
        config_key: str,
        file_config: Dict[str, Any],
        default_val: Any = None,
        is_bool: bool = False,
        is_list: bool = False,
    ) -> Any:
        """
        Resolve configuration value from multiple sources in priority order:
        1. Command line argument
        2. Environment variable
        3. Configuration file
        4. Default value

        Args:
            arg_val: Value from command line argument
            env_var_name: Environment variable name
            config_key: Key in configuration file
            file_config: Configuration dictionary from file
            default_val: Default value if none found
            is_bool: Whether the value should be treated as boolean
            is_list: Whether the value should be treated as a list

        Returns:
            Resolved configuration value
        """
        # Priority 1: Command line argument
        if arg_val is not None:
            if is_bool:
                return bool(arg_val)
            return arg_val

        # Priority 2: Environment variable
        env_val = os.environ.get(env_var_name)
        if env_val is not None:
            if is_bool:
                return env_val.lower() in ["true", "1", "yes"]
            if is_list:
                return [item.strip() for item in env_val.split(",")] if env_val else []
            return env_val

        # Priority 3: Configuration file
        file_val = file_config.get(config_key)
        if file_val is not None:
            return file_val

        # Priority 4: Default value
        return default_val

    def setup_logging(self, log_level: str = "INFO") -> None:
        """Setup enhanced logging configuration with better formatting and colors."""
        import sys
        from colorama import init, Fore, Back, Style

        # Initialize colorama for cross-platform color support
        init(autoreset=True)

        logging_levels = {
            "INFO": 20,
            "DEBUG": 10,
            "ERROR": 40,
            "WARNING": 30,
            "NOTSET": 0,
        }

        # Custom formatter with colors and better formatting
        class ColoredFormatter(logging.Formatter):
            """Custom formatter with colors and enhanced formatting."""

            def __init__(self):
                super().__init__()
                self.colors = {
                    "DEBUG": Fore.CYAN,
                    "INFO": Fore.GREEN,
                    "WARNING": Fore.YELLOW,
                    "ERROR": Fore.RED,
                    "CRITICAL": Fore.RED + Back.WHITE,
                    "USER": Fore.MAGENTA,
                    "DETAIL": Fore.BLUE,
                }
                self.reset = Style.RESET_ALL

            def format(self, record):
                # Add colors for console output
                color = self.colors.get(record.levelname, Fore.WHITE)

                # Custom formatting based on log level
                if record.levelname == "INFO":
                    formatted_time = (
                        f"{Fore.BLUE}{self.formatTime(record, '%H:%M:%S')}{self.reset}"
                    )
                    return f"{formatted_time} {Fore.GREEN}INFO{self.reset} {color}{record.getMessage()}{self.reset}"
                elif record.levelname == "WARNING":
                    return f"{Fore.YELLOW}⚠️  WARNING{self.reset} {color}{record.getMessage()}{self.reset}"
                elif record.levelname == "ERROR":
                    return f"{Fore.RED}❌ ERROR{self.reset} {color}{record.getMessage()}{self.reset}"
                elif record.levelname == "USER":
                    return f"{Fore.MAGENTA}👤 USER{self.reset} {color}{record.getMessage()}{self.reset}"
                elif record.levelname == "DETAIL":
                    return f"{Fore.BLUE}🔧 DETAIL{self.reset} {color}{record.getMessage()}{self.reset}"
                else:
                    return (
                        f"{color}{record.levelname}{self.reset} {record.getMessage()}"
                    )

        # File formatter (no colors)
        file_formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )

        # Console handler with colors
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(ColoredFormatter())

        # File handler without colors
        file_handler = logging.FileHandler(
            "scrape-mediux.log", mode="a", encoding="utf-8"
        )
        file_handler.setFormatter(file_formatter)

        # Setup root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(
            logging_levels.get(
                os.environ.get("LOG_LEVEL", log_level).upper(), logging.INFO
            )
        )

        # Clear existing handlers and add our custom ones
        root_logger.handlers.clear()
        root_logger.addHandler(console_handler)
        root_logger.addHandler(file_handler)

        # Custom log levels for user experience
        logging.addLevelName(25, "USER")  # Between INFO (20) and WARNING (30)
        logging.addLevelName(15, "DETAIL")  # Between DEBUG (10) and INFO (20)

    def create_argument_parser(self) -> argparse.ArgumentParser:
        """Create and configure the argument parser."""
        parser = argparse.ArgumentParser(
            description="Scrape Mediux and create bulk data file with optional YAML field filtering."
        )

        # Configuration and paths
        parser.add_argument(
            "--config_path",
            type=str,
            help="Directory to configuration file, defaults to /config",
            default=os.environ.get("CONFIG_PATH", "/config"),
        )
        parser.add_argument(
            "--root_folder",
            type=str,
            help="Root folder(s) containing subfolders with media IDs. Can be a single path or multiple paths separated by commas.",
        )

        # API and authentication
        parser.add_argument("--api_key", type=str, help="TMDB API key")
        parser.add_argument("--username", type=str, help="Mediux username")
        parser.add_argument("--password", type=str, help="Mediux password")
        parser.add_argument("--nickname", type=str, help="Mediux nickname")
        parser.add_argument(
            "--profile_path", type=str, help="Path to Chrome user profile"
        )

        # External services
        parser.add_argument("--sonarr_api_key", type=str, help="Sonarr API key")
        parser.add_argument("--sonarr_endpoint", type=str, help="Sonarr API endpoint")
        parser.add_argument(
            "--discord_webhook_url",
            type=str,
            help="Discord webhook URL for notifications",
        )

        # Plex integration
        parser.add_argument(
            "--plex_url",
            type=str,
            help="Plex server URL (optional, enables Plex API mode if provided)",
        )
        parser.add_argument(
            "--plex_token",
            type=str,
            help="Plex API token (optional, enables Plex API mode if provided)",
        )
        parser.add_argument(
            "--plex_libraries",
            nargs="*",
            help="List of Plex library names to scan (optional, enables Plex API mode if provided)",
        )

        # Processing options
        parser.add_argument(
            "--folders",
            nargs="*",
            help="Specific sub-folders within root_folder(s) to process (optional)",
        )
        parser.add_argument(
            "--headless",
            action=argparse.BooleanOptionalAction,
            help="Run Selenium in headless mode",
        )
        parser.add_argument(
            "--process_all",
            action=argparse.BooleanOptionalAction,
            help="Process all items regardless of existing data",
        )
        parser.add_argument(
            "--retry_on_yaml_failure",
            action=argparse.BooleanOptionalAction,
            help="Retry scraping if YAML extraction fails initially",
        )

        # User preferences
        parser.add_argument(
            "--preferred_users",
            nargs="*",
            help="List of preferred Mediux users for YAML data",
        )
        parser.add_argument(
            "--excluded_users",
            nargs="*",
            help="List of Mediux users to exclude for YAML data",
        )

        # Technical options
        parser.add_argument(
            "--chromedriver_path", type=str, help="Path to the ChromeDriver executable"
        )
        parser.add_argument(
            "--output_dir", type=str, help="Directory to copy the output files to"
        )
        parser.add_argument(
            "--cron", type=str, help="Cron expression for scheduling the script"
        )

        # Special modes
        parser.add_argument(
            "--copy_only",
            action="store_true",
            help="Only copy files to the output_dir and exit",
        )
        parser.add_argument(
            "--disable_season_fix",
            action="store_true",
            help="Disable automatic fix for malformed seasons YAML structure",
        )

        # Data processing
        parser.add_argument(
            "--remove_paths",
            nargs="*",
            help="List of YAML field paths to remove (others will be kept). Use dot notation with wildcards. Examples: *.url_background, seasons.*.url_poster. Note: *.field matches all instances, use specific paths for selective removal. WARNING: Some YAML comments may be lost when filtering is applied.",
        )

        # Cache management
        parser.add_argument(
            "--disable_cache",
            action="store_true",
            help="Disable loading and saving of caches (fresh start each time)",
        )
        parser.add_argument(
            "--clear_cache",
            action="store_true",
            help="Clear existing cache files before running",
        )
        parser.add_argument(
            "--cache_dir",
            type=str,
            default="./out",
            help="Directory to store cache files (default: ./out)",
        )

        return parser

    def parse_arguments_and_load_config(self) -> Dict[str, Any]:
        """
        Parse command line arguments and load configuration from all sources.

        Returns:
            Dictionary containing all resolved configuration values
        """
        parser = self.create_argument_parser()
        args = parser.parse_args()

        # Load file configuration
        try:
            file_config = self.load_config_file(args.config_path)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            self.logger.error(f"Failed to load configuration: {e}")
            raise

        # Process root_folder (can be comma-separated string or list)
        root_folder_val = self._resolve_config_value(
            arg_val=args.root_folder,
            env_var_name="ROOT_FOLDER",
            config_key="root_folder",
            file_config=file_config,
        )

        if isinstance(root_folder_val, str):
            root_folder_val = [
                rf.strip() for rf in root_folder_val.split(",") if rf.strip()
            ]
        elif root_folder_val is None:
            root_folder_val = []

        # Build complete configuration dictionary
        app_config = {
            "config_path_val": args.config_path,
            "root_folder_val": root_folder_val,
            "api_key": self._resolve_config_value(
                arg_val=args.api_key,
                env_var_name="API_KEY",
                config_key="api_key",
                file_config=file_config,
            ),
            "username": self._resolve_config_value(
                arg_val=args.username,
                env_var_name="USERNAME",
                config_key="username",
                file_config=file_config,
            ),
            "password": self._resolve_config_value(
                arg_val=args.password,
                env_var_name="PASSWORD",
                config_key="password",
                file_config=file_config,
            ),
            "nickname": self._resolve_config_value(
                arg_val=args.nickname,
                env_var_name="NICKNAME",
                config_key="nickname",
                file_config=file_config,
            ),
            "profile_path": self._resolve_config_value(
                arg_val=args.profile_path,
                env_var_name="PROFILE_PATH",
                config_key="profile_path",
                file_config=file_config,
                default_val="/profile",
            ),
            "sonarr_api_key": self._resolve_config_value(
                arg_val=args.sonarr_api_key,
                env_var_name="SONARR_API_KEY",
                config_key="sonarr_api_key",
                file_config=file_config,
            ),
            "sonarr_endpoint": self._resolve_config_value(
                arg_val=args.sonarr_endpoint,
                env_var_name="SONARR_ENDPOINT",
                config_key="sonarr_endpoint",
                file_config=file_config,
            ),
            "discord_webhook_url": self._resolve_config_value(
                arg_val=args.discord_webhook_url,
                env_var_name="DISCORD_WEBHOOK_URL",
                config_key="discord_webhook_url",
                file_config=file_config,
            ),
            "plex_url": self._resolve_config_value(
                arg_val=args.plex_url,
                env_var_name="PLEX_URL",
                config_key="plex_url",
                file_config=file_config,
            ),
            "plex_token": self._resolve_config_value(
                arg_val=args.plex_token,
                env_var_name="PLEX_TOKEN",
                config_key="plex_token",
                file_config=file_config,
            ),
            "plex_libraries": self._resolve_config_value(
                arg_val=args.plex_libraries,
                env_var_name="PLEX_LIBRARIES",
                config_key="plex_libraries",
                file_config=file_config,
                is_list=True,
                default_val=[],
            ),
            "selected_folders": self._resolve_config_value(
                arg_val=args.folders,
                env_var_name="FOLDERS",
                config_key="folders",
                file_config=file_config,
                default_val=[],
                is_list=True,
            ),
            "headless": self._resolve_config_value(
                arg_val=args.headless,
                env_var_name="HEADLESS",
                config_key="headless",
                file_config=file_config,
                default_val=True,
                is_bool=True,
            ),
            "process_all": self._resolve_config_value(
                arg_val=args.process_all,
                env_var_name="PROCESS_ALL",
                config_key="process_all",
                file_config=file_config,
                default_val=False,
                is_bool=True,
            ),
            "retry_on_yaml_failure": self._resolve_config_value(
                arg_val=args.retry_on_yaml_failure,
                env_var_name="RETRY_ON_YAML_FAILURE",
                config_key="retry_on_yaml_failure",
                file_config=file_config,
                default_val=False,
                is_bool=True,
            ),
            "preferred_users": self._resolve_config_value(
                arg_val=args.preferred_users,
                env_var_name="PREFERRED_USERS",
                config_key="preferred_users",
                file_config=file_config,
                is_list=True,
                default_val=[],
            ),
            "excluded_users": self._resolve_config_value(
                arg_val=args.excluded_users,
                env_var_name="EXCLUDED_USERS",
                config_key="excluded_users",
                file_config=file_config,
                is_list=True,
                default_val=[],
            ),
            "chromedriver_path": self._resolve_config_value(
                arg_val=args.chromedriver_path,
                env_var_name="CHROMEDRIVER_PATH",
                config_key="chromedriver_path",
                file_config=file_config,
            ),
            "output_dir_val": self._resolve_config_value(
                arg_val=args.output_dir,
                env_var_name="OUTPUT_DIR",
                config_key="output_dir",
                file_config=file_config,
            ),
            "cron_expression": self._resolve_config_value(
                arg_val=args.cron,
                env_var_name="CRON_EXPRESSION",
                config_key="cron",
                file_config=file_config,
            ),
            "copy_only": self._resolve_config_value(
                arg_val=args.copy_only,
                env_var_name="COPY_ONLY",
                config_key="copy_only",
                file_config=file_config,
                default_val=False,
                is_bool=True,
            ),
            "disable_season_fix": self._resolve_config_value(
                arg_val=args.disable_season_fix,
                env_var_name="DISABLE_SEASON_FIX",
                config_key="disable_season_fix",
                file_config=file_config,
                default_val=False,
                is_bool=True,
            ),
            "remove_paths": self._resolve_config_value(
                arg_val=args.remove_paths,
                env_var_name="REMOVE_PATHS",
                config_key="remove_paths",
                file_config=file_config,
                is_list=True,
                default_val=[],
            ),
            "tz": file_config.get("TZ"),
            "disable_cache": self._resolve_config_value(
                arg_val=args.disable_cache,
                env_var_name="DISABLE_CACHE",
                config_key="disable_cache",
                file_config=file_config,
                default_val=False,
                is_bool=True,
            ),
            "clear_cache": self._resolve_config_value(
                arg_val=args.clear_cache,
                env_var_name="CLEAR_CACHE",
                config_key="clear_cache",
                file_config=file_config,
                default_val=False,
                is_bool=True,
            ),
            "cache_dir": self._resolve_config_value(
                arg_val=args.cache_dir,
                env_var_name="CACHE_DIR",
                config_key="cache_dir",
                file_config=file_config,
                default_val="./out",
            ),
        }

        return app_config


def validate_path(path: Union[str, List[str]], description: str = "Path") -> None:
    """
    Validate that a path or list of paths exists and is a directory.

    Args:
        path: Path or list of paths to validate
        description: Description of the path for error messages

    Raises:
        ValueError: If path is not set
        FileNotFoundError: If path doesn't exist
        NotADirectoryError: If path is not a directory
    """
    if isinstance(path, list):
        for p in path:
            _validate_single_path(p, f"{description} entry")
    else:
        _validate_single_path(path, description)


def _validate_single_path(path: str, description: str) -> None:
    """
    Validate a single path.

    Args:
        path: Path to validate
        description: Description of the path for error messages

    Raises:
        ValueError: If path is not set
        FileNotFoundError: If path doesn't exist
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

#!/usr/bin/env python3
# filepath: /home/zhyp/Code/scrape-mediux/main.py
import os
import argparse
import atexit
import logging
import sys

# Add src directory to path if not already there
if os.path.abspath("./src") not in sys.path:
    sys.path.insert(0, os.path.abspath("./src"))

# Configure logging
logging_dict = {
    "INFO": 20,
    "DEBUG": 10,
    "ERROR": 40,
    "WARNING": 30,
    "NOTSET": 0,
}

logging.basicConfig(
    level=logging_dict.get(os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("scrape-mediux.log", mode="a", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# Configure YAML parser
from ruamel.yaml import YAML

yaml = YAML()
yaml.allow_duplicate_keys = True

# Constants
from src.config.paths import CACHE_FILE

CONFIG_FILE = "config.json"

# Import modules
from src.config.loader import load_config, validate_path
from src.runner.processor import run
from src.runner.scheduler import schedule_run
from src.data.bulk import write_data_to_files


def setup_argument_parser():
    """Set up and return the argument parser"""
    parser = argparse.ArgumentParser(
        description="Scrape Mediux and create bulk data file."
    )
    parser.add_argument(
        "--config_path",
        type=str,
        help="Directory to configuration file, defaults to /config",
        default=os.environ.get("CONFIG_PATH", "/config"),
    )
    parser.add_argument(
        "--root_folder",
        type=str,
        help="Root folder containing subfolders with IMDb IDs",
    )
    parser.add_argument("--api_key", type=str, help="TMDB API key")
    parser.add_argument("--username", type=str, help="Mediux username")
    parser.add_argument("--password", type=str, help="Mediux password")
    parser.add_argument("--nickname", type=str, help="Mediux nickname")
    parser.add_argument(
        "--profile_path",
        type=str,
        help="Path to Chrome user profile",
    )
    parser.add_argument("--sonarr_api_key", type=str, help="Sonarr API key")
    parser.add_argument("--sonarr_endpoint", type=str, help="Sonarr API endpoint")
    parser.add_argument(
        "--folders",
        nargs="*",
        help="Specific folders to search for IMDb IDs (optional)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run Selenium in headless mode",
        default=None,
    )
    parser.add_argument(
        "--cron",
        type=str,
        help="Cron expression for scheduling the script",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        help="Directory to copy the output files to",
    )
    parser.add_argument(
        "--process_all",
        action=argparse.BooleanOptionalAction,
        help="Process all items regardless of whether they have been processed before",
    )
    parser.add_argument(
        "--chromedriver_path",
        type=str,
        help="Path to the ChromeDriver executable",
    )
    parser.add_argument(
        "--retry_on_yaml_failure",
        action="store_true",
        help="Retry by reloading the page if YAML button exists but an error occurs",
        default=None,
    )
    return parser


def _get_config_value(arg_value, config_key, config, default=None):
    """Helper to get config value from args or config dict with optional default"""
    return arg_value if arg_value is not None else config.get(config_key, default)


def merge_config_with_args(args, config):
    """Merge CLI arguments with config file values"""
    run_config = {
        "config_path": args.config_path,
        "root_folder": _get_config_value(args.root_folder, "root_folder", config),
        "api_key": _get_config_value(args.api_key, "api_key", config),
        "username": _get_config_value(args.username, "username", config),
        "password": _get_config_value(args.password, "password", config),
        "nickname": _get_config_value(args.nickname, "nickname", config),
        "profile_path": _get_config_value(
            args.profile_path, "profile_path", config, "/profile"
        ),
        "sonarr_api_key": _get_config_value(
            args.sonarr_api_key, "sonarr_api_key", config
        ),
        "sonarr_endpoint": _get_config_value(
            args.sonarr_endpoint, "sonarr_endpoint", config
        ),
        "selected_folders": _get_config_value(args.folders, "folders", config),
        "headless": _get_config_value(args.headless, "headless", config, True),
        "cron_expression": _get_config_value(args.cron, "cron", config),
        "output_dir": _get_config_value(args.output_dir, "output_dir", config),
        "process_all": _get_config_value(
            args.process_all, "process_all", config, False
        ),
        "chromedriver_path": _get_config_value(
            args.chromedriver_path, "chromedriver_path", config
        ),
        "retry_on_yaml_failure": _get_config_value(
            args.retry_on_yaml_failure, "retry_on_yaml_failure", config, False
        ),
    }

    if "TZ" in config:
        os.environ["TZ"] = config["TZ"]

    return run_config


def setup_exit_handler(root_folder, output_dir):
    """Set up exit handler for file writing"""
    global new_data, cache, folder_bulk_data
    new_data, cache, folder_bulk_data = {}, {}, {}

    def exit_handler():
        if root_folder:
            try:
                write_data_to_files(
                    new_data=new_data,
                    root_folder=root_folder,
                    output_dir=output_dir,
                    yaml_parser=yaml,
                    cache=cache,
                    cache_file=CACHE_FILE,
                )
            except Exception as e:
                logger.error(f"Error in exit handler: {e}")

    if root_folder:
        try:
            validate_path(root_folder, "Root folder")
            atexit.register(exit_handler)
        except Exception as e:
            logger.error(f"Error during validation of root folder: {e}")
            return False
    else:
        logger.warning(
            "Root folder is not set. Skipping atexit registration for write_data_to_files."
        )
    return True


def main():
    """Main entry point for the scraper"""
    parser = setup_argument_parser()
    args = parser.parse_args()

    config = load_config(args.config_path)
    merged_config = merge_config_with_args(args, config)

    setup_exit_handler(merged_config["root_folder"], merged_config["output_dir"])

    try:
        if merged_config["cron_expression"]:
            schedule_run(
                cron_expression=merged_config["cron_expression"],
                api_key=merged_config["api_key"],
                username=merged_config["username"],
                password=merged_config["password"],
                profile_path=merged_config["profile_path"],
                nickname=merged_config["nickname"],
                sonarr_api_key=merged_config["sonarr_api_key"],
                sonarr_endpoint=merged_config["sonarr_endpoint"],
                root_folder=merged_config["root_folder"],
                selected_folders=merged_config["selected_folders"],
                headless=merged_config["headless"],
                process_all=merged_config["process_all"],
                chromedriver_path=merged_config["chromedriver_path"],
                retry_on_yaml_failure=merged_config["retry_on_yaml_failure"],
                config_path=merged_config["config_path"],
                output_dir=merged_config["output_dir"],
            )
        else:
            global new_data, cache, folder_bulk_data
            new_data, cache, folder_bulk_data = run(
                api_key=merged_config["api_key"],
                username=merged_config["username"],
                password=merged_config["password"],
                profile_path=merged_config["profile_path"],
                nickname=merged_config["nickname"],
                sonarr_api_key=merged_config["sonarr_api_key"],
                sonarr_endpoint=merged_config["sonarr_endpoint"],
                root_folder=merged_config["root_folder"],
                selected_folders=merged_config["selected_folders"],
                headless=merged_config["headless"],
                process_all=merged_config["process_all"],
                chromedriver_path=merged_config["chromedriver_path"],
                retry_on_yaml_failure=merged_config["retry_on_yaml_failure"],
                config_path=merged_config["config_path"],
            )
    except Exception as e:
        logger.error(f"Unhandled error: {e}")
        exit(1)


if __name__ == "__main__":
    main()

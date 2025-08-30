"""
Main application entry point for Mediux Scraper.

This module provides a simple entry point that imports and orchestrates
the various modules of the Mediux scraper application.
"""

import logging
import os
import uuid

from modules.base import FileSystemConstants
from modules.config import ConfigManager
from modules.orchestrator import run
from modules.scheduler import schedule_run

# Set up basic environment configuration
os.environ["PLEXAPI_HEADER_IDENTIFIER"] = uuid.uuid3(
    uuid.NAMESPACE_DNS, "Scrape-Mediux"
).hex
os.environ["PLEXAPI_HEADER_DEVICE_NAME"] = "Scrape-Mediux"
os.environ["PLEXAPI_HEADER_PROVIDES"] = ""


def main():
    """Main entry point."""

    # Setup logging
    config_manager = ConfigManager()
    config_manager.setup_logging()

    # Get logger after custom setup
    logger = logging.getLogger(__name__)

    # Parse configuration
    app_settings = config_manager.parse_arguments_and_load_config()

    # Handle copy-only mode
    if app_settings.get("copy_only"):
        if not app_settings["output_dir"]:
            logger.error("No output_dir specified for --copy_only mode.")
            exit(1)
        from modules.file_manager import FileWriter

        file_writer = FileWriter()
        file_writer._copy_to_output_dir(app_settings["output_dir"])
        logger.info("Copy-only mode complete. Exiting.")
        exit(0)

    # Set timezone if provided
    if app_settings.get("tz"):
        os.environ["TZ"] = app_settings["tz"]

    try:
        run_args = {
            "api_key": app_settings["api_key"],
            "username": app_settings["username"],
            "password": app_settings["password"],
            "profile_path": app_settings["profile_path"],
            "nickname": app_settings["nickname"],
            "sonarr_api_key": app_settings["sonarr_api_key"],
            "sonarr_endpoint": app_settings["sonarr_endpoint"],
            "config_path": app_settings["config_path"],
            "output_dir_global": app_settings["output_dir"],
            "discord_webhook_url_global": app_settings.get("discord_webhook_url"),
            "headless": app_settings["headless"],
            "process_all": app_settings["process_all"],
            "chromedriver_path": app_settings["chromedriver_path"],
            "retry_on_yaml_failure": app_settings["retry_on_yaml_failure"],
            "preferred_users": app_settings["preferred_users"],
            "excluded_users": app_settings["excluded_users"],
            "disable_season_fix": app_settings["disable_season_fix"],
            "remove_paths": app_settings["remove_paths"],
            "plex_url": app_settings.get("plex_url"),
            "plex_token": app_settings.get("plex_token"),
            "plex_libraries": app_settings.get("plex_libraries"),
            "mediux_url": app_settings.get("mediux_url"),
            "disable_cache": app_settings.get("disable_cache", False),
            "clear_cache": app_settings.get("clear_cache", False),
            "cache_dir": app_settings.get(
                "cache_dir", FileSystemConstants.OUTPUT_DIR_DEFAULT
            ),
        }

        if app_settings["cron_expression"]:
            schedule_run(
                cron_expression=app_settings["cron_expression"],
                args_dict=run_args,
            )
        else:
            run(**run_args)

    except SystemExit:
        logger.info("SystemExit called, script terminating.")
        raise
    except KeyboardInterrupt:
        logger.info("Script interrupted by user (KeyboardInterrupt).")
    except Exception as e:
        logger.error(f"Unhandled error in __main__: {e}", exc_info=True)
        exit(1)


if __name__ == "__main__":
    main()

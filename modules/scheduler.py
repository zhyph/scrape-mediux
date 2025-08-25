"""
Scheduler module for Mediux Scraper.

This module handles script execution scheduling using cron expressions.
"""

import os
import logging
from datetime import datetime
from time import sleep
from croniter import croniter

logger = logging.getLogger(__name__)


def schedule_run(*, cron_expression, args_dict):
    """Schedule script execution using cron expression."""
    logger.info(f"Scheduling script with cron expression: {cron_expression}")
    base_time = datetime.now()
    logger.info(f"Current time: {base_time}")
    logger.info(
        f"Environment Timezone: {os.environ.get('TZ', 'None is set, use the env from the docker compose or docker run to provide your TZ')}"
    )
    cron_iter = croniter(cron_expression, base_time)
    next_run_time = cron_iter.get_next(datetime)
    logger.info(f"Next scheduled run at: {next_run_time}")

    while True:
        now = datetime.now()
        if now >= next_run_time:
            logger.info("Scheduled run started...")
            try:
                # Import the run function here to avoid circular imports
                from modules.orchestrator import run
                run(**args_dict)
                write_data_to_files()
            except Exception as e:
                logger.error(f"Error during scheduled run: {e}")
            next_run_time = cron_iter.get_next(datetime)
            logger.info(f"Next scheduled run at: {next_run_time}")
        sleep(60)


def write_data_to_files():
    """Write collected data to files."""
    # Import globals and functions here to avoid circular imports
    from modules.orchestrator import (
        new_data, cache, root_folder_global, output_dir_global, cache_config
    )
    from modules.file_manager import FileWriter

    if not root_folder_global:
        logger.error("Root folder is not set. Cannot write data.")
        return

    from modules.config import validate_path
    validate_path(path=root_folder_global, description="Root folder")
    logger.info("Writing data to files...")

    file_writer = FileWriter()

    # Save intelligent cache if not disabled
    if cache_config.should_save_cache():
        from modules.intelligent_cache import get_cache_manager

        intelligent_cache_manager = get_cache_manager()
        intelligent_cache_manager.save_cache(
            cache_config.get_cache_file_path("intelligent_cache.pkl")
        )

    file_writer.write_data_to_files(
        new_data=new_data,
        root_folder_global=root_folder_global,
        cache=cache if cache_config.should_save_cache() else {},
        cache_file=(
            cache_config.get_cache_file_path("tmdb_cache.pkl")
            if cache_config.should_save_cache()
            else None
        ),
        output_dir_global=output_dir_global,
    )

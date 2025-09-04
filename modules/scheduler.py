"""
Scheduler module for Mediux Scraper.

This module handles script execution scheduling using cron expressions.
"""

import logging
import os
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
            except Exception as e:
                logger.error(f"Error during scheduled run: {e}")
            next_run_time = cron_iter.get_next(datetime)
            logger.info(f"Next scheduled run at: {next_run_time}")
        sleep(60)

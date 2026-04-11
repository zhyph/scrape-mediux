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


def schedule_run(*, cron_expression: str, args_dict: dict) -> None:
    """Schedule recurring scraper runs using a cron expression.

    Runs indefinitely, checking every 60 seconds whether the next scheduled
    time has been reached and executing ``orchestrator.run()`` with the
    provided arguments when it has.

    Args:
        cron_expression: A valid cron expression (e.g. ``"0 2 * * *"`` for
            daily at 02:00). Timezone is determined by the ``TZ`` environment
            variable or the system default.
        args_dict: Keyword arguments forwarded verbatim to
            :func:`modules.orchestrator.run`. Must include at minimum
            ``api_key``, ``username``, ``password``, and ``nickname``.

    Raises:
        croniter.CroniterBadCronError: If ``cron_expression`` is invalid.

    Note:
        This function loops forever. Errors raised inside a scheduled run are
        caught and logged so that the scheduler continues to the next
        scheduled interval rather than exiting.
    """
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

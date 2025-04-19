import logging
import os
from datetime import datetime
from time import sleep
import croniter
from src.config.paths import CACHE_FILE

logger = logging.getLogger(__name__)


def schedule_run(
    cron_expression,
    api_key,
    username,
    password,
    profile_path,
    nickname,
    sonarr_api_key,
    sonarr_endpoint,
    root_folder,
    selected_folders=None,
    headless=True,
    process_all=False,
    chromedriver_path=None,
    retry_on_yaml_failure=False,
    config_path=None,
    output_dir=None,
):
    """
    Schedule periodic runs of the scraper using cron syntax.

    Args:
        cron_expression (str): Cron expression for scheduling
        api_key (str): TMDB API key
        username (str): Mediux username
        password (str): Mediux password
        profile_path (str): Path to Chrome profile
        nickname (str): Mediux nickname
        sonarr_api_key (str): Sonarr API key
        sonarr_endpoint (str): Sonarr API endpoint URL
        root_folder (str or list): Root folder(s) containing media
        selected_folders (list, optional): Specific folders to process
        headless (bool): Run Chrome in headless mode
        process_all (bool): Process all items, even if already in cache
        chromedriver_path (str, optional): Path to chromedriver
        retry_on_yaml_failure (bool): Whether to retry if YAML extraction fails
        config_path (str, optional): Path to config directory
        output_dir (str, optional): Directory to copy output files to
    """
    from .processor import run
    from src.data.bulk import write_data_to_files

    # Import YAML here to avoid circular import
    from ruamel.yaml import YAML

    yaml = YAML()
    yaml.allow_duplicate_keys = True

    logger.info(f"Scheduling script with cron expression: {cron_expression}")
    base_time = datetime.now()
    logger.info(f"Current time: {base_time}")
    logger.info(
        f"Environment Timezone: {os.environ.get('TZ', 'None is set, use the env from the docker compose or docker run to provide your TZ')}"
    )
    cron_iter = croniter.croniter(cron_expression, base_time)
    next_run = cron_iter.get_next(datetime)
    logger.info(f"Next scheduled run at: {next_run}")

    while True:
        now = datetime.now()
        if now >= next_run:
            logger.info("Scheduled run started...")
            try:
                new_data, cache = run(
                    api_key,
                    username,
                    password,
                    profile_path,
                    nickname,
                    sonarr_api_key,
                    sonarr_endpoint,
                    root_folder,
                    selected_folders,
                    headless,
                    process_all,
                    chromedriver_path,
                    retry_on_yaml_failure,
                    config_path,
                )

                write_data_to_files(
                    new_data=new_data,
                    root_folder=root_folder,
                    output_dir=output_dir,
                    yaml_parser=yaml,
                    cache=cache,
                    cache_file=CACHE_FILE,
                )
            except Exception as e:
                logger.error(f"Error during scheduled run: {e}")
            next_run = cron_iter.get_next(datetime)
            logger.info(f"Next scheduled run at: {next_run}")
        sleep(60)

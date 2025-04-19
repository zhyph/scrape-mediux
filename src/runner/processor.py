import logging
from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm
from src.config.paths import CACHE_FILE, get_kometa_file

logger = logging.getLogger(__name__)


def _load_prerequisites():
    """Load required modules and return them to avoid import clutter in main function."""
    from src.browser.driver import init_driver
    from src.browser.mediux import login_mediux, scrape_mediux
    from src.config.loader import validate_path
    from src.data.cache import load_cache
    from src.media.finder import get_media_ids
    from src.media.tmdb import fetch_tmdb_id
    from src.services.sonarr import check_series_status
    from src.data.bulk import load_bulk_data
    from collections import defaultdict
    import os
    from ruamel.yaml import YAML

    yaml = YAML()
    yaml.allow_duplicate_keys = True

    return {
        "init_driver": init_driver,
        "login_mediux": login_mediux,
        "scrape_mediux": scrape_mediux,
        "validate_path": validate_path,
        "load_cache": load_cache,
        "get_media_ids": get_media_ids,
        "fetch_tmdb_id": fetch_tmdb_id,
        "check_series_status": check_series_status,
        "load_bulk_data": load_bulk_data,
        "defaultdict": defaultdict,
        "os": os,
        "yaml": yaml,
    }


def _load_folder_data(root_folders, yaml):
    """Load bulk data for all folders."""
    import os
    from src.data.bulk import load_bulk_data

    folder_cache = {root: os.listdir(root) for root in root_folders}
    folder_bulk_data = {}

    for root, folders in folder_cache.items():
        folder_bulk_data.update(
            {
                folder: load_bulk_data(get_kometa_file(folder), False, yaml)
                for folder in folders
                if os.path.isdir(os.path.join(root, folder))
            }
        )
    logger.debug(f"Loaded bulk data for folders: {list(folder_bulk_data.keys())}")
    return folder_bulk_data


def _check_tv_series(tvdb_id, curr_bulk_data, ended, process_all):
    """Check if TV series needs processing based on TVDB ID and status."""
    if tvdb_id in curr_bulk_data.get("metadata", {}) and not process_all:
        if not ended:
            logger.info(f"Series with TVDB ID {tvdb_id} is ongoing. Updating entry.")
            del curr_bulk_data["metadata"][tvdb_id]
            return True
        else:
            logger.info(
                f"Series with TVDB ID {tvdb_id} has ended and already exists in YAML. Skipping entry."
            )
            return False
    return True


def _should_process_media(
    media_id,
    _media_name,
    media_type,
    tmdb_id,
    tvdb_id,
    ended,
    folder_map,
    folder_bulk_data,
    process_all,
):
    """Determine if a media item should be processed."""
    for folder in folder_map[media_id]:
        curr_bulk_data = folder_bulk_data.get(folder, {"metadata": {}})

        if media_type == "tv" and tvdb_id is not None:
            if not _check_tv_series(tvdb_id, curr_bulk_data, ended, process_all):
                return False

        if tmdb_id in curr_bulk_data["metadata"] and not process_all:
            logger.info(
                f"Skipping TMDB ID {tmdb_id} as it is already in ./out/kometa/{folder}_data.yml"
            )
            return False

    return True


def _process_media_item(
    driver,
    media_id,
    media_name,
    external_source,
    api_key,
    cache,
    sonarr_api_key,
    sonarr_endpoint,
    folder_map,
    folder_bulk_data,
    process_all,
    retry_on_yaml_failure,
    config_path,
):
    """Process a single media item."""
    from src.media.tmdb import fetch_tmdb_id
    from src.services.sonarr import check_series_status
    from src.browser.mediux import scrape_mediux

    try:
        tmdb_id, media_type = fetch_tmdb_id(media_id, external_source, api_key, cache)
    except Exception as e:
        logger.error(f"Failed to fetch TMDB ID for {external_source} {media_id}: {e}")
        return None, None

    tvdb_id = None
    ended = None
    if media_type == "tv":
        try:
            tvdb_id, ended = check_series_status(
                media_name, sonarr_api_key, sonarr_endpoint
            )
        except Exception as e:
            logger.error(f"Failed to check series status for {media_name}: {e}")
            return None, None

    if not _should_process_media(
        media_id,
        media_name,
        media_type,
        tmdb_id,
        tvdb_id,
        ended,
        folder_map,
        folder_bulk_data,
        process_all,
    ):
        return None, None

    logger.info(
        f"Processing Media ID: {media_id}, TMDB ID: {tmdb_id}, Media Type: {media_type}"
    )
    if not tmdb_id:
        return None, None

    yaml_data = scrape_mediux(
        driver, tmdb_id, media_type, retry_on_yaml_failure, config_path
    )
    if not yaml_data:
        logger.warning(f"No YAML data found for TMDB ID {tmdb_id}.")
        return None, None

    return tmdb_id, yaml_data


def run(
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
):
    """
    Main function to run the Mediux scraper.

    Args:
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

    Returns:
        dict: New data that was scraped
    """
    # Load dependencies
    deps = _load_prerequisites()

    new_data = deps["defaultdict"](dict)

    logger.info("Starting the script...")

    deps["validate_path"](root_folder, "Root folder")
    cache = deps["load_cache"](CACHE_FILE)

    root_folders = root_folder if isinstance(root_folder, list) else [root_folder]
    folder_bulk_data = _load_folder_data(root_folders, deps["yaml"])

    media_ids, folder_map = deps["get_media_ids"](root_folder, selected_folders)
    logger.info(f"Media IDs to process: {len(media_ids)}")

    driver = deps["init_driver"](headless, profile_path, chromedriver_path)
    updated_titles = []

    try:
        deps["login_mediux"](driver, username, password, nickname)

        with logging_redirect_tqdm():
            for media_id, media_name, external_source in tqdm(
                media_ids, desc="Processing media IDs"
            ):
                tmdb_id, yaml_data = _process_media_item(
                    driver,
                    media_id,
                    media_name,
                    external_source,
                    api_key,
                    cache,
                    sonarr_api_key,
                    sonarr_endpoint,
                    folder_map,
                    folder_bulk_data,
                    process_all,
                    retry_on_yaml_failure,
                    config_path,
                )

                if yaml_data:
                    for folder in folder_map[media_id]:
                        new_data[folder][tmdb_id] = yaml_data
                    updated_titles.append(media_name)
    finally:
        logger.info("Quitting WebDriver...")
        driver.quit()
        logger.info("Script finished.")

        if updated_titles:
            logger.info("Updated Titles:")
            for title in updated_titles:
                logger.info(f"- {title}")
        else:
            logger.info("No titles were updated.")

    return new_data, cache, folder_bulk_data

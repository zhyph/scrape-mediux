"""
Main application orchestrator for Mediux Scraper.

This module coordinates all components of the Mediux scraper application,
providing a clean, modular entry point that orchestrates the various
services and utilities.
"""

import uuid
from io import StringIO
from ruamel import yaml
import os
import atexit
import logging
from collections import defaultdict
from datetime import datetime
from time import sleep
from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm
from urllib3.exceptions import ReadTimeoutError
from selenium.common.exceptions import TimeoutException
from croniter import croniter

# Configure requests connection pool for better performance
import requests
from urllib3.util import Retry
from requests.adapters import HTTPAdapter

# Create a session with optimized connection pool
session = requests.Session()
adapter = HTTPAdapter(
    pool_connections=10,  # Connection pool for HTTP requests
    pool_maxsize=10,  # Max connections per pool
    max_retries=Retry(
        total=3, backoff_factor=0.3, status_forcelist=[429, 500, 502, 503, 504]
    ),
)
session.mount("http://", adapter)
session.mount("https://", adapter)

# Import modular components
from modules.config import ConfigManager, validate_path
from modules.scraper import WebDriverManager, MediuxLoginManager, MediuxScraper
from modules.tmdb_client import TMDBClient
from modules.data_processor import (
    YAMLDataFilter,
    YAMLStructureProcessor,
    DataComparisonEngine,
)
from modules.file_manager import CacheManager, BulkDataManager, FileWriter
from modules.external_services import (
    DiscordNotifier,
    SonarrClient,
    PlexClient,
    MediaDiscoveryService,
)


# Global variables for backward compatibility
new_data = defaultdict(dict)
cache = {}
folder_bulk_data = {}
root_folder_global = ""
output_dir_global = None
config_path_global = None
discord_webhook_url_global = None


# Cache configuration class for better encapsulation
class CacheConfig:
    """Configuration class for cache management settings."""

    def __init__(
        self,
        disable_cache: bool = False,
        clear_cache: bool = False,
        cache_dir: str = "./out",
    ):
        self.disable_cache = disable_cache
        self.clear_cache = clear_cache
        self.cache_dir = cache_dir

    def get_cache_file_path(self, filename: str) -> str:
        """Get full path for cache file."""
        return os.path.join(self.cache_dir, filename)

    def should_load_cache(self) -> bool:
        """Determine if cache should be loaded."""
        return not self.disable_cache

    def should_save_cache(self) -> bool:
        """Determine if cache should be saved."""
        return not self.disable_cache


# Global cache configuration instance
cache_config = CacheConfig()

logger = logging.getLogger(__name__)

# Global YAML parser instance with duplicate keys allowed
yaml_parser = yaml.YAML()
yaml_parser.allow_duplicate_keys = True

# Set up basic environment configuration
os.environ["PLEXAPI_HEADER_IDENTIFIER"] = uuid.uuid3(
    uuid.NAMESPACE_DNS, "Scrape-Mediux"
).hex
os.environ["PLEXAPI_HEADER_DEVICE_NAME"] = "Scrape-Mediux"
os.environ["PLEXAPI_HEADER_PROVIDES"] = ""


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
                run(**args_dict)
                write_data_to_files()
            except Exception as e:
                logger.error(f"Error during scheduled run: {e}")
            next_run_time = cron_iter.get_next(datetime)
            logger.info(f"Next scheduled run at: {next_run_time}")
        sleep(60)


def write_data_to_files():
    """Write collected data to files."""
    global new_data, cache, root_folder_global, cache_config

    if not root_folder_global:
        logger.error("Root folder is not set. Cannot write data.")
        return

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


def _initialize_and_login_driver(
    *,
    headless,
    profile_path,
    chromedriver_path,
    username,
    password,
    nickname,
):
    """Initialize WebDriver and login to Mediux."""
    webdriver_manager = WebDriverManager(config_path_global)
    driver = webdriver_manager.init_driver(
        headless=headless,
        profile_path=profile_path,
        chromedriver_path=chromedriver_path,
    )

    login_manager = MediuxLoginManager(webdriver_manager)
    try:
        login_manager.login(
            driver=driver,
            username=username,
            password=password,
            nickname=nickname,
        )
        return driver
    except Exception as e:
        logger.error(f"Failed to login during driver re-initialization: {e}")
        if driver:
            driver.quit()
        raise


def _get_media_ids(
    *,
    root_folder=None,
    selected_folders=None,
    plex_url=None,
    plex_token=None,
    plex_libraries=None,
):
    """Get media IDs using Plex API or folder scanning."""
    # First priority: Try Plex if all parameters are provided
    if plex_url and plex_token and plex_libraries and len(plex_libraries) > 0:
        try:
            plex_client = PlexClient(plex_url, plex_token)
            return plex_client.get_media_ids_from_plex(plex_libraries)
        except Exception as e:
            logger.error(f"Failed to get media IDs from Plex: {e}")
            logger.warning("Plex connection failed. Falling back to folder scanning.")

    # Second priority: Try to list available libraries if partial Plex config
    if (
        plex_url
        and plex_token
        and root_folder
        and (not plex_libraries or len(plex_libraries) == 0)
    ):
        try:
            plex_client = PlexClient(plex_url, plex_token)
            available = plex_client.list_available_libraries()
            logger.info("Available Plex libraries:")
            for lib in available:
                logger.info(f"  - {lib}")
            logger.warning(
                "No Plex libraries specified. Please set 'plex_libraries' in your config or CLI. Using root_folder instead."
            )
        except Exception as e:
            logger.error(f"Could not connect to Plex to list libraries: {e}")
            logger.warning("Using root_folder instead.")

    # Final fallback: Use folder scanning if root_folder is available
    if root_folder:
        logger.info("Fetching media IDs from folder names...")
        discovery_service = MediaDiscoveryService()
        return discovery_service.get_media_ids_from_folder(
            root_folder, selected_folders
        )
    else:
        logger.error("No Plex config or root_folder provided. Nothing to do. Exiting.")
        exit(1)


def _should_skip_scraping(
    *,
    media_name,
    media_type,
    tmdb_id,
    key_for_log,
    ended_status,
    is_in_yaml,
    process_all_flag,
):
    """Determine if scraping should be skipped based on series status and existing data."""
    if is_in_yaml and not process_all_flag:
        if media_type == "tv":
            if ended_status:
                logger.info(
                    f"⏭️  SKIPPING: {media_name} (ID: {key_for_log}, TMDB: {tmdb_id}) as it's in YAML and not processing all."
                )
                return True
            else:
                logger.info(
                    f"📺 ONGOING TV SHOW: {media_name} (ID: {key_for_log}, TMDB: {tmdb_id}) is in YAML. Will re-scrape for comparison."
                )
                return False
        elif media_type == "movie":
            logger.info(
                f"⏭️  SKIPPING: {media_name} (TMDB: {tmdb_id}) as it's in YAML and not processing all."
            )
            return True
    return False


def _process_single_media_item(
    *,
    media_id_from_folder,
    media_name,
    external_source_type,
    driver,
    api_key,
    sonarr_api_key,
    sonarr_endpoint,
    process_all,
    retry_on_yaml_failure,
    preferred_users,
    excluded_users,
    folder_map_for_media,
    updated_titles_list,
    fixed_titles_list,
    disable_season_fix=False,
    media_type_from_plex=None,
    remove_paths=None,
    shared_cache=None,
    shared_new_data=None,
    shared_folder_bulk_data=None,
):
    """Process a single media item."""
    # Declare globals for fallback
    global cache, new_data, folder_bulk_data

    # Use provided resources if available, otherwise use globals
    if shared_cache is not None:
        cache = shared_cache
    if shared_new_data is not None:
        new_data = shared_new_data
    if shared_folder_bulk_data is not None:
        folder_bulk_data = shared_folder_bulk_data

    # Use standard append function
    safe_append = lambda container, item: container.append(item)

    # Log the start of processing immediately
    media_separator = "=" * 60
    logger.info(f"{media_separator}")
    logger.info(f"🎬 STARTING: {media_name}")
    logger.info(f"   Source ID: {media_id_from_folder}")
    logger.info(f"{media_separator}")

    # Initialize services
    tmdb_client = TMDBClient(api_key)
    structure_processor = YAMLStructureProcessor()
    comparison_engine = DataComparisonEngine()

    tmdb_id = None
    media_type = media_type_from_plex

    # Resolve TMDB ID
    if external_source_type == "tmdb_id":
        tmdb_id = media_id_from_folder
        if not media_type:
            try:
                _, media_type = tmdb_client.fetch_tmdb_id(
                    media_id=tmdb_id,
                    external_source="tmdb_id",
                    cache=cache,
                    media_name=media_name,
                )
            except Exception as e:
                logger.error(f"Error determining media type for TMDB ID {tmdb_id}: {e}")
                return
    else:
        try:
            tmdb_id, media_type_from_fetch = tmdb_client.fetch_tmdb_id(
                media_id=media_id_from_folder,
                external_source=external_source_type,
                cache=cache,
                media_name=media_name,
            )
            if not media_type:
                media_type = media_type_from_fetch
        except Exception as e:
            logger.error(
                f"  - Error fetching TMDB ID for {external_source_type} {media_id_from_folder}: {e}"
            )
            return

    if not tmdb_id or not media_type:
        # logger.debug(f"Could not resolve TMDB ID or media type for {media_id_from_folder}, skipping.")
        return

    # Check Sonarr for TV series
    tvdb_id_for_tv, ended_status = None, None
    if media_type == "tv" and sonarr_api_key and sonarr_endpoint:
        sonarr_client = SonarrClient(sonarr_api_key, sonarr_endpoint)
        tvdb_id_for_tv, ended_status = sonarr_client.check_series_status(
            media_name=media_name,
            tmdb_id=tmdb_id,
        )

    # Check existing YAML data
    old_yaml_content, is_already_in_yaml, key_for_log = None, False, None

    if media_type == "tv":
        key_for_log = tvdb_id_for_tv
    elif media_type == "movie":
        key_for_log = tmdb_id

    if key_for_log:
        key_for_log = str(key_for_log)
        for f_name_map in folder_map_for_media.get(media_id_from_folder, []):
            key_for_bulk_data = (
                f_name_map[0] if isinstance(f_name_map, tuple) else f_name_map
            )
            f_bulk_data = folder_bulk_data.get(key_for_bulk_data, {})
            metadata = f_bulk_data.get("metadata", {})

            if key_for_log in metadata:
                old_yaml_content = metadata[key_for_log]
                is_already_in_yaml = True
                # logger.debug(f"Found existing YAML for {media_type} ID {key_for_log} in folder {key_for_bulk_data}")
                break

    # Determine if we should skip scraping based on series status
    should_skip = _should_skip_scraping(
        media_name=media_name,
        media_type=media_type,
        tmdb_id=tmdb_id,
        key_for_log=key_for_log,
        ended_status=ended_status,
        is_in_yaml=is_already_in_yaml,
        process_all_flag=process_all,
    )

    if should_skip:
        # Add completion marker for skipped items
        media_separator = "=" * 60
        logger.info(f"{media_separator}\n")
        return

    # Scrape Mediux
    scraper = MediuxScraper()
    new_raw_yaml = scraper.scrape_mediux(
        driver=driver,
        tmdb_id=tmdb_id,
        media_type=media_type,
        retry_on_yaml_failure=retry_on_yaml_failure,
        preferred_users=preferred_users,
        excluded_users=excluded_users,
    )

    if not new_raw_yaml:
        logger.warning(
            f"No YAML data found from Mediux for '{media_name}' (TMDB ID {tmdb_id})."
        )
        return

    # Process YAML structure for TV shows
    if media_type == "tv":
        is_malformed = False
        try:
            parsed_for_check = yaml_parser.load(new_raw_yaml)

            if parsed_for_check and isinstance(parsed_for_check, dict):
                media_id_key = next(iter(parsed_for_check))
                content = parsed_for_check.get(media_id_key)

                if content and "seasons" in content:
                    seasons_node = content.get("seasons")
                    if seasons_node and seasons_node.get("episodes", None) is not None:
                        logger.info(
                            f"Detected malformed 'seasons' block for '{media_name}'."
                        )
                        is_malformed = True
                    else:
                        logger.info(f"YAML structure for '{media_name}' appears valid.")
                else:
                    logger.info(
                        f"YAML for '{media_name}' has no 'seasons' block or empty content, structure is considered valid."
                    )
            else:
                logger.warning(
                    f"Could not parse YAML for '{media_name}' into a dictionary for checking."
                )

        except Exception as e:
            logger.error(
                f"Error while checking YAML structure for '{media_name}': {e}",
                exc_info=True,
            )

        if is_malformed and not disable_season_fix:
            new_raw_yaml, was_fixed = structure_processor.preprocess_yaml_string(
                yaml_string=new_raw_yaml,
            )
            if was_fixed:
                logger.info(f"YAML for '{media_name}' was successfully fixed.")
                log_id_str = (
                    f"TVDB: {tvdb_id_for_tv}" if tvdb_id_for_tv else f"TMDB: {tmdb_id}"
                )
                safe_append(fixed_titles_list, f"{media_name} ({log_id_str})")
            else:
                logger.warning(
                    f"Preprocessing was triggered for '{media_name}' but no changes were made by the function."
                )
        elif is_malformed and disable_season_fix:
            logger.info(
                f"Malformed YAML detected for '{media_name}' but automatic fix is disabled."
            )

    # Apply filtering if specified
    final_yaml_data = new_raw_yaml
    new_comparable_content = None

    if remove_paths:
        try:
            parsed_yaml = yaml_parser.load(new_raw_yaml)

            if parsed_yaml and isinstance(parsed_yaml, dict):
                filter_engine = YAMLDataFilter()
                filtered_yaml = filter_engine.filter_yaml_data_by_paths(
                    yaml_data=parsed_yaml,
                    remove_paths=remove_paths,
                )

                if filtered_yaml:
                    # Check if the filtered result is marked as filtered empty
                    is_filtered_empty = (
                        isinstance(filtered_yaml, dict)
                        and len(filtered_yaml) == 1
                        and filtered_yaml.get("_filtered_empty_") is True
                    )

                    if is_filtered_empty:
                        # Handle filtered empty case - create recognizable empty structure
                        media_id_key = next(iter(parsed_yaml.keys()))
                        final_yaml_data = (
                            f"# Filtered empty by remove_paths\n{media_id_key}:"
                        )
                        logger.info(
                            f"Filtering resulted in empty structure for '{media_name}' (TMDB: {tmdb_id}) - marked as filtered empty"
                        )
                        new_comparable_content = None
                    else:
                        string_stream = StringIO()
                        yaml_parser.dump(filtered_yaml, string_stream)
                        final_yaml_data = string_stream.getvalue()

                        import re

                        final_yaml_data = re.sub(
                            r"(\s+)([^:\n]+):\s*\{\}", r"\1\2:", final_yaml_data
                        )

                        new_comparable_content = comparison_engine.extract_comparable_content_from_scraped_yaml(
                            raw_yaml_data=final_yaml_data,
                            media_name=media_name,
                            media_type=media_type,
                            tmdb_id=tmdb_id,
                            tvdb_id_for_tv=tvdb_id_for_tv,
                            yaml_parser=yaml_parser,
                            remove_paths=None,
                        )
                else:
                    final_yaml_data = new_raw_yaml
                    logger.warning(
                        f"Filtering resulted in empty YAML for '{media_name}' (TMDB: {tmdb_id}), keeping original"
                    )
                    new_comparable_content = (
                        comparison_engine.extract_comparable_content_from_scraped_yaml(
                            raw_yaml_data=final_yaml_data,
                            media_name=media_name,
                            media_type=media_type,
                            tmdb_id=tmdb_id,
                            tvdb_id_for_tv=tvdb_id_for_tv,
                            yaml_parser=yaml_parser,
                            remove_paths=None,
                        )
                    )
            else:
                new_comparable_content = (
                    comparison_engine.extract_comparable_content_from_scraped_yaml(
                        raw_yaml_data=final_yaml_data,
                        media_name=media_name,
                        media_type=media_type,
                        tmdb_id=tmdb_id,
                        tvdb_id_for_tv=tvdb_id_for_tv,
                        yaml_parser=yaml_parser,
                        remove_paths=None,
                    )
                )
        except Exception as e:
            logger.error(
                f"Failed to filter YAML for '{media_name}' (TMDB: {tmdb_id}): {e}"
            )
            final_yaml_data = new_raw_yaml
            new_comparable_content = (
                comparison_engine.extract_comparable_content_from_scraped_yaml(
                    raw_yaml_data=final_yaml_data,
                    media_name=media_name,
                    media_type=media_type,
                    tmdb_id=tmdb_id,
                    tvdb_id_for_tv=tvdb_id_for_tv,
                    yaml_parser=yaml_parser,
                    remove_paths=None,
                )
            )
    else:
        new_comparable_content = (
            comparison_engine.extract_comparable_content_from_scraped_yaml(
                raw_yaml_data=final_yaml_data,
                media_name=media_name,
                media_type=media_type,
                tmdb_id=tmdb_id,
                tvdb_id_for_tv=tvdb_id_for_tv,
                yaml_parser=yaml_parser,
                remove_paths=None,
            )
        )

    # Final processing for TV shows
    if media_type == "tv" and new_comparable_content:
        try:
            parsed_yaml_data = yaml_parser.load(final_yaml_data)

            string_stream = StringIO()
            yaml_parser.dump(parsed_yaml_data, string_stream)
            final_yaml_data = string_stream.getvalue()
        except Exception as e:
            logger.error(f"Failed to re-process TV YAML for '{media_name}': {e}")

    id_for_comp_log = (
        tvdb_id_for_tv if media_type == "tv" and tvdb_id_for_tv else tmdb_id
    )

    title_should_be_updated_flag = comparison_engine.compare_yaml_and_log_changes(
        media_name=media_name,
        media_type=media_type,
        id_for_logging=id_for_comp_log,
        old_content=old_yaml_content,
        new_content_to_compare=new_comparable_content,
    )

    if title_should_be_updated_flag:
        log_id_str = (
            f"TVDB: {tvdb_id_for_tv}"
            if media_type == "tv" and tvdb_id_for_tv
            else f"TMDB: {tmdb_id}"
        )
        safe_append(updated_titles_list, f"{media_name} ({log_id_str})")

    for folder_name in folder_map_for_media.get(media_id_from_folder, []):
        new_data[folder_name][tmdb_id] = final_yaml_data

    # Mark completion of this media item with prominent separator
    media_separator = "=" * 60
    logger.info(f"✅ COMPLETED: {media_name}")
    logger.info(f"{media_separator}\n")


def run(
    *,
    api_key,
    username,
    password,
    profile_path,
    nickname,
    sonarr_api_key,
    sonarr_endpoint,
    selected_folders=None,
    headless=True,
    process_all=False,
    chromedriver_path=None,
    retry_on_yaml_failure=False,
    preferred_users=None,
    excluded_users=None,
    disable_season_fix=False,
    remove_paths=None,
    plex_url=None,
    plex_token=None,
    plex_libraries=None,
    disable_cache=False,
    clear_cache=False,
    cache_dir="./out",
):
    """Main execution function."""
    global cache, new_data, folder_bulk_data, root_folder_global

    # Update global cache configuration
    global cache_config
    cache_config = CacheConfig(
        disable_cache=disable_cache, clear_cache=clear_cache, cache_dir=cache_dir
    )

    import time

    start_time = time.time()
    logger.info("🚀 MEDIUX SCRAPER STARTED")

    folder_count = (
        len(root_folder_global) if isinstance(root_folder_global, list) else 1
    )
    logger.info(f"📂 Processing {folder_count} folder(s)")

    if selected_folders:
        logger.debug(f"Target folders: {', '.join(selected_folders)}")
    if preferred_users:
        logger.debug(f"Preferred users: {', '.join(preferred_users)}")
    if excluded_users:
        logger.debug(f"Excluded users: {', '.join(excluded_users)}")

    # Phase 1: Setup and Configuration
    separator = "=" * 60
    logger.info(f"\n{separator}\n🔧 SETUP & CONFIGURATION\n{separator}")

    # Handle cache management
    if cache_config.clear_cache:
        logger.info("🧹 Clearing existing cache files...")
        cache_files = [
            cache_config.get_cache_file_path("tmdb_cache.pkl"),
            cache_config.get_cache_file_path("intelligent_cache.pkl"),
        ]
        for cache_file in cache_files:
            if os.path.exists(cache_file):
                os.remove(cache_file)
                logger.info(f"✅ Removed cache file: {cache_file}")

    if cache_config.disable_cache:
        logger.info("🚫 Cache loading and saving disabled - fresh start each time")
        cache = {}

        # Create a dummy intelligent cache manager that does nothing
        class DummyCacheManager:
            def load_cache(self):
                pass

            def save_cache(self):
                pass

            def get_cache_stats(self):
                return {}

        intelligent_cache_manager = DummyCacheManager()
    else:
        logger.info("👤 Loading configuration and cache...")
        cache_manager = CacheManager()
        cache = cache_manager.load_cache()

        # Load intelligent cache
        from modules.intelligent_cache import get_cache_manager

        intelligent_cache_manager = get_cache_manager()
        intelligent_cache_manager.load_cache(
            cache_config.get_cache_file_path("intelligent_cache.pkl")
        )

    root_folders_list = (
        root_folder_global
        if isinstance(root_folder_global, list)
        else [root_folder_global]
    )

    folder_bulk_data.clear()
    for root_path_item in root_folders_list:
        if not os.path.isdir(root_path_item):
            continue
        for folder_item in os.listdir(root_path_item):
            if os.path.isdir(os.path.join(root_path_item, folder_item)):
                bulk_manager = BulkDataManager()
                folder_bulk_data[folder_item] = bulk_manager.load_bulk_data(
                    bulk_data_file=f"./out/kometa/{folder_item}_data.yml"
                )

    # Handle Plex libraries - load data for Plex library names
    if plex_libraries:
        import re

        logger.log(25, f"Loading {len(plex_libraries)} Plex libraries...")
        for lib_name in plex_libraries:
            safe_lib = re.sub(r"[^\w\-]", "_", lib_name.lower())
            folder_bulk_data[lib_name] = BulkDataManager().load_bulk_data(
                bulk_data_file=f"./out/kometa/{safe_lib}_data.yml"
            )

    # Phase 2: Media Discovery
    logger.info(f"\n{separator}\n🔍 MEDIA DISCOVERY\n{separator}")
    logger.info("👤 Scanning for media IDs...")

    media_ids_to_process, folder_map_for_media = _get_media_ids(
        root_folder=root_folder_global,
        selected_folders=selected_folders,
        plex_url=plex_url,
        plex_token=plex_token,
        plex_libraries=plex_libraries,
    )

    logger.info(f"✅ Found {len(media_ids_to_process)} media items to process")
    if remove_paths:
        logger.info(f"👤 YAML filtering enabled for {len(remove_paths)} path(s)")

    driver = None
    updated_titles_list = []
    fixed_titles_list = []
    new_data.clear()

    # Phase 3: WebDriver Initialization
    logger.info(f"\n{separator}\n🌐 BROWSER INITIALIZATION\n{separator}")
    logger.info("👤 Starting Chrome WebDriver...")

    driver = None
    try:
        driver = _initialize_and_login_driver(
            headless=headless,
            profile_path=profile_path,
            chromedriver_path=chromedriver_path,
            username=username,
            password=password,
            nickname=nickname,
        )
        logger.info("✅ Successfully logged into Mediux")

        # Phase 4: Media Processing
        logger.info(f"\n{separator}\n⚙️  MEDIA PROCESSING\n{separator}")
        logger.info(f"👤 Processing {len(media_ids_to_process)} media items...")

        with logging_redirect_tqdm():
            for (
                media_id_from_folder,
                media_name,
                external_source_type,
                media_type_from_plex,
            ) in tqdm(media_ids_to_process, desc="Processing media"):
                try:
                    _process_single_media_item(
                        media_id_from_folder=media_id_from_folder,
                        media_name=media_name,
                        external_source_type=external_source_type,
                        media_type_from_plex=media_type_from_plex,
                        driver=driver,
                        api_key=api_key,
                        sonarr_api_key=sonarr_api_key,
                        sonarr_endpoint=sonarr_endpoint,
                        process_all=process_all,
                        retry_on_yaml_failure=retry_on_yaml_failure,
                        preferred_users=preferred_users,
                        excluded_users=excluded_users,
                        folder_map_for_media=folder_map_for_media,
                        updated_titles_list=updated_titles_list,
                        fixed_titles_list=fixed_titles_list,
                        disable_season_fix=disable_season_fix,
                        remove_paths=remove_paths,
                        shared_cache=cache,
                        shared_new_data=new_data,
                        shared_folder_bulk_data=folder_bulk_data,
                    )
                except (ReadTimeoutError, TimeoutException):
                    logger.error(
                        "A timeout error occurred. Re-initializing WebDriver and logging in again."
                    )
                    if driver:
                        driver.quit()
                    driver = _initialize_and_login_driver(
                        headless=headless,
                        profile_path=profile_path,
                        chromedriver_path=chromedriver_path,
                        username=username,
                        password=password,
                        nickname=nickname,
                    )
    finally:
        # Phase 5: Cleanup and Summary
        logger.info(f"\n{separator}\n🧹 CLEANUP & SUMMARY\n{separator}")

        end_time = time.time()
        duration = end_time - start_time

        logger.info("👤 Shutting down...")
        if driver:
            driver.quit()

        # Enhanced final summary
        logger.info(f"\n{separator}\n📊 FINAL RESULTS\n{separator}")

        if updated_titles_list:
            logger.info(f"✅ {len(updated_titles_list)} titles were updated:")
            for title in updated_titles_list:
                print(f"   • {title}")
        else:
            logger.info("📋 No titles were updated - all content was up to date")

        truly_fixed_and_updated = [
            title for title in fixed_titles_list if title in updated_titles_list
        ]

        if truly_fixed_and_updated:
            logger.info(
                f"🔧 {len(truly_fixed_and_updated)} titles had YAML structure fixed:"
            )
            for title in truly_fixed_and_updated:
                print(f"   • {title}")

        # Performance summary
        logger.info(f"⏱️  Total processing time: {duration:.1f} seconds")
        if media_ids_to_process:
            avg_time = duration / len(media_ids_to_process)
            logger.info(f"📈 Average time per item: {avg_time:.1f} seconds")

        # Cache performance summary
        if intelligent_cache_manager and hasattr(
            intelligent_cache_manager, "get_cache_stats"
        ):
            try:
                cache_stats = intelligent_cache_manager.get_cache_stats()
                if cache_stats:
                    logger.info("📊 Cache Performance:")
                    for namespace, stats in cache_stats.items():
                        if stats.get("hits", 0) > 0 or stats.get("misses", 0) > 0:
                            total = stats.get("hits", 0) + stats.get("misses", 0)
                            hit_rate = (
                                (stats.get("hits", 0) / total * 100) if total > 0 else 0
                            )
                            logger.info(
                                f"   • {namespace}: {stats.get('hits', 0)} hits, {stats.get('misses', 0)} misses ({hit_rate:.1f}% hit rate)"
                            )
                    logger.info(f"   • Cache file: ./out/intelligent_cache.pkl")
            except Exception as e:
                logger.debug(f"Could not retrieve cache stats: {e}")

        # Discord notifications
        if updated_titles_list and discord_webhook_url_global:
            max_titles_per_message = 15
            num_titles = len(updated_titles_list)

            discord_notifier = DiscordNotifier()
            for i in range(0, num_titles, max_titles_per_message):
                chunk = updated_titles_list[i : i + max_titles_per_message]
                message_content = "Newly processed/updated titles:\n- " + "\n- ".join(
                    chunk
                )
                if (
                    num_titles > max_titles_per_message
                    and i + max_titles_per_message < num_titles
                ):
                    message_content += f"\n...and {num_titles - (i + max_titles_per_message)} more titles."
                elif num_titles > max_titles_per_message and i == 0:
                    message_content += f"\n(Showing first {max_titles_per_message} of {num_titles} titles)"

                discord_notifier.send_notification(
                    webhook_url=discord_webhook_url_global, message=message_content
                )

        if truly_fixed_and_updated and discord_webhook_url_global:
            message_content = (
                "The following TV shows had their YAML structure automatically fixed "
                "and may require manual review:\n- "
                + "\n- ".join(truly_fixed_and_updated)
            )
            discord_notifier = DiscordNotifier()
            discord_notifier.send_notification(
                webhook_url=discord_webhook_url_global, message=message_content
            )

        logger.info("🎉 Mediux scraper completed successfully!")


def main():
    """Main entry point."""
    # Setup logging
    config_manager = ConfigManager()
    config_manager.setup_logging()

    # Get logger after custom setup
    global logger
    logger = logging.getLogger(__name__)

    # Parse configuration
    app_settings = config_manager.parse_arguments_and_load_config()

    # Set global variables
    global config_path_global, root_folder_global, output_dir_global, discord_webhook_url_global
    config_path_global = app_settings["config_path_val"]
    root_folder_global = app_settings["root_folder_val"]
    output_dir_global = app_settings["output_dir_val"]
    discord_webhook_url_global = app_settings["discord_webhook_url"]

    # Handle copy-only mode
    if app_settings.get("copy_only"):
        if not output_dir_global:
            logger.error("No output_dir specified for --copy_only mode.")
            exit(1)
        file_writer = FileWriter()
        file_writer._copy_to_output_dir(output_dir_global)
        logger.info("Copy-only mode complete. Exiting.")
        exit(0)

    # Set timezone if provided
    if app_settings.get("tz"):
        os.environ["TZ"] = app_settings["tz"]

    # Register data writing with atexit if root folder is set
    # We'll validate the path later in the run() function when we actually need it
    if root_folder_global:
        atexit.register(write_data_to_files)
    else:
        logger.warning(
            "Root folder is not set. `write_data_to_files` will not be registered with atexit."
        )

    try:
        run_args_for_schedule = {
            "api_key": app_settings["api_key"],
            "username": app_settings["username"],
            "password": app_settings["password"],
            "profile_path": app_settings["profile_path"],
            "nickname": app_settings["nickname"],
            "sonarr_api_key": app_settings["sonarr_api_key"],
            "sonarr_endpoint": app_settings["sonarr_endpoint"],
            "selected_folders": app_settings["selected_folders"],
            "headless": app_settings["headless"],
            "process_all": app_settings["process_all"],
            "chromedriver_path": app_settings["chromedriver_path"],
            "retry_on_yaml_failure": app_settings["retry_on_yaml_failure"],
            "preferred_users": app_settings["preferred_users"],
            "excluded_users": app_settings["excluded_users"],
            "disable_season_fix": app_settings["disable_season_fix"],
            "remove_paths": app_settings["remove_paths"],
            "plex_url": app_settings["plex_url"],
            "plex_token": app_settings["plex_token"],
            "plex_libraries": app_settings["plex_libraries"],
            "disable_cache": app_settings.get("disable_cache", False),
            "clear_cache": app_settings.get("clear_cache", False),
            "cache_dir": app_settings.get("cache_dir", "./out"),
        }

        if app_settings["cron_expression"]:
            schedule_run(
                cron_expression=app_settings["cron_expression"],
                args_dict=run_args_for_schedule,
            )
        else:
            run(**run_args_for_schedule)

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

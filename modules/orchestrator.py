"""
Orchestrator module for Mediux Scraper.

This module coordinates the main execution flow of the Mediux scraper,
including setup, media processing, and cleanup.
"""

import logging
import os
import sys
import time
from typing import Tuple

from selenium.common.exceptions import TimeoutException
from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm
from urllib3.exceptions import ReadTimeoutError

from modules.intelligent_cache import (
    set_global_cache_manager,
    create_cache_manager_from_config,
)
from modules.base import ScraperContext, FileSystemConstants, MediuxConfig, _exit_with_error

# Detect if running in an interactive terminal for progress bar control
is_interactive = sys.stdout.isatty() and sys.stderr.isatty()


logger = logging.getLogger(__name__)


def parse_mediux_url(mediux_url: str) -> Tuple[str, str, str, str]:
    """
    Parse a Mediux URL and extract media information.

    Args:
        mediux_url: Mediux URL in format https://mediux.pro/shows|movies/id

    Returns:
        Tuple of (media_id, media_name, source, media_type) or raises ValueError

    Raises:
        ValueError: If URL format is invalid
    """
    from urllib.parse import urlparse

    parsed_url = urlparse(mediux_url)
    path_parts = parsed_url.path.strip("/").split("/")

    # Mediux URL structure: /shows|movies/id
    if len(path_parts) != 2:
        raise ValueError(
            f"Invalid Mediux URL format: {mediux_url}. Expected: https://mediux.pro/movies/12345 or https://mediux.pro/shows/67890"
        )

    media_type_from_url = path_parts[0]
    media_id = path_parts[1]

    # Map to standardized media type
    if "tv" in media_type_from_url.lower() or "show" in media_type_from_url.lower():
        media_type = "tv"
    else:
        media_type = "movie"

    # Use placeholder title - will be resolved during processing
    media_name = f"Mediux {media_type.title()} ID {media_id}"

    return (media_id, media_name, "tmdb_id", media_type)


def _setup_phase(context, cache_manager, plex_libraries):
    """Phase 1: Create output dirs, init cache, load Plex library bulk data.

    Returns:
        The active intelligent_cache_manager (real or dummy).
    """
    separator = "=" * 60
    logger.info(f"\n{separator}\n🔧 SETUP & CONFIGURATION\n{separator}")

    # Ensure output directories exist
    for dir_path in [FileSystemConstants.OUTPUT_DIR_DEFAULT, FileSystemConstants.KOMETA_DIR]:
        if not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)
            logger.debug(f"Created directory: {dir_path}")

    # Handle optional cache clearing
    if cache_manager.clear_cache_on_startup:
        logger.info("🧹 Clearing existing cache files...")
        cache_file = cache_manager.get_cache_file_path(
            FileSystemConstants.INTELLIGENT_CACHE_FILENAME
        )
        if os.path.exists(cache_file):
            os.remove(cache_file)
            logger.info(f"✅ Removed cache file: {cache_file}")

    # Load (or stub) the intelligent cache
    if cache_manager.disable_cache:
        logger.info("🚫 Cache loading and saving disabled - fresh start each time")

        class _DummyCacheManager:
            def get_cache_stats(self):
                """Returns empty stats when caching is disabled."""
                return {}

        intelligent_cache_manager = _DummyCacheManager()
    else:
        logger.info("👤 Loading intelligent cache...")
        from modules.intelligent_cache import get_cache_manager

        intelligent_cache_manager = get_cache_manager()
        intelligent_cache_manager.load_cache()

    # Pre-load existing YAML data for each configured Plex library
    if plex_libraries:
        import re

        logger.log(25, f"Loading {len(plex_libraries)} Plex libraries...")
        from modules.file_manager import BulkDataManager

        for lib_name in plex_libraries:
            safe_lib = re.sub(r"[^\w\-]", "_", lib_name.lower())
            context.folder_bulk_data[lib_name] = BulkDataManager().load_bulk_data(
                bulk_data_file=(
                    f"{FileSystemConstants.KOMETA_DIR}/{safe_lib}"
                    f"{FileSystemConstants.DATA_FILE_SUFFIX}"
                )
            )

    return intelligent_cache_manager


def _discover_media_phase(mediux_url, plex_url, plex_token, plex_libraries):
    """Phase 2: Discover media items via Plex or a direct Mediux URL.

    Returns:
        Tuple of (media_ids_to_process, folder_map_for_media).
    """
    separator = "=" * 60
    logger.info(f"\n{separator}\n🔍 MEDIA DISCOVERY\n{separator}")

    if mediux_url:
        logger.info("🎯 Direct Mediux URL provided - bypassing Plex library discovery")
        logger.info(f"📌 Target URL: {mediux_url}")
        try:
            media_id, title, source, media_type = parse_mediux_url(mediux_url)
        except ValueError as e:
            _exit_with_error(str(e), logger)
        media_ids_to_process = [(media_id, title, source, media_type)]
        folder_map_for_media = {media_id: [("Direct URL", media_type)]}
        logger.info(f"📋 Created media item: ID={media_id}, Type={media_type}")
        logger.info(f"📋 Will navigate directly to: {mediux_url}")
        return media_ids_to_process, folder_map_for_media

    logger.info("👤 Scanning for media IDs...")
    from modules.media_discovery import get_media_ids

    try:
        media_ids_to_process, folder_map_for_media = get_media_ids(
            plex_url=plex_url,
            plex_token=plex_token,
            plex_libraries=plex_libraries,
        )
    except ValueError as e:
        _exit_with_error(f"Configuration error: {e}", logger)
    except Exception as e:
        logger.error(f"Failed to retrieve media IDs: {e}")
        logger.info("Please check your Plex configuration and try again.")
        _exit_with_error("", code=1)

    if not media_ids_to_process:
        logger.info(
            "Ensure 'plex_url', 'plex_token', and 'plex_libraries' are correctly configured."
        )
        _exit_with_error(
            "No media items found. Please check your Plex configuration.", logger
        )

    logger.info(f"✅ Found {len(media_ids_to_process)} media items to process")
    return media_ids_to_process, folder_map_for_media


def _process_media_phase(
    media_ids_to_process,
    folder_map_for_media,
    config,
    context,
    webdriver_manager,
    login_manager,
    headless,
    profile_path,
    chromedriver_path,
    username,
    password,
    nickname,
):
    """Phase 4: Iterate over media items with timeout recovery."""
    separator = "=" * 60
    logger.info(f"\n{separator}\n⚙️  MEDIA PROCESSING\n{separator}")
    logger.info(f"👤 Processing {len(media_ids_to_process)} media items...")

    from modules.media_processing import process_single_media_item

    with logging_redirect_tqdm():
        for (
            media_id_from_folder,
            media_name,
            external_source_type,
            media_type_from_plex,
        ) in tqdm(
            media_ids_to_process,
            desc="Processing media",
            disable=not is_interactive,
        ):
            try:
                process_single_media_item(
                    media_id_from_folder=media_id_from_folder,
                    media_name=media_name,
                    external_source_type=external_source_type,
                    folder_map_for_media=folder_map_for_media,
                    config=config,
                    media_type_from_plex=media_type_from_plex,
                    context=context,
                )
            except (ReadTimeoutError, TimeoutException):
                logger.error(
                    "A timeout error occurred. Re-initializing WebDriver and logging in again."
                )
                webdriver_manager.safe_quit_driver()
                webdriver_manager.init_driver(
                    headless=headless,
                    profile_path=profile_path,
                    chromedriver_path=chromedriver_path,
                )
                login_manager.login(
                    username=username,
                    password=password,
                    nickname=nickname,
                )


def _cleanup_phase(
    context,
    cache_manager,
    intelligent_cache_manager,
    output_dir_global,
    discord_webhook_url_global,
    media_ids_to_process,
    webdriver_manager,
    duration,
):
    """Phase 5: Save cache, write output files, log summary, send Discord notifications."""
    separator = "=" * 60
    logger.info(f"\n{separator}\n🧹 CLEANUP & SUMMARY\n{separator}")

    # Persist intelligent cache
    if not cache_manager.disable_cache and intelligent_cache_manager is not None:
        logger.info("🧠 Saving intelligent cache...")
        try:
            filepath = cache_manager.get_cache_file_path(
                FileSystemConstants.INTELLIGENT_CACHE_FILENAME
            )
            if hasattr(intelligent_cache_manager, "cache"):
                getattr(intelligent_cache_manager, "cache").save_to_file(filepath)
            else:
                logger.debug("Dummy cache manager detected - skipping intelligent cache save")
            logger.info("✅ Intelligent cache saved successfully.")
        except Exception as e:
            logger.error(f"❌ Failed to save intelligent cache: {e}")

    # Write YAML output files
    logger.info("👤 Saving data to files...")
    from modules.file_manager import FileWriter

    FileWriter().write_data_to_files(
        new_data=context.new_data,
        output_dir_global=output_dir_global,
    )

    logger.info("👤 Shutting down...")
    webdriver_manager.safe_quit_driver()

    # Final results summary
    logger.info(f"\n{separator}\n📊 FINAL RESULTS\n{separator}")

    if context.updated_titles_list:
        logger.info(f"✅ {len(context.updated_titles_list)} titles were updated:")
        for media_name, log_id_str, tmdb_id, media_type in context.updated_titles_list:
            url = (
                MediuxConfig.get_movie_url(tmdb_id)
                if media_type == "movie"
                else MediuxConfig.get_show_url(tmdb_id)
            )
            print(f"   • {media_name} ({log_id_str}) - {url}")
    else:
        logger.info("📋 No titles were updated - all content was up to date")

    # Titles that were both fixed and updated
    truly_fixed_and_updated = []
    updated_displays = {
        f"{name} ({id_str})"
        for name, id_str, _, _ in context.updated_titles_list
    }
    for fixed_name, fixed_id_str, _, _ in context.fixed_titles_list:
        display = f"{fixed_name} ({fixed_id_str})"
        if display in updated_displays:
            truly_fixed_and_updated.append(display)

    if truly_fixed_and_updated:
        logger.info(f"🔧 {len(truly_fixed_and_updated)} titles had YAML structure fixed:")
        for title in truly_fixed_and_updated:
            print(f"   • {title}")

    # Performance summary
    logger.info(f"⏱️  Total processing time: {duration:.1f} seconds")
    if media_ids_to_process:
        avg_time = duration / len(media_ids_to_process)
        logger.info(f"📈 Average time per item: {avg_time:.1f} seconds")

    # Cache performance summary
    if intelligent_cache_manager and hasattr(intelligent_cache_manager, "get_cache_stats"):
        try:
            cache_stats = intelligent_cache_manager.get_cache_stats()
            if cache_stats:
                logger.debug("📊 Cache Performance:")
                for namespace, stats in cache_stats.items():
                    hits = stats.get("hits", 0)
                    misses = stats.get("misses", 0)
                    if hits > 0 or misses > 0:
                        total = hits + misses
                        hit_rate = (hits / total * 100) if total > 0 else 0
                        logger.debug(
                            f"      • {namespace}: {hit_rate:.1f}% hit rate "
                            f"({hits} hits, {misses} misses)"
                        )
                logger.debug(
                    f"   • Cache file: "
                    f"{cache_manager.get_cache_file_path(FileSystemConstants.INTELLIGENT_CACHE_FILENAME)}"
                )
        except Exception as e:
            logger.debug(f"Could not retrieve cache stats: {e}")

    # Discord notifications
    from modules.external_services import DiscordNotifier

    discord_notifier = DiscordNotifier()

    if context.updated_titles_list and discord_webhook_url_global:
        logger.info("👤 Sending Discord notifications...")
        max_titles_per_message = 15
        num_titles = len(context.updated_titles_list)
        rate_limited = False
        wait_time = None

        for i in range(0, num_titles, max_titles_per_message):
            chunk = context.updated_titles_list[i : i + max_titles_per_message]
            display_strings = []
            for media_name, log_id_str, tmdb_id, media_type in chunk:
                url = (
                    MediuxConfig.get_movie_url(tmdb_id)
                    if media_type == "movie"
                    else MediuxConfig.get_show_url(tmdb_id)
                )
                display_strings.append(f"{media_name} ({log_id_str}) - <{url}>")

            message_content = "Newly processed/updated titles:\n- " + "\n- ".join(
                display_strings
            )
            if num_titles > max_titles_per_message and i + max_titles_per_message < num_titles:
                message_content += (
                    f"\n...and {num_titles - (i + max_titles_per_message)} more titles."
                )
            elif num_titles > max_titles_per_message and i == 0:
                message_content += (
                    f"\n(Showing first {max_titles_per_message} of {num_titles} titles)"
                )

            success, wait_time_value = discord_notifier.send_notification(
                webhook_url=discord_webhook_url_global, message=message_content
            )
            if not success:
                rate_limited = True
                wait_time = wait_time_value
                break

        if rate_limited and wait_time:
            DiscordNotifier.send_rate_limited_message(
                discord_webhook_url_global, num_titles, wait_time
            )
        elif rate_limited:
            DiscordNotifier.send_rate_limited_message(discord_webhook_url_global, num_titles)

    if truly_fixed_and_updated and discord_webhook_url_global:
        message_content = (
            "The following TV shows had their YAML structure automatically fixed "
            "and may require manual review:\n- "
            + "\n- ".join(truly_fixed_and_updated)
        )
        # One message — rate limiting unlikely
        discord_notifier.send_notification(
            webhook_url=discord_webhook_url_global, message=message_content
        )

    logger.info("🎉 Mediux scraper completed successfully!")


def run(
    *,
    api_key,
    username,
    password,
    profile_path,
    nickname,
    sonarr_api_key,
    sonarr_endpoint,
    config_path=None,
    output_dir_global=None,
    discord_webhook_url_global=None,
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
    mediux_url=None,
    disable_cache=False,
    clear_cache=False,
    cache_dir=FileSystemConstants.OUTPUT_DIR_DEFAULT,
    max_cache_size=1000,
    default_cache_ttl=3600,
    max_cache_memory_mb=50.0,
    memory_check_interval=100,
    namespace_configs=None,
):
    """Main execution function."""
    context = ScraperContext()

    cache_manager = create_cache_manager_from_config(
        disable_cache=disable_cache,
        clear_cache=clear_cache,
        cache_dir=cache_dir,
        max_cache_size=max_cache_size,
        default_cache_ttl=default_cache_ttl,
        max_cache_memory_mb=max_cache_memory_mb,
        memory_check_interval=memory_check_interval,
        namespace_configs=namespace_configs,
    )
    set_global_cache_manager(cache_manager)

    start_time = time.time()
    logger.info("🚀 MEDIUX SCRAPER STARTED")
    logger.info("📂 Processing media libraries")
    if preferred_users:
        logger.debug(f"Preferred users: {', '.join(preferred_users)}")
    if excluded_users:
        logger.debug(f"Excluded users: {', '.join(excluded_users)}")

    intelligent_cache_manager = _setup_phase(context, cache_manager, plex_libraries)

    media_ids_to_process, folder_map_for_media = _discover_media_phase(
        mediux_url, plex_url, plex_token, plex_libraries
    )

    if remove_paths:
        logger.info(f"👤 YAML filtering enabled for {len(remove_paths)} path(s)")

    context.clear_new_data()

    from modules.base import MediaProcessingConfig

    config = MediaProcessingConfig(
        api_key=api_key,
        sonarr_api_key=sonarr_api_key,
        sonarr_endpoint=sonarr_endpoint,
        process_all=process_all,
        retry_on_yaml_failure=retry_on_yaml_failure,
        preferred_users=preferred_users,
        excluded_users=excluded_users,
        disable_season_fix=disable_season_fix,
        remove_paths=remove_paths,
        mediux_url=mediux_url,
    )

    separator = "=" * 60
    logger.info(f"\n{separator}\n🌐 BROWSER INITIALIZATION\n{separator}")
    logger.info("👤 Starting Chrome WebDriver...")
    from modules.scraper import MediuxLoginManager, WebDriverManager

    webdriver_manager = WebDriverManager(config_path)

    try:
        webdriver_manager.init_driver(
            headless=headless,
            profile_path=profile_path,
            chromedriver_path=chromedriver_path,
        )
        login_manager = MediuxLoginManager(webdriver_manager)
        login_manager.login(username=username, password=password, nickname=nickname)
        logger.info("✅ Successfully logged into Mediux")

        _process_media_phase(
            media_ids_to_process=media_ids_to_process,
            folder_map_for_media=folder_map_for_media,
            config=config,
            context=context,
            webdriver_manager=webdriver_manager,
            login_manager=login_manager,
            headless=headless,
            profile_path=profile_path,
            chromedriver_path=chromedriver_path,
            username=username,
            password=password,
            nickname=nickname,
        )

    finally:
        _cleanup_phase(
            context=context,
            cache_manager=cache_manager,
            intelligent_cache_manager=intelligent_cache_manager,
            output_dir_global=output_dir_global,
            discord_webhook_url_global=discord_webhook_url_global,
            media_ids_to_process=media_ids_to_process,
            webdriver_manager=webdriver_manager,
            duration=time.time() - start_time,
        )


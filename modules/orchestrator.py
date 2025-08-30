"""
Orchestrator module for Mediux Scraper.

This module coordinates the main execution flow of the Mediux scraper,
including setup, media processing, and cleanup.
"""

import logging
import os
import sys
import time

from selenium.common.exceptions import TimeoutException
from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm
from urllib3.exceptions import ReadTimeoutError

from modules.intelligent_cache import (
    set_global_cache_manager,
    create_cache_manager_from_config,
)
from modules.base import ScraperContext, FileSystemConstants

# Detect if running in an interactive terminal for progress bar control
is_interactive = sys.stdout.isatty() and sys.stderr.isatty()


logger = logging.getLogger(__name__)


def parse_mediux_url(mediux_url: str) -> tuple:
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
):
    """Main execution function."""
    # Create centralized scraper context
    context = ScraperContext()

    # Configure global cache manager with the unified settings
    cache_manager = create_cache_manager_from_config(
        disable_cache=disable_cache,
        clear_cache=clear_cache,
        cache_dir=cache_dir,
    )
    set_global_cache_manager(cache_manager)

    start_time = time.time()
    logger.info("🚀 MEDIUX SCRAPER STARTED")

    logger.info("📂 Processing media libraries")

    if preferred_users:
        logger.debug(f"Preferred users: {', '.join(preferred_users)}")
    if excluded_users:
        logger.debug(f"Excluded users: {', '.join(excluded_users)}")

    # Phase 1: Setup and Configuration
    separator = "=" * 60
    logger.info(f"\n{separator}\n🔧 SETUP & CONFIGURATION\n{separator}")

    # Ensure output directories exist
    output_dir = FileSystemConstants.OUTPUT_DIR_DEFAULT
    kometa_dir = FileSystemConstants.KOMETA_DIR
    for dir_path in [output_dir, kometa_dir]:
        if not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)
            logger.debug(f"Created directory: {dir_path}")

    # Handle cache management
    if cache_manager.clear_cache_on_startup:
        logger.info("🧹 Clearing existing cache files...")
        cache_files = [
            cache_manager.get_cache_file_path(
                FileSystemConstants.INTELLIGENT_CACHE_FILENAME
            ),
        ]
        for cache_file in cache_files:
            if os.path.exists(cache_file):
                os.remove(cache_file)
                logger.info(f"✅ Removed cache file: {cache_file}")

    if cache_manager.disable_cache:
        logger.info("🚫 Cache loading and saving disabled - fresh start each time")

        # Create a dummy intelligent cache manager that does nothing
        class DummyCacheManager:

            def get_cache_stats(self):
                """Get cache statistics. Returns empty dict when caching is disabled."""
                return {}

        intelligent_cache_manager = DummyCacheManager()
    else:
        logger.info("👤 Loading intelligent cache...")

        # Load intelligent cache
        from modules.intelligent_cache import get_cache_manager

        intelligent_cache_manager = get_cache_manager()
        # Cache loading removed - load_cache method was unused

    # Handle Plex libraries - load data for Plex library names
    if plex_libraries:
        import re

        logger.log(25, f"Loading {len(plex_libraries)} Plex libraries...")
        for lib_name in plex_libraries:
            safe_lib = re.sub(r"[^\w\-]", "_", lib_name.lower())
            from modules.file_manager import BulkDataManager

            context.folder_bulk_data[lib_name] = BulkDataManager().load_bulk_data(
                bulk_data_file=f"{FileSystemConstants.KOMETA_DIR}/{safe_lib}{FileSystemConstants.DATA_FILE_SUFFIX}"
            )

    # Phase 2: Media Discovery
    logger.info(f"\n{separator}\n🔍 MEDIA DISCOVERY\n{separator}")

    # Check for direct Mediux URL bypass
    if mediux_url:
        logger.info("🎯 Direct Mediux URL provided - bypassing Plex library discovery")
        logger.info(f"📌 Target URL: {mediux_url}")

        try:
            # Extract media ID and info from URL using helper function
            media_id, title, source, media_type = parse_mediux_url(mediux_url)

            # Create single media item for processing
            media_ids_to_process = [(media_id, title, source, media_type)]
            folder_map_for_media = {media_id: [("Direct URL", media_type)]}

            logger.info(f"📋 Created media item: ID={media_id}, Type={media_type}")
            logger.info(f"📋 Will navigate directly to: {mediux_url}")
        except ValueError as e:
            logger.error(str(e))
            exit(1)
    else:
        logger.info("👤 Scanning for media IDs...")

        from modules.media_discovery import get_media_ids

        try:
            media_ids_to_process, folder_map_for_media = get_media_ids(
                plex_url=plex_url,
                plex_token=plex_token,
                plex_libraries=plex_libraries,
            )
        except ValueError as e:
            logger.error(f"Configuration error: {e}")
            exit(1)
        except Exception as e:
            logger.error(f"Failed to retrieve media IDs: {e}")
            logger.info("Please check your Plex configuration and try again.")
            exit(1)

        if not media_ids_to_process or len(media_ids_to_process) == 0:
            logger.error("No media items found. Please check your Plex configuration.")
            logger.info(
                "Ensure 'plex_url', 'plex_token', and 'plex_libraries' are correctly configured."
            )
            exit(1)

        logger.info(f"✅ Found {len(media_ids_to_process)} media items to process")
    if remove_paths:
        logger.info(f"👤 YAML filtering enabled for {len(remove_paths)} path(s)")

    context.clear_new_data()

    # Create media processing configuration
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

    # Phase 3: WebDriver Initialization
    logger.info(f"\n{separator}\n🌐 BROWSER INITIALIZATION\n{separator}")
    logger.info("👤 Starting Chrome WebDriver...")
    from modules.scraper import MediuxLoginManager, WebDriverManager

    driver = None
    webdriver_manager = WebDriverManager(config_path)

    try:
        driver = webdriver_manager.init_driver(
            headless=headless,
            profile_path=profile_path,
            chromedriver_path=chromedriver_path,
        )

        login_manager = MediuxLoginManager(webdriver_manager)
        login_manager.login(
            driver=driver,
            username=username,
            password=password,
            nickname=nickname,
        )
        logger.info("✅ Successfully logged into Mediux")

        # Set driver in context for processing functions
        context.set_driver(driver)

        # Phase 4: Media Processing
        logger.info(f"\n{separator}\n⚙️  MEDIA PROCESSING\n{separator}")
        logger.info(f"👤 Processing {len(media_ids_to_process)} media items...")

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
                    from modules.media_processing import process_single_media_item

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

                    # Safely quit current driver and clean up processes
                    webdriver_manager.safe_quit_driver(driver)

                    # Initialize new driver with enhanced stability options
                    driver = webdriver_manager.init_driver(
                        headless=headless,
                        profile_path=profile_path,
                        chromedriver_path=chromedriver_path,
                    )

                    # Re-login to Mediux
                    login_manager.login(
                        driver=driver,
                        username=username,
                        password=password,
                        nickname=nickname,
                    )

                    # Update context with new driver
                    context.set_driver(driver)
    finally:
        # Phase 5: Cleanup and Summary
        logger.info(f"\n{separator}\n🧹 CLEANUP & SUMMARY\n{separator}")

        end_time = time.time()
        duration = end_time - start_time

        # Save intelligent cache if not disabled and it's a real cache manager
        if not cache_manager.disable_cache and "intelligent_cache_manager" in locals():
            logger.info("🧠 Saving intelligent cache...")
            try:
                filepath = cache_manager.get_cache_file_path(
                    FileSystemConstants.INTELLIGENT_CACHE_FILENAME
                )
                # Check if we have a real cache manager (not a dummy one)
                if hasattr(intelligent_cache_manager, "cache"):
                    # Use the NamespaceCache save_to_file method directly
                    getattr(intelligent_cache_manager, "cache").save_to_file(filepath)
                else:
                    logger.debug(
                        "Dummy cache manager detected - skipping intelligent cache save"
                    )
                logger.info("✅ Intelligent cache saved successfully.")
            except Exception as e:
                logger.error(f"❌ Failed to save intelligent cache: {e}")

        # Write data to files before shutting down
        logger.info("👤 Saving data to files...")

        # Use unified FileWriter implementation
        from modules.file_manager import FileWriter

        file_writer = FileWriter()
        file_writer.write_data_to_files(
            new_data=context.new_data,
            output_dir_global=output_dir_global,
        )

        logger.info("👤 Shutting down...")
        webdriver_manager.safe_quit_driver(driver)

        # Enhanced final summary
        logger.info(f"\n{separator}\n📊 FINAL RESULTS\n{separator}")

        if context.updated_titles_list:
            logger.info(f"✅ {len(context.updated_titles_list)} titles were updated:")
            for title in context.updated_titles_list:
                print(f"   • {title}")
        else:
            logger.info("📋 No titles were updated - all content was up to date")

        truly_fixed_and_updated = [
            title
            for title in context.fixed_titles_list
            if title in context.updated_titles_list
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
                    logger.debug("📊 Cache Performance:")
                    for namespace, stats in cache_stats.items():
                        if stats.get("hits", 0) > 0 or stats.get("misses", 0) > 0:
                            total = stats.get("hits", 0) + stats.get("misses", 0)
                            hit_rate = (
                                (stats.get("hits", 0) / total * 100) if total > 0 else 0
                            )
                            logger.debug(
                                f"      • {namespace}: {hit_rate:.1f}% hit rate ({stats.get('hits', 0)} hits, {stats.get('misses', 0)} misses)"
                            )
                    logger.debug(
                        f"   • Cache file: {cache_manager.get_cache_file_path(FileSystemConstants.INTELLIGENT_CACHE_FILENAME)}"
                    )
            except Exception as e:
                logger.debug(f"Could not retrieve cache stats: {e}")

        # Discord notifications
        if context.updated_titles_list and discord_webhook_url_global:
            max_titles_per_message = 15
            num_titles = len(context.updated_titles_list)

            from modules.external_services import DiscordNotifier

            discord_notifier = DiscordNotifier()
            for i in range(0, num_titles, max_titles_per_message):
                chunk = context.updated_titles_list[i : i + max_titles_per_message]
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
            from modules.external_services import DiscordNotifier

            discord_notifier = DiscordNotifier()
            discord_notifier.send_notification(
                webhook_url=discord_webhook_url_global, message=message_content
            )

        logger.info("🎉 Mediux scraper completed successfully!")


# Global variables for backward compatibility
output_dir_global = None
discord_webhook_url_global = None

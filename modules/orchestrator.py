"""
Orchestrator module for Mediux Scraper.

This module coordinates the main execution flow of the Mediux scraper,
including setup, media processing, and cleanup.
"""

import logging
import os
import time

from selenium.common.exceptions import TimeoutException
from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm
from urllib3.exceptions import ReadTimeoutError

from modules.cache_config import cache_config
from modules.media_processing import cache, folder_bulk_data, new_data

logger = logging.getLogger(__name__)


def run(
    *,
    api_key,
    username,
    password,
    profile_path,
    nickname,
    sonarr_api_key,
    sonarr_endpoint,
    root_folder_global,
    config_path=None,
    output_dir_global=None,
    discord_webhook_url_global=None,
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
    # Update global cache configuration
    global cache_config
    from modules.cache_config import CacheConfig

    cache_config = CacheConfig(
        disable_cache=disable_cache, clear_cache=clear_cache, cache_dir=cache_dir
    )

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

    # Ensure output directories exist
    output_dir = "./out"
    kometa_dir = "./out/kometa"
    for dir_path in [output_dir, kometa_dir]:
        if not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)
            logger.debug(f"Created directory: {dir_path}")

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
        from modules.file_manager import CacheManager

        cache_manager = CacheManager()
        cache = cache_manager.load_cache()

        # Load intelligent cache
        from modules.intelligent_cache import get_cache_manager

        intelligent_cache_manager = get_cache_manager()
        intelligent_cache_manager.load_cache(
            cache_config.get_cache_file_path("intelligent_cache.pkl")
        )

    if root_folder_global:
        root_folders_list = (
            root_folder_global
            if isinstance(root_folder_global, list)
            else [root_folder_global]
        )

        folder_bulk_data.clear()
        for root_path_item in root_folders_list:
            if not root_path_item or not os.path.isdir(root_path_item):
                continue
            for folder_item in os.listdir(root_path_item):
                if os.path.isdir(os.path.join(root_path_item, folder_item)):
                    from modules.file_manager import BulkDataManager

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
            from modules.file_manager import BulkDataManager

            folder_bulk_data[lib_name] = BulkDataManager().load_bulk_data(
                bulk_data_file=f"./out/kometa/{safe_lib}_data.yml"
            )

    # Phase 2: Media Discovery
    logger.info(f"\n{separator}\n🔍 MEDIA DISCOVERY\n{separator}")
    logger.info("👤 Scanning for media IDs...")

    from modules.media_discovery import get_media_ids

    media_ids_to_process, folder_map_for_media = get_media_ids(
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
        from modules.scraper import MediuxLoginManager, WebDriverManager

        webdriver_manager = WebDriverManager(config_path)
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
                    from modules.media_processing import process_single_media_item

                    process_single_media_item(
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
                    driver = webdriver_manager.init_driver(
                        headless=headless,
                        profile_path=profile_path,
                        chromedriver_path=chromedriver_path,
                    )
                    login_manager.login(
                        driver=driver,
                        username=username,
                        password=password,
                        nickname=nickname,
                    )
    finally:
        # Phase 5: Cleanup and Summary
        logger.info(f"\n{separator}\n🧹 CLEANUP & SUMMARY\n{separator}")

        end_time = time.time()
        duration = end_time - start_time

        # Save intelligent cache if not disabled and it's a real cache manager
        if not cache_config.disable_cache and "intelligent_cache_manager" in locals():
            logger.info("🧠 Saving intelligent cache...")
            try:
                filepath = cache_config.get_cache_file_path("intelligent_cache.pkl")
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
            new_data=new_data,
            cache=cache if cache_config.should_save_cache() else {},
            cache_file=(
                cache_config.get_cache_file_path("tmdb_cache.pkl")
                if cache_config.should_save_cache()
                else None
            ),
            output_dir_global=output_dir_global,
            root_folder_global=root_folder_global,
        )

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
                                f"      • {namespace}: {hit_rate:.1f}% hit rate ({stats.get('hits', 0)} hits, {stats.get('misses', 0)} misses)"
                            )
                    logger.info("   • Cache file: ./out/intelligent_cache.pkl")
            except Exception as e:
                logger.debug(f"Could not retrieve cache stats: {e}")

        # Discord notifications
        if updated_titles_list and discord_webhook_url_global:
            max_titles_per_message = 15
            num_titles = len(updated_titles_list)

            from modules.external_services import DiscordNotifier

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
            from modules.external_services import DiscordNotifier

            discord_notifier = DiscordNotifier()
            discord_notifier.send_notification(
                webhook_url=discord_webhook_url_global, message=message_content
            )

        logger.info("🎉 Mediux scraper completed successfully!")


# Global variables for backward compatibility
root_folder_global = ""
output_dir_global = None
discord_webhook_url_global = None

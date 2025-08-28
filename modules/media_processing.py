"""
Media processing module for Mediux Scraper.

This module handles the processing of individual media items,
including scraping logic, data comparison, and result management.
"""

import logging
from collections import defaultdict
from io import StringIO

# Import global YAML parser instance
from modules.config import yaml_parser

logger = logging.getLogger(__name__)


def should_skip_scraping(
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
                    f"⏭️  SKIPPING: {media_name} (ID: {key_for_log}, TMDB: {tmdb_id}) - ENDED series already in YAML."
                )
                return True
            else:
                logger.info(
                    f"📺 ONGOING TV SHOW: {media_name} (ID: {key_for_log}, TMDB: {tmdb_id}) is in YAML. Will re-scrape for comparison."
                )
                return False
        elif media_type == "movie":
            logger.info(
                f"⏭️  SKIPPING: {media_name} (TMDB: {tmdb_id}) - Movie already in YAML."
            )
            return True
    return False


def process_single_media_item(
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
    from modules.data_processor import DataComparisonEngine, YAMLStructureProcessor
    from modules.tmdb_client import TMDBClient

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
        from modules.external_services import SonarrClient

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
    should_skip = should_skip_scraping(
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
    from modules.scraper import MediuxScraper

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
                from modules.data_processor import YAMLDataFilter

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


# Global variables for backward compatibility
new_data = defaultdict(dict)
cache = {}
folder_bulk_data = {}

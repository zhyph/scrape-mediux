"""
Media processing module for Mediux Scraper.

This module handles the processing of individual media items,
including scraping logic, data comparison, and result management.
"""

import logging
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


def _resolve_tmdb_id(
    *,
    media_id_from_folder,
    external_source_type,
    media_type_from_plex,
    media_name,
    tmdb_client,
):
    """Resolve TMDB ID and media type with error handling."""
    tmdb_id = None
    media_type = media_type_from_plex

    if external_source_type == "tmdb_id":
        tmdb_id = media_id_from_folder
        if not media_type:
            try:
                _, media_type = tmdb_client.fetch_tmdb_id(
                    media_id=tmdb_id,
                    external_source="tmdb_id",
                    media_name=media_name,
                )
            except Exception as e:
                logger.error(f"Error determining media type for TMDB ID {tmdb_id}: {e}")
                return None, None
    else:
        try:
            tmdb_id, media_type_from_fetch = tmdb_client.fetch_tmdb_id(
                media_id=media_id_from_folder,
                external_source=external_source_type,
                media_name=media_name,
            )
            if not media_type:
                media_type = media_type_from_fetch
        except Exception as e:
            logger.error(
                f"  - Error fetching TMDB ID for {external_source_type} {media_id_from_folder}: {e}"
            )
            return None, None

    return tmdb_id, media_type


def _check_sonarr_status(
    *,
    media_type,
    media_name,
    tmdb_id,
    sonarr_api_key,
    sonarr_endpoint,
):
    """Check Sonarr for TV series status and return TVDB ID and ended status."""
    tvdb_id_for_tv, ended_status = None, None

    if media_type == "tv" and sonarr_api_key and sonarr_endpoint:
        from modules.external_services import SonarrClient

        sonarr_client = SonarrClient(sonarr_api_key, sonarr_endpoint)
        tvdb_id_for_tv, ended_status = sonarr_client.check_series_status(
            media_name=media_name,
            tmdb_id=tmdb_id,
        )

    return tvdb_id_for_tv, ended_status


def _get_existing_yaml_data(
    *,
    media_type,
    tvdb_id_for_tv,
    tmdb_id,
    media_id_from_folder,
    folder_map_for_media,
    folder_bulk_data,
):
    """Find and return existing YAML content, status, and log key."""
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
                break

    return old_yaml_content, is_already_in_yaml, key_for_log


def _check_tv_yaml_structure(new_raw_yaml, media_name):
    """Check if TV show YAML structure is malformed and requires fixing."""
    is_malformed = False

    try:
        parsed_for_check = yaml_parser.load(new_raw_yaml)

        if not parsed_for_check or not isinstance(parsed_for_check, dict):
            logger.warning(
                f"Could not parse YAML for '{media_name}' into a dictionary for checking."
            )
            return False

        media_id_key = next(iter(parsed_for_check))
        content = parsed_for_check.get(media_id_key)

        if not content or "seasons" not in content:
            logger.info(
                f"YAML for '{media_name}' has no 'seasons' block or empty content, structure is considered valid."
            )
            return False

        seasons_node = content.get("seasons")
        if seasons_node and seasons_node.get("episodes", None) is not None:
            logger.info(f"Detected malformed 'seasons' block for '{media_name}'.")
            is_malformed = True
        else:
            logger.info(f"YAML structure for '{media_name}' appears valid.")

    except Exception as e:
        logger.error(
            f"Error while checking YAML structure for '{media_name}': {e}",
            exc_info=True,
        )

    return is_malformed


def _fix_malformed_tv_yaml(
    new_raw_yaml,
    media_name,
    disable_season_fix,
    tvdb_id_for_tv,
    tmdb_id,
    fixed_titles_list,
    safe_append,
):
    """Handle fixing of malformed TV YAML structure."""
    if disable_season_fix:
        logger.info(
            f"Malformed YAML detected for '{media_name}' but automatic fix is disabled."
        )
        return new_raw_yaml

    from modules.data_processor import YAMLStructureProcessor

    structure_processor = YAMLStructureProcessor()
    fixed_yaml, was_fixed = structure_processor.preprocess_yaml_string(
        yaml_string=new_raw_yaml,
    )

    if was_fixed:
        logger.info(f"YAML for '{media_name}' was successfully fixed.")
        log_id_str = f"TVDB: {tvdb_id_for_tv}" if tvdb_id_for_tv else f"TMDB: {tmdb_id}"
        safe_append(fixed_titles_list, f"{media_name} ({log_id_str})")
    else:
        logger.warning(
            f"Preprocessing was triggered for '{media_name}' but no changes were made by the function."
        )

    return fixed_yaml


def _scrape_and_process_mediux_data(
    *,
    driver,
    tmdb_id,
    media_type,
    media_name,
    retry_on_yaml_failure,
    preferred_users,
    excluded_users,
    disable_season_fix,
    tvdb_id_for_tv,
    fixed_titles_list,
    safe_append,
):
    """Scrape Mediux data and process YAML structure for TV shows."""
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
        return None

    # Process YAML structure for TV shows if needed
    if media_type == "tv":
        is_malformed = _check_tv_yaml_structure(new_raw_yaml, media_name)

        if is_malformed:
            new_raw_yaml = _fix_malformed_tv_yaml(
                new_raw_yaml=new_raw_yaml,
                media_name=media_name,
                disable_season_fix=disable_season_fix,
                tvdb_id_for_tv=tvdb_id_for_tv,
                tmdb_id=tmdb_id,
                fixed_titles_list=fixed_titles_list,
                safe_append=safe_append,
            )

    return new_raw_yaml


def _extract_comparable_content(
    *,
    raw_yaml_data,
    media_name,
    media_type,
    tmdb_id,
    tvdb_id_for_tv,
    comparison_engine,
):
    """Extract comparable content from YAML data - helper function."""
    return comparison_engine.extract_comparable_content_from_scraped_yaml(
        raw_yaml_data=raw_yaml_data,
        media_name=media_name,
        media_type=media_type,
        tmdb_id=tmdb_id,
        tvdb_id_for_tv=tvdb_id_for_tv,
        remove_paths=None,
    )


def _handle_filtered_empty_case(
    *,
    parsed_yaml,
    media_name,
    tmdb_id,
):
    """Handle the case where filtering resulted in empty structure."""
    media_id_key = next(iter(parsed_yaml.keys()))
    final_yaml_data = f"# Filtered empty by remove_paths\n{media_id_key}:"
    logger.info(
        f"Filtering resulted in empty structure for '{media_name}' (TMDB: {tmdb_id}) - marked as filtered empty"
    )
    return final_yaml_data, None


def _apply_yaml_filters(
    *,
    parsed_yaml,
    remove_paths,
):
    """Apply YAML filtering logic."""
    from modules.data_processor import YAMLDataFilter

    filter_engine = YAMLDataFilter()
    return filter_engine.filter_yaml_data_by_paths(
        yaml_data=parsed_yaml,
        remove_paths=remove_paths,
    )


def _process_filtered_yaml(
    *,
    filtered_yaml,
):
    """Process filtered YAML result and convert to string."""
    string_stream = StringIO()
    yaml_parser.dump(filtered_yaml, string_stream)
    final_yaml_data = string_stream.getvalue()

    import re

    final_yaml_data = re.sub(r"(\s+)([^:\n]+):\s*\{\}", r"\1\2:", final_yaml_data)

    return final_yaml_data


def _perform_yaml_filtering(
    *,
    parsed_yaml,
    media_name,
    tmdb_id,
    new_raw_yaml,
    comparison_engine,
    media_type,
    tvdb_id_for_tv,
    remove_paths,
):
    """Perform YAML filtering and return final data and comparable content."""
    filtered_yaml = _apply_yaml_filters(
        parsed_yaml=parsed_yaml,
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
            return _handle_filtered_empty_case(
                parsed_yaml=parsed_yaml,
                media_name=media_name,
                tmdb_id=tmdb_id,
            )
        else:
            final_yaml_data = _process_filtered_yaml(
                filtered_yaml=filtered_yaml,
            )
            new_comparable_content = _extract_comparable_content(
                raw_yaml_data=final_yaml_data,
                media_name=media_name,
                media_type=media_type,
                tmdb_id=tmdb_id,
                tvdb_id_for_tv=tvdb_id_for_tv,
                comparison_engine=comparison_engine,
            )
            return final_yaml_data, new_comparable_content
    else:
        final_yaml_data = new_raw_yaml
        logger.warning(
            f"Filtering resulted in empty YAML for '{media_name}' (TMDB: {tmdb_id}), keeping original"
        )
        new_comparable_content = _extract_comparable_content(
            raw_yaml_data=final_yaml_data,
            media_name=media_name,
            media_type=media_type,
            tmdb_id=tmdb_id,
            tvdb_id_for_tv=tvdb_id_for_tv,
            comparison_engine=comparison_engine,
        )
        return final_yaml_data, new_comparable_content


def _handle_filtering_error(
    *,
    media_name,
    tmdb_id,
    new_raw_yaml,
    comparison_engine,
    media_type,
    tvdb_id_for_tv,
    e,
):
    """Handle YAML filtering errors and return fallback data."""
    logger.error(f"Failed to filter YAML for '{media_name}' (TMDB: {tmdb_id}): {e}")
    final_yaml_data = new_raw_yaml
    new_comparable_content = _extract_comparable_content(
        raw_yaml_data=final_yaml_data,
        media_name=media_name,
        media_type=media_type,
        tmdb_id=tmdb_id,
        tvdb_id_for_tv=tvdb_id_for_tv,
        comparison_engine=comparison_engine,
    )
    return final_yaml_data, new_comparable_content


def _process_tv_yaml_final(
    *, final_yaml_data, media_name, media_type, new_comparable_content
):
    """Process final YAML data for TV shows with formatting."""
    if media_type == "tv" and new_comparable_content:
        try:
            parsed_yaml_data = yaml_parser.load(final_yaml_data)
            string_stream = StringIO()
            yaml_parser.dump(parsed_yaml_data, string_stream)
            final_yaml_data = string_stream.getvalue()
        except Exception as e:
            logger.error(f"Failed to re-process TV YAML for '{media_name}': {e}")

    return final_yaml_data


def _apply_filtering_and_extract_content(
    *,
    new_raw_yaml,
    media_name,
    tmdb_id,
    tvdb_id_for_tv,
    media_type,
    remove_paths,
    comparison_engine,
):
    """Apply filtering and extract comparable content from YAML data."""
    final_yaml_data = new_raw_yaml
    new_comparable_content = None

    if remove_paths:
        try:
            parsed_yaml = yaml_parser.load(new_raw_yaml)

            if parsed_yaml and isinstance(parsed_yaml, dict):
                final_yaml_data, new_comparable_content = _perform_yaml_filtering(
                    parsed_yaml=parsed_yaml,
                    media_name=media_name,
                    tmdb_id=tmdb_id,
                    new_raw_yaml=new_raw_yaml,
                    comparison_engine=comparison_engine,
                    media_type=media_type,
                    tvdb_id_for_tv=tvdb_id_for_tv,
                    remove_paths=remove_paths,
                )
            else:
                # Fall back to original extraction if parsing failed
                new_comparable_content = _extract_comparable_content(
                    raw_yaml_data=final_yaml_data,
                    media_name=media_name,
                    media_type=media_type,
                    tmdb_id=tmdb_id,
                    tvdb_id_for_tv=tvdb_id_for_tv,
                    comparison_engine=comparison_engine,
                )
        except Exception as e:
            final_yaml_data, new_comparable_content = _handle_filtering_error(
                media_name=media_name,
                tmdb_id=tmdb_id,
                new_raw_yaml=new_raw_yaml,
                comparison_engine=comparison_engine,
                media_type=media_type,
                tvdb_id_for_tv=tvdb_id_for_tv,
                e=e,
            )
    else:
        # No filtering needed
        new_comparable_content = _extract_comparable_content(
            raw_yaml_data=final_yaml_data,
            media_name=media_name,
            media_type=media_type,
            tmdb_id=tmdb_id,
            tvdb_id_for_tv=tvdb_id_for_tv,
            comparison_engine=comparison_engine,
        )

    # Apply final TV processing
    final_yaml_data = _process_tv_yaml_final(
        final_yaml_data=final_yaml_data,
        media_name=media_name,
        media_type=media_type,
        new_comparable_content=new_comparable_content,
    )

    return final_yaml_data, new_comparable_content


def _perform_comparison_and_update(
    *,
    comparison_engine,
    media_name,
    media_type,
    tvdb_id_for_tv,
    tmdb_id,
    old_yaml_content,
    new_comparable_content,
    final_yaml_data,
    updated_titles_list,
    folder_map_for_media,
    media_id_from_folder,
    new_data,
    safe_append,
):
    """Perform comparison, update lists, and store new data."""
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

    # Store data in new_data for each folder
    for folder_name in folder_map_for_media.get(media_id_from_folder, []):
        new_data[folder_name][tmdb_id] = final_yaml_data


def process_single_media_item(
    *,
    media_id_from_folder,
    media_name,
    external_source_type,
    folder_map_for_media,
    config,
    media_type_from_plex=None,
    context=None,
):
    """Process a single media item.

    Args:
        media_id_from_folder: Media identifier from folder structure
        media_name: Name of the media item
        external_source_type: Type of external source (e.g., 'tmdb_id', 'imdb_id')
        folder_map_for_media: Mapping of folders to media items
        config: MediaProcessingConfig object containing processing parameters
        media_type_from_plex: Optional media type hint from Plex
        context: Optional ScraperContext for shared state management
    """
    # Import type hints
    from modules.base import ScraperContext, MediaProcessingConfig

    # Use provided context or create a new one for backward compatibility
    if context is None:
        context = ScraperContext()

    # Extract values from context for easier access
    new_data = context.new_data
    folder_bulk_data = context.folder_bulk_data
    updated_titles_list = context.updated_titles_list
    fixed_titles_list = context.fixed_titles_list
    driver = context.driver

    # Use standard append function
    safe_append = lambda container, item: container.append(item)

    # Log the start of processing immediately
    media_separator = "=" * 60
    logger.info(f"{media_separator}")
    logger.info(f"🎬 STARTING: {media_name}")
    logger.info(f"   Source ID: {media_id_from_folder}")
    logger.info(f"{media_separator}")

    # Initialize services
    from modules.data_processor import DataComparisonEngine
    from modules.tmdb_client import TMDBClient

    tmdb_client = TMDBClient(config.api_key)
    comparison_engine = DataComparisonEngine()

    # Resolve TMDB ID and media type
    tmdb_id, media_type = _resolve_tmdb_id(
        media_id_from_folder=media_id_from_folder,
        external_source_type=external_source_type,
        media_type_from_plex=media_type_from_plex,
        media_name=media_name,
        tmdb_client=tmdb_client,
    )

    if not tmdb_id or not media_type:
        return

    # Check Sonarr for TV series status
    tvdb_id_for_tv, ended_status = _check_sonarr_status(
        media_type=media_type,
        media_name=media_name,
        tmdb_id=tmdb_id,
        sonarr_api_key=config.sonarr_api_key,
        sonarr_endpoint=config.sonarr_endpoint,
    )

    # Check existing YAML data
    old_yaml_content, is_already_in_yaml, key_for_log = _get_existing_yaml_data(
        media_type=media_type,
        tvdb_id_for_tv=tvdb_id_for_tv,
        tmdb_id=tmdb_id,
        media_id_from_folder=media_id_from_folder,
        folder_map_for_media=folder_map_for_media,
        folder_bulk_data=folder_bulk_data,
    )

    # Determine if we should skip scraping based on series status
    should_skip = should_skip_scraping(
        media_name=media_name,
        media_type=media_type,
        tmdb_id=tmdb_id,
        key_for_log=key_for_log,
        ended_status=ended_status,
        is_in_yaml=is_already_in_yaml,
        process_all_flag=config.process_all,
    )

    if should_skip:
        # Add completion marker for skipped items
        media_separator = "=" * 60
        logger.info(f"{media_separator}\n")
        return

    # Scrape and process Mediux data
    new_raw_yaml = _scrape_and_process_mediux_data(
        driver=driver,
        tmdb_id=tmdb_id,
        media_type=media_type,
        media_name=media_name,
        retry_on_yaml_failure=config.retry_on_yaml_failure,
        preferred_users=config.preferred_users,
        excluded_users=config.excluded_users,
        disable_season_fix=config.disable_season_fix,
        tvdb_id_for_tv=tvdb_id_for_tv,
        fixed_titles_list=fixed_titles_list,
        safe_append=safe_append,
    )

    if not new_raw_yaml:
        return

    # Apply filtering and extract comparable content
    final_yaml_data, new_comparable_content = _apply_filtering_and_extract_content(
        new_raw_yaml=new_raw_yaml,
        media_name=media_name,
        tmdb_id=tmdb_id,
        tvdb_id_for_tv=tvdb_id_for_tv,
        media_type=media_type,
        remove_paths=config.remove_paths,
        comparison_engine=comparison_engine,
    )

    # Perform comparison and update lists
    _perform_comparison_and_update(
        comparison_engine=comparison_engine,
        media_name=media_name,
        media_type=media_type,
        tvdb_id_for_tv=tvdb_id_for_tv,
        tmdb_id=tmdb_id,
        old_yaml_content=old_yaml_content,
        new_comparable_content=new_comparable_content,
        final_yaml_data=final_yaml_data,
        updated_titles_list=updated_titles_list,
        folder_map_for_media=folder_map_for_media,
        media_id_from_folder=media_id_from_folder,
        new_data=new_data,
        safe_append=safe_append,
    )

    # Mark completion of this media item with prominent separator
    media_separator = "=" * 60
    logger.info(f"✅ COMPLETED: {media_name}")
    logger.info(f"{media_separator}\n")

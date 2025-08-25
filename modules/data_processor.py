"""
Data processing and filtering utilities for Mediux Scraper.

This module handles YAML data filtering, structure preprocessing, data comparison,
and change detection for the Mediux scraper.
"""

import re
import logging
from typing import Dict, List, Any, Optional, Set, Tuple
from collections.abc import Mapping, Sequence
from ruamel.yaml import YAML

logger = logging.getLogger(__name__)


class YAMLDataFilter:
    """Handles filtering of YAML data based on path patterns."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def _matches_path_pattern(self, current_path: List[str], pattern: str) -> bool:
        """
        Check if a path matches a pattern with wildcards.

        Args:
            current_path: List of keys representing the current path
            pattern: Pattern string with wildcards

        Returns:
            True if the path matches the pattern
        """
        pattern_parts = pattern.split(".")
        path_parts = [str(p) for p in current_path]

        # If pattern is longer than path, no match
        if len(pattern_parts) > len(path_parts):
            return False

        # For basic field names (no dots), be more selective about matching
        if len(pattern_parts) == 1 and "." not in pattern:
            field_name = pattern_parts[0]
            # Only match if the last part of the path equals the pattern
            if path_parts[-1] != field_name:
                return False

            # For basic field patterns, only match top-level fields (directly under media ID)
            # Don't match fields that are nested deeper in structures like seasons or episodes
            if len(path_parts) != 2:
                # This field is nested deeper than the top level - don't match basic field patterns
                return False

            return True

        # For dotted patterns, try to match at every possible starting position in the path
        for start_pos in range(len(path_parts) - len(pattern_parts) + 1):
            matches = True
            for i, pattern_part in enumerate(pattern_parts):
                path_part = path_parts[start_pos + i]
                if pattern_part != "*" and pattern_part != path_part:
                    matches = False
                    break
            if matches:
                return True

        return False

    def _should_remove_path(
        self, current_path: List[str], remove_paths: Optional[List[str]]
    ) -> bool:
        """
        Determine if a path should be removed based on remove_paths patterns.

        Args:
            current_path: Current path being evaluated
            remove_paths: List of path patterns to remove

        Returns:
            True if the path should be removed
        """
        if not remove_paths:
            return False

        path_str = ".".join(str(p) for p in current_path)
        self.logger.debug(f"Checking path: {path_str}")

        for pattern in remove_paths:
            matches = self._matches_path_pattern(current_path, pattern)
            if matches:
                self.logger.debug(f"  Path {path_str} matches pattern {pattern}")
                return True
            else:
                self.logger.debug(f"  Path {path_str} does NOT match pattern {pattern}")

        return False

    def filter_yaml_data_by_paths(
        self, yaml_data: Dict[str, Any], remove_paths: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Filter YAML data by removing specified fields using path patterns.

        Args:
            yaml_data: Parsed YAML data (dict)
            remove_paths: List of field path patterns to remove

        Returns:
            Filtered YAML data
        """
        if not yaml_data or not isinstance(yaml_data, dict):
            return yaml_data

        if not remove_paths:
            return yaml_data

        self.logger.debug(f"Filtering YAML data with remove_paths: {remove_paths}")

        def filter_recursive(obj: Any, path: List[str]) -> Any:
            """Apply remove_paths filtering recursively."""
            if isinstance(obj, dict):
                filtered_dict = {}
                for key, value in obj.items():
                    new_path = path + [str(key)]
                    # Check if this field (key) should be removed
                    field_should_be_removed = self._should_remove_path(
                        new_path, remove_paths
                    )
                    if not field_should_be_removed:
                        if isinstance(value, (dict, list)):
                            filtered_value = filter_recursive(value, new_path)
                            # Only add the key if the filtered value is not None and not empty
                            if filtered_value is not None and not (
                                isinstance(filtered_value, dict)
                                and len(filtered_value) == 0
                            ):
                                filtered_dict[key] = filtered_value
                        else:
                            # For leaf values, add them directly since we've already checked the key path
                            filtered_dict[key] = value
                # Handle empty structures intelligently for Kometa compatibility
                if not filtered_dict:
                    # Check if this is the seasons section - convert to empty list for Kometa
                    if path and len(path) >= 1 and path[-1] == "seasons":
                        # Convert empty seasons dict to empty list to avoid iteration errors
                        return []

                    # Check if this is a structural element that should be preserved
                    if path and len(path) >= 2:
                        parent_key = path[-2] if len(path) >= 2 else None
                        if parent_key == "seasons":
                            # This is a season entry - preserve it even if empty
                            return {}
                        elif (
                            path[-1].isdigit()
                            and len(path) >= 3
                            and path[-3] == "seasons"
                        ):
                            # This is a season number - preserve it even if empty
                            return {}
                        elif parent_key == "episodes":
                            # This is an episode entry - preserve it even if empty
                            return {}

                    # Check if we're at the top level (media ID level)
                    if len(path) == 1:
                        # At the top level, mark as filtered empty
                        return {"_filtered_empty_": True}

                    # For other cases, return empty dict to preserve structure
                    return {}

                # Check if this is the seasons section and all its children are empty
                if path and len(path) >= 1 and path[-1] == "seasons":
                    # Check if all values in the seasons dict are empty
                    if all(
                        isinstance(v, dict) and len(v) == 0
                        for v in filtered_dict.values()
                    ):
                        # All season entries are empty - convert to empty list for Kometa compatibility
                        return []

                return filtered_dict
            elif isinstance(obj, list):
                filtered_list = []
                for i, item in enumerate(obj):
                    new_path = path + [str(i)]
                    if not self._should_remove_path(new_path, remove_paths):
                        if isinstance(item, (dict, list)):
                            filtered_item = filter_recursive(item, new_path)
                            if filtered_item is not None and not (
                                isinstance(filtered_item, dict)
                                and len(filtered_item) == 0
                            ):
                                filtered_list.append(filtered_item)
                        else:
                            # For list items, check if the item should be removed
                            if not self._should_remove_path(new_path, remove_paths):
                                filtered_list.append(item)

                # For lists, preserve them even if they're empty to maintain structure
                # Only mark as filtered empty if we're at the top level
                if not filtered_list:
                    # Check if we're at the top level (media ID level)
                    if len(path) == 1:
                        # At the top level, mark as filtered empty
                        return {"_filtered_empty_": True}

                    # For other cases, return empty list to preserve structure
                    return []

                return filtered_list
            else:
                return obj

        filtered_data = {}
        for media_id, content in yaml_data.items():
            if remove_paths:
                # For remove_paths: use filtering to remove specified paths
                filtered_content = filter_recursive(content, [str(media_id)])
                if filtered_content is not None:
                    filtered_data[media_id] = filtered_content

        if remove_paths:
            self.logger.info(
                f"YAML filtering applied - removing paths: {', '.join(remove_paths)}"
            )

        return filtered_data if filtered_data else yaml_data


class YAMLStructureProcessor:
    """Handles YAML structure preprocessing and fixes."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def preprocess_yaml_string(self, yaml_string: str) -> Tuple[str, bool]:
        """
        Pre-processes a raw YAML string to fix structural issues where multiple
        'episodes:' blocks appear directly under 'seasons:'. This is invalid YAML.
        The function uses a targeted regex to wrap each misplaced 'episodes:' block
        in a numbered season key.

        Args:
            yaml_string: Raw YAML string to process

        Returns:
            Tuple containing the processed YAML string and a boolean indicating
            if any changes were made.
        """
        if "seasons:" not in yaml_string or "episodes:" not in yaml_string:
            return yaml_string, False

        seasons_match = re.search(
            r"^(?P<indent>\s*)seasons:", yaml_string, re.MULTILINE
        )
        if not seasons_match:
            return yaml_string, False

        seasons_indent = seasons_match.group("indent")
        valid_season_indent = seasons_indent + "  "
        misplaced_episode_indent = valid_season_indent + "  "

        regex = re.compile(
            f"^{re.escape(misplaced_episode_indent)}episodes:", re.MULTILINE
        )
        matches = regex.findall(yaml_string)

        if not matches:
            return yaml_string, False

        season_count = 1

        def season_replacer(match):
            nonlocal season_count
            replacement = f"{valid_season_indent}{season_count}:\n{match.group(0)}"
            season_count += 1
            return replacement

        self.logger.info(
            f"Preprocessing YAML to fix {len(matches)} misplaced 'episodes' blocks."
        )
        processed_yaml = regex.sub(season_replacer, yaml_string)

        return processed_yaml, True


class DataComparisonEngine:
    """Handles comparison of YAML data and change detection."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def compare_yaml_and_log_changes(
        self,
        media_name: str,
        media_type: str,
        id_for_logging: str,
        old_content: Any,
        new_content_to_compare: Any,
    ) -> bool:
        """
        Compare old and new YAML content and log changes.

        Args:
            media_name: Name of the media item
            media_type: Type of media ('movie' or 'tv')
            id_for_logging: ID to use for logging
            old_content: Previous YAML content
            new_content_to_compare: New YAML content to compare

        Returns:
            True if content has changed, False otherwise
        """
        if new_content_to_compare is None:
            self.logger.warning(
                f"No new YAML content to compare for '{media_name}' (ID: {id_for_logging})."
            )
            return False

        import logging
        from typing import Dict, List, Any, Optional, Set, Tuple
        from collections.abc import Mapping, Sequence

        from modules.tmdb_client import to_standard_dict

        std_new_content = to_standard_dict(item=new_content_to_compare)
        id_type_str = "TVDB" if media_type == "tv" else "TMDB"

        if old_content is None:
            self.logger.info(
                f"New {media_type} entry for '{media_name}' ({id_type_str}: {id_for_logging}). Adding to updated titles."
            )
            return True

        std_old_content = to_standard_dict(item=old_content)
        if std_new_content != std_old_content:
            self.logger.info(
                f"YAML data for {media_type} '{media_name}' ({id_type_str}: {id_for_logging}) has changed."
            )
            return True
        else:
            self.logger.info(
                f"YAML data for {media_type} '{media_name}' ({id_type_str}: {id_for_logging}) is unchanged."
            )
            return False

    def extract_comparable_content_from_scraped_yaml(
        self,
        raw_yaml_data: str,
        media_name: str,
        media_type: str,
        tmdb_id: str,
        tvdb_id_for_tv: Optional[str],
        yaml_parser: YAML,
        remove_paths: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Extract comparable content from scraped YAML data.

        Args:
            raw_yaml_data: Raw YAML string
            media_name: Name of the media item
            media_type: Type of media
            tmdb_id: TMDB ID
            tvdb_id_for_tv: TVDB ID (for TV shows)
            yaml_parser: YAML parser instance
            remove_paths: Paths to remove during filtering

        Returns:
            Extracted content or None if parsing fails
        """
        if not raw_yaml_data:
            return None

        try:
            parsed_wrapper = yaml_parser.load(raw_yaml_data)
            if not parsed_wrapper or not isinstance(parsed_wrapper, dict):
                self.logger.error(
                    f"Parsed new YAML for '{media_name}' (TMDB: {tmdb_id}) is not a valid dictionary or is empty."
                )
                return None

            from modules.tmdb_client import to_standard_dict

            parsed_wrapper = {
                str(k): to_standard_dict(v) for k, v in parsed_wrapper.items()
            }

            # Apply filtering if specified
            if remove_paths:
                filter_engine = YAMLDataFilter()
                parsed_wrapper = filter_engine.filter_yaml_data_by_paths(
                    yaml_data=parsed_wrapper,
                    remove_paths=remove_paths,
                )
                if not parsed_wrapper or (
                    isinstance(parsed_wrapper, dict)
                    and len(parsed_wrapper) == 1
                    and parsed_wrapper.get("_filtered_empty_")
                ):
                    if isinstance(parsed_wrapper, dict) and parsed_wrapper.get(
                        "_filtered_empty_"
                    ):
                        self.logger.info(
                            f"Filtering resulted in empty structure for '{media_name}' (TMDB: {tmdb_id}) - marked as filtered empty"
                        )
                    else:
                        self.logger.warning(
                            f"Filtering removed all content for '{media_name}' (TMDB: {tmdb_id})"
                        )
                    return None

            expected_key = str(tvdb_id_for_tv if media_type == "tv" else tmdb_id)

            if expected_key in parsed_wrapper:
                return parsed_wrapper[expected_key]
            elif len(parsed_wrapper) == 1:
                first_key = list(parsed_wrapper.keys())[0]
                self.logger.warning(
                    f"Scraped YAML for '{media_name}' (TMDB: {tmdb_id}) was keyed by '{first_key}' instead of expected '{expected_key}'. Using content from '{first_key}'."
                )
                return parsed_wrapper[first_key]
            else:
                self.logger.error(
                    f"Could not find expected key '{expected_key}' or a single key in newly parsed YAML for '{media_name}': {list(parsed_wrapper.keys())}"
                )
                return None

        except Exception as e:
            self.logger.error(
                f"Failed to parse or process newly scraped YAML for '{media_name}' (TMDB: {tmdb_id}): {e}"
            )
            return None


class SetURLExtractor:
    """Extracts set URLs from YAML data."""

    def extract_set_urls(self, yaml_data: str) -> Set[str]:
        """
        Extract set URLs from YAML data.

        Args:
            yaml_data: YAML data as string

        Returns:
            Set of extracted URLs
        """
        set_urls = set()
        lines = yaml_data.split("\n")
        for line in lines:
            match = re.search(r"#.*(https://mediux.pro/sets/\d+)", line)
            if match:
                set_urls.add(match.group(1))
        return set_urls

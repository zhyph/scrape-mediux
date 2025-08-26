"""
External service integrations for Mediux Scraper.

This module handles integrations with external services like Sonarr,
Discord notifications, and Plex API for media discovery.
"""

import os
import re
import logging
import requests
from typing import List, Dict, Any, Optional, Tuple, Set, Union
from collections import defaultdict
from tenacity import retry, stop_after_attempt, wait_fixed

logger = logging.getLogger(__name__)

# Import intelligent cache
from modules.intelligent_cache import get_cache_manager


class DiscordNotifier:
    """Handles Discord webhook notifications."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def send_notification(self, webhook_url: Optional[str], message: str) -> None:
        """
        Send a notification to Discord webhook.

        Args:
            webhook_url: Discord webhook URL
            message: Message to send
        """
        if not webhook_url:
            self.logger.debug(
                "Discord webhook URL not configured. Skipping notification."
            )
            return

        if not message:
            self.logger.debug(
                "No message content to send to Discord. Skipping notification."
            )
            return

        self.logger.info(f"Sending notification to Discord: {message[:100]}...")
        payload = {"content": message}
        try:
            response = requests.post(webhook_url, json=payload, timeout=10)
            response.raise_for_status()
            self.logger.info("Discord notification sent successfully.")
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Failed to send Discord notification: {e}")


class SonarrClient:
    """Client for interacting with Sonarr API."""

    def __init__(self, api_key: str, endpoint: str):
        self.api_key = api_key
        self.endpoint = endpoint.rstrip("/")
        self.headers = {
            "X-Api-Key": api_key,
            "accept": "application/json",
        }
        self.logger = logging.getLogger(__name__)

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def check_series_status(
        self, media_name: str, tmdb_id: Optional[str] = None
    ) -> Tuple[Optional[str], Optional[bool]]:
        """
        Check series status in Sonarr.

        Args:
            media_name: Name of the series to check
            tmdb_id: Optional TMDB ID for precise matching

        Returns:
            Tuple of (tvdb_id, ended_status) or (None, None) if not found
        """
        self.logger.info(f"Checking series status for {media_name}...")

        # Try intelligent cache first
        cache_manager = get_cache_manager()
        cached_result = cache_manager.get_sonarr_status(media_name, tmdb_id)

        if cached_result:
            self.logger.info(f"Sonarr cache hit for {media_name}")
            return cached_result

        url = f"{self.endpoint}/api/v3/series/lookup?term={media_name}"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        data = response.json()

        if data and isinstance(data, list):
            if tmdb_id:
                self.logger.debug(f"Searching for series with TMDB ID: {tmdb_id}")
                for series in data:
                    series_tmdb_id = series.get("tmdbId")
                    if series_tmdb_id and str(series_tmdb_id) == str(tmdb_id):
                        self.logger.info(
                            f"Found matching series for '{media_name}' by TMDB ID: {tmdb_id}"
                        )
                        tvdb_id = series.get("tvdbId")
                        ended = series.get("ended")
                        self.logger.info(
                            f"Series status for {media_name}: TVDB ID={tvdb_id}, Ended={ended}."
                        )

                        # Cache the result
                        result = (str(tvdb_id) if tvdb_id else None, ended)
                        cache_manager.set_sonarr_status(
                            media_name, tmdb_id, result[0], result[1]
                        )
                        return result
                self.logger.warning(
                    f"No series with TMDB ID {tmdb_id} found for '{media_name}'. Falling back to first result."
                )

            series_info = data[0]
            tvdb_id = series_info.get("tvdbId")
            ended = series_info.get("ended")
            self.logger.info(
                f"Series status for {media_name} (from first result): TVDB ID={tvdb_id}, Ended={ended}."
            )

            # Cache the result
            result = (str(tvdb_id) if tvdb_id else None, ended)
            cache_manager.set_sonarr_status(media_name, tmdb_id, result[0], result[1])
            return result

        self.logger.warning(f"No series information found for {media_name}.")
        # Cache the negative result to avoid repeated API calls
        cache_manager.set_sonarr_status(media_name, tmdb_id, None, None)
        return None, None


class PlexClient:
    """Client for interacting with Plex API."""

    def __init__(self, url: str, token: str):
        self.url = url.rstrip("/")
        self.token = token
        self.logger = logging.getLogger(__name__)

    def get_media_ids_from_plex(
        self, libraries: List[str]
    ) -> Tuple[List[Tuple[str, str, str, str]], Dict[str, List[str]]]:
        """
        Fetch media IDs from Plex libraries.

        Args:
            libraries: List of library names to scan

        Returns:
            Tuple of (media_ids_list, folder_map)
        """
        self.logger.info("Fetching media IDs from Plex API...")

        # Try intelligent cache first
        cache_manager = get_cache_manager()
        cache_key = f"plex:{':'.join(sorted(libraries))}"

        cached_result = cache_manager.cache.get("media_ids", cache_key)
        if cached_result:
            self.logger.info("Plex media IDs cache hit")
            return cached_result

        # Cache miss - perform the API calls
        try:
            from plexapi.server import PlexServer
        except ImportError:
            self.logger.error(
                "plexapi is not installed. Please add 'plexapi' to requirements.txt."
            )
            raise

        plex = PlexServer(self.url, self.token)
        media_ids = []
        folder_map = defaultdict(list)

        for lib_name in libraries:
            self.logger.info(f"Scanning Plex library: {lib_name}")
            try:
                library = plex.library.section(lib_name)
            except Exception as e:
                self.logger.error(f"Invalid Plex library section: {lib_name} ({e})")
                continue

            try:
                for item in library.all():
                    media_name = item.title
                    media_type = "tv" if library.type == "show" else library.type

                    # Extract and normalize GUIDs
                    guids = {
                        guid.id.split("://")[0]
                        .replace("themoviedb", "tmdb")
                        .replace("thetvdb", "tvdb"): guid.id.split("://")[1]
                        .split("?")[0]
                        for guid in item.guids
                    }

                    # Prioritize which ID to use
                    id_to_use, source = None, None
                    if "tmdb" in guids:
                        id_to_use, source = guids["tmdb"], "tmdb_id"
                    elif "imdb" in guids:
                        id_to_use, source = guids["imdb"], "imdb_id"
                    elif "tvdb" in guids:
                        id_to_use, source = guids["tvdb"], "tvdb_id"

                    if id_to_use and source:
                        media_ids.append((id_to_use, media_name, source, media_type))
                        folder_map[id_to_use].append((lib_name, media_type))
                    else:
                        self.logger.warning(
                            f"No usable ID found for '{media_name}' in Plex library '{lib_name}'"
                        )
            except Exception as e:
                self.logger.error(f"Error scanning library '{lib_name}': {e}")
                continue

        self.logger.info(f"Found {len(media_ids)} media IDs from Plex.")
        result = (media_ids, folder_map)

        # Cache the result for future use
        cache_manager.cache.set("media_ids", cache_key, result)
        return result

    def list_available_libraries(self) -> List[str]:
        """
        List all available Plex libraries.

        Returns:
            List of library names
        """
        try:
            from plexapi.server import PlexServer
        except ImportError:
            self.logger.error(
                "plexapi is not installed. Please add 'plexapi' to requirements.txt."
            )
            raise

        plex = PlexServer(self.url, self.token)
        available = [section.title for section in plex.library.sections()]

        self.logger.info("Available Plex libraries:")
        for lib in available:
            self.logger.info(f"  - {lib}")

        return available


class MediaDiscoveryService:
    """Service for discovering media from various sources."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def get_media_ids_from_folder(
        self,
        root_folder: Union[str, List[str]],
        selected_folders: Optional[List[str]] = None,
    ) -> Tuple[List[Tuple[str, str, str, None]], Dict[str, List[str]]]:
        """
        Get media IDs from folder structure.

        Args:
            root_folder: Root folder(s) to scan
            selected_folders: Optional list of specific folders to process

        Returns:
            Tuple of (media_ids_list, folder_map)
        """
        self.logger.info("Fetching media IDs from folder names...")

        # Try intelligent cache first
        cache_manager = get_cache_manager()
        cache_key = self._generate_folder_cache_key(root_folder, selected_folders)

        cached_result = cache_manager.cache.get("media_ids", cache_key)
        if cached_result:
            self.logger.info("Media IDs cache hit for folder scan")
            return cached_result

        # Cache miss - perform the scan

        import os
        from modules.config import validate_path

        validate_path(path=root_folder, description="Root folder")

        media_ids = []
        folder_map = defaultdict(list)
        root_folders = root_folder if isinstance(root_folder, list) else [root_folder]

        for root in root_folders:
            if not root:
                continue
            folders_to_search = (
                selected_folders if selected_folders else os.listdir(root)
            )

            for folder in folders_to_search:
                self.logger.debug(f"Searching folder: {folder}")
                folder_path = os.path.join(root, folder)
                if os.path.isdir(folder_path):
                    self._process_subfolders(
                        folder_path=folder_path,
                        folder=folder,
                        media_ids=media_ids,
                        folder_map=folder_map,
                    )

        self.logger.info(f"Found media IDs: {media_ids}")
        result = (media_ids, folder_map)

        # Cache the result for future use
        cache_manager.cache.set("media_ids", cache_key, result)
        return result

    def _generate_folder_cache_key(
        self,
        root_folder: Union[str, List[str]],
        selected_folders: Optional[List[str]] = None,
    ) -> str:
        """
        Generate a cache key that includes folder content information to detect changes.

        Args:
            root_folder: Root folder(s) to scan
            selected_folders: Optional list of specific folders to process

        Returns:
            Cache key string that changes when folder contents change
        """
        import os
        import hashlib

        # Base key components
        root_key = (
            str(root_folder) if isinstance(root_folder, str) else ":".join(root_folder)
        )
        folder_key = str(sorted(selected_folders or []))

        # Get folder modification information
        folder_info = []
        root_folders = root_folder if isinstance(root_folder, list) else [root_folder]

        for root in root_folders:
            if not root or not os.path.exists(root):
                continue

            try:
                # Get root folder modification time
                root_mtime = os.path.getmtime(root)
                folder_info.append(f"root_mtime:{root_mtime}")

                # Get list of subdirectories if not using selected_folders
                if not selected_folders:
                    subdirs = []
                    for item in os.listdir(root):
                        item_path = os.path.join(root, item)
                        if os.path.isdir(item_path):
                            # Include subdirectory name and its modification time
                            item_mtime = os.path.getmtime(item_path)
                            subdirs.append(f"{item}:{item_mtime}")

                    # Sort for consistent ordering
                    subdirs.sort()
                    folder_info.append(f"subdirs:{'|'.join(subdirs)}")
                else:
                    # When using selected_folders, include their modification times
                    selected_info = []
                    for folder in selected_folders:
                        folder_path = os.path.join(root, folder)
                        if os.path.exists(folder_path):
                            folder_mtime = os.path.getmtime(folder_path)
                            selected_info.append(f"{folder}:{folder_mtime}")

                    selected_info.sort()
                    folder_info.append(f"selected:{'|'.join(selected_info)}")

            except OSError as e:
                self.logger.warning(f"Could not get folder info for {root}: {e}")
                folder_info.append(f"error:{root}")

        # Combine all information into a hash
        key_components = [root_key, folder_key] + sorted(folder_info)
        key_string = "|".join(key_components)

        # Use MD5 hash to keep key length reasonable
        return hashlib.md5(key_string.encode()).hexdigest()

    def _extract_media_info_from_subfolder(
        self, subfolder: str
    ) -> Optional[Tuple[str, str, str]]:
        """
        Extract media information from subfolder name.

        Args:
            subfolder: Subfolder name to parse

        Returns:
            Tuple of (media_id, media_name, external_source) or None if not parseable
        """
        imdb_match = re.search(r"imdb-(tt\d+)", subfolder)
        tvdb_match = re.search(r"tvdb-(\d+)", subfolder)
        tmdb_match = re.search(r"tmdb-(\d+)", subfolder)
        name_match = re.search(r"(.+)(?=\{(imdb|tvdb|tmdb)-)", subfolder)

        if imdb_match and name_match:
            media_id = imdb_match.group(1)
            external_source = "imdb_id"
        elif tvdb_match and name_match:
            media_id = tvdb_match.group(1)
            external_source = "tvdb_id"
        elif tmdb_match and name_match:
            media_id = tmdb_match.group(1)
            external_source = "tmdb_id"
        else:
            return None

        media_name = name_match.group(1).strip()
        return media_id, media_name, external_source

    def _process_subfolders(
        self,
        folder_path: str,
        folder: str,
        media_ids: List[Tuple[str, str, str, None]],
        folder_map: Dict[str, List[str]],
    ) -> None:
        """
        Process subfolders to extract media information.

        Args:
            folder_path: Path to the folder to process
            folder: Name of the folder
            media_ids: List to append found media IDs
            folder_map: Map to track folder associations
        """
        subfolders = os.listdir(folder_path)
        for subfolder in subfolders:
            subfolder_path = os.path.join(folder_path, subfolder)
            if os.path.isdir(subfolder_path):
                media_info = self._extract_media_info_from_subfolder(
                    subfolder=subfolder
                )
                if media_info:
                    media_id, media_name, external_source = media_info
                    media_ids.append((media_id, media_name, external_source, None))
                    folder_map[media_id].append(folder)

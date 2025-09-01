"""
External service integrations for Mediux Scraper.

This module handles integrations with external services like Sonarr,
Discord notifications, and Plex API for media discovery.
"""

import logging
import os
import re
from collections import defaultdict
from typing import Dict, List, Optional, Tuple, Union

import requests

from modules.base import WebAutomationConstants
from modules.http_client import get_global_session
from modules.intelligent_cache import get_cache_manager

logger = logging.getLogger(__name__)


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
            session = get_global_session()
            response = session.post(
                webhook_url,
                json=payload,
                timeout=WebAutomationConstants.ELEMENT_WAIT_TIMEOUT_STANDARD,
            )
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
            return cached_result

        url = f"{self.endpoint}/api/v3/series/lookup?term={media_name}"
        session = get_global_session()
        response = session.get(url, headers=self.headers)
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

        try:
            from plexapi.server import PlexServer
        except ImportError:
            self.logger.error(
                "plexapi is not installed. Please add 'plexapi' to requirements.txt."
            )
            raise

        session = get_global_session()
        plex = PlexServer(self.url, self.token, session=session)
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

        session = get_global_session()
        plex = PlexServer(self.url, self.token, session=session)
        available = [section.title for section in plex.library.sections()]

        self.logger.info("Available Plex libraries:")
        for lib in available:
            self.logger.info(f"  - {lib}")

        return available

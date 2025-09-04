"""
External service integrations for Mediux Scraper.

This module handles integrations with external services like Sonarr,
Discord notifications, and Plex API for media discovery.
"""

import logging
import time
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import requests

from modules.base import WebAutomationConstants
from modules.http_client import get_global_session
from modules.intelligent_cache import get_cache_manager

logger = logging.getLogger(__name__)


class DiscordNotifier:
    """Handles Discord webhook notifications."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def send_notification(
        self, webhook_url: Optional[str], message: str
    ) -> tuple[bool, Optional[int]]:
        """
        Send a notification to Discord webhook.

        Args:
            webhook_url: Discord webhook URL
            message: Message to send

        Returns:
            bool: True if sent successfully, False if rate limited
        """
        if not webhook_url:
            self.logger.debug(
                "Discord webhook URL not configured. Skipping notification."
            )
            return (True, None)

        if not message:
            self.logger.debug(
                "No message content to send to Discord. Skipping notification."
            )
            return (True, None)

        self.logger.debug(f"Sending notification to Discord: {message[:100]}...")
        payload = {"content": message}
        try:
            session = get_global_session()
            response = session.post(
                webhook_url,
                json=payload,
                timeout=WebAutomationConstants.ELEMENT_WAIT_TIMEOUT_STANDARD,
            )
            response.raise_for_status()
            self.logger.debug("Discord notification sent successfully.")
            return (True, None)
        except requests.exceptions.HTTPError as e:
            if hasattr(e, "response") and e.response and e.response.status_code == 429:
                # Rate limit exceeded
                retry_after = e.response.headers.get("Retry-After", "300")
                try:
                    wait_time = int(retry_after)
                except ValueError:
                    wait_time = 300  # Default to 5 minutes if invalid
                self.logger.warning(
                    f"Discord rate limit hit! Waiting {wait_time} seconds until retry."
                )
                return (False, wait_time)
            else:
                self.logger.error(f"HTTP error sending Discord notification: {e}")
                return (True, None)  # Return True to avoid stopping the whole process
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Failed to send Discord notification: {e}")
            return (True, None)  # Return True to avoid stopping the whole process

    @staticmethod
    def send_rate_limited_message(
        webhook_url: Optional[str], total_titles: int, wait_time: int = 300
    ) -> None:
        """
        Send a final message when the report was too long and got rate limited.
        Waits for the specified time before sending.

        Args:
            webhook_url: Discord webhook URL
            total_titles: Total number of titles that were being reported
            wait_time: Time to wait in seconds before sending (default 5 minutes)
        """
        if not webhook_url:
            return

        logger.info(
            f"⏳ Waiting {wait_time} seconds for Discord rate limit to expire..."
        )
        time.sleep(wait_time)

        message = (
            f"🔥 Final report length was too much for Discord!\n"
            f"📊 Processed {total_titles} titles total.\n"
            f"📋 Check the logs for the complete report."
        )
        discord_notifier = DiscordNotifier()
        # Try to send the final message, but if rate limited again, just log it
        success, _ = discord_notifier.send_notification(webhook_url, message)
        if not success:
            logger.warning(
                "Final rate limit message was also rate limited - the report summary couldn't be sent."
            )


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
        self._plex_server = None

    def _get_plex_server(self):
        """Get or create the PlexServer instance (lazy loading)."""
        if self._plex_server is None:
            try:
                from plexapi.server import PlexServer
            except ImportError:
                self.logger.error(
                    "plexapi is not installed. Please add 'plexapi' to requirements.txt."
                )
                raise
            session = get_global_session()
            self._plex_server = PlexServer(self.url, self.token, session=session)
        return self._plex_server

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

        plex = self._get_plex_server()
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
        plex = self._get_plex_server()
        available = [section.title for section in plex.library.sections()]

        self.logger.info("Available Plex libraries:")
        for lib in available:
            self.logger.info(f"  - {lib}")

        return available

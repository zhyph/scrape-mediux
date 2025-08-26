"""
TMDB API client for Mediux Scraper.

This module handles all interactions with The Movie Database (TMDB) API,
including ID resolution, title similarity calculations, and external ID lookups.
"""

import logging
import re
from collections.abc import Mapping, Sequence
from typing import Any, Dict, List, Optional, Tuple

import requests
from tenacity import retry, stop_after_attempt, wait_fixed

from modules.intelligent_cache import get_cache_manager

logger = logging.getLogger(__name__)


class TitleSimilarityCalculator:
    """Handles title similarity calculations for media matching."""

    def calculate_similarity(self, title1: str, title2: str) -> float:
        """
        Calculate similarity score between two titles using Jaccard similarity.

        Args:
            title1: First title to compare
            title2: Second title to compare

        Returns:
            Similarity score between 0.0 and 1.0
        """
        if not title1 or not title2:
            return 0.0

        # Normalize titles: remove punctuation and convert to lowercase
        title1 = re.sub(r"[^\w\s]", "", title1.lower())
        title2 = re.sub(r"[^\w\s]", "", title2.lower())

        # Create word sets
        words1 = set(title1.split())
        words2 = set(title2.split())

        # Calculate Jaccard similarity
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))

        if union == 0:
            return 0.0

        return intersection / union


class TMDBClient:
    """Client for interacting with TMDB API."""

    BASE_URL = "https://api.themoviedb.org/3"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "accept": "application/json",
        }
        self.similarity_calculator = TitleSimilarityCalculator()
        self.logger = logging.getLogger(__name__)

    def _check_direct_tmdb_api(
        self, media_id: str
    ) -> Tuple[bool, bool, Optional[requests.Response], Optional[requests.Response]]:
        """
        Check if a TMDB ID exists as either movie or TV show.

        Args:
            media_id: TMDB ID to check

        Returns:
            Tuple of (tv_exists, movie_exists, tv_response, movie_response)
        """
        self.logger.debug(f"Using TMDB ID {media_id} directly.")

        tv_url = f"{self.BASE_URL}/tv/{media_id}"
        movie_url = f"{self.BASE_URL}/movie/{media_id}"
        tv_response = movie_response = None

        try:
            tv_response = requests.get(tv_url, headers=self.headers)
        except Exception as e:
            self.logger.debug(f"Error checking TV endpoint for TMDB ID {media_id}: {e}")

        try:
            movie_response = requests.get(movie_url, headers=self.headers)
        except Exception as e:
            self.logger.debug(
                f"Error checking movie endpoint for TMDB ID {media_id}: {e}"
            )

        tv_exists = tv_response is not None and tv_response.status_code == 200
        movie_exists = movie_response is not None and movie_response.status_code == 200

        return tv_exists, movie_exists, tv_response, movie_response

    def _resolve_direct_tmdb_conflict(
        self,
        media_id: str,
        media_name: Optional[str],
        tv_response: requests.Response,
        movie_response: requests.Response,
    ) -> Tuple[str, str]:
        """
        Resolve conflict when TMDB ID exists as both movie and TV show.

        Args:
            media_id: TMDB ID with conflict
            media_name: Media name for similarity comparison
            tv_response: TV show API response
            movie_response: Movie API response

        Returns:
            Tuple of (resolved_media_id, media_type)
        """
        self.logger.warning(
            f"TMDB ID {media_id} exists as both movie and TV show. Using media name to decide."
        )

        if not media_name:
            self.logger.info("No media name provided. Defaulting to TV show.")
            return media_id, "tv"

        tv_data = tv_response.json()
        movie_data = movie_response.json()

        tv_title = tv_data.get("name", "")
        movie_title = movie_data.get("title", "")

        tv_score = self.similarity_calculator.calculate_similarity(media_name, tv_title)
        movie_score = self.similarity_calculator.calculate_similarity(
            media_name, movie_title
        )

        self.logger.info(".2f")

        if tv_score > movie_score:
            self.logger.info(f"Selected TV show '{tv_title}' based on title similarity")
            return media_id, "tv"
        else:
            self.logger.info(
                f"Selected movie '{movie_title}' based on title similarity"
            )
            return media_id, "movie"

    def _query_external_id(
        self, media_id: str, external_source: str
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Query TMDB API for external ID to get TMDB ID.

        Args:
            media_id: External media ID (IMDB, TVDB, etc.)
            external_source: Type of external source

        Returns:
            Tuple of (movie_results, tv_results)
        """
        self.logger.debug(
            f"Fetching TMDB ID for {external_source} {media_id} from TMDB API..."
        )
        url = f"{self.BASE_URL}/find/{media_id}?external_source={external_source}"

        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        data = response.json()

        return data.get("movie_results", []), data.get("tv_results", [])

    def _resolve_external_id_conflict(
        self,
        media_id: str,
        external_source: str,
        media_name: Optional[str],
        movie_result: Dict,
        tv_result: Dict,
    ) -> Tuple[str, str]:
        """
        Resolve conflict when external ID matches both movie and TV show.

        Args:
            media_id: External media ID
            external_source: Type of external source
            media_name: Media name for similarity comparison
            movie_result: Movie result from API
            tv_result: TV result from API

        Returns:
            Tuple of (tmdb_id, media_type)
        """
        self.logger.warning(
            f"{external_source} {media_id} matches both movie and TV show."
        )

        if media_name:
            tv_title = tv_result.get("name", "")
            movie_title = movie_result.get("title", "")

            tv_score = self.similarity_calculator.calculate_similarity(
                media_name, tv_title
            )
            movie_score = self.similarity_calculator.calculate_similarity(
                media_name, movie_title
            )

            self.logger.info(".2f")

            if tv_score > movie_score:
                self.logger.info(
                    f"Selected TV show '{tv_title}' based on title similarity"
                )
                return tv_result["id"], "tv"
            else:
                self.logger.info(
                    f"Selected movie '{movie_title}' based on title similarity"
                )
                return movie_result["id"], "movie"
        else:
            # Use confidence scoring based on vote count and popularity
            movie_confidence = movie_result.get("vote_count", 0) * 2 + movie_result.get(
                "popularity", 0
            )
            tv_confidence = tv_result.get("vote_count", 0) * 2 + tv_result.get(
                "popularity", 0
            )

            if tv_confidence > movie_confidence:
                self.logger.info(".2f")
                return tv_result["id"], "tv"
            else:
                self.logger.info(".2f")
                return movie_result["id"], "movie"

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def fetch_tmdb_id(
        self,
        media_id: str,
        external_source: str,
        cache: Dict[str, Tuple[Optional[str], Optional[str]]],
        media_name: Optional[str] = None,
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Fetch TMDB ID for a given media ID from external source.

        Args:
            media_id: Media ID to look up
            external_source: Type of external source (imdb_id, tvdb_id, tmdb_id)
            cache: Cache dictionary for storing results (backward compatibility)
            media_name: Optional media name for conflict resolution

        Returns:
            Tuple of (tmdb_id, media_type) or (None, None) if not found
        """
        # Try intelligent cache first
        cache_manager = get_cache_manager()
        cached_result = cache_manager.get_tmdb_id(
            media_id, external_source, media_name or ""
        )

        if cached_result:
            self.logger.info(
                f"Fetching TMDB ID for {external_source} {media_id} from intelligent cache."
            )
            return cached_result

        # Fallback to legacy cache for backward compatibility
        if media_id in cache:
            self.logger.info(
                f"Fetching TMDB ID for {external_source} {media_id} from legacy cache."
            )
            return cache[media_id]

        if external_source == "tmdb_id":
            tv_exists, movie_exists, tv_response, movie_response = (
                self._check_direct_tmdb_api(media_id)
            )

            if tv_exists and movie_exists and tv_response and movie_response:
                tmdb_id, media_type = self._resolve_direct_tmdb_conflict(
                    media_id=media_id,
                    media_name=media_name,
                    tv_response=tv_response,
                    movie_response=movie_response,
                )
            elif tv_exists:
                self.logger.info(f"TMDB ID {media_id} identified as TV show.")
                tmdb_id, media_type = media_id, "tv"
            elif movie_exists:
                self.logger.info(f"TMDB ID {media_id} identified as movie.")
                tmdb_id, media_type = media_id, "movie"
            else:
                self.logger.error(f"TMDB ID {media_id} not found as movie or TV show.")
                tmdb_id, media_type = None, None

        else:
            movie_results, tv_results = self._query_external_id(
                media_id, external_source
            )

            if movie_results and tv_results:
                tmdb_id, media_type = self._resolve_external_id_conflict(
                    media_id=media_id,
                    external_source=external_source,
                    media_name=media_name,
                    movie_result=movie_results[0],
                    tv_result=tv_results[0],
                )
            elif movie_results:
                tmdb_id = movie_results[0]["id"]
                media_type = "movie"
            elif tv_results:
                tmdb_id = tv_results[0]["id"]
                media_type = "tv"
            else:
                tmdb_id, media_type = None, None

        if tmdb_id:
            tmdb_id = str(tmdb_id)

        # Store in both intelligent cache and legacy cache for backward compatibility
        cache_manager = get_cache_manager()
        if tmdb_id and media_type:
            cache_manager.set_tmdb_id(media_id, external_source, tmdb_id, media_type)
        cache[media_id] = (tmdb_id, media_type)

        self.logger.debug(
            f"TMDB ID for {external_source} {media_id}: {tmdb_id}, Media Type: {media_type}"
        )
        return tmdb_id, media_type


def to_standard_dict(item: Any) -> Any:
    """
    Convert collections (like CommentedMap from ruamel.yaml) to standard Python dict/list.

    Args:
        item: Item to convert

    Returns:
        Converted item with standard Python types
    """
    if isinstance(item, Mapping):
        return {k: to_standard_dict(v) for k, v in item.items()}
    elif isinstance(item, Sequence) and not isinstance(item, (str, bytes)):
        return [to_standard_dict(x) for x in item]
    else:
        return item

"""
Media discovery module for Mediux Scraper.

This module handles the discovery of media IDs from various sources
including Plex API and folder scanning.
"""

import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def get_media_ids(
    *,
    plex_url: Optional[str] = None,
    plex_token: Optional[str] = None,
    plex_libraries: Optional[List[str]] = None,
) -> Tuple[List[Tuple[str, str, str, str]], Dict[str, List[Tuple[str, str]]]]:
    """
    Discover media IDs from Plex libraries.

    Attempts to retrieve media IDs from configured Plex libraries. If no
    libraries are specified but credentials exist, lists available libraries
    to help with configuration. Raises ValueError when credentials are missing.

    Args:
        plex_url: Plex server URL (e.g., ``http://localhost:32400``)
        plex_token: Plex API authentication token
        plex_libraries: Names of libraries to scan (e.g., ``["Movies", "TV Shows"]``)

    Returns:
        A tuple of:

        - List of ``(media_id, media_name, source_type, media_type)`` tuples
        - Dict mapping ``media_id`` to a list of ``(library_name, media_type)`` tuples

    Raises:
        ValueError: If ``plex_url`` or ``plex_token`` are missing
    """
    # First priority: Try Plex if all parameters are provided
    if plex_url and plex_token and plex_libraries and len(plex_libraries) > 0:
        try:
            from modules.external_services import PlexClient

            plex_client = PlexClient(plex_url, plex_token)
            return plex_client.get_media_ids_from_plex(plex_libraries)
        except Exception as e:
            logger.error(f"Failed to get media IDs from Plex: {e}")
            logger.warning(
                "Plex connection failed. Ensure Plex configuration is correct."
            )

    # Second priority: Try to list available libraries if partial Plex config
    if plex_url and plex_token and (not plex_libraries or len(plex_libraries) == 0):
        try:
            from modules.external_services import PlexClient

            plex_client = PlexClient(plex_url, plex_token)
            available = plex_client.list_available_libraries()
            logger.info("Available Plex libraries:")
            for lib in available:
                logger.info(f"  - {lib}")
            logger.warning(
                "No Plex libraries specified. Please set 'plex_libraries' in your config or CLI."
            )
        except Exception as e:
            logger.error(f"Could not connect to Plex to list libraries: {e}")

    # If we can't get Plex libraries, raise an exception that will be handled upstream
    if not plex_url or not plex_token:
        logger.error(
            "Plex configuration is required. Please set 'plex_url' and 'plex_token' in your config or CLI."
        )
        raise ValueError("Missing required Plex configuration")

    # If we get here without returning, something went wrong
    logger.error("Failed to retrieve media IDs")
    return ([], {})

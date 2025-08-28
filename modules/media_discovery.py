"""
Media discovery module for Mediux Scraper.

This module handles the discovery of media IDs from various sources
including Plex API and folder scanning.
"""

import logging

logger = logging.getLogger(__name__)


def get_media_ids(
    *,
    root_folder=None,
    selected_folders=None,
    plex_url=None,
    plex_token=None,
    plex_libraries=None,
):
    """Get media IDs using Plex API or folder scanning."""
    # First priority: Try Plex if all parameters are provided
    if plex_url and plex_token and plex_libraries and len(plex_libraries) > 0:
        try:
            from modules.external_services import PlexClient

            plex_client = PlexClient(plex_url, plex_token)
            return plex_client.get_media_ids_from_plex(plex_libraries)
        except Exception as e:
            logger.error(f"Failed to get media IDs from Plex: {e}")
            logger.warning("Plex connection failed. Falling back to folder scanning.")

    # Second priority: Try to list available libraries if partial Plex config
    if (
        plex_url
        and plex_token
        and root_folder
        and (not plex_libraries or len(plex_libraries) == 0)
    ):
        try:
            from modules.external_services import PlexClient

            plex_client = PlexClient(plex_url, plex_token)
            available = plex_client.list_available_libraries()
            logger.info("Available Plex libraries:")
            for lib in available:
                logger.info(f"  - {lib}")
            logger.warning(
                "No Plex libraries specified. Please set 'plex_libraries' in your config or CLI. Using root_folder instead."
            )
        except Exception as e:
            logger.error(f"Could not connect to Plex to list libraries: {e}")
            logger.warning("Using root_folder instead.")

    # Final fallback: Use folder scanning if root_folder is available
    if root_folder:
        from modules.external_services import MediaDiscoveryService

        discovery_service = MediaDiscoveryService()
        return discovery_service.get_media_ids_from_folder(
            root_folder, selected_folders
        )
    else:
        logger.error("No Plex config or root_folder provided. Nothing to do. Exiting.")
        exit(1)

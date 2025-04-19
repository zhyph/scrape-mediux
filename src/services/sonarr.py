import logging
import requests
from tenacity import retry, stop_after_attempt, wait_fixed

logger = logging.getLogger(__name__)


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def check_series_status(media_name, sonarr_api_key, sonarr_endpoint):
    """
    Check if a TV series has ended using Sonarr API.

    Args:
        media_name (str): Name of the media to look up
        sonarr_api_key (str): Sonarr API key
        sonarr_endpoint (str): Sonarr API endpoint

    Returns:
        tuple: (tvdb_id, ended) where ended is a boolean
    """
    logger.info(f"Checking series status for {media_name}...")
    url = f"{sonarr_endpoint}/api/v3/series/lookup?term={media_name}"
    headers = {
        "X-Api-Key": sonarr_api_key,
        "accept": "application/json",
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    data = response.json()
    if data and isinstance(data, list):
        series_info = data[0]
        tvdb_id = series_info["tvdbId"]
        ended = series_info["ended"]
        logger.info(
            f"Series status for {media_name}: TVDB ID={tvdb_id}, Ended={ended}."
        )
        return tvdb_id, ended
    logger.warning(f"No series information found for {media_name}.")
    return None, None

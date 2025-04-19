import logging
import requests
from tenacity import retry, stop_after_attempt, wait_fixed

logger = logging.getLogger(__name__)


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def fetch_tmdb_id(media_id, external_source, api_key, cache):
    """
    Fetch TMDB ID for a media item using external IDs (IMDB, TVDB) or directly if TMDB ID.

    Args:
        media_id (str): Media ID (IMDB, TVDB, or TMDB)
        external_source (str): Source type ('imdb_id', 'tvdb_id', or 'tmdb_id')
        api_key (str): TMDB API key
        cache (dict): Cache of previously fetched TMDB IDs

    Returns:
        tuple: (tmdb_id, media_type) where media_type is 'movie' or 'tv'
    """
    if external_source == "tmdb_id":
        logger.info(f"Using TMDB ID {media_id} directly.")

        url = f"https://api.themoviedb.org/3/movie/{media_id}"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "accept": "application/json",
        }
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return media_id, "movie"
        elif response.status_code == 404:
            url = f"https://api.themoviedb.org/3/tv/{media_id}"
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                return media_id, "tv"
            else:
                logger.error(f"TMDB ID {media_id} not found as movie or TV show.")
                return None, None
        else:
            response.raise_for_status()

    if media_id in cache:
        logger.info(f"Fetching TMDB ID for {external_source} {media_id} from cache.")
        return cache[media_id]

    logger.info(f"Fetching TMDB ID for {external_source} {media_id} from TMDB API...")
    url = f"https://api.themoviedb.org/3/find/{media_id}?external_source={external_source}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "accept": "application/json",
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    data = response.json()
    if data.get("movie_results"):
        tmdb_id = data["movie_results"][0]["id"]
        media_type = "movie"
    elif data.get("tv_results"):
        tmdb_id = data["tv_results"][0]["id"]
        media_type = "tv"
    else:
        tmdb_id, media_type = None, None

    cache[media_id] = (tmdb_id, media_type)
    logger.info(
        f"TMDB ID for {external_source} {media_id}: {tmdb_id}, Media Type: {media_type}"
    )
    return tmdb_id, media_type

import os
import pickle
import logging

logger = logging.getLogger(__name__)


def load_cache(cache_file):
    """
    Load TMDB cache from disk.

    Args:
        cache_file (str): Path to cache file

    Returns:
        dict: Cached TMDB IDs
    """
    if os.path.exists(cache_file):
        logger.info(f"Loading cache from {cache_file}...")
        with open(cache_file, "rb") as f:
            cache = pickle.load(f)
        logger.info("Cache loaded successfully.")
        return cache
    logger.info("No cache file found. Initializing new cache.")
    return {}


def save_cache(updated_cache, cache_file):
    """
    Save TMDB cache to disk, merging with existing cache if present.

    Args:
        updated_cache (dict): Updated cache data
        cache_file (str): Path to cache file
    """
    logger.info(f"Saving cache to {cache_file}...")
    if os.path.exists(cache_file):
        with open(cache_file, "rb") as f:
            existing_cache = pickle.load(f)
    else:
        existing_cache = {}

    existing_cache.update(updated_cache)

    os.makedirs(os.path.dirname(cache_file), exist_ok=True)
    with open(cache_file, "wb") as f:
        pickle.dump(existing_cache, f)
    logger.info("Cache saved successfully.")

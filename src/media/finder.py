import os
import re
import logging
from collections import defaultdict
from src.config import validate_path

logger = logging.getLogger(__name__)


def _extract_media_id_info(subfolder):
    """Extract media ID information from a subfolder name."""
    imdb_match = re.search(r"imdb-(tt\d+)", subfolder)
    tvdb_match = re.search(r"tvdb-(\d+)", subfolder)
    tmdb_match = re.search(r"tmdb-(\d+)", subfolder)
    name_match = re.search(r"(.+)(?=\{(imdb|tvdb|tmdb)-)", subfolder)

    if imdb_match and name_match:
        return imdb_match.group(1), name_match.group(1).strip(), "imdb_id"
    elif tvdb_match and name_match:
        return tvdb_match.group(1), name_match.group(1).strip(), "tvdb_id"
    elif tmdb_match and name_match:
        return tmdb_match.group(1), name_match.group(1).strip(), "tmdb_id"

    return None, None, None


def _process_subfolder(subfolder_path, subfolder, media_ids, folder_map, parent_folder):
    """Process a single subfolder to extract media ID."""
    if not os.path.isdir(subfolder_path):
        return

    media_id, media_name, external_source = _extract_media_id_info(subfolder)

    if media_id:
        media_ids.append((media_id, media_name, external_source))
        folder_map[media_id].append(parent_folder)


def _scan_folder(folder_path, folder, media_ids, folder_map):
    """Scan a folder for subfolders containing media IDs."""
    if not os.path.isdir(folder_path):
        return

    subfolders = os.listdir(folder_path)
    for subfolder in subfolders:
        subfolder_path = os.path.join(folder_path, subfolder)
        _process_subfolder(subfolder_path, subfolder, media_ids, folder_map, folder)


def get_media_ids(root_folder, selected_folders=None):
    """
    Extract media IDs (IMDB, TVDB, TMDB) from folder names.

    Args:
        root_folder (str or list): Path(s) to root folder(s) containing media directories
        selected_folders (list, optional): Specific folders to search within root_folder

    Returns:
        tuple: (media_ids, folder_map) where:
            - media_ids is a list of tuples (id, name, source)
            - folder_map is a defaultdict mapping media_ids to folder names
    """
    logger.info("Fetching media IDs from folder names...")
    validate_path(root_folder, "Root folder")

    media_ids = []
    folder_map = defaultdict(list)
    root_folders = root_folder if isinstance(root_folder, list) else [root_folder]

    for root in root_folders:
        folders_to_search = selected_folders if selected_folders else os.listdir(root)

        for folder in folders_to_search:
            logger.debug(f"Searching folder: {folder}")
            folder_path = os.path.join(root, folder)
            _scan_folder(folder_path, folder, media_ids, folder_map)

    logger.info(f"Found media IDs: {media_ids}")
    return media_ids, folder_map

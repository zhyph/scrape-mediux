import os
import logging
import shutil
from .extractor import extract_set_urls
from src.config.paths import get_kometa_file, BULK_FILE, ensure_dir


logger = logging.getLogger(__name__)


def load_bulk_data(bulk_data_file, only_set_urls=False, yaml_parser=None):
    """
    Load bulk data from YAML file.

    Args:
        bulk_data_file (str): Path to bulk data file
        only_set_urls (bool): If True, only extract set URLs
        yaml_parser: YAML parser object

    Returns:
        dict or set: Bulk data or set of URLs if only_set_urls=True
    """
    if not yaml_parser:
        raise ValueError("YAML parser must be provided")

    if os.path.exists(bulk_data_file):
        logger.info(f"Loading bulk data from {bulk_data_file}...")
        with open(bulk_data_file, "r", encoding="utf-8") as f:
            if only_set_urls:
                bulk_data = extract_set_urls(f.read())
                logger.info(f"Loaded {len(bulk_data)} set URLs from bulk data.")
            else:
                bulk_data = yaml_parser.load(f)
                logger.info("Bulk data loaded successfully.")

        if not bulk_data:
            logger.warning("No data found in bulk data file.")
            return set() if only_set_urls else {"metadata": {}}

        return bulk_data

    logger.warning(f"Bulk data file {bulk_data_file} not found.")
    return set() if only_set_urls else {"metadata": {}}


def _collect_existing_urls(root_folders, yaml_parser):
    """Helper function to collect existing URLs from files."""
    existing_urls = set()
    folder_cache = {root: os.listdir(root) for root in root_folders}

    for root, folders in folder_cache.items():
        for folder in folders:
            folder_path = os.path.join(root, folder)
            if os.path.isdir(folder_path):
                file_path = get_kometa_file(folder)
                existing_urls.update(load_bulk_data(file_path, True, yaml_parser))

    return existing_urls


def _process_folder_data(folder, data, yaml_parser, existing_urls):
    """Process data for a single folder and return updated information."""
    file_name = get_kometa_file(folder)
    total_urls = 0

    # Load existing data or create empty structure
    if os.path.exists(file_name):
        with open(file_name, "r", encoding="utf-8") as f:
            existing_data = yaml_parser.load(f) or {"metadata": {}}
    else:
        existing_data = {"metadata": {}}

    # Process each yaml data entry
    for _, yaml_data in data.items():
        existing_data["metadata"].update(yaml_parser.load(yaml_data))
        urls = extract_set_urls(yaml_data)
        existing_urls.update(urls)
        total_urls += len(urls)

    # Write updated data
    with open(file_name, "w", encoding="utf-8") as f:
        yaml_parser.dump(existing_data, f)

    return file_name, total_urls


def _copy_to_output_dir(output_dir):
    """Copy files to output directory."""
    from src.config.paths import KOMETA_DIR

    os.makedirs(output_dir, exist_ok=True)
    logger.debug(f"Created output directory {output_dir}.")

    for filename in os.listdir(KOMETA_DIR):
        src_file = os.path.join(KOMETA_DIR, filename)
        dst_file = os.path.join(output_dir, filename)
        shutil.copy2(src_file, dst_file)

    logger.info(f"Files copied to {output_dir}.")


def write_data_to_files(
    new_data, root_folder, output_dir, yaml_parser, cache, cache_file
):
    """
    Write collected data to YAML files and extract set URLs.
    """
    from src.config import validate_path
    from src.data.cache import save_cache
    from src.config.paths import BULK_FILE

    validate_path(root_folder, "Root folder")
    logger.info("Writing data to files...")

    # Normalize root_folder to always be a list
    root_folders = root_folder if isinstance(root_folder, list) else [root_folder]

    # Collect existing URLs
    existing_urls = _collect_existing_urls(root_folders, yaml_parser)

    # Process each folder's data
    updated_files = []
    total_urls_extracted = 0

    for folder, data in new_data.items():
        file_name, urls_count = _process_folder_data(
            folder, data, yaml_parser, existing_urls
        )
        updated_files.append(file_name)
        total_urls_extracted += urls_count

    # Log summary information
    logger.info(f"Updated {len(updated_files)} files: {', '.join(updated_files)}")
    logger.info(f"Extracted a total of {total_urls_extracted} unique set URLs.")

    # Write URL file
    with open(BULK_FILE, "w", encoding="utf-8") as f:
        for url in sorted(existing_urls):
            f.write(url + "\n")
    logger.info(f"Set URLs updated in '{BULK_FILE}'.")

    # Save cache
    save_cache(cache, cache_file)
    logger.info("Data writing completed.")

    # Copy files if output directory provided
    if output_dir:
        logger.info(f"Copying files to {output_dir}...")
        _copy_to_output_dir(output_dir)

"""
File I/O and cache management for Mediux Scraper.

This module handles cache operations, file reading/writing, data persistence,
and bulk data management for the Mediux scraper.
"""

import os
import logging
import pickle
import shutil
from typing import Dict, List, Any, Optional, Set, Tuple, Union
from collections import defaultdict
from ruamel import yaml

logger = logging.getLogger(__name__)


class CacheManager:
    """Manages TMDB API cache operations."""

    def __init__(self, cache_file: str = "./out/tmdb_cache.pkl"):
        self.cache_file = cache_file
        self.logger = logging.getLogger(__name__)

    def load_cache(self) -> Dict[str, Tuple[Optional[str], Optional[str]]]:
        """
        Load cache from file.

        Returns:
            Cache dictionary or empty dict if file doesn't exist
        """
        if os.path.exists(self.cache_file):
            self.logger.info(f"Loading cache from {self.cache_file}...")
            with open(self.cache_file, "rb") as f:
                cache = pickle.load(f)
            self.logger.info("Cache loaded successfully.")
            return cache
        self.logger.info("No cache file found. Initializing new cache.")
        return {}

    def save_cache(
        self, updated_cache: Dict[str, Tuple[Optional[str], Optional[str]]]
    ) -> None:
        """
        Save cache to file, merging with existing cache.

        Args:
            updated_cache: Cache data to save
        """
        self.logger.info(f"Saving cache to {self.cache_file}...")

        if os.path.exists(self.cache_file):
            with open(self.cache_file, "rb") as f:
                existing_cache = pickle.load(f)
        else:
            existing_cache = {}

        existing_cache.update(updated_cache)

        with open(self.cache_file, "wb") as f:
            pickle.dump(existing_cache, f)
        self.logger.info("Cache saved successfully.")


class BulkDataManager:
    """Manages bulk data file operations."""

    def __init__(self):
        self.yaml = yaml.YAML()
        self.yaml.allow_duplicate_keys = True
        self.logger = logging.getLogger(__name__)

    def load_bulk_data(
        self, bulk_data_file: str, only_set_urls: bool = False
    ) -> Union[Dict[str, Any], Set[str]]:
        """
        Load bulk data from YAML file.

        Args:
            bulk_data_file: Path to bulk data file
            only_set_urls: If True, return only set URLs

        Returns:
            Bulk data dictionary or set of URLs
        """
        if os.path.exists(bulk_data_file):
            self.logger.info(f"Loading bulk data from {bulk_data_file}...")
            with open(bulk_data_file, "r", encoding="utf-8") as f:
                if only_set_urls:
                    from modules.data_processor import SetURLExtractor

                    extractor = SetURLExtractor()
                    bulk_data = extractor.extract_set_urls(f.read())
                    self.logger.info(
                        f"Loaded {len(bulk_data)} set URLs from bulk data."
                    )
                else:
                    try:
                        bulk_data = self.yaml.load(f)
                        if (
                            bulk_data
                            and "metadata" in bulk_data
                            and isinstance(bulk_data["metadata"], dict)
                        ):
                            bulk_data["metadata"] = {
                                str(k): v for k, v in bulk_data["metadata"].items()
                            }
                        self.logger.info("Bulk data loaded successfully.")
                    except Exception as e:
                        self.logger.error(
                            f"Error loading bulk data from {bulk_data_file}: {e}"
                        )
                        bulk_data = {"metadata": {}}

            if not bulk_data:
                self.logger.warning("No data found in bulk data file.")
                return set() if only_set_urls else {"metadata": {}}

            return bulk_data

        self.logger.debug(f"Bulk data file {bulk_data_file} not found.")
        return set() if only_set_urls else {"metadata": {}}


class FileWriter:
    """Handles writing data to files and managing output directories."""

    def __init__(self):
        self.yaml = yaml.YAML()
        self.yaml.allow_duplicate_keys = True
        self.logger = logging.getLogger(__name__)

    def _collect_existing_urls(
        self, root_folder_global: Union[str, List[str]]
    ) -> Set[str]:
        """
        Collect existing set URLs from all data files.

        Args:
            root_folder_global: Root folder(s) to scan

        Returns:
            Set of existing URLs
        """
        existing_urls = set()

        root_folders_list = (
            root_folder_global
            if isinstance(root_folder_global, list)
            else [root_folder_global]
        )
        folder_cache = {root: os.listdir(root) for root in root_folders_list}

        for root, folders_in_root in folder_cache.items():
            for folder_item in folders_in_root:
                folder_path = os.path.join(root, folder_item)
                if os.path.isdir(folder_path):
                    file_path = f"./out/kometa/{folder_item}_data.yml"
                    bulk_manager = BulkDataManager()
                    existing_urls.update(
                        bulk_manager.load_bulk_data(
                            bulk_data_file=file_path, only_set_urls=True
                        )
                    )

        return existing_urls

    def _update_data_file(
        self,
        folder_name: Union[str, Tuple[str, ...]],
        data_to_write: Dict[str, Any],
        existing_urls_set: Set[str],
    ) -> Tuple[str, int]:
        """
        Update a data file with new data.

        Args:
            folder_name: Name of the folder/file
            data_to_write: Data to write
            existing_urls_set: Set to update with new URLs

        Returns:
            Tuple of (file_name, total_urls_added)
        """
        import re

        name_to_process = (
            folder_name[0] if isinstance(folder_name, tuple) else folder_name
        )
        safe_folder = re.sub(r"[^\w\-]", "_", name_to_process.lower())
        file_name = f"./out/kometa/{safe_folder}_data.yml"
        total_urls = 0

        file_data = {"metadata": {}}
        if os.path.exists(file_name):
            with open(file_name, "r", encoding="utf-8") as f:
                loaded_data = self.yaml.load(f)
                if loaded_data and "metadata" in loaded_data:
                    file_data = loaded_data
                elif loaded_data:
                    file_data["metadata"] = loaded_data

        from modules.data_processor import SetURLExtractor

        extractor = SetURLExtractor()

        for key, item_yaml_data in data_to_write.items():
            parsed_item_yaml = self.yaml.load(item_yaml_data)
            if parsed_item_yaml:
                # Merge the parsed YAML content directly into metadata
                # instead of nesting it under the key
                file_data["metadata"].update(parsed_item_yaml)
            item_urls = extractor.extract_set_urls(yaml_data=item_yaml_data)
            existing_urls_set.update(item_urls)
            total_urls += len(item_urls)

        with open(file_name, "w", encoding="utf-8") as f:
            self.yaml.dump(file_data, f)

        return file_name, total_urls

    def _copy_to_output_dir(self, output_dir_global: Optional[str]) -> None:
        """
        Copy files to the output directory.

        Args:
            output_dir_global: Output directory path
        """
        if not output_dir_global:
            return

        self.logger.info(f"Copying files to {output_dir_global}...")
        if not os.path.exists(output_dir_global):
            os.makedirs(output_dir_global)
            self.logger.debug(f"Created output directory {output_dir_global}.")

        kometa_out_dir = "./out/kometa"
        if not os.path.exists(kometa_out_dir):
            self.logger.warning(
                f"Source directory {kometa_out_dir} does not exist. Nothing to copy."
            )
            return

        for filename in os.listdir(kometa_out_dir):
            src_file = os.path.join(kometa_out_dir, filename)
            dst_file = os.path.join(output_dir_global, filename)
            shutil.copy2(src_file, dst_file)
        self.logger.info(f"Files copied to {output_dir_global}.")

    def write_data_to_files(
        self,
        new_data: Dict[str, Dict[str, str]],
        root_folder_global: Union[str, List[str]],
        cache: Dict[str, Tuple[Optional[str], Optional[str]]],
        cache_file: str,
        output_dir_global: Optional[str],
    ) -> None:
        """
        Write all collected data to files.

        Args:
            new_data: New data to write
            root_folder_global: Root folder for URL collection
            cache: Cache to save
            cache_file: Cache file path
            output_dir_global: Output directory for copying files
        """
        if not root_folder_global:
            self.logger.error("Root folder is not set. Cannot write data.")
            return

        from modules.config import validate_path

        validate_path(path=root_folder_global, description="Root folder")

        self.logger.info("Writing data to files...")

        os.makedirs("./out/kometa", exist_ok=True)
        self.logger.debug("Ensured output directory './out/kometa' exists.")

        existing_urls = self._collect_existing_urls(root_folder_global)

        updated_files_list = []

        for folder_name, data_for_folder in new_data.items():
            file_name_str, _ = self._update_data_file(
                folder_name=folder_name,
                data_to_write=data_for_folder,
                existing_urls_set=existing_urls,
            )
            updated_files_list.append(file_name_str)

        if updated_files_list:
            self.logger.info(
                f"Updated {len(updated_files_list)} files: {', '.join(updated_files_list)}"
            )
        else:
            self.logger.info("No data files were updated.")

        self.logger.info(f"Collected a total of {len(existing_urls)} unique set URLs.")

        with open("./out/ppsh-bulk.txt", "w", encoding="utf-8") as f:
            for url in sorted(list(existing_urls)):
                f.write(url + "\n")
        self.logger.info("Set URLs updated in './out/ppsh-bulk.txt'.")

        cache_manager = CacheManager(cache_file)
        cache_manager.save_cache(cache)
        self.logger.info("Data writing completed.")

        self._copy_to_output_dir(output_dir_global)

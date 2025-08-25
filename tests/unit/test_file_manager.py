"""
Tests for file_manager.py module.
"""

import os
import tempfile
import pickle
import shutil
from unittest.mock import Mock, patch, MagicMock

import pytest
from modules.file_manager import CacheManager, BulkDataManager, FileWriter


class TestCacheManager:
    """Test cases for CacheManager class."""

    def test_init_default_values(self):
        """Test CacheManager initialization with default values."""
        cache_manager = CacheManager()
        assert cache_manager.cache_file == "./out/tmdb_cache.pkl"
        assert hasattr(cache_manager, "logger")

    def test_init_custom_cache_file(self):
        """Test CacheManager initialization with custom cache file."""
        cache_manager = CacheManager(cache_file="/custom/cache.pkl")
        assert cache_manager.cache_file == "/custom/cache.pkl"

    def test_load_cache_file_exists(self, temp_dir):
        """Test load_cache when cache file exists."""
        cache_file = os.path.join(temp_dir, "test_cache.pkl")
        test_cache = {"key1": ("value1", "movie"), "key2": ("value2", "tv")}

        with open(cache_file, "wb") as f:
            pickle.dump(test_cache, f)

        cache_manager = CacheManager(cache_file=cache_file)

        with patch.object(cache_manager, "logger") as mock_logger:
            result = cache_manager.load_cache()

            assert result == test_cache
            mock_logger.info.assert_called()

    def test_load_cache_file_not_exists(self, temp_dir):
        """Test load_cache when cache file doesn't exist."""
        cache_file = os.path.join(temp_dir, "nonexistent_cache.pkl")
        cache_manager = CacheManager(cache_file=cache_file)

        with patch.object(cache_manager, "logger") as mock_logger:
            result = cache_manager.load_cache()

            assert result == {}
            mock_logger.info.assert_called_with(
                "No cache file found. Initializing new cache."
            )

    def test_save_cache_file_exists(self, temp_dir):
        """Test save_cache when cache file exists."""
        cache_file = os.path.join(temp_dir, "test_cache.pkl")
        existing_cache = {"existing": ("data", "movie")}

        # Create existing cache file
        with open(cache_file, "wb") as f:
            pickle.dump(existing_cache, f)

        new_cache = {"new": ("data2", "tv")}
        cache_manager = CacheManager(cache_file=cache_file)

        with patch.object(cache_manager, "logger") as mock_logger:
            cache_manager.save_cache(new_cache)  # type: ignore

            # Verify the cache was merged and saved
            with open(cache_file, "rb") as f:
                saved_cache = pickle.load(f)

            assert saved_cache == {
                "existing": ("data", "movie"),
                "new": ("data2", "tv"),
            }
            mock_logger.info.assert_called()

    def test_save_cache_file_not_exists(self, temp_dir):
        """Test save_cache when cache file doesn't exist."""
        cache_file = os.path.join(temp_dir, "new_cache.pkl")
        new_cache = {"key": ("value", "movie")}
        cache_manager = CacheManager(cache_file=cache_file)

        with patch.object(cache_manager, "logger") as mock_logger:
            cache_manager.save_cache(new_cache)  # type: ignore

            # Verify the cache was saved
            with open(cache_file, "rb") as f:
                saved_cache = pickle.load(f)

            assert saved_cache == new_cache
            mock_logger.info.assert_called()


class TestBulkDataManager:
    """Test cases for BulkDataManager class."""

    def test_init(self):
        """Test BulkDataManager initialization."""
        bulk_manager = BulkDataManager()
        assert bulk_manager.yaml is not None  # Should have yaml_parser from config
        assert hasattr(bulk_manager, "logger")

    def test_load_bulk_data_file_not_exists(self):
        """Test load_bulk_data when file doesn't exist."""
        bulk_manager = BulkDataManager()

        with patch.object(bulk_manager, "logger") as mock_logger:
            result = bulk_manager.load_bulk_data("/nonexistent/file.yml")

            assert result == {"metadata": {}}
            mock_logger.debug.assert_called()

    def test_load_bulk_data_file_exists_full_data(self, temp_dir):
        """Test load_bulk_data when file exists with full data."""
        yaml_file = os.path.join(temp_dir, "test_data.yml")
        yaml_content = """
metadata:
  tt0111161:
    title: "Test Movie"
    year: 2023
"""

        with open(yaml_file, "w") as f:
            f.write(yaml_content)

        bulk_manager = BulkDataManager()

        with patch.object(bulk_manager, "logger") as mock_logger:
            result = bulk_manager.load_bulk_data(yaml_file)

            assert isinstance(result, dict)
            assert "metadata" in result
            assert "tt0111161" in result["metadata"]
            mock_logger.info.assert_called()

    def test_load_bulk_data_only_set_urls(self, temp_dir):
        """Test load_bulk_data with only_set_urls=True."""
        yaml_file = os.path.join(temp_dir, "test_data.yml")
        yaml_content = """
metadata:
  tt0111161:
    title: "Test Movie"
# https://mediux.pro/sets/12345
# https://mediux.pro/sets/67890
"""

        with open(yaml_file, "w") as f:
            f.write(yaml_content)

        bulk_manager = BulkDataManager()

        with patch("modules.data_processor.SetURLExtractor") as mock_extractor:
            mock_instance = Mock()
            mock_instance.extract_set_urls.return_value = {
                "https://mediux.pro/sets/12345",
                "https://mediux.pro/sets/67890",
            }
            mock_extractor.return_value = mock_instance

            with patch.object(bulk_manager, "logger") as mock_logger:
                result = bulk_manager.load_bulk_data(yaml_file, only_set_urls=True)

                assert result == {
                    "https://mediux.pro/sets/12345",
                    "https://mediux.pro/sets/67890",
                }
                mock_logger.info.assert_called()

    def test_load_bulk_data_yaml_error(self, temp_dir):
        """Test load_bulk_data when YAML parsing fails."""
        yaml_file = os.path.join(temp_dir, "test_data.yml")
        invalid_yaml_content = """
metadata:
  invalid: yaml: content:
    missing_value_here
"""

        with open(yaml_file, "w") as f:
            f.write(invalid_yaml_content)

        bulk_manager = BulkDataManager()

        with patch.object(bulk_manager, "logger") as mock_logger:
            result = bulk_manager.load_bulk_data(yaml_file)

            assert result == {"metadata": {}}
            mock_logger.error.assert_called()

    def test_load_bulk_data_metadata_conversion(self, temp_dir):
        """Test load_bulk_data metadata key conversion."""
        yaml_file = os.path.join(temp_dir, "test_data.yml")
        yaml_content = """
metadata:
  123:
    title: "Test Movie"
  456:
    title: "Test TV Show"
"""

        with open(yaml_file, "w") as f:
            f.write(yaml_content)

        bulk_manager = BulkDataManager()

        with patch.object(bulk_manager, "logger") as mock_logger:
            result = bulk_manager.load_bulk_data(yaml_file)

            assert isinstance(result, dict)
            assert "metadata" in result
            # Should convert numeric keys to strings
            assert "123" in result["metadata"]
            assert "456" in result["metadata"]
            mock_logger.info.assert_called()


class TestFileWriter:
    """Test cases for FileWriter class."""

    def test_init(self):
        """Test FileWriter initialization."""
        file_writer = FileWriter()
        assert file_writer.yaml is not None  # Should have yaml_parser from config
        assert hasattr(file_writer, "logger")

    def test_collect_existing_urls_no_root_folder(self):
        """Test _collect_existing_urls with no root folder."""
        file_writer = FileWriter()
        result = file_writer._collect_existing_urls([])
        assert result == set()

    def test_collect_existing_urls_with_folders(self, temp_dir):
        """Test _collect_existing_urls with existing folders."""
        # Create mock folder structure
        folder1 = os.path.join(temp_dir, "folder1")
        folder2 = os.path.join(temp_dir, "folder2")
        os.makedirs(folder1)
        os.makedirs(folder2)

        # Create mock data files in the expected location (./out/kometa/)
        data_file1 = os.path.join(os.getcwd(), "out", "kometa", "folder1_data.yml")
        os.makedirs(os.path.dirname(data_file1), exist_ok=True)

        yaml_content = """
metadata:
  tt0111161:
    title: "Test Movie"
# https://mediux.pro/sets/12345
"""

        with open(data_file1, "w") as f:
            f.write(yaml_content)

        file_writer = FileWriter()

        with patch("modules.data_processor.SetURLExtractor") as mock_extractor:
            mock_instance = Mock()
            mock_instance.extract_set_urls.return_value = {
                "https://mediux.pro/sets/12345"
            }
            mock_extractor.return_value = mock_instance

            result = file_writer._collect_existing_urls(temp_dir)

            assert "https://mediux.pro/sets/12345" in result

    def test_update_data_file_new_file(self, temp_dir):
        """Test _update_data_file with new file."""
        file_writer = FileWriter()
        existing_urls = set()

        data_to_write = {
            "tt0111161": """
title: "Test Movie"
year: 2023
# https://mediux.pro/sets/12345
"""
        }

        with patch("modules.data_processor.SetURLExtractor") as mock_extractor:
            mock_instance = Mock()
            mock_instance.extract_set_urls.return_value = {
                "https://mediux.pro/sets/12345"
            }
            mock_extractor.return_value = mock_instance

            file_name, total_urls = file_writer._update_data_file(
                folder_name="test_folder",
                data_to_write=data_to_write,
                existing_urls_set=existing_urls,
            )

            assert "test_folder_data.yml" in file_name
            assert total_urls == 1
            assert "https://mediux.pro/sets/12345" in existing_urls

            # Verify file was created
            assert os.path.exists(file_name)

    def test_update_data_file_existing_file(self, temp_dir):
        """Test _update_data_file with existing file."""
        file_writer = FileWriter()

        # Create existing file
        existing_file = os.path.join(temp_dir, "out", "kometa", "test_folder_data.yml")
        os.makedirs(os.path.dirname(existing_file), exist_ok=True)

        existing_yaml = """
metadata:
  tt0111162:
    title: "Existing Movie"
"""

        with open(existing_file, "w") as f:
            f.write(existing_yaml)

        existing_urls = set()
        data_to_write = {
            "tt0111161": """
title: "New Movie"
# https://mediux.pro/sets/67890
"""
        }

        with patch("modules.data_processor.SetURLExtractor") as mock_extractor:
            mock_instance = Mock()
            mock_instance.extract_set_urls.return_value = {
                "https://mediux.pro/sets/67890"
            }
            mock_extractor.return_value = mock_instance

            file_name, total_urls = file_writer._update_data_file(
                folder_name="test_folder",
                data_to_write=data_to_write,
                existing_urls_set=existing_urls,
            )

            assert total_urls == 1
            assert "https://mediux.pro/sets/67890" in existing_urls

    def test_update_data_file_tuple_folder_name(self, temp_dir):
        """Test _update_data_file with tuple folder name."""
        file_writer = FileWriter()
        existing_urls = set()

        data_to_write = {"tt0111161": "title: 'Test Movie'"}

        with patch("modules.data_processor.SetURLExtractor") as mock_extractor:
            mock_instance = Mock()
            mock_instance.extract_set_urls.return_value = set()
            mock_extractor.return_value = mock_instance

            file_name, total_urls = file_writer._update_data_file(
                folder_name=("test_folder", "extra"),
                data_to_write=data_to_write,
                existing_urls_set=existing_urls,
            )

            assert "test_folder_data.yml" in file_name

    def test_copy_to_output_dir_no_output_dir(self):
        """Test _copy_to_output_dir with no output directory."""
        file_writer = FileWriter()
        file_writer._copy_to_output_dir(None)
        # Should not raise any exception

    def test_copy_to_output_dir_no_source_dir(self, temp_dir):
        """Test _copy_to_output_dir with no source directory."""
        output_dir = os.path.join(temp_dir, "output")
        file_writer = FileWriter()

        # Ensure the source directory doesn't exist
        import shutil

        source_dir = os.path.join(os.getcwd(), "out", "kometa")
        if os.path.exists(source_dir):
            shutil.rmtree(source_dir)

        with patch.object(file_writer, "logger") as mock_logger:
            file_writer._copy_to_output_dir(output_dir)

            # Should log a warning that source directory doesn't exist
            mock_logger.warning.assert_called_with(
                f"Source directory ./out/kometa does not exist. Nothing to copy."
            )

    def test_copy_to_output_dir_success(self, temp_dir):
        """Test _copy_to_output_dir successful copy."""
        # Create source directory with files using absolute path
        source_dir = os.path.join(os.getcwd(), "out", "kometa")
        os.makedirs(source_dir, exist_ok=True)

        test_file = os.path.join(source_dir, "test.yml")
        with open(test_file, "w") as f:
            f.write("test content")

        output_dir = os.path.join(temp_dir, "output")
        file_writer = FileWriter()

        with patch.object(file_writer, "logger") as mock_logger:
            file_writer._copy_to_output_dir(output_dir)

            # Verify file was copied
            copied_file = os.path.join(output_dir, "test.yml")
            assert os.path.exists(copied_file), f"Expected file {copied_file} to exist"

            # Verify the info log was called
            assert any(
                "Files copied to" in str(call)
                for call in mock_logger.info.call_args_list
            ), "Expected info log about files being copied"

    def test_write_data_to_files_no_root_folder(self):
        """Test write_data_to_files with no root folder."""
        file_writer = FileWriter()

        with patch.object(file_writer, "logger") as mock_logger:
            file_writer.write_data_to_files(
                new_data={},
                root_folder_global=None,  # type: ignore
                cache={},
                cache_file=None,
                output_dir_global=None,
            )

            mock_logger.error.assert_called_with(
                "Root folder is not set. Cannot write data."
            )

    def test_write_data_to_files_success(self, temp_dir):
        """Test write_data_to_files successful operation."""
        file_writer = FileWriter()

        # Create temporary root folder
        root_folder = temp_dir
        test_folder = os.path.join(root_folder, "test_media")
        os.makedirs(test_folder)

        new_data = {"test_media": {"tt0111161": "title: 'Test Movie'"}}

        with patch.object(file_writer, "logger") as mock_logger:
            with patch("modules.file_manager.CacheManager") as mock_cache_manager:
                file_writer.write_data_to_files(
                    new_data=new_data,
                    root_folder_global=root_folder,
                    cache={"test": ("data", "movie")},
                    cache_file="/test/cache.pkl",
                    output_dir_global=None,
                )

                mock_logger.info.assert_called()
                mock_cache_manager.assert_called_once()

    def test_write_data_to_files_no_cache_file(self, temp_dir):
        """Test write_data_to_files with no cache file."""
        file_writer = FileWriter()

        # Create temporary root folder
        root_folder = temp_dir
        test_folder = os.path.join(root_folder, "test_media")
        os.makedirs(test_folder)

        new_data = {"test_media": {"tt0111161": "title: 'Test Movie'"}}

        with patch.object(file_writer, "logger") as mock_logger:
            file_writer.write_data_to_files(
                new_data=new_data,
                root_folder_global=root_folder,
                cache={},
                cache_file=None,
                output_dir_global=None,
            )

            # Should log that cache saving is disabled
            mock_logger.info.assert_called()

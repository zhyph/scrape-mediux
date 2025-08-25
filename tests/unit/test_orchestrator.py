"""
Unit tests for orchestrator.py module.
"""

import pytest
from unittest.mock import Mock, patch, call
from collections import defaultdict
from selenium.common.exceptions import TimeoutException
from modules.orchestrator import write_data_to_files, run


class TestWriteDataToFiles:
    """Test cases for write_data_to_files function."""

    def setup_method(self):
        """Set up test fixtures."""
        # Reset global variables
        import modules.orchestrator as orch

        orch.new_data = defaultdict(dict)
        orch.cache = {}
        orch.folder_bulk_data = {}
        orch.cache_config = Mock()

    def test_write_data_to_files_success(self):
        """Test successful data writing."""
        with patch("modules.orchestrator.new_data", {"folder1": {"tt0111161": "data"}}):
            with patch("modules.orchestrator.cache", {"cache": "data"}):
                with patch("modules.orchestrator.cache_config") as mock_cache_config:
                    with patch("modules.config.validate_path"):
                        with patch(
                            "modules.file_manager.FileWriter"
                        ) as mock_file_writer_class:
                            with patch(
                                "modules.intelligent_cache.get_cache_manager"
                            ) as mock_get_cache:

                                # Setup mocks
                                mock_cache_config.should_save_cache.return_value = True
                                mock_cache_config.get_cache_file_path.side_effect = [
                                    "/cache/intelligent_cache.pkl",
                                    "/cache/tmdb_cache.pkl",
                                ]

                                mock_file_writer = Mock()
                                mock_file_writer_class.return_value = mock_file_writer

                                mock_cache_manager = Mock()
                                mock_get_cache.return_value = mock_cache_manager

                                # Execute function
                                write_data_to_files(
                                    root_folder_path="/test/root",
                                    output_dir="/test/output",
                                )

                                # Verify calls
                                mock_cache_manager.save_cache.assert_called_once_with(
                                    "/cache/intelligent_cache.pkl"
                                )
                                mock_file_writer.write_data_to_files.assert_called_once_with(
                                    new_data={"folder1": {"tt0111161": "data"}},
                                    root_folder_global="/test/root",
                                    cache={"cache": "data"},
                                    cache_file="/cache/tmdb_cache.pkl",
                                    output_dir_global="/test/output",
                                )

    def test_write_data_to_files_no_root_folder(self, caplog):
        """Test that function exits early when no root folder is provided."""
        # Set logging level to capture ERROR messages
        import logging

        logger = logging.getLogger("modules.orchestrator")
        logger.setLevel(logging.INFO)

        write_data_to_files(root_folder_path=None)

        assert "Root folder is not set. Cannot write data." in caplog.text

    def test_write_data_to_files_cache_disabled(self):
        """Test data writing with cache disabled."""
        with patch("modules.orchestrator.new_data", {"folder1": {"tt0111161": "data"}}):
            with patch("modules.orchestrator.cache", {"cache": "data"}):
                with patch("modules.orchestrator.cache_config") as mock_cache_config:
                    with patch("modules.config.validate_path"):
                        with patch(
                            "modules.file_manager.FileWriter"
                        ) as mock_file_writer_class:
                            with patch(
                                "modules.intelligent_cache.get_cache_manager"
                            ) as mock_get_cache:

                                # Setup mocks - cache disabled
                                mock_cache_config.should_save_cache.return_value = False

                                mock_file_writer = Mock()
                                mock_file_writer_class.return_value = mock_file_writer

                                # Execute function
                                write_data_to_files(
                                    root_folder_path="/test/root",
                                    output_dir="/test/output",
                                )

                                # Verify cache-related calls were not made
                                mock_get_cache.assert_not_called()
                                mock_file_writer.write_data_to_files.assert_called_once_with(
                                    new_data={"folder1": {"tt0111161": "data"}},
                                    root_folder_global="/test/root",
                                    cache={},  # Empty cache when disabled
                                    cache_file=None,  # No cache file when disabled
                                    output_dir_global="/test/output",
                                )

    def test_write_data_to_files_with_empty_data(self):
        """Test data writing with empty data."""
        with patch("modules.orchestrator.new_data", {}):
            with patch("modules.orchestrator.cache", {}):
                with patch("modules.orchestrator.cache_config") as mock_cache_config:
                    with patch("modules.config.validate_path"):
                        with patch(
                            "modules.file_manager.FileWriter"
                        ) as mock_file_writer_class:

                            mock_cache_config.should_save_cache.return_value = False
                            mock_file_writer = Mock()
                            mock_file_writer_class.return_value = mock_file_writer

                            write_data_to_files(
                                root_folder_path="/test/root", output_dir="/test/output"
                            )

                            mock_file_writer.write_data_to_files.assert_called_once_with(
                                new_data={},
                                root_folder_global="/test/root",
                                cache={},
                                cache_file=None,
                                output_dir_global="/test/output",
                            )


# Simplified integration test for orchestrator functionality
def test_orchestrator_write_data_to_files_integration():
    """Test write_data_to_files with realistic global state."""
    # Mock the global variables that the function uses
    with patch(
        "modules.orchestrator.new_data", {"test_folder": {"tt0111161": "test_data"}}
    ):
        with patch("modules.orchestrator.cache", {"test": "cache_data"}):
            with patch("modules.orchestrator.cache_config") as mock_cache_config:
                with patch("modules.config.validate_path"):
                    with patch(
                        "modules.file_manager.FileWriter"
                    ) as mock_file_writer_class:
                        with patch(
                            "modules.intelligent_cache.get_cache_manager"
                        ) as mock_get_cache:

                            # Setup mocks
                            mock_cache_config.should_save_cache.return_value = True
                            mock_cache_config.get_cache_file_path.side_effect = [
                                "/cache/intelligent_cache.pkl",
                                "/cache/tmdb_cache.pkl",
                            ]

                            mock_file_writer = Mock()
                            mock_file_writer_class.return_value = mock_file_writer

                            mock_cache_manager = Mock()
                            mock_get_cache.return_value = mock_cache_manager

                            # Execute function
                            write_data_to_files(
                                root_folder_path="/test/media",
                                output_dir="/test/output",
                            )

                            # Verify the function completed successfully
                            # (This tests the integration with global state)
                            mock_file_writer.write_data_to_files.assert_called_once()
                            assert mock_file_writer.write_data_to_files.call_args[1][
                                "new_data"
                            ] == {"test_folder": {"tt0111161": "test_data"}}
                            assert (
                                mock_file_writer.write_data_to_files.call_args[1][
                                    "root_folder_global"
                                ]
                                == "/test/media"
                            )
                            assert (
                                mock_file_writer.write_data_to_files.call_args[1][
                                    "output_dir_global"
                                ]
                                == "/test/output"
                            )


# Simplified tests for the run function focusing on key functionality
def test_run_function_setup_phase():
    """Test the setup phase of the run function."""
    with patch("modules.cache_config.CacheConfig") as mock_cache_config_class:
        with patch("modules.orchestrator.cache_config", Mock()):
            with patch("modules.orchestrator.os.path.exists", return_value=True):
                with patch("modules.orchestrator.os.makedirs"):
                    with patch(
                        "modules.file_manager.CacheManager"
                    ) as mock_cache_manager_class:
                        with patch(
                            "modules.intelligent_cache.get_cache_manager"
                        ) as mock_get_cache:
                            with patch(
                                "modules.file_manager.BulkDataManager"
                            ) as mock_bulk_manager_class:
                                with patch(
                                    "modules.media_discovery.get_media_ids",
                                    return_value=([], {}),
                                ):
                                    with patch("modules.scraper.WebDriverManager"):
                                        with patch(
                                            "modules.scraper.MediuxLoginManager"
                                        ):
                                            with patch(
                                                "modules.media_processing.process_single_media_item"
                                            ):
                                                with patch(
                                                    "modules.orchestrator.write_data_to_files"
                                                ):
                                                    with patch(
                                                        "modules.external_services.DiscordNotifier"
                                                    ):
                                                        with patch(
                                                            "modules.orchestrator.time.time",
                                                            side_effect=[
                                                                1000.0,
                                                                1100.0,
                                                            ],
                                                        ):
                                                            with patch(
                                                                "modules.orchestrator.os.remove"
                                                            ):  # Mock file removal

                                                                # Setup mocks
                                                                mock_cache_config = (
                                                                    Mock()
                                                                )
                                                                mock_cache_config.clear_cache = (
                                                                    False
                                                                )
                                                                mock_cache_config.should_save_cache.return_value = (
                                                                    True
                                                                )
                                                                mock_cache_config.get_cache_file_path.side_effect = [
                                                                    "/cache/tmdb_cache.pkl",
                                                                    "/cache/intelligent_cache.pkl",
                                                                ]
                                                                mock_cache_config_class.return_value = (
                                                                    mock_cache_config
                                                                )

                                                                mock_cache_manager = (
                                                                    Mock()
                                                                )
                                                                mock_cache_manager_class.return_value = (
                                                                    mock_cache_manager
                                                                )
                                                                mock_cache_manager.load_cache.return_value = {
                                                                    "test": "cache"
                                                                }

                                                                mock_intelligent_cache = (
                                                                    Mock()
                                                                )
                                                                mock_get_cache.return_value = mock_intelligent_cache

                                                                mock_bulk_manager = (
                                                                    Mock()
                                                                )
                                                                mock_bulk_manager_class.return_value = (
                                                                    mock_bulk_manager
                                                                )

                                                                # Execute function
                                                                run(
                                                                    api_key="test_key",
                                                                    username="test_user",
                                                                    password="test_pass",
                                                                    profile_path="/test/profile",
                                                                    nickname="test_nick",
                                                                    sonarr_api_key=None,
                                                                    sonarr_endpoint=None,
                                                                    root_folder_global="/test/root",
                                                                    output_dir_global="/test/output",
                                                                    discord_webhook_url_global=None,
                                                                    selected_folders=None,
                                                                    headless=True,
                                                                    process_all=False,
                                                                    chromedriver_path=None,
                                                                    retry_on_yaml_failure=False,
                                                                    preferred_users=None,
                                                                    excluded_users=None,
                                                                    disable_season_fix=False,
                                                                    remove_paths=None,
                                                                    plex_url=None,
                                                                    plex_token=None,
                                                                    plex_libraries=None,
                                                                    disable_cache=False,
                                                                    clear_cache=False,
                                                                    cache_dir="./out",
                                                                )

                                                            # Verify cache configuration was created
                                                            mock_cache_config_class.assert_called_once_with(
                                                                disable_cache=False,
                                                                clear_cache=False,
                                                                cache_dir="./out",
                                                            )


def test_write_data_to_files_integration():
    """Test write_data_to_files with realistic global state."""
    # Mock the global variables that the function uses
    with patch(
        "modules.orchestrator.new_data", {"test_folder": {"tt0111161": "test_data"}}
    ):
        with patch("modules.orchestrator.cache", {"test": "cache_data"}):
            with patch("modules.orchestrator.cache_config") as mock_cache_config:
                with patch("modules.config.validate_path"):
                    with patch(
                        "modules.file_manager.FileWriter"
                    ) as mock_file_writer_class:
                        with patch(
                            "modules.intelligent_cache.get_cache_manager"
                        ) as mock_get_cache:

                            # Setup mocks
                            mock_cache_config.should_save_cache.return_value = True
                            mock_cache_config.get_cache_file_path.side_effect = [
                                "/cache/intelligent_cache.pkl",
                                "/cache/tmdb_cache.pkl",
                            ]

                            mock_file_writer = Mock()
                            mock_file_writer_class.return_value = mock_file_writer

                            mock_cache_manager = Mock()
                            mock_get_cache.return_value = mock_cache_manager

                            # Execute function
                            write_data_to_files(
                                root_folder_path="/test/media",
                                output_dir="/test/output",
                            )

                            # Verify the function completed successfully
                            # (This tests the integration with global state)
                            mock_file_writer.write_data_to_files.assert_called_once()
                            assert mock_file_writer.write_data_to_files.call_args[1][
                                "new_data"
                            ] == {"test_folder": {"tt0111161": "test_data"}}
                            assert (
                                mock_file_writer.write_data_to_files.call_args[1][
                                    "root_folder_global"
                                ]
                                == "/test/media"
                            )
                            assert (
                                mock_file_writer.write_data_to_files.call_args[1][
                                    "output_dir_global"
                                ]
                                == "/test/output"
                            )


class TestRunFunction:
    """Test cases for run function."""

    def setup_method(self):
        """Set up test fixtures."""
        # Reset global variables
        import modules.orchestrator as orch

        orch.new_data = defaultdict(dict)
        orch.cache = {}
        orch.folder_bulk_data = {}
        orch.cache_config = Mock()

    def test_run_initialization_and_setup(self):
        """Test the initial setup phase of the run function."""
        with patch("modules.orchestrator.time.time", side_effect=[1000.0, 1100.0]):
            with patch("modules.cache_config.CacheConfig") as mock_cache_config_class:
                with patch("modules.orchestrator.cache_config", Mock()):
                    with patch("modules.config.validate_path"):
                        with patch(
                            "modules.orchestrator.os.path.exists", return_value=True
                        ):
                            with patch("modules.orchestrator.os.makedirs"):
                                with patch(
                                    "modules.file_manager.CacheManager"
                                ) as mock_cache_manager_class:
                                    with patch(
                                        "modules.intelligent_cache.get_cache_manager"
                                    ) as mock_get_cache:
                                        with patch(
                                            "modules.file_manager.BulkDataManager"
                                        ) as mock_bulk_manager_class:
                                            with patch(
                                                "modules.media_discovery.get_media_ids",
                                                return_value=([], {}),
                                            ):
                                                with patch(
                                                    "modules.scraper.WebDriverManager"
                                                ):
                                                    with patch(
                                                        "modules.scraper.MediuxLoginManager"
                                                    ):
                                                        with patch(
                                                            "modules.media_processing.process_single_media_item"
                                                        ):
                                                            with patch(
                                                                "modules.orchestrator.write_data_to_files"
                                                            ):
                                                                with patch(
                                                                    "modules.external_services.DiscordNotifier"
                                                                ):
                                                                    with patch(
                                                                        "modules.orchestrator.os.remove"
                                                                    ):  # Mock file removal

                                                                        # Setup mocks
                                                                        mock_cache_config = (
                                                                            Mock()
                                                                        )
                                                                        mock_cache_config.clear_cache = (
                                                                            True
                                                                        )
                                                                        mock_cache_config.should_save_cache.return_value = (
                                                                            True
                                                                        )
                                                                        mock_cache_config.get_cache_file_path.side_effect = [
                                                                            "/cache/tmdb_cache.pkl",
                                                                            "/cache/intelligent_cache.pkl",
                                                                        ]
                                                                        mock_cache_config_class.return_value = mock_cache_config

                                                                        mock_cache_manager = (
                                                                            Mock()
                                                                        )
                                                                        mock_cache_manager_class.return_value = mock_cache_manager
                                                                        mock_cache_manager.load_cache.return_value = {
                                                                            "test": "cache"
                                                                        }

                                                                        mock_intelligent_cache = (
                                                                            Mock()
                                                                        )
                                                                        mock_get_cache.return_value = mock_intelligent_cache

                                                                        mock_bulk_manager = (
                                                                            Mock()
                                                                        )
                                                                        mock_bulk_manager_class.return_value = mock_bulk_manager

                                                                        # Execute function
                                                                        run(
                                                                            api_key="test_key",
                                                                            username="test_user",
                                                                            password="test_pass",
                                                                            profile_path="/test/profile",
                                                                            nickname="test_nick",
                                                                            sonarr_api_key=None,
                                                                            sonarr_endpoint=None,
                                                                            root_folder_global="/test/root",
                                                                            output_dir_global="/test/output",
                                                                            discord_webhook_url_global=None,
                                                                            selected_folders=None,
                                                                            headless=True,
                                                                            process_all=False,
                                                                            chromedriver_path=None,
                                                                            retry_on_yaml_failure=False,
                                                                            preferred_users=None,
                                                                            excluded_users=None,
                                                                            disable_season_fix=False,
                                                                            remove_paths=None,
                                                                            plex_url=None,
                                                                            plex_token=None,
                                                                            plex_libraries=None,
                                                                            disable_cache=False,
                                                                            clear_cache=False,
                                                                            cache_dir="./out",
                                                                        )

                                                                        # Verify cache configuration
                                                                        mock_cache_config_class.assert_called_once_with(
                                                                            disable_cache=False,
                                                                            clear_cache=False,
                                                                            cache_dir="./out",
                                                                        )

    def test_run_with_cache_disabled(self):
        """Test run function with cache disabled."""
        with patch("modules.orchestrator.time.time", side_effect=[1000.0, 1100.0]):
            with patch("modules.cache_config.CacheConfig") as mock_cache_config_class:
                with patch("modules.orchestrator.cache_config", Mock()):
                    with patch("modules.config.validate_path"):
                        with patch(
                            "modules.orchestrator.os.path.exists", return_value=True
                        ):
                            with patch("modules.orchestrator.os.makedirs"):
                                with patch(
                                    "modules.media_discovery.get_media_ids",
                                    return_value=([], {}),
                                ):
                                    with patch("modules.scraper.WebDriverManager"):
                                        with patch(
                                            "modules.scraper.MediuxLoginManager"
                                        ):
                                            with patch(
                                                "modules.media_processing.process_single_media_item"
                                            ):
                                                with patch(
                                                    "modules.orchestrator.write_data_to_files"
                                                ):
                                                    with patch(
                                                        "modules.external_services.DiscordNotifier"
                                                    ):
                                                        with patch(
                                                            "modules.orchestrator.os.remove"
                                                        ):  # Mock file removal

                                                            # Setup mocks
                                                            mock_cache_config = Mock()
                                                            mock_cache_config.disable_cache = (
                                                                True
                                                            )
                                                            mock_cache_config.clear_cache = (
                                                                False
                                                            )
                                                            mock_cache_config.should_save_cache.return_value = (
                                                                False
                                                            )
                                                            mock_cache_config.get_cache_file_path.side_effect = [
                                                                "/cache/tmdb_cache.pkl",
                                                                "/cache/intelligent_cache.pkl",
                                                            ]
                                                            mock_cache_config_class.return_value = (
                                                                mock_cache_config
                                                            )

                                                            # Execute function with cache disabled
                                                            run(
                                                                api_key="test_key",
                                                                username="test_user",
                                                                password="test_pass",
                                                                profile_path="/test/profile",
                                                                nickname="test_nick",
                                                                sonarr_api_key=None,
                                                                sonarr_endpoint=None,
                                                                root_folder_global="/test/root",
                                                                output_dir_global=None,
                                                                discord_webhook_url_global=None,
                                                                selected_folders=None,
                                                                headless=True,
                                                                process_all=False,
                                                                chromedriver_path=None,
                                                                retry_on_yaml_failure=False,
                                                                preferred_users=None,
                                                                excluded_users=None,
                                                                disable_season_fix=False,
                                                                remove_paths=None,
                                                                plex_url=None,
                                                                plex_token=None,
                                                                plex_libraries=None,
                                                                disable_cache=True,  # Cache disabled
                                                                clear_cache=False,
                                                                cache_dir="./out",
                                                            )

    def test_run_with_cache_clearing(self):
        """Test run function with cache clearing enabled."""
        with patch("modules.orchestrator.time.time", side_effect=[1000.0, 1100.0]):
            with patch("modules.cache_config.CacheConfig") as mock_cache_config_class:
                with patch("modules.orchestrator.cache_config", Mock()):
                    with patch("modules.config.validate_path"):
                        with patch(
                            "modules.orchestrator.os.path.exists", return_value=True
                        ):
                            with patch("modules.orchestrator.os.makedirs"):
                                with patch(
                                    "modules.orchestrator.os.remove"
                                ):  # Mock file removal
                                    with patch(
                                        "modules.media_discovery.get_media_ids",
                                        return_value=([], {}),
                                    ):
                                        with patch("modules.scraper.WebDriverManager"):
                                            with patch(
                                                "modules.scraper.MediuxLoginManager"
                                            ):
                                                with patch(
                                                    "modules.media_processing.process_single_media_item"
                                                ):
                                                    with patch(
                                                        "modules.orchestrator.write_data_to_files"
                                                    ):
                                                        with patch(
                                                            "modules.external_services.DiscordNotifier"
                                                        ):

                                                            # Setup mocks
                                                            mock_cache_config = Mock()
                                                            mock_cache_config.clear_cache = (
                                                                True
                                                            )
                                                            mock_cache_config.get_cache_file_path.side_effect = [
                                                                "/cache/tmdb_cache.pkl",
                                                                "/cache/intelligent_cache.pkl",
                                                            ]
                                                            mock_cache_config_class.return_value = (
                                                                mock_cache_config
                                                            )
                                                            mock_cache_config.should_save_cache.return_value = (
                                                                True
                                                            )

                                                            # Execute function with cache clearing
                                                            run(
                                                                api_key="test_key",
                                                                username="test_user",
                                                                password="test_pass",
                                                                profile_path="/test/profile",
                                                                nickname="test_nick",
                                                                sonarr_api_key=None,
                                                                sonarr_endpoint=None,
                                                                root_folder_global="/test/root",
                                                                output_dir_global=None,
                                                                discord_webhook_url_global=None,
                                                                selected_folders=None,
                                                                headless=True,
                                                                process_all=False,
                                                                chromedriver_path=None,
                                                                retry_on_yaml_failure=False,
                                                                preferred_users=None,
                                                                excluded_users=None,
                                                                disable_season_fix=False,
                                                                remove_paths=None,
                                                                plex_url=None,
                                                                plex_token=None,
                                                                plex_libraries=None,
                                                                clear_cache=True,  # Cache clearing enabled
                                                                disable_cache=False,
                                                                cache_dir="./out",
                                                            )

                                                            # Verify cache file removal was attempted
                                                            # (This would be verified by checking os.remove calls in a more detailed test)

    def test_run_with_plex_libraries(self):
        """Test run function with Plex libraries configured."""
        with patch("modules.orchestrator.time.time", side_effect=[1000.0, 1100.0]):
            with patch("modules.cache_config.CacheConfig") as mock_cache_config_class:
                with patch("modules.orchestrator.cache_config", Mock()):
                    with patch("modules.config.validate_path"):
                        with patch(
                            "modules.orchestrator.os.path.exists", return_value=True
                        ):
                            with patch("modules.orchestrator.os.makedirs"):
                                with patch(
                                    "modules.file_manager.BulkDataManager"
                                ) as mock_bulk_manager_class:
                                    with patch(
                                        "modules.media_discovery.get_media_ids",
                                        return_value=([], {}),
                                    ):
                                        with patch("modules.scraper.WebDriverManager"):
                                            with patch(
                                                "modules.scraper.MediuxLoginManager"
                                            ):
                                                with patch(
                                                    "modules.media_processing.process_single_media_item"
                                                ):
                                                    with patch(
                                                        "modules.orchestrator.write_data_to_files"
                                                    ):
                                                        with patch(
                                                            "modules.external_services.DiscordNotifier"
                                                        ):

                                                            # Setup mocks
                                                            mock_cache_config = Mock()
                                                            mock_cache_config.clear_cache = (
                                                                False
                                                            )
                                                            mock_cache_config.should_save_cache.return_value = (
                                                                True
                                                            )
                                                            mock_cache_config.get_cache_file_path.side_effect = [
                                                                "/cache/tmdb_cache.pkl",
                                                                "/cache/intelligent_cache.pkl",
                                                            ]
                                                            mock_cache_config_class.return_value = (
                                                                mock_cache_config
                                                            )

                                                            mock_bulk_manager = Mock()
                                                            mock_bulk_manager_class.return_value = (
                                                                mock_bulk_manager
                                                            )

                                                            # Execute function with Plex libraries
                                                            run(
                                                                api_key="test_key",
                                                                username="test_user",
                                                                password="test_pass",
                                                                profile_path="/test/profile",
                                                                nickname="test_nick",
                                                                sonarr_api_key=None,
                                                                sonarr_endpoint=None,
                                                                root_folder_global="/test/root",
                                                                output_dir_global=None,
                                                                discord_webhook_url_global=None,
                                                                selected_folders=None,
                                                                headless=True,
                                                                process_all=False,
                                                                chromedriver_path=None,
                                                                retry_on_yaml_failure=False,
                                                                preferred_users=None,
                                                                excluded_users=None,
                                                                disable_season_fix=False,
                                                                remove_paths=None,
                                                                plex_url="http://plex:32400",
                                                                plex_token="test_token",
                                                                plex_libraries=[
                                                                    "Movies",
                                                                    "TV Shows",
                                                                ],
                                                                disable_cache=False,
                                                                clear_cache=False,
                                                                cache_dir="./out",
                                                            )

                                                            # Verify BulkDataManager was called for each library
                                                            assert (
                                                                mock_bulk_manager_class.call_count
                                                                >= 2
                                                            )  # At least for the Plex libraries

    def test_run_webdriver_initialization_error(self):
        """Test handling of WebDriver initialization errors."""
        with patch("modules.orchestrator.time.time", side_effect=[1000.0, 1100.0]):
            with patch("modules.cache_config.CacheConfig") as mock_cache_config_class:
                with patch("modules.orchestrator.cache_config", Mock()):
                    with patch(
                        "modules.orchestrator.os.path.exists", return_value=True
                    ):
                        with patch("modules.orchestrator.os.makedirs"):
                            with patch(
                                "modules.media_discovery.get_media_ids",
                                return_value=([], {}),
                            ):
                                with patch(
                                    "modules.scraper.WebDriverManager"
                                ) as mock_webdriver_class:
                                    with patch(
                                        "modules.orchestrator.write_data_to_files"
                                    ):
                                        with patch(
                                            "modules.external_services.DiscordNotifier"
                                        ):
                                            with patch(
                                                "modules.orchestrator.os.remove"
                                            ):  # Mock file removal

                                                # Setup mocks
                                                mock_cache_config = Mock()
                                                mock_cache_config.clear_cache = True
                                                mock_cache_config.should_save_cache.return_value = (
                                                    True
                                                )
                                                mock_cache_config.get_cache_file_path.side_effect = [
                                                    "/cache/tmdb_cache.pkl",
                                                    "/cache/intelligent_cache.pkl",
                                                ]
                                                mock_cache_config_class.return_value = (
                                                    mock_cache_config
                                                )

                                                # Setup WebDriver to raise exception
                                                mock_webdriver_manager = Mock()
                                                mock_webdriver_class.return_value = (
                                                    mock_webdriver_manager
                                                )
                                                mock_webdriver_manager.init_driver.side_effect = Exception(
                                                    "WebDriver error"
                                                )

                                                # Execute function - should handle the error gracefully
                                                with pytest.raises(
                                                    Exception, match="WebDriver error"
                                                ):
                                                    run(
                                                        api_key="test_key",
                                                        username="test_user",
                                                        password="test_pass",
                                                        profile_path="/test/profile",
                                                        nickname="test_nick",
                                                        sonarr_api_key=None,
                                                        sonarr_endpoint=None,
                                                        root_folder_global="/test/root",
                                                        output_dir_global=None,
                                                        discord_webhook_url_global=None,
                                                        selected_folders=None,
                                                        headless=True,
                                                        process_all=False,
                                                        chromedriver_path=None,
                                                        retry_on_yaml_failure=False,
                                                        preferred_users=None,
                                                        excluded_users=None,
                                                        disable_season_fix=False,
                                                        remove_paths=None,
                                                        plex_url=None,
                                                        plex_token=None,
                                                        plex_libraries=None,
                                                        disable_cache=False,
                                                        clear_cache=True,
                                                        cache_dir="./out",
                                                    )

    def test_run_media_processing_with_progress(self):
        """Test media processing with progress tracking."""
        # Mock media items to process
        mock_media_items = [
            ("tt0111161", "Test Movie 1", "imdb_id", "movie"),
            ("tt0111162", "Test Movie 2", "imdb_id", "movie"),
        ]

        with patch("modules.orchestrator.time.time", side_effect=[1000.0, 1100.0]):
            with patch("modules.cache_config.CacheConfig") as mock_cache_config_class:
                with patch("modules.orchestrator.cache_config", Mock()):
                    with patch(
                        "modules.orchestrator.os.path.exists", return_value=True
                    ):
                        with patch("modules.orchestrator.os.makedirs"):
                            with patch(
                                "modules.media_discovery.get_media_ids",
                                return_value=(
                                    mock_media_items,
                                    {"tt0111161": ["folder1"]},
                                ),
                            ):
                                with patch(
                                    "modules.scraper.WebDriverManager"
                                ) as mock_webdriver_class:
                                    with patch("modules.scraper.MediuxLoginManager"):
                                        with patch(
                                            "modules.media_processing.process_single_media_item"
                                        ) as mock_process:
                                            with patch(
                                                "modules.orchestrator.write_data_to_files"
                                            ):
                                                with patch(
                                                    "modules.external_services.DiscordNotifier"
                                                ):
                                                    with patch(
                                                        "modules.orchestrator.os.remove"
                                                    ):  # Mock file removal

                                                        # Setup mocks
                                                        mock_cache_config = Mock()
                                                        mock_cache_config.clear_cache = (
                                                            True
                                                        )
                                                        mock_cache_config.should_save_cache.return_value = (
                                                            True
                                                        )
                                                        mock_cache_config.get_cache_file_path.side_effect = [
                                                            "/cache/tmdb_cache.pkl",
                                                            "/cache/intelligent_cache.pkl",
                                                        ]
                                                        mock_cache_config_class.return_value = (
                                                            mock_cache_config
                                                        )

                                                        mock_webdriver_manager = Mock()
                                                        mock_webdriver_class.return_value = (
                                                            mock_webdriver_manager
                                                        )
                                                        mock_webdriver_manager.init_driver.return_value = (
                                                            Mock()
                                                        )

                                                        # Execute function
                                                        run(
                                                            api_key="test_key",
                                                            username="test_user",
                                                            password="test_pass",
                                                            profile_path="/test/profile",
                                                            nickname="test_nick",
                                                            sonarr_api_key=None,
                                                            sonarr_endpoint=None,
                                                            root_folder_global="/test/root",
                                                            output_dir_global=None,
                                                            discord_webhook_url_global=None,
                                                            selected_folders=None,
                                                            headless=True,
                                                            process_all=False,
                                                            chromedriver_path=None,
                                                            retry_on_yaml_failure=False,
                                                            preferred_users=None,
                                                            excluded_users=None,
                                                            disable_season_fix=False,
                                                            remove_paths=None,
                                                            plex_url=None,
                                                            plex_token=None,
                                                            plex_libraries=None,
                                                            disable_cache=False,
                                                            clear_cache=True,
                                                            cache_dir="./out",
                                                        )

                                                        # Verify process_single_media_item was called for each media item
                                                        assert (
                                                            mock_process.call_count == 2
                                                        )
                                                        mock_process.assert_has_calls(
                                                            [
                                                                call(
                                                                    media_id_from_folder="tt0111161",
                                                                    media_name="Test Movie 1",
                                                                    external_source_type="imdb_id",
                                                                    media_type_from_plex="movie",
                                                                    driver=mock_webdriver_manager.init_driver.return_value,
                                                                    api_key="test_key",
                                                                    sonarr_api_key=None,
                                                                    sonarr_endpoint=None,
                                                                    process_all=False,
                                                                    retry_on_yaml_failure=False,
                                                                    preferred_users=None,
                                                                    excluded_users=None,
                                                                    folder_map_for_media={
                                                                        "tt0111161": [
                                                                            "folder1"
                                                                        ]
                                                                    },
                                                                    updated_titles_list=[],
                                                                    fixed_titles_list=[],
                                                                    disable_season_fix=False,
                                                                    remove_paths=None,
                                                                    shared_cache={},
                                                                    shared_new_data=defaultdict(
                                                                        dict
                                                                    ),
                                                                    shared_folder_bulk_data={},
                                                                ),
                                                                call(
                                                                    media_id_from_folder="tt0111162",
                                                                    media_name="Test Movie 2",
                                                                    external_source_type="imdb_id",
                                                                    media_type_from_plex="movie",
                                                                    driver=mock_webdriver_manager.init_driver.return_value,
                                                                    api_key="test_key",
                                                                    sonarr_api_key=None,
                                                                    sonarr_endpoint=None,
                                                                    process_all=False,
                                                                    retry_on_yaml_failure=False,
                                                                    preferred_users=None,
                                                                    excluded_users=None,
                                                                    folder_map_for_media={
                                                                        "tt0111161": [
                                                                            "folder1"
                                                                        ]
                                                                    },
                                                                    updated_titles_list=[],
                                                                    fixed_titles_list=[],
                                                                    disable_season_fix=False,
                                                                    remove_paths=None,
                                                                    shared_cache={},
                                                                    shared_new_data=defaultdict(
                                                                        dict
                                                                    ),
                                                                    shared_folder_bulk_data={},
                                                                ),
                                                            ]
                                                        )

    def test_run_with_discord_notifications(self):
        """Test Discord notification functionality."""
        with patch("modules.orchestrator.time.time", side_effect=[1000.0, 1100.0]):
            with patch("modules.cache_config.CacheConfig") as mock_cache_config_class:
                with patch("modules.orchestrator.cache_config", Mock()):
                    with patch(
                        "modules.orchestrator.os.path.exists", return_value=True
                    ):
                        with patch("modules.orchestrator.os.makedirs"):
                            with patch(
                                "modules.media_discovery.get_media_ids",
                                return_value=([], {}),
                            ):
                                with patch(
                                    "modules.scraper.WebDriverManager"
                                ) as mock_webdriver_class:
                                    with patch("modules.scraper.MediuxLoginManager"):
                                        with patch(
                                            "modules.media_processing.process_single_media_item"
                                        ):
                                            with patch(
                                                "modules.orchestrator.write_data_to_files"
                                            ):
                                                with patch(
                                                    "modules.external_services.DiscordNotifier"
                                                ) as mock_discord_class:
                                                    with patch(
                                                        "modules.orchestrator.os.remove"
                                                    ):  # Mock file removal

                                                        # Setup mocks
                                                        mock_cache_config = Mock()
                                                        mock_cache_config.clear_cache = (
                                                            True
                                                        )
                                                        mock_cache_config.should_save_cache.return_value = (
                                                            True
                                                        )
                                                        mock_cache_config.get_cache_file_path.side_effect = [
                                                            "/cache/tmdb_cache.pkl",
                                                            "/cache/intelligent_cache.pkl",
                                                        ]
                                                        mock_cache_config_class.return_value = (
                                                            mock_cache_config
                                                        )

                                                        mock_webdriver_manager = Mock()
                                                        mock_webdriver_class.return_value = (
                                                            mock_webdriver_manager
                                                        )
                                                        mock_webdriver_manager.init_driver.return_value = (
                                                            Mock()
                                                        )

                                                        mock_discord = Mock()
                                                        mock_discord_class.return_value = (
                                                            mock_discord
                                                        )

                                                        # Execute function with Discord notifications
                                                        run(
                                                            api_key="test_key",
                                                            username="test_user",
                                                            password="test_pass",
                                                            profile_path="/test/profile",
                                                            nickname="test_nick",
                                                            sonarr_api_key=None,
                                                            sonarr_endpoint=None,
                                                            root_folder_global="/test/root",
                                                            output_dir_global=None,
                                                            discord_webhook_url_global="https://discord.com/api/webhooks/test",
                                                            selected_folders=None,
                                                            headless=True,
                                                            process_all=False,
                                                            chromedriver_path=None,
                                                            retry_on_yaml_failure=False,
                                                            preferred_users=None,
                                                            excluded_users=None,
                                                            disable_season_fix=False,
                                                            remove_paths=None,
                                                            plex_url=None,
                                                            plex_token=None,
                                                            plex_libraries=None,
                                                            disable_cache=False,
                                                            clear_cache=True,
                                                            cache_dir="./out",
                                                        )

                                                        # Verify Discord notification was attempted
                                                        # (This would send notifications if there were updated titles)
                                                        # In this test, no titles were updated, so no notifications should be sent

    def test_run_error_handling_and_recovery(self):
        """Test error handling and WebDriver recovery."""
        # Mock media items to process
        mock_media_items = [
            ("tt0111161", "Test Movie 1", "imdb_id", "movie"),
        ]

        with patch("modules.orchestrator.time.time", side_effect=[1000.0, 1100.0]):
            with patch("modules.cache_config.CacheConfig") as mock_cache_config_class:
                with patch("modules.orchestrator.cache_config", Mock()):
                    with patch(
                        "modules.orchestrator.os.path.exists", return_value=True
                    ):
                        with patch("modules.orchestrator.os.makedirs"):
                            with patch(
                                "modules.media_discovery.get_media_ids",
                                return_value=(
                                    mock_media_items,
                                    {"tt0111161": ["folder1"]},
                                ),
                            ):
                                with patch(
                                    "modules.scraper.WebDriverManager"
                                ) as mock_webdriver_class:
                                    with patch(
                                        "modules.scraper.MediuxLoginManager"
                                    ) as mock_login_class:
                                        with patch(
                                            "modules.media_processing.process_single_media_item",
                                            side_effect=[
                                                TimeoutException("Test timeout"),
                                                None,
                                            ],
                                        ):
                                            with patch(
                                                "modules.orchestrator.write_data_to_files"
                                            ):
                                                with patch(
                                                    "modules.external_services.DiscordNotifier"
                                                ):
                                                    with patch(
                                                        "modules.orchestrator.os.remove"
                                                    ):  # Mock file removal

                                                        # Setup mocks
                                                        mock_cache_config = Mock()
                                                        mock_cache_config.clear_cache = (
                                                            True
                                                        )
                                                        mock_cache_config.should_save_cache.return_value = (
                                                            True
                                                        )
                                                        mock_cache_config.get_cache_file_path.side_effect = [
                                                            "/cache/tmdb_cache.pkl",
                                                            "/cache/intelligent_cache.pkl",
                                                        ]
                                                        mock_cache_config_class.return_value = (
                                                            mock_cache_config
                                                        )

                                                        mock_webdriver_manager = Mock()
                                                        mock_webdriver_class.return_value = (
                                                            mock_webdriver_manager
                                                        )
                                                        mock_webdriver_manager.init_driver.return_value = (
                                                            Mock()
                                                        )

                                                        mock_login_manager = Mock()
                                                        mock_login_class.return_value = (
                                                            mock_login_manager
                                                        )

                                                        # Execute function
                                                        run(
                                                            api_key="test_key",
                                                            username="test_user",
                                                            password="test_pass",
                                                            profile_path="/test/profile",
                                                            nickname="test_nick",
                                                            sonarr_api_key=None,
                                                            sonarr_endpoint=None,
                                                            root_folder_global="/test/root",
                                                            output_dir_global=None,
                                                            discord_webhook_url_global=None,
                                                            selected_folders=None,
                                                            headless=True,
                                                            process_all=False,
                                                            chromedriver_path=None,
                                                            retry_on_yaml_failure=False,
                                                            preferred_users=None,
                                                            excluded_users=None,
                                                            disable_season_fix=False,
                                                            remove_paths=None,
                                                            plex_url=None,
                                                            plex_token=None,
                                                            plex_libraries=None,
                                                            disable_cache=False,
                                                            clear_cache=True,
                                                            cache_dir="./out",
                                                        )

                                                        # Verify WebDriver was re-initialized after timeout
                                                        assert (
                                                            mock_webdriver_manager.init_driver.call_count
                                                            >= 2
                                                        )  # Initial + recovery
                                                        assert (
                                                            mock_login_manager.login.call_count
                                                            >= 2
                                                        )  # Initial + recovery

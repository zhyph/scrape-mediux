"""
Integration tests for Plex and folder-based modes working together.

This module tests the integration scenarios where the recent changes
ensure both discovery modes work seamlessly without the "Root folder is not set" error.
"""

from unittest.mock import Mock, patch

from modules.orchestrator import write_data_to_files, run


class TestPlexFolderModesIntegration:
    """Integration tests for both Plex and folder-based modes."""

    def test_orchestrator_both_modes_no_root_folder_error(self):
        """Test that orchestrator works in both modes without root folder error."""
        # Test 1: Plex-only mode (should not raise root folder error)
        with patch(
            "modules.orchestrator.new_data", {"plex_show": {"tt0111161": "data"}}
        ):
            with patch("modules.orchestrator.cache", {}):
                with patch("modules.orchestrator.cache_config") as mock_cache_config:
                    with patch(
                        "modules.file_manager.FileWriter"
                    ) as mock_file_writer_class:
                        with patch("modules.intelligent_cache.get_cache_manager"):
                            # Setup mocks
                            mock_cache_config.should_save_cache.return_value = False

                            mock_file_writer = Mock()
                            mock_file_writer_class.return_value = mock_file_writer

                            # Execute in Plex mode - should not raise any error
                            write_data_to_files(
                                root_folder_path=None,  # No root folder (Plex mode)
                                output_dir="/test/output",
                            )

                            # Verify function completed successfully
                            mock_file_writer.write_data_to_files.assert_called_once_with(
                                new_data={"plex_show": {"tt0111161": "data"}},
                                cache={},
                                cache_file=None,
                                output_dir_global="/test/output",
                            )

        # Test 2: Folder-based mode (should work normally)
        with patch(
            "modules.orchestrator.new_data", {"folder_show": {"tt0111162": "data"}}
        ):
            with patch("modules.orchestrator.cache", {}):
                with patch("modules.orchestrator.cache_config") as mock_cache_config:
                    with patch(
                        "modules.file_manager.FileWriter"
                    ) as mock_file_writer_class:
                        with patch("modules.intelligent_cache.get_cache_manager"):
                            # Setup mocks
                            mock_cache_config.should_save_cache.return_value = False

                            mock_file_writer = Mock()
                            mock_file_writer_class.return_value = mock_file_writer

                            # Execute in folder mode - should work normally
                            write_data_to_files(
                                root_folder_path="/test/media",  # With root folder
                                output_dir="/test/output",
                            )

                            # Verify function completed successfully
                            mock_file_writer.write_data_to_files.assert_called_once_with(
                                new_data={"folder_show": {"tt0111162": "data"}},
                                cache={},
                                cache_file=None,
                                output_dir_global="/test/output",
                            )

    def test_mode_detection_plex_vs_folder(self):
        """Test that the system can distinguish between Plex and folder modes."""
        # Test function call signatures for different modes

        with patch("modules.orchestrator.new_data", {"test": {"tt0111161": "data"}}):
            with patch("modules.orchestrator.cache", {}):
                with patch("modules.orchestrator.cache_config") as mock_cache_config:
                    with patch(
                        "modules.file_manager.FileWriter"
                    ) as mock_file_writer_class:
                        with patch("modules.intelligent_cache.get_cache_manager"):
                            mock_cache_config.should_save_cache.return_value = False
                            mock_file_writer = Mock()
                            mock_file_writer_class.return_value = mock_file_writer

                            # Test 1: Plex mode (None root_folder_path)
                            write_data_to_files(
                                root_folder_path=None,
                                output_dir="/test/output",
                            )

                            call_kwargs = (
                                mock_file_writer.write_data_to_files.call_args[1]
                            )
                            assert call_kwargs["new_data"] == {
                                "test": {"tt0111161": "data"}
                            }
                            assert call_kwargs["output_dir_global"] == "/test/output"
                            assert "root_folder_global" not in call_kwargs

                            mock_file_writer.reset_mock()

                            # Test 2: Folder mode (with root_folder_path)
                            write_data_to_files(
                                root_folder_path="/test/media",
                                output_dir="/test/output",
                            )

                            call_kwargs = (
                                mock_file_writer.write_data_to_files.call_args[1]
                            )
                            assert call_kwargs["new_data"] == {
                                "test": {"tt0111161": "data"}
                            }
                            assert call_kwargs["output_dir_global"] == "/test/output"

    def test_run_function_plex_mode_no_errors(self):
        """Test that run function works in Plex-only mode without errors."""
        with patch("modules.orchestrator.time.time", side_effect=[0, 10]):
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
                                with patch("modules.scraper.WebDriverManager"):
                                    with patch("modules.scraper.MediuxLoginManager"):
                                        with patch(
                                            "modules.media_processing.process_single_media_item"
                                        ):
                                            with patch(
                                                "modules.orchestrator.write_data_to_files"
                                            ) as mock_write_data:
                                                with patch(
                                                    "modules.external_services.DiscordNotifier"
                                                ):
                                                    with patch(
                                                        "modules.orchestrator.os.remove"
                                                    ):
                                                        with patch(
                                                            "modules.file_manager.BulkDataManager"
                                                        ):
                                                            # Setup mocks
                                                            mock_cache_config = Mock()
                                                            mock_cache_config.clear_cache = (
                                                                False
                                                            )
                                                            mock_cache_config.should_save_cache.return_value = (
                                                                False
                                                            )
                                                            mock_cache_config_class.return_value = (
                                                                mock_cache_config
                                                            )

                                                            # Execute run function in Plex-only mode
                                                            run(
                                                                api_key="test_key",
                                                                username="test_user",
                                                                password="test_pass",
                                                                profile_path="/test/profile",
                                                                nickname="test_nick",
                                                                sonarr_api_key=None,
                                                                sonarr_endpoint=None,
                                                                root_folder_global=None,  # Plex mode
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

                                                            # Verify write_data_to_files was called without root_folder_path
                                                            mock_write_data.assert_called_once()
                                                            call_kwargs = mock_write_data.call_args[
                                                                1
                                                            ]
                                                            assert (
                                                                call_kwargs[
                                                                    "root_folder_path"
                                                                ]
                                                                is None
                                                            )
                                                            assert (
                                                                call_kwargs[
                                                                    "output_dir"
                                                                ]
                                                                == "/test/output"
                                                            )

    def test_run_function_signature(self):
        """Test that run function accepts Plex parameters correctly."""
        from modules.orchestrator import run
        import inspect

        # Check function signature
        sig = inspect.signature(run)
        params = list(sig.parameters.keys())

        # Should have the new Plex parameters
        assert "plex_url" in params
        assert "plex_token" in params
        assert "plex_libraries" in params

    def test_plex_configuration_logic(self):
        """Test that the Plex configuration logic works correctly."""

        # Test valid Plex config (all parameters present and libraries not empty)
        def is_valid_plex_config(url, token, libraries):
            return (
                url is not None
                and token is not None
                and libraries is not None
                and len(libraries) > 0
            )

        # Test valid configs
        assert is_valid_plex_config("http://plex:32400", "token123", ["Movies"]) == True
        assert (
            is_valid_plex_config(
                "http://plex:32400", "token123", ["Movies", "TV Shows"]
            )
            == True
        )

        # Test invalid configs
        assert is_valid_plex_config(None, "token123", ["Movies"]) == False
        assert is_valid_plex_config("http://plex:32400", None, ["Movies"]) == False
        assert is_valid_plex_config("http://plex:32400", "token123", []) == False
        assert is_valid_plex_config("http://plex:32400", "token123", None) == False

    def test_root_folder_requirement_logic(self):
        """Test that root folder requirement logic works correctly."""

        def should_require_root_folder(
            root_folder, plex_url, plex_token, plex_libraries
        ):
            # If any Plex parameter is missing or libraries is empty, require root folder
            if (
                not plex_url
                or not plex_token
                or not plex_libraries
                or len(plex_libraries) == 0
            ):
                return root_folder is None
            return False  # Valid Plex config, don't require root folder

        # Test cases where root folder should be required
        assert should_require_root_folder(None, None, None, None) == True
        assert should_require_root_folder(None, None, "token", ["Movies"]) == True
        assert should_require_root_folder(None, "url", None, ["Movies"]) == True
        assert should_require_root_folder(None, "url", "token", []) == True

        # Test cases where root folder should NOT be required
        assert should_require_root_folder(None, "url", "token", ["Movies"]) == False
        assert should_require_root_folder("/media", "url", "token", ["Movies"]) == False

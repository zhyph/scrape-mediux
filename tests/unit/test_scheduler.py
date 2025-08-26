"""
Unit tests for scheduler.py module.
"""

import os
from datetime import datetime
from unittest.mock import Mock, patch

import pytest
from freezegun import freeze_time

from modules.scheduler import schedule_run, write_data_to_files


class TestScheduleRun:
    """Test cases for schedule_run function."""

    def test_schedule_run_initialization(self, caplog):
        """Test that schedule_run initializes correctly and logs expected messages."""
        # Set logging level to capture INFO messages
        import logging

        logger = logging.getLogger("modules.scheduler")
        logger.setLevel(logging.INFO)

        with patch(
            "modules.scheduler.sleep", side_effect=InterruptedError("Stop loop")
        ):
            with patch("modules.scheduler.croniter") as mock_croniter_class:
                with patch("modules.orchestrator.run") as mock_run:
                    with patch(
                        "modules.scheduler.write_data_to_files"
                    ) as mock_write_files:
                        # Setup croniter mock
                        mock_croniter = Mock()
                        mock_croniter_class.return_value = mock_croniter
                        mock_croniter.get_next.return_value = datetime(
                            2024, 1, 1, 12, 0, 0
                        )

                        with freeze_time("2024-01-01 12:00:00"):
                            with pytest.raises(InterruptedError):
                                schedule_run(
                                    cron_expression="0 12 * * *",
                                    args_dict={"test": "args"},
                                )

        # Check that initialization logs were made
        assert "Scheduling script with cron expression: 0 12 * * *" in caplog.text
        assert "Current time:" in caplog.text
        assert "Environment Timezone:" in caplog.text

    def test_schedule_run_execution_on_time(self, caplog):
        """Test that schedule_run executes when it's time."""
        # Set logging level to capture INFO messages
        import logging

        logger = logging.getLogger("modules.scheduler")
        logger.setLevel(logging.INFO)

        with patch(
            "modules.scheduler.sleep", side_effect=[None, InterruptedError("Stop loop")]
        ):
            with patch("modules.scheduler.croniter") as mock_croniter_class:
                with patch("modules.orchestrator.run") as mock_run:
                    with patch(
                        "modules.scheduler.write_data_to_files"
                    ) as mock_write_files:
                        # Setup croniter mock with side_effect for multiple calls
                        mock_croniter = Mock()
                        mock_croniter_class.return_value = mock_croniter

                        # First call returns past time (should execute), second call returns future time
                        past_time = datetime(
                            2024, 1, 1, 11, 0, 0
                        )  # Before current time
                        future_time = datetime(
                            2024, 1, 1, 13, 0, 0
                        )  # After current time
                        mock_croniter.get_next.side_effect = [past_time, future_time]

                        with freeze_time("2024-01-01 12:00:00"):
                            with pytest.raises(InterruptedError):
                                schedule_run(
                                    cron_expression="0 12 * * *",
                                    args_dict={"test": "args"},
                                )

        # Check that execution occurred
        assert "Scheduled run started..." in caplog.text
        mock_run.assert_called_once_with(test="args")
        mock_write_files.assert_called_once()

    def test_schedule_run_execution_error_handling(self, caplog):
        """Test that schedule_run handles execution errors gracefully."""
        # Set logging level to capture ERROR messages
        import logging

        logger = logging.getLogger("modules.scheduler")
        logger.setLevel(logging.INFO)

        with patch(
            "modules.scheduler.sleep", side_effect=InterruptedError("Stop loop")
        ):
            with patch("modules.scheduler.croniter") as mock_croniter_class:
                with patch(
                    "modules.orchestrator.run", side_effect=Exception("Test error")
                ) as mock_run:
                    with patch(
                        "modules.scheduler.write_data_to_files"
                    ) as mock_write_files:
                        # Setup croniter mock with side_effect for multiple calls
                        mock_croniter = Mock()
                        mock_croniter_class.return_value = mock_croniter

                        # First call returns past time (should execute once), second call returns future time
                        past_time = datetime(
                            2024, 1, 1, 11, 0, 0
                        )  # Before current time
                        future_time = datetime(
                            2024, 1, 1, 13, 0, 0
                        )  # After current time
                        mock_croniter.get_next.side_effect = [past_time, future_time]

                        with freeze_time("2024-01-01 12:00:00"):
                            with pytest.raises(InterruptedError):
                                schedule_run(
                                    cron_expression="0 12 * * *",
                                    args_dict={"test": "args"},
                                )

        # Check that error was logged and write_data_to_files was NOT called due to error
        assert "Error during scheduled run: Test error" in caplog.text
        mock_run.assert_called_once_with(test="args")
        mock_write_files.assert_not_called()  # Should not be called when run() raises exception

    def test_schedule_run_no_execution_before_time(self, caplog):
        """Test that schedule_run doesn't execute before scheduled time."""
        # Set logging level to capture INFO messages
        import logging

        logger = logging.getLogger("modules.scheduler")
        logger.setLevel(logging.INFO)

        with patch(
            "modules.scheduler.sleep", side_effect=InterruptedError("Stop loop")
        ):
            with patch("modules.scheduler.croniter") as mock_croniter_class:
                with patch("modules.orchestrator.run") as mock_run:
                    with patch(
                        "modules.scheduler.write_data_to_files"
                    ) as mock_write_files:
                        # Setup croniter mock
                        mock_croniter = Mock()
                        mock_croniter_class.return_value = mock_croniter

                        # Return future time (should not execute)
                        future_time = datetime(
                            2024, 1, 1, 13, 0, 0
                        )  # After current time
                        mock_croniter.get_next.return_value = future_time

                        with freeze_time("2024-01-01 12:00:00"):
                            with pytest.raises(InterruptedError):
                                schedule_run(
                                    cron_expression="0 13 * * *",
                                    args_dict={"test": "args"},
                                )

        # Check that execution did not occur
        assert "Scheduled run started..." not in caplog.text
        mock_run.assert_not_called()
        mock_write_files.assert_not_called()

    def test_schedule_run_with_timezone_env_var(self, caplog):
        """Test that schedule_run logs timezone from environment variable."""
        # Set logging level to capture INFO messages
        import logging

        logger = logging.getLogger("modules.scheduler")
        logger.setLevel(logging.INFO)

        with patch.dict(os.environ, {"TZ": "America/New_York"}):
            with patch(
                "modules.scheduler.sleep", side_effect=InterruptedError("Stop loop")
            ):
                with patch("modules.scheduler.croniter") as mock_croniter_class:
                    with freeze_time("2024-01-01 12:00:00"):
                        # Setup croniter mock with proper datetime
                        mock_croniter = Mock()
                        mock_croniter_class.return_value = mock_croniter
                        mock_croniter.get_next.return_value = datetime(
                            2024, 1, 1, 12, 0, 0
                        )

                        with pytest.raises(InterruptedError):
                            schedule_run(
                                cron_expression="0 12 * * *", args_dict={"test": "args"}
                            )

        assert "America/New_York" in caplog.text


class TestWriteDataToFiles:
    """Test cases for write_data_to_files function."""

    def test_write_data_to_files_success(self):
        """Test successful data writing."""
        with patch("modules.orchestrator.new_data", {"test": "data"}):
            with patch("modules.orchestrator.cache", {"cache": "data"}):
                with patch("modules.orchestrator.root_folder_global", "/test/root"):
                    with patch(
                        "modules.orchestrator.output_dir_global", "/test/output"
                    ):
                        with patch(
                            "modules.orchestrator.cache_config"
                        ) as mock_cache_config:
                            with patch("modules.config.validate_path") as mock_validate:
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
                                        mock_file_writer_class.return_value = (
                                            mock_file_writer
                                        )

                                        mock_cache_manager = Mock()
                                        mock_get_cache.return_value = mock_cache_manager

                                        # Execute function
                                        write_data_to_files()

                                        # Verify calls
                                        mock_validate.assert_called_once_with(
                                            path="/test/root", description="Root folder"
                                        )
                                        mock_cache_manager.save_cache.assert_called_once_with(
                                            "/cache/intelligent_cache.pkl"
                                        )
                                        mock_file_writer.write_data_to_files.assert_called_once_with(
                                            new_data={"test": "data"},
                                            root_folder_global="/test/root",
                                            cache={"cache": "data"},
                                            cache_file="/cache/tmdb_cache.pkl",
                                            output_dir_global="/test/output",
                                        )

    def test_write_data_to_files_no_root_folder(self, caplog):
        """Test that function exits early when no root folder is set."""
        with patch("modules.orchestrator.root_folder_global", None):
            write_data_to_files()

        assert "Root folder is not set. Cannot write data." in caplog.text

    def test_write_data_to_files_cache_disabled(self):
        """Test data writing with cache disabled."""
        with patch("modules.orchestrator.new_data", {"test": "data"}):
            with patch("modules.orchestrator.cache", {"cache": "data"}):
                with patch("modules.orchestrator.root_folder_global", "/test/root"):
                    with patch(
                        "modules.orchestrator.output_dir_global", "/test/output"
                    ):
                        with patch(
                            "modules.orchestrator.cache_config"
                        ) as mock_cache_config:
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
                                        mock_file_writer_class.return_value = (
                                            mock_file_writer
                                        )

                                        # Execute function
                                        write_data_to_files()

                                        # Verify cache-related calls were not made
                                        mock_get_cache.assert_not_called()
                                        mock_file_writer.write_data_to_files.assert_called_once_with(
                                            new_data={"test": "data"},
                                            root_folder_global="/test/root",
                                            cache={},  # Empty cache when disabled
                                            cache_file=None,  # No cache file when disabled
                                            output_dir_global="/test/output",
                                        )

    def test_write_data_to_files_with_empty_data(self):
        """Test data writing with empty data."""
        with patch("modules.orchestrator.new_data", {}):
            with patch("modules.orchestrator.cache", {}):
                with patch("modules.orchestrator.root_folder_global", "/test/root"):
                    with patch(
                        "modules.orchestrator.output_dir_global", "/test/output"
                    ):
                        with patch(
                            "modules.orchestrator.cache_config"
                        ) as mock_cache_config:
                            with patch("modules.config.validate_path"):
                                with patch(
                                    "modules.file_manager.FileWriter"
                                ) as mock_file_writer_class:
                                    mock_cache_config.should_save_cache.return_value = (
                                        False
                                    )
                                    mock_file_writer = Mock()
                                    mock_file_writer_class.return_value = (
                                        mock_file_writer
                                    )

                                    write_data_to_files()

                                    mock_file_writer.write_data_to_files.assert_called_once_with(
                                        new_data={},
                                        root_folder_global="/test/root",
                                        cache={},
                                        cache_file=None,
                                        output_dir_global="/test/output",
                                    )

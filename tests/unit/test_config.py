"""
Tests for config.py module.
"""

import json
import pytest
import tempfile
import os
from unittest.mock import patch, Mock, MagicMock
from argparse import Namespace

from modules.config import (
    ConfigManager,
    validate_path,
    _validate_single_path,
    yaml_parser,
)


class TestConfigManager:
    """Test cases for ConfigManager class."""

    def test_init(self):
        """Test ConfigManager initialization."""
        config_manager = ConfigManager()
        assert config_manager.config_path == "./config.json"
        assert hasattr(config_manager, "logger")

    def test_load_config_file_success(self, temp_dir, sample_config):
        """Test successful config file loading."""
        config_file = os.path.join(temp_dir, "config.json")
        with open(config_file, "w") as f:
            json.dump(sample_config, f)

        config_manager = ConfigManager()
        result = config_manager.load_config_file(config_file)

        assert result == sample_config

    def test_load_config_file_not_found(self):
        """Test config file not found error."""
        config_manager = ConfigManager()

        with pytest.raises(FileNotFoundError, match="Configuration file not found"):
            config_manager.load_config_file("/nonexistent/config.json")

    def test_load_config_file_invalid_json(self, temp_dir):
        """Test invalid JSON config file."""
        config_file = os.path.join(temp_dir, "config.json")
        with open(config_file, "w") as f:
            f.write("invalid json content {")

        config_manager = ConfigManager()

        with pytest.raises(json.JSONDecodeError):
            config_manager.load_config_file(config_file)

    def test_load_config_file_with_directory_path(self, temp_dir, sample_config):
        """Test loading config from directory path."""
        # Create config.json in temp directory
        config_file = os.path.join(temp_dir, "config.json")
        with open(config_file, "w") as f:
            json.dump(sample_config, f)

        config_manager = ConfigManager()
        result = config_manager.load_config_file(temp_dir)

        assert result == sample_config

    def test_resolve_config_value_priority_command_line(self, sample_config):
        """Test command line argument priority."""
        config_manager = ConfigManager()

        result = config_manager._resolve_config_value(
            arg_val="cli_value",
            env_var_name="TEST_VAR",
            config_key="test_key",
            file_config=sample_config,
            default_val="default",
        )

        assert result == "cli_value"

    def test_resolve_config_value_priority_env_var(self, sample_config):
        """Test environment variable priority."""
        config_manager = ConfigManager()

        with patch.dict(os.environ, {"TEST_VAR": "env_value"}):
            result = config_manager._resolve_config_value(
                arg_val=None,
                env_var_name="TEST_VAR",
                config_key="test_key",
                file_config=sample_config,
                default_val="default",
            )

            assert result == "env_value"

    def test_resolve_config_value_priority_file_config(self, sample_config):
        """Test file config priority."""
        config_manager = ConfigManager()

        result = config_manager._resolve_config_value(
            arg_val=None,
            env_var_name="NONEXISTENT_VAR",
            config_key="api_key",
            file_config=sample_config,
            default_val="default",
        )

        assert result == sample_config["api_key"]

    def test_resolve_config_value_priority_default(self, sample_config):
        """Test default value priority."""
        config_manager = ConfigManager()

        result = config_manager._resolve_config_value(
            arg_val=None,
            env_var_name="NONEXISTENT_VAR",
            config_key="nonexistent_key",
            file_config=sample_config,
            default_val="default_value",
        )

        assert result == "default_value"

    def test_resolve_config_value_boolean_true(self, sample_config):
        """Test boolean resolution with true values."""
        config_manager = ConfigManager()

        for true_val in ["true", "1", "yes"]:
            with patch.dict(os.environ, {"TEST_VAR": true_val}):
                result = config_manager._resolve_config_value(
                    arg_val=None,
                    env_var_name="TEST_VAR",
                    config_key="nonexistent_key",
                    file_config=sample_config,
                    default_val=False,
                    is_bool=True,
                )
                assert result is True

    def test_resolve_config_value_boolean_false(self, sample_config):
        """Test boolean resolution with false values."""
        config_manager = ConfigManager()

        for false_val in ["false", "0", "no"]:
            with patch.dict(os.environ, {"TEST_VAR": false_val}):
                result = config_manager._resolve_config_value(
                    arg_val=None,
                    env_var_name="TEST_VAR",
                    config_key="nonexistent_key",
                    file_config=sample_config,
                    default_val=True,
                    is_bool=True,
                )
                assert result is False

    def test_resolve_config_value_list_env(self, sample_config):
        """Test list resolution from environment variable."""
        config_manager = ConfigManager()

        with patch.dict(os.environ, {"TEST_VAR": "item1,item2,item3"}):
            result = config_manager._resolve_config_value(
                arg_val=None,
                env_var_name="TEST_VAR",
                config_key="nonexistent_key",
                file_config=sample_config,
                is_list=True,
            )

            assert result == ["item1", "item2", "item3"]

    def test_resolve_config_value_list_empty_env(self, sample_config):
        """Test list resolution from empty environment variable."""
        config_manager = ConfigManager()

        with patch.dict(os.environ, {"TEST_VAR": ""}):
            result = config_manager._resolve_config_value(
                arg_val=None,
                env_var_name="TEST_VAR",
                config_key="nonexistent_key",
                file_config=sample_config,
                is_list=True,
                default_val=[],
            )

            assert result == []

    @patch("colorama.init")
    @patch("logging.getLogger")
    @patch("logging.FileHandler")
    @patch("logging.StreamHandler")
    @patch("sys.stdout", new_callable=lambda: Mock())
    def test_setup_logging(
        self,
        mock_stdout,
        mock_stream_handler,
        mock_file_handler,
        mock_get_logger,
        mock_colorama_init,
    ):
        """Test logging setup."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        config_manager = ConfigManager()
        config_manager.setup_logging(log_level="DEBUG")

        # Verify colorama.init was called
        mock_colorama_init.assert_called_once_with(autoreset=True)

    def test_create_argument_parser(self):
        """Test argument parser creation."""
        config_manager = ConfigManager()
        parser = config_manager.create_argument_parser()

        assert parser is not None
        assert hasattr(parser, "parse_args")

        # Test parsing some basic arguments
        args = parser.parse_args(["--api_key", "test_key"])
        assert args.api_key == "test_key"

    def test_parse_arguments_and_load_config_minimal(self, temp_dir, sample_config):
        """Test minimal argument parsing and config loading."""
        # Create minimal config
        minimal_config = {
            "api_key": "test_key",
            "username": "test_user",
            "password": "test_pass",
            "nickname": "test_nick",
        }
        config_file = os.path.join(temp_dir, "config.json")
        with open(config_file, "w") as f:
            json.dump(minimal_config, f)

        config_manager = ConfigManager()

        with patch("sys.argv", ["main.py", "--config_path", config_file]):
            result = config_manager.parse_arguments_and_load_config()

        assert result is not None
        assert result["api_key"] == "test_key"
        assert result["username"] == "test_user"

    def test_parse_arguments_and_load_config_with_args_override(
        self, temp_dir, sample_config
    ):
        """Test argument parsing with command line overrides."""
        config_file = os.path.join(temp_dir, "config.json")
        with open(config_file, "w") as f:
            json.dump(sample_config, f)

        config_manager = ConfigManager()

        with patch(
            "sys.argv",
            ["main.py", "--config_path", config_file, "--api_key", "override_key"],
        ):
            result = config_manager.parse_arguments_and_load_config()

        assert result["api_key"] == "override_key"  # Should override file config


class TestValidatePath:
    """Test cases for validate_path function."""

    def test_validate_path_single_valid(self, temp_dir):
        """Test validating a single valid path."""
        # temp_dir is a valid directory
        validate_path(temp_dir, "Test directory")

        # No exception should be raised

    def test_validate_path_single_invalid(self):
        """Test validating a single invalid path."""
        with pytest.raises(FileNotFoundError, match="does not exist"):
            validate_path("/nonexistent/path", "Test path")

    def test_validate_path_single_not_directory(self, temp_dir):
        """Test validating a path that exists but is not a directory."""
        file_path = os.path.join(temp_dir, "test_file.txt")
        with open(file_path, "w") as f:
            f.write("test")

        with pytest.raises(NotADirectoryError, match="is not a directory"):
            validate_path(file_path, "Test file")

    def test_validate_path_list_valid(self, temp_dir):
        """Test validating a list of valid paths."""
        paths = [temp_dir, temp_dir]  # Same directory twice
        validate_path(paths, "Test directories")

        # No exception should be raised

    def test_validate_path_list_with_invalid(self, temp_dir):
        """Test validating a list with an invalid path."""
        paths = [temp_dir, "/nonexistent/path"]

        with pytest.raises(FileNotFoundError, match="does not exist"):
            validate_path(paths, "Test paths")


class TestValidateSinglePath:
    """Test cases for _validate_single_path function."""

    def test_validate_single_path_empty_string(self):
        """Test validating an empty string path."""
        with pytest.raises(ValueError, match="is not set"):
            _validate_single_path("", "Test path")

    def test_validate_single_path_valid(self, temp_dir):
        """Test validating a valid path."""
        _validate_single_path(temp_dir, "Test directory")

        # No exception should be raised


class TestYAMLParser:
    """Test cases for global YAML parser instance."""

    def test_yaml_parser_exists(self):
        """Test that yaml_parser is available."""
        assert yaml_parser is not None

    def test_yaml_parser_allow_duplicate_keys(self):
        """Test that yaml_parser allows duplicate keys."""
        assert hasattr(yaml_parser, "allow_duplicate_keys")
        assert yaml_parser.allow_duplicate_keys is True

    def test_yaml_parser_basic_functionality(self):
        """Test basic YAML parsing functionality."""
        yaml_content = """
        test_key: test_value
        test_number: 42
        test_list:
          - item1
          - item2
        """

        result = yaml_parser.load(yaml_content)
        assert result is not None
        assert result["test_key"] == "test_value"
        assert result["test_number"] == 42
        assert result["test_list"] == ["item1", "item2"]

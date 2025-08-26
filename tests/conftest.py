"""
Shared test fixtures and utilities for Mediux Scraper tests.
"""

import itertools
import json
import tempfile
from unittest.mock import Mock

import pytest


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield tmp_dir


@pytest.fixture
def mock_logger():
    """Mock logger for testing."""
    return Mock()


@pytest.fixture
def sample_config():
    """Sample configuration for testing."""
    return {
        "api_key": "test_api_key",
        "username": "test_user",
        "password": "test_pass",
        "nickname": "test_nick",
        "profile_path": "/test/profile",
        "sonarr_api_key": "test_sonarr_key",
        "sonarr_endpoint": "http://test-sonarr:8989",
        "discord_webhook_url": "https://discord.com/api/webhooks/test",
        "plex_url": "http://test-plex:32400",
        "plex_token": "test_plex_token",
        "plex_libraries": ["Movies", "TV Shows"],
        "root_folder": "/test/media",
        "folders": ["folder1", "folder2"],
        "headless": True,
        "process_all": False,
        "retry_on_yaml_failure": False,
        "preferred_users": ["user1", "user2"],
        "excluded_users": ["bad_user"],
        "disable_season_fix": False,
        "remove_paths": ["*.url_background"],
        "disable_cache": False,
        "clear_cache": False,
        "cache_dir": "./out",
        "config_path": "/config",
        "root_folder_val": ["/test/media"],
        "selected_folders": [],
        "output_dir_val": "/test/output",
        "TZ": "UTC",
    }


@pytest.fixture
def sample_yaml_data():
    """Sample YAML data for testing."""
    return {
        "tt0111161": {
            "title": "The Shawshank Redemption",
            "year": 1994,
            "seasons": {
                "1": {
                    "episodes": {
                        "1": {
                            "title": "Episode 1",
                            "url_poster": "https://example.com/poster.jpg",
                        }
                    }
                }
            },
        }
    }


@pytest.fixture
def mock_cache_manager():
    """Mock cache manager for testing."""
    cache_manager = Mock()
    cache_manager.get_tmdb_id.return_value = None
    cache_manager.set_tmdb_id.return_value = None
    cache_manager.get_sonarr_status.return_value = None
    cache_manager.set_sonarr_status.return_value = None
    cache_manager.get_yaml_data.return_value = None
    cache_manager.set_yaml_data.return_value = None
    cache_manager.get_media_ids.return_value = None
    cache_manager.set_media_ids.return_value = None
    cache_manager.get_cache_stats.return_value = {}
    cache_manager.cleanup_expired.return_value = None
    cache_manager.clear_cache.return_value = None
    cache_manager.save_cache.return_value = None
    cache_manager.load_cache.return_value = None
    return cache_manager


@pytest.fixture
def mock_webdriver():
    """Mock Selenium WebDriver for testing."""
    driver = Mock()
    driver.get.return_value = None
    driver.quit.return_value = None
    driver.find_elements.return_value = []
    driver.find_element.return_value = Mock()
    driver.execute_script.return_value = None

    # Mock WebElement
    mock_element = Mock()
    mock_element.click.return_value = None
    mock_element.get_attribute.return_value = "test_yaml_data"
    mock_element.text = "test text"
    driver.find_element.return_value = mock_element

    return driver


@pytest.fixture
def mock_response():
    """Mock HTTP response for testing."""
    response = Mock()
    response.status_code = 200
    response.json.return_value = {"test": "data"}
    response.raise_for_status.return_value = None
    return response


@pytest.fixture(autouse=True)
def cleanup_temp_files():
    """Clean up temporary files created during tests."""
    yield
    # Cleanup logic if needed


def create_temp_file(content, suffix=".json"):
    """Create a temporary file with given content."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False) as f:
        f.write(content)
        return f.name


def create_temp_config(config_data):
    """Create a temporary config file."""
    return create_temp_file(json.dumps(config_data), ".json")


def create_temp_yaml(yaml_content):
    """Create a temporary YAML file."""


@pytest.fixture
def mock_plex_client():
    """Mock PlexClient for testing."""
    plex_client = Mock()
    plex_client.get_media_ids_from_plex.return_value = ["tt0111161", "tt0068646"]
    plex_client.list_available_libraries.return_value = ["Movies", "TV Shows"]
    return plex_client


@pytest.fixture
def mock_discovery_service():
    """Mock MediaDiscoveryService for testing."""
    discovery_service = Mock()
    discovery_service.get_media_ids_from_folder.return_value = [
        "tt0111161",
        "tt0068646",
    ]
    return discovery_service


@pytest.fixture
def mock_yaml_parser():
    """Mock YAML parser for testing."""
    parser = Mock()
    parser.load.return_value = {"tt0111161": {"title": "Test Movie"}}
    parser.dump.return_value = None
    return parser


@pytest.fixture
def mock_time():
    """Mock time.time() with sufficient values for logging operations."""
    # Generate incrementing timestamps starting from 1000.0
    return itertools.count(1000.0, 10.0)

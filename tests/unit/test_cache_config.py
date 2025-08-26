"""
Tests for cache_config.py module.
"""

import os

from modules.cache_config import CacheConfig, cache_config


class TestCacheConfig:
    """Test cases for CacheConfig class."""

    def test_init_default_values(self):
        """Test CacheConfig initialization with default values."""
        config = CacheConfig()
        assert config.disable_cache is False
        assert config.clear_cache is False
        assert config.cache_dir == "./out"

    def test_init_custom_values(self):
        """Test CacheConfig initialization with custom values."""
        config = CacheConfig(
            disable_cache=True, clear_cache=True, cache_dir="/custom/cache"
        )
        assert config.disable_cache is True
        assert config.clear_cache is True
        assert config.cache_dir == "/custom/cache"

    def test_get_cache_file_path(self):
        """Test get_cache_file_path method."""
        config = CacheConfig(cache_dir="/test/cache")
        result = config.get_cache_file_path("test.pkl")
        expected = os.path.join("/test/cache", "test.pkl")
        assert result == expected

    def test_should_load_cache_enabled(self):
        """Test should_load_cache when cache is enabled."""
        config = CacheConfig(disable_cache=False)
        assert config.should_load_cache() is True

    def test_should_load_cache_disabled(self):
        """Test should_load_cache when cache is disabled."""
        config = CacheConfig(disable_cache=True)
        assert config.should_load_cache() is False

    def test_should_save_cache_enabled(self):
        """Test should_save_cache when cache is enabled."""
        config = CacheConfig(disable_cache=False)
        assert config.should_save_cache() is True

    def test_should_save_cache_disabled(self):
        """Test should_save_cache when cache is disabled."""
        config = CacheConfig(disable_cache=True)
        assert config.should_save_cache() is False


class TestGlobalCacheConfig:
    """Test cases for global cache_config instance."""

    def test_global_instance_exists(self):
        """Test that global cache_config instance exists."""
        assert hasattr(cache_config, "disable_cache")
        assert hasattr(cache_config, "clear_cache")
        assert hasattr(cache_config, "cache_dir")

    def test_global_instance_methods(self):
        """Test that global instance has required methods."""
        assert hasattr(cache_config, "get_cache_file_path")
        assert hasattr(cache_config, "should_load_cache")
        assert hasattr(cache_config, "should_save_cache")

    def test_global_instance_default_values(self):
        """Test global instance default values."""
        assert cache_config.disable_cache is False
        assert cache_config.clear_cache is False
        assert cache_config.cache_dir == "./out"

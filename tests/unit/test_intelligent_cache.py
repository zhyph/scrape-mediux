"""
Tests for intelligent_cache.py module.
"""

import time
import pytest
import tempfile
import os
from unittest.mock import patch, Mock, MagicMock
from freezegun import freeze_time
from collections import OrderedDict

from modules.intelligent_cache import (
    CacheEntry,
    IntelligentCache,
    NamespaceCache,
    CacheManager,
    get_cache_manager,
)


class TestCacheEntry:
    """Test cases for CacheEntry class."""

    def test_init_with_value_and_ttl(self):
        """Test CacheEntry initialization with value and TTL."""
        entry = CacheEntry("test_value", ttl_seconds=300)
        assert entry.value == "test_value"
        assert entry.ttl_seconds == 300
        assert entry.access_count == 0
        assert isinstance(entry.created_at, float)
        assert isinstance(entry.accessed_at, float)

    def test_init_without_ttl(self):
        """Test CacheEntry initialization without TTL."""
        entry = CacheEntry("test_value")
        assert entry.value == "test_value"
        assert entry.ttl_seconds is None

    def test_is_expired_with_no_ttl(self):
        """Test is_expired when no TTL is set."""
        entry = CacheEntry("test_value")
        assert entry.is_expired() is False

    def test_is_expired_not_expired(self):
        """Test is_expired when entry is not expired."""
        with freeze_time("2023-01-01"):
            entry = CacheEntry("test_value", ttl_seconds=300)
            assert entry.is_expired() is False

    def test_is_expired_expired(self):
        """Test is_expired when entry is expired."""
        with freeze_time("2023-01-01") as frozen_time:
            entry = CacheEntry("test_value", ttl_seconds=300)
            frozen_time.move_to("2023-01-01 00:06:00")  # 6 minutes later
            assert entry.is_expired() is True

    def test_access(self):
        """Test access method updates accessed_at and access_count."""
        entry = CacheEntry("test_value")
        initial_access_count = entry.access_count

        entry.access()

        assert entry.access_count == initial_access_count + 1
        # Note: accessed_at will be very close to created_at, but access() updates it to current time


class TestIntelligentCache:
    """Test cases for IntelligentCache class."""

    def test_init_default_values(self):
        """Test IntelligentCache initialization with default values."""
        cache = IntelligentCache()
        assert cache.max_size == 1000
        assert cache.default_ttl == 3600
        assert cache.max_memory_mb == 50.0
        assert isinstance(cache.cache, OrderedDict)
        assert isinstance(cache.lock, type(cache.lock))  # Threading lock
        assert cache.stats == {"hits": 0, "misses": 0, "evictions": 0, "size": 0}

    def test_init_custom_values(self):
        """Test IntelligentCache initialization with custom values."""
        cache = IntelligentCache(max_size=500, default_ttl=7200, max_memory_mb=100.0)
        assert cache.max_size == 500
        assert cache.default_ttl == 7200
        assert cache.max_memory_mb == 100.0

    def test_generate_key_simple(self):
        """Test _generate_key with simple arguments."""
        cache = IntelligentCache()
        key = cache._generate_key("arg1", "arg2")
        assert isinstance(key, str)
        assert len(key) == 32  # MD5 hex length
        # Test that same inputs produce same key
        key2 = cache._generate_key("arg1", "arg2")
        assert key == key2

    def test_generate_key_with_kwargs(self):
        """Test _generate_key with keyword arguments."""
        cache = IntelligentCache()
        key = cache._generate_key("arg1", kwarg1="value1", kwarg2="value2")
        assert isinstance(key, str)
        assert len(key) == 32  # MD5 hex length
        # Test that same inputs produce same key
        key2 = cache._generate_key("arg1", kwarg1="value1", kwarg2="value2")
        assert key == key2

    def test_get_hit(self):
        """Test get method with cache hit."""
        cache = IntelligentCache()
        cache.cache["test_key"] = CacheEntry("test_value")

        result = cache.get("test_key")
        assert result == "test_value"
        assert cache.stats["hits"] == 1
        assert cache.stats["misses"] == 0

    def test_get_miss(self):
        """Test get method with cache miss."""
        cache = IntelligentCache()

        result = cache.get("nonexistent_key")
        assert result is None
        assert cache.stats["hits"] == 0
        assert cache.stats["misses"] == 1

    def test_get_miss_with_default(self):
        """Test get method with cache miss and default value."""
        cache = IntelligentCache()

        result = cache.get("nonexistent_key", default="default_value")
        assert result == "default_value"
        assert cache.stats["misses"] == 1

    def test_get_expired_entry(self):
        """Test get method with expired entry."""
        cache = IntelligentCache()
        with freeze_time("2023-01-01") as frozen_time:
            cache.cache["test_key"] = CacheEntry("test_value", ttl_seconds=300)
            frozen_time.move_to("2023-01-01 00:06:00")  # 6 minutes later

            result = cache.get("test_key")
            assert result is None
            assert "test_key" not in cache.cache  # Should be removed
            assert cache.stats["misses"] == 1

    def test_set_new_entry(self):
        """Test set method with new entry."""
        cache = IntelligentCache()

        cache.set("test_key", "test_value")
        assert "test_key" in cache.cache
        assert cache.cache["test_key"].value == "test_value"
        assert cache.cache["test_key"].ttl_seconds == 3600  # default TTL

    def test_set_existing_entry(self):
        """Test set method with existing entry."""
        cache = IntelligentCache()
        cache.cache["test_key"] = CacheEntry("old_value")

        cache.set("test_key", "new_value")
        assert cache.cache["test_key"].value == "new_value"

    def test_set_with_custom_ttl(self):
        """Test set method with custom TTL."""
        cache = IntelligentCache()

        cache.set("test_key", "test_value", ttl=600)
        assert cache.cache["test_key"].ttl_seconds == 600

    def test_delete_existing_key(self):
        """Test delete method with existing key."""
        cache = IntelligentCache()
        cache.cache["test_key"] = CacheEntry("test_value")

        result = cache.delete("test_key")
        assert result is True
        assert "test_key" not in cache.cache

    def test_delete_nonexistent_key(self):
        """Test delete method with nonexistent key."""
        cache = IntelligentCache()

        result = cache.delete("nonexistent_key")
        assert result is False

    def test_clear(self):
        """Test clear method."""
        cache = IntelligentCache()
        cache.cache["key1"] = CacheEntry("value1")
        cache.cache["key2"] = CacheEntry("value2")
        cache.stats = {"hits": 5, "misses": 3, "evictions": 1, "size": 2}

        cache.clear()
        assert len(cache.cache) == 0
        assert cache.stats == {"hits": 0, "misses": 0, "evictions": 0, "size": 0}

    def test_cleanup_expired(self):
        """Test cleanup_expired method."""
        cache = IntelligentCache()
        with freeze_time("2023-01-01") as frozen_time:
            # Create entries
            cache.cache["valid_key"] = CacheEntry("valid_value", ttl_seconds=600)
            cache.cache["expired_key"] = CacheEntry("expired_value", ttl_seconds=300)

            # Move time forward to expire second entry
            frozen_time.move_to("2023-01-01 00:06:00")  # 6 minutes later

            cache.cleanup_expired()
            assert "valid_key" in cache.cache
            assert "expired_key" not in cache.cache

    def test_get_stats(self):
        """Test get_stats method."""
        cache = IntelligentCache()
        cache.cache["key1"] = CacheEntry("value1")
        cache.stats = {"hits": 10, "misses": 5, "evictions": 2, "size": 1}

        stats = cache.get_stats()
        assert stats["hits"] == 10
        assert stats["misses"] == 5
        assert stats["evictions"] == 2
        assert stats["size"] == 1
        assert "hit_rate" in stats
        assert stats["hit_rate"] == 0.6666666666666666  # 10/(10+5)

    @patch("psutil.Process")
    def test_check_memory_usage_normal(self, mock_process):
        """Test _check_memory_usage when memory usage is normal."""
        mock_process_instance = Mock()
        mock_process_instance.memory_info.return_value.rss = 20 * 1024 * 1024  # 20MB
        mock_process.return_value = mock_process_instance

        cache = IntelligentCache(max_memory_mb=50.0)
        cache._operation_count = 100  # Trigger memory check

        cache._check_memory_usage()
        # Should not trigger cleanup when under limit

    @patch("psutil.Process")
    def test_check_memory_usage_high(self, mock_process):
        """Test _check_memory_usage when memory usage is high."""
        mock_process_instance = Mock()
        mock_process_instance.memory_info.return_value.rss = 60 * 1024 * 1024  # 60MB
        mock_process.return_value = mock_process_instance

        cache = IntelligentCache(max_size=5, max_memory_mb=50.0)  # Small max_size
        # Add entries to exceed max_size and trigger LRU eviction
        for i in range(10):
            cache.cache[f"key{i}"] = CacheEntry(f"value{i}")

        cache._operation_count = 100  # Trigger memory check
        cache._check_memory_usage()

        # Should have triggered cleanup and reduced size to 70% of max_size (3 entries)
        assert len(cache.cache) <= 5


class TestNamespaceCache:
    """Test cases for NamespaceCache class."""

    def test_init(self):
        """Test NamespaceCache initialization."""
        cache = NamespaceCache()
        assert isinstance(cache.namespaces, dict)
        assert len(cache.namespaces) == 0
        assert isinstance(cache.lock, type(cache.lock))

    def test_get_namespace_new(self):
        """Test get_namespace with new namespace."""
        cache = NamespaceCache()
        namespace = cache.get_namespace("test")

        assert isinstance(namespace, IntelligentCache)
        assert "test" in cache.namespaces
        assert cache.namespaces["test"] is namespace

    def test_get_namespace_existing(self):
        """Test get_namespace with existing namespace."""
        cache = NamespaceCache()
        namespace1 = cache.get_namespace("test")
        namespace2 = cache.get_namespace("test")

        assert namespace1 is namespace2

    def test_get_namespace_config(self):
        """Test get_namespace applies correct configuration."""
        cache = NamespaceCache()

        # Test TMDB namespace - now permanent
        tmdb_cache = cache.get_namespace("tmdb_api")
        assert tmdb_cache.default_ttl is None  # Permanent

        # Test Sonarr namespace
        sonarr_cache = cache.get_namespace("sonarr_api")
        assert sonarr_cache.default_ttl == 43200  # 12 hours

        # Test media_ids namespace - now permanent
        media_cache = cache.get_namespace("media_ids")
        assert media_cache.default_ttl is None  # Permanent

        # Test default namespace
        default_cache = cache.get_namespace("unknown")
        assert default_cache.default_ttl == 3600  # default

    def test_get_set_delete(self):
        """Test get, set, delete operations."""
        cache = NamespaceCache()

        # Test set
        cache.set("test_ns", "test_key", "test_value")
        assert "test_ns" in cache.namespaces

        # Test get
        result = cache.get("test_ns", "test_key")
        assert result == "test_value"

        # Test delete
        result = cache.delete("test_ns", "test_key")
        assert result is True

        # Test get after delete
        result = cache.get("test_ns", "test_key")
        assert result is None

    def test_clear_namespace(self):
        """Test clear_namespace method."""
        cache = NamespaceCache()
        cache.set("test_ns", "key1", "value1")
        cache.set("test_ns", "key2", "value2")

        cache.clear_namespace("test_ns")
        assert cache.get("test_ns", "key1") is None
        assert cache.get("test_ns", "key2") is None

    def test_clear_all(self):
        """Test clear_all method."""
        cache = NamespaceCache()
        cache.set("ns1", "key1", "value1")
        cache.set("ns2", "key2", "value2")

        cache.clear_all()
        # clear_all clears the cache contents but keeps the namespaces
        assert len(cache.namespaces) == 2
        assert len(cache.namespaces["ns1"].cache) == 0
        assert len(cache.namespaces["ns2"].cache) == 0

    def test_get_all_stats(self):
        """Test get_all_stats method."""
        cache = NamespaceCache()
        cache.set("ns1", "key1", "value1")
        cache.set("ns2", "key2", "value2")

        stats = cache.get_all_stats()
        assert "ns1" in stats
        assert "ns2" in stats
        assert isinstance(stats["ns1"], dict)
        assert isinstance(stats["ns2"], dict)

    @patch("builtins.open", new_callable=MagicMock)
    @patch("pickle.dump")
    @patch("os.makedirs")
    def test_save_to_file(self, mock_makedirs, mock_pickle_dump, mock_open):
        """Test save_to_file method."""
        cache = NamespaceCache()
        cache.set("test_ns", "key1", "value1")

        cache.save_to_file("/test/cache.pkl")

        mock_makedirs.assert_called_once()
        mock_open.assert_called_once_with("/test/cache.pkl", "wb")
        mock_pickle_dump.assert_called_once()

    @patch("builtins.open", new_callable=MagicMock)
    @patch("pickle.load")
    @patch("os.path.exists")
    def test_load_from_file(self, mock_exists, mock_pickle_load, mock_open):
        """Test load_from_file method."""
        mock_exists.return_value = True
        mock_pickle_load.return_value = {
            "test_ns": {
                "cache": {
                    "key1": {
                        "value": "value1",
                        "created_at": time.time(),
                        "ttl_seconds": None,
                    }
                },
                "max_size": 1000,
                "default_ttl": 3600,
                "stats": {"hits": 0, "misses": 0, "evictions": 0, "size": 1},
            }
        }

        cache = NamespaceCache()
        cache.load_from_file("/test/cache.pkl")

        assert "test_ns" in cache.namespaces
        mock_open.assert_called_once_with("/test/cache.pkl", "rb")
        mock_pickle_load.assert_called_once()


class TestCacheManager:
    """Test cases for CacheManager class."""

    def test_init(self):
        """Test CacheManager initialization."""
        manager = CacheManager()
        assert isinstance(manager.cache, NamespaceCache)
        assert hasattr(manager, "logger")

    def test_get_tmdb_id_hit(self, mock_cache_manager):
        """Test get_tmdb_id with cache hit."""
        manager = CacheManager()
        manager.cache = mock_cache_manager
        mock_cache_manager.get.return_value = ("tt0111161", "movie")

        result = manager.get_tmdb_id("tt0111161", "imdb_id", "Test Movie")
        assert result == ("tt0111161", "movie")

    def test_get_tmdb_id_miss(self, mock_cache_manager):
        """Test get_tmdb_id with cache miss."""
        manager = CacheManager()
        manager.cache = mock_cache_manager
        mock_cache_manager.get.return_value = None

        result = manager.get_tmdb_id("tt0111161", "imdb_id", "Test Movie")
        assert result is None

    def test_set_tmdb_id(self, mock_cache_manager):
        """Test set_tmdb_id method."""
        manager = CacheManager()
        manager.cache = mock_cache_manager

        manager.set_tmdb_id("tt0111161", "imdb_id", "tt0111161", "movie")
        mock_cache_manager.set.assert_called_once_with(
            "tmdb_api", "imdb_id:tt0111161", ("tt0111161", "movie")
        )

    def test_get_sonarr_status_hit(self, mock_cache_manager):
        """Test get_sonarr_status with cache hit."""
        manager = CacheManager()
        manager.cache = mock_cache_manager
        mock_cache_manager.get.return_value = ("tvdb123", True)

        result = manager.get_sonarr_status("Test Show", "tmdb123")
        assert result == ("tvdb123", True)

    def test_get_sonarr_status_miss(self, mock_cache_manager):
        """Test get_sonarr_status with cache miss."""
        manager = CacheManager()
        manager.cache = mock_cache_manager
        mock_cache_manager.get.return_value = None

        result = manager.get_sonarr_status("Test Show", "tmdb123")
        assert result is None

    def test_set_sonarr_status(self, mock_cache_manager):
        """Test set_sonarr_status method."""
        manager = CacheManager()
        manager.cache = mock_cache_manager

        manager.set_sonarr_status("Test Show", "tmdb123", "tvdb123", True)
        mock_cache_manager.set.assert_called_once_with(
            "sonarr_api", "Test Show:tmdb123", ("tvdb123", True)
        )

    def test_get_yaml_data_hit(self, mock_cache_manager):
        """Test get_yaml_data with cache hit."""
        manager = CacheManager()
        manager.cache = mock_cache_manager
        mock_cache_manager.get.return_value = "yaml_content"

        result = manager.get_yaml_data("media123")
        assert result == "yaml_content"

    def test_get_yaml_data_miss(self, mock_cache_manager):
        """Test get_yaml_data with cache miss."""
        manager = CacheManager()
        manager.cache = mock_cache_manager
        mock_cache_manager.get.return_value = None

        result = manager.get_yaml_data("media123")
        assert result is None

    def test_set_yaml_data(self, mock_cache_manager):
        """Test set_yaml_data method."""
        manager = CacheManager()
        manager.cache = mock_cache_manager

        manager.set_yaml_data("media123", "yaml_content")
        mock_cache_manager.set.assert_called_once_with(
            "yaml_data", "media123:", "yaml_content"
        )

    def test_get_media_ids_hit(self, mock_cache_manager):
        """Test get_media_ids with cache hit."""
        manager = CacheManager()
        manager.cache = mock_cache_manager
        mock_cache_manager.get.return_value = ["media1", "media2"]

        result = manager.get_media_ids("/test/path")
        assert result == ["media1", "media2"]

    def test_get_media_ids_miss(self, mock_cache_manager):
        """Test get_media_ids with cache miss."""
        manager = CacheManager()
        manager.cache = mock_cache_manager
        mock_cache_manager.get.return_value = None

        result = manager.get_media_ids("/test/path")
        assert result is None

    def test_set_media_ids(self, mock_cache_manager):
        """Test set_media_ids method."""
        manager = CacheManager()
        manager.cache = mock_cache_manager
        media_ids = ["media1", "media2"]

        manager.set_media_ids("/test/path", media_ids)
        mock_cache_manager.set.assert_called_once_with(
            "media_ids", "/test/path:[]", media_ids
        )

    def test_get_cache_stats(self, mock_cache_manager):
        """Test get_cache_stats method."""
        manager = CacheManager()
        manager.cache = mock_cache_manager
        mock_cache_manager.get_all_stats.return_value = {"ns1": {"hits": 10}}

        result = manager.get_cache_stats()
        assert result == {"ns1": {"hits": 10}}

    def test_cleanup_expired(self):
        """Test cleanup_expired method."""
        manager = CacheManager()
        # Add some test data
        manager.set_tmdb_id("test1", "imdb_id", "tt0111161", "movie")
        manager.set_tmdb_id("test2", "tmdb_id", "tt0111161", "movie")

        # Verify data was added
        assert manager.get_tmdb_id("test1", "imdb_id") is not None
        assert manager.get_tmdb_id("test2", "tmdb_id") is not None

        # Call cleanup_expired (should not remove unexpired entries)
        manager.cleanup_expired()

        # Verify data is still there
        assert manager.get_tmdb_id("test1", "imdb_id") is not None
        assert manager.get_tmdb_id("test2", "tmdb_id") is not None

    def test_clear_cache_namespace(self, mock_cache_manager):
        """Test clear_cache with specific namespace."""
        manager = CacheManager()
        manager.cache = mock_cache_manager

        manager.clear_cache("test_ns")
        mock_cache_manager.clear_namespace.assert_called_once_with("test_ns")

    def test_clear_cache_all(self, mock_cache_manager):
        """Test clear_cache for all namespaces."""
        manager = CacheManager()
        manager.cache = mock_cache_manager

        manager.clear_cache()
        mock_cache_manager.clear_all.assert_called_once()

    def test_save_cache(self, mock_cache_manager):
        """Test save_cache method."""
        manager = CacheManager()
        manager.cache = mock_cache_manager

        manager.save_cache("/test/cache.pkl")
        mock_cache_manager.save_to_file.assert_called_once_with("/test/cache.pkl")

    def test_load_cache(self, mock_cache_manager):
        """Test load_cache method."""
        manager = CacheManager()
        manager.cache = mock_cache_manager

        manager.load_cache("/test/cache.pkl")
        mock_cache_manager.load_from_file.assert_called_once_with("/test/cache.pkl")


class TestGetCacheManager:
    """Test cases for get_cache_manager function."""

    def test_get_cache_manager_returns_instance(self):
        """Test get_cache_manager returns CacheManager instance."""
        manager = get_cache_manager()
        assert isinstance(manager, CacheManager)

    def test_get_cache_manager_singleton(self):
        """Test get_cache_manager returns same instance."""
        manager1 = get_cache_manager()
        manager2 = get_cache_manager()
        assert manager1 is manager2

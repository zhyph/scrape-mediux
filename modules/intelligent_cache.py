"""
Intelligent caching system for Mediux Scraper.

This module provides smart caching capabilities with time-based expiration,
memory limits, and different strategies for various types of data.
"""

import time
import threading
import logging
import pickle
import os
from typing import Dict, Any, Optional, Tuple, Set
from collections import OrderedDict
import hashlib

logger = logging.getLogger(__name__)


class CacheEntry:
    """Represents a single cache entry with metadata."""

    def __init__(self, value: Any, ttl_seconds: Optional[int] = None):
        self.value = value
        self.created_at = time.time()
        self.accessed_at = time.time()
        self.ttl_seconds = ttl_seconds
        self.access_count = 0

    def is_expired(self) -> bool:
        """Check if the cache entry has expired."""
        if self.ttl_seconds is None:
            return False
        return (time.time() - self.created_at) > self.ttl_seconds

    def access(self):
        """Mark the entry as accessed."""
        self.accessed_at = time.time()
        self.access_count += 1


class IntelligentCache:
    """Intelligent cache with TTL, memory limits, and statistics."""

    def __init__(
        self, max_size: int = 1000, default_ttl: int = 3600, max_memory_mb: float = 50.0
    ):
        """
        Initialize intelligent cache.

        Args:
            max_size: Maximum number of cache entries
            default_ttl: Default TTL in seconds for cache entries
            max_memory_mb: Maximum memory usage in MB before triggering cleanup
        """
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.max_memory_mb = max_memory_mb
        self.cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self.lock = threading.RLock()
        self.stats = {"hits": 0, "misses": 0, "evictions": 0, "size": 0}
        self._memory_check_interval = 100  # Check memory every N operations
        self._operation_count = 0
        self._last_memory_cleanup = time.time()

    def _generate_key(self, *args, **kwargs) -> str:
        """Generate a cache key from arguments."""
        key_parts = [str(arg) for arg in args]
        key_parts.extend(f"{k}:{v}" for k, v in sorted(kwargs.items()))
        key_string = "|".join(key_parts)
        return hashlib.md5(key_string.encode()).hexdigest()

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from cache with statistics tracking."""
        with self.lock:
            if key in self.cache:
                entry = self.cache[key]
                if entry.is_expired():
                    # Remove expired entry
                    del self.cache[key]
                    self.stats["misses"] += 1
                    self.stats["size"] = len(self.cache)
                    return default

                entry.access()
                self.stats["hits"] += 1
                # Move to end for LRU ordering
                self.cache.move_to_end(key)
                return entry.value
            else:
                self.stats["misses"] += 1
                return default

    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """Set a value in cache with optional TTL."""
        with self.lock:
            if key in self.cache:
                # Update existing entry
                entry = self.cache[key]
                entry.value = value
                entry.created_at = time.time()
                entry.ttl_seconds = ttl or self.default_ttl
                entry.access()
                self.cache.move_to_end(key)
            else:
                # Check memory usage periodically
                self._operation_count += 1
                if self._operation_count % self._memory_check_interval == 0:
                    self._check_memory_usage()

                # Add new entry
                if len(self.cache) >= self.max_size:
                    # Remove oldest entry (LRU)
                    oldest_key, oldest_entry = self.cache.popitem(last=False)
                    self.stats["evictions"] += 1
                    logger.debug(f"Cache eviction: {oldest_key}")

                entry = CacheEntry(value, ttl or self.default_ttl)
                self.cache[key] = entry
                self.stats["size"] = len(self.cache)

    def delete(self, key: str) -> bool:
        """Delete a key from cache."""
        with self.lock:
            if key in self.cache:
                del self.cache[key]
                self.stats["size"] = len(self.cache)
                return True
            return False

    def clear(self):
        """Clear all cache entries."""
        with self.lock:
            self.cache.clear()
            self.stats = {"hits": 0, "misses": 0, "evictions": 0, "size": 0}

    def cleanup_expired(self):
        """Remove all expired entries from cache."""
        with self.lock:
            expired_keys = []
            for key, entry in self.cache.items():
                if entry.is_expired():
                    expired_keys.append(key)

            for key in expired_keys:
                del self.cache[key]

            self.stats["size"] = len(self.cache)
            if expired_keys:
                logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")

    def _check_memory_usage(self):
        """Check memory usage and trigger cleanup if necessary."""
        try:
            import psutil
            import os

            # Get current process memory usage
            process = psutil.Process(os.getpid())
            memory_mb = process.memory_info().rss / 1024 / 1024

            if memory_mb > self.max_memory_mb:
                logger.warning(
                    f"Cache memory usage ({memory_mb:.1f} MB) exceeds limit ({self.max_memory_mb} MB). Triggering cleanup."
                )
                self._force_memory_cleanup()

        except ImportError:
            # psutil not available, skip memory monitoring
            pass
        except Exception as e:
            logger.debug(f"Memory monitoring failed: {e}")

    def _force_memory_cleanup(self):
        """Force cleanup to reduce memory usage."""
        with self.lock:
            # Remove expired entries first
            expired_keys = []
            for key, entry in self.cache.items():
                if entry.is_expired():
                    expired_keys.append(key)

            for key in expired_keys:
                del self.cache[key]

            # If still over memory limit, remove least recently used items
            target_size = int(self.max_size * 0.7)  # Reduce to 70% of max size
            while len(self.cache) > target_size:
                oldest_key, oldest_entry = self.cache.popitem(last=False)
                self.stats["evictions"] += 1

            self.stats["size"] = len(self.cache)
            logger.info(
                f"Memory cleanup completed. Cache size reduced to {len(self.cache)} entries."
            )

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self.lock:
            total_requests = self.stats["hits"] + self.stats["misses"]
            hit_rate = (
                (self.stats["hits"] / total_requests) if total_requests > 0 else 0
            )

            return {
                **self.stats,
                "hit_rate": hit_rate,
                "max_size": self.max_size,
                "default_ttl": self.default_ttl,
                "max_memory_mb": self.max_memory_mb,
            }


class NamespaceCache:
    """Cache with multiple namespaces for different data types."""

    def __init__(self):
        self.namespaces: Dict[str, IntelligentCache] = {}
        self.lock = threading.RLock()
        self.logger = logging.getLogger(__name__)

    def get_namespace(self, name: str) -> IntelligentCache:
        """Get or create a cache namespace."""
        with self.lock:
            if name not in self.namespaces:
                # Configure different TTLs for different namespaces - optimized for daily runs
                ttl_config = {
                    "tmdb_api": 86400,  # 24 hours for TMDB data (movies/TV rarely change)
                    "sonarr_api": 3600,  # 1 hour for Sonarr data (series status changes)
                    "yaml_data": 7200,  # 2 hours for processed YAML (moderate refresh)
                    "media_ids": 43200,  # 12 hours for media ID lookups (folder structure stable)
                    "config": 300,  # 5 minutes for config data (frequent changes)
                }
                ttl = ttl_config.get(name, 3600)
                self.namespaces[name] = IntelligentCache(max_size=5000, default_ttl=ttl)
            return self.namespaces[name]

    def get(self, namespace: str, key: str, default: Any = None) -> Any:
        """Get from a specific namespace."""
        cache = self.get_namespace(namespace)
        return cache.get(key, default)

    def set(self, namespace: str, key: str, value: Any, ttl: Optional[int] = None):
        """Set in a specific namespace."""
        cache = self.get_namespace(namespace)
        cache.set(key, value, ttl)

    def delete(self, namespace: str, key: str) -> bool:
        """Delete from a specific namespace."""
        cache = self.get_namespace(namespace)
        return cache.delete(key)

    def clear_namespace(self, namespace: str):
        """Clear a specific namespace."""
        with self.lock:
            if namespace in self.namespaces:
                self.namespaces[namespace].clear()

    def clear_all(self):
        """Clear all namespaces."""
        with self.lock:
            for cache in self.namespaces.values():
                cache.clear()

    def get_all_stats(self) -> Dict[str, Any]:
        """Get statistics for all namespaces."""
        with self.lock:
            all_stats = {}
            for name, cache in self.namespaces.items():
                all_stats[name] = cache.get_stats()
            return all_stats

    def save_to_file(self, filepath: str):
        """Save all cache data to a pickle file."""
        with self.lock:
            try:
                # Create directory if it doesn't exist
                os.makedirs(os.path.dirname(filepath), exist_ok=True)

                # Prepare data for serialization
                cache_data = {}
                for name, cache in self.namespaces.items():
                    # Convert OrderedDict to regular dict for serialization
                    cache_dict = dict(cache.cache)
                    # Remove the lock object as it can't be pickled
                    cache_data[name] = {
                        "cache": cache_dict,
                        "max_size": cache.max_size,
                        "default_ttl": cache.default_ttl,
                        "stats": cache.stats,
                    }

                with open(filepath, "wb") as f:
                    pickle.dump(cache_data, f)

                self.logger.info(f"Intelligent cache saved to {filepath}")
            except Exception as e:
                self.logger.error(f"Failed to save intelligent cache: {e}")

    def load_from_file(self, filepath: str):
        """Load cache data from a pickle file."""
        if not os.path.exists(filepath):
            self.logger.info(f"Intelligent cache file not found: {filepath}")
            return

        try:
            with open(filepath, "rb") as f:
                cache_data = pickle.load(f)

            with self.lock:
                for name, data in cache_data.items():
                    if name not in self.namespaces:
                        # Create namespace if it doesn't exist
                        cache = IntelligentCache(
                            max_size=data.get("max_size", 500),
                            default_ttl=data.get("default_ttl", 3600),
                        )
                        self.namespaces[name] = cache

                    # Restore cache data
                    cache = self.namespaces[name]
                    cache.cache = OrderedDict(data.get("cache", {}))
                    # Reset statistics for new run but preserve cache data
                    cache.stats = {
                        "hits": 0,
                        "misses": 0,
                        "evictions": 0,
                        "size": len(cache.cache),
                    }

            self.logger.info(f"Intelligent cache loaded from {filepath}")
        except Exception as e:
            self.logger.error(f"Failed to load intelligent cache: {e}")


class CacheManager:
    """High-level cache manager with intelligent caching strategies."""

    def __init__(self):
        self.cache = NamespaceCache()
        self.logger = logging.getLogger(__name__)

    def get_tmdb_id(
        self, media_id: str, external_source: str, media_name: str = ""
    ) -> Optional[Tuple[str, str]]:
        """Get TMDB ID with intelligent caching."""
        cache_key = f"{external_source}:{media_id}"
        result = self.cache.get("tmdb_api", cache_key)

        if result is not None:
            self.logger.debug(f"TMDB cache hit for {external_source}:{media_id}")
            return result
        else:
            self.logger.debug(f"TMDB cache miss for {external_source}:{media_id}")
            return None

    def set_tmdb_id(
        self, media_id: str, external_source: str, tmdb_id: str, media_type: str
    ):
        """Set TMDB ID in cache."""
        cache_key = f"{external_source}:{media_id}"
        self.cache.set("tmdb_api", cache_key, (tmdb_id, media_type))
        self.logger.debug(f"Cached TMDB ID: {external_source}:{media_id} -> {tmdb_id}")

    def get_sonarr_status(
        self, media_name: str, tmdb_id: Optional[str]
    ) -> Optional[Tuple[str, bool]]:
        """Get Sonarr series status with caching."""
        cache_key = f"{media_name}:{tmdb_id or 'none'}"
        result = self.cache.get("sonarr_api", cache_key)

        if result is not None:
            self.logger.debug(f"Sonarr cache hit for {media_name}")
            return result
        else:
            self.logger.debug(f"Sonarr cache miss for {media_name}")
            return None

    def set_sonarr_status(
        self,
        media_name: str,
        tmdb_id: Optional[str],
        tvdb_id: Optional[str],
        ended: Optional[bool],
    ):
        """Set Sonarr series status in cache."""
        cache_key = f"{media_name}:{tmdb_id or 'none'}"
        self.cache.set("sonarr_api", cache_key, (tvdb_id, ended))
        self.logger.debug(f"Cached Sonarr status: {media_name} -> {tvdb_id}, {ended}")

    def get_yaml_data(self, media_id: str, filters: str = "") -> Optional[str]:
        """Get processed YAML data with caching."""
        cache_key = f"{media_id}:{filters}"
        result = self.cache.get("yaml_data", cache_key)

        if result is not None:
            self.logger.debug(f"YAML cache hit for {media_id}")
            return result
        else:
            self.logger.debug(f"YAML cache miss for {media_id}")
            return None

    def set_yaml_data(self, media_id: str, yaml_data: str, filters: str = ""):
        """Set processed YAML data in cache."""
        cache_key = f"{media_id}:{filters}"
        self.cache.set("yaml_data", cache_key, yaml_data)
        self.logger.debug(f"Cached YAML data for {media_id}")

    def get_media_ids(
        self, folder_path: str, selected_folders: Optional[list] = None
    ) -> Optional[list]:
        """Get media IDs from folder with caching."""
        cache_key = f"{folder_path}:{selected_folders or []}"
        result = self.cache.get("media_ids", cache_key)

        if result is not None:
            self.logger.debug(f"Media IDs cache hit for {folder_path}")
            return result
        else:
            self.logger.debug(f"Media IDs cache miss for {folder_path}")
            return None

    def set_media_ids(
        self, folder_path: str, media_ids: list, selected_folders: Optional[list] = None
    ):
        """Set media IDs in cache."""
        cache_key = f"{folder_path}:{selected_folders or []}"
        self.cache.set("media_ids", cache_key, media_ids)
        self.logger.debug(f"Cached media IDs for {folder_path}: {len(media_ids)} items")

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics."""
        return self.cache.get_all_stats()

    def cleanup_expired(self):
        """Clean up expired entries across all namespaces."""
        for name in self.cache.namespaces:
            self.cache.namespaces[name].cleanup_expired()

    def clear_cache(self, namespace: Optional[str] = None):
        """Clear cache entries."""
        if namespace:
            self.cache.clear_namespace(namespace)
            self.logger.info(f"Cleared cache namespace: {namespace}")
        else:
            self.cache.clear_all()
            self.logger.info("Cleared all cache namespaces")

    def save_cache(self, filepath: str):
        """Save intelligent cache to file."""
        self.cache.save_to_file(filepath)

    def load_cache(self, filepath: str):
        """Load intelligent cache from file."""
        self.cache.load_from_file(filepath)


# Global cache manager instance
_global_cache_manager = CacheManager()


def get_cache_manager() -> CacheManager:
    """Get the global cache manager instance."""
    return _global_cache_manager

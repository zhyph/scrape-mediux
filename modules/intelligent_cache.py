"""
Intelligent caching system for Mediux Scraper.

This module provides smart caching capabilities with time-based expiration,
memory limits, and different strategies for various types of data.
"""

import logging
import os
import pickle
import threading
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

from .base import FileSystemConstants

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
        self,
        max_size: int = 1000,
        default_ttl: int = 3600,
        max_memory_mb: float = 50.0,
        memory_check_interval: int = 100,
    ):
        """
        Initialize intelligent cache.

        Args:
            max_size: Maximum number of cache entries
            default_ttl: Default TTL in seconds for cache entries
            max_memory_mb: Maximum memory usage in MB before triggering cleanup
            memory_check_interval: Check memory usage every N operations
        """
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.max_memory_mb = max_memory_mb
        self.memory_check_interval = memory_check_interval
        self.cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self.lock = threading.RLock()
        self.stats = {"hits": 0, "misses": 0, "evictions": 0, "size": 0}
        self._operation_count = 0

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
                if self._operation_count % self.memory_check_interval == 0:
                    self._check_memory_usage()

                # Add new entry
                if len(self.cache) >= self.max_size:
                    # Remove oldest entry (LRU)
                    oldest_key = self.cache.popitem(last=False)
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
            import os

            import psutil

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

    def __init__(
        self,
        default_max_size: int = 1000,
        default_ttl: int = 3600,
        max_memory_mb: float = 50.0,
        memory_check_interval: int = 100,
        namespace_configs: Optional[Dict[str, Dict]] = None,
    ):
        """
        Initialize namespace cache.

        Args:
            default_max_size: Default maximum cache size for namespaces
            default_ttl: Default TTL for namespaces
            max_memory_mb: Maximum memory usage in MB before triggering cleanup
            memory_check_interval: Check memory usage every N operations
            namespace_configs: Custom configuration for specific namespaces
        """
        self.namespaces: Dict[str, IntelligentCache] = {}
        self.lock = threading.RLock()
        self.logger = logging.getLogger(__name__)

        # Store default configuration
        self.default_max_size = default_max_size
        self.default_ttl = default_ttl
        self.max_memory_mb = max_memory_mb
        self.memory_check_interval = memory_check_interval

        # Namespace-specific configurations
        self.namespace_configs = (
            namespace_configs or self._get_default_namespace_configs()
        )

    def _get_default_namespace_configs(self) -> Dict[str, Dict]:
        """Get default namespace configurations."""
        return {
            "tmdb_api": {
                "max_size": 5000,
                "default_ttl": None,  # permanent - TMDB IDs are inherently stable
                "description": "TMDB API responses - permanent cache for stable IDs",
            },
            "sonarr_api": {
                "max_size": 2000,
                "default_ttl": 86400,  # 24 hours - series status changes are moderate
                "description": "Sonarr API responses - moderate change frequency",
            },
        }

    def get_namespace_config(self, namespace: str) -> Dict:
        """Get configuration for a specific namespace."""
        return self.namespace_configs.get(
            namespace,
            {
                "max_size": self.default_max_size,
                "default_ttl": self.default_ttl,
                "description": f"Default configuration for {namespace}",
            },
        )

    def get_namespace(self, name: str) -> IntelligentCache:
        """Get or create a cache namespace."""
        with self.lock:
            if name not in self.namespaces:
                config = self.get_namespace_config(name)
                self.namespaces[name] = IntelligentCache(
                    max_size=config["max_size"],
                    default_ttl=config["default_ttl"],
                    max_memory_mb=self.max_memory_mb,
                    memory_check_interval=self.memory_check_interval,
                )
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
                dir_path = os.path.dirname(filepath)
                if dir_path and not os.path.exists(dir_path):
                    os.makedirs(dir_path, exist_ok=True)
                    self.logger.debug(f"Created cache directory: {dir_path}")

                # Only save if there are namespaces with data
                if not self.namespaces:
                    self.logger.debug("No cache data to save")
                    return

                # Prepare data for serialization
                cache_data = {}
                for name, cache in self.namespaces.items():
                    # Convert OrderedDict to regular dict for serialization
                    cache_dict = {}
                    for key, entry in cache.cache.items():
                        cache_dict[key] = {
                            "value": entry.value,
                            "created_at": entry.created_at,
                            "accessed_at": entry.accessed_at,
                            "ttl_seconds": entry.ttl_seconds,
                            "access_count": entry.access_count,
                        }

                    cache_data[name] = {
                        "cache": cache_dict,
                        "max_size": cache.max_size,
                        "default_ttl": cache.default_ttl,
                    }

                with open(filepath, "wb") as f:
                    pickle.dump(cache_data, f)

                self.logger.info(f"Intelligent cache saved to {filepath}")
            except Exception as e:
                self.logger.error(f"Failed to save intelligent cache: {e}")
                import traceback

                self.logger.debug(f"Cache save error details: {traceback.format_exc()}")

    def load_from_file(self, filepath: str):
        """Load all cache data from a pickle file."""
        with self.lock:
            try:
                if not os.path.exists(filepath):
                    self.logger.debug(
                        f"Cache file {filepath} does not exist - starting with empty cache"
                    )
                    return

                self.logger.debug(f"Loading intelligent cache from {filepath}")

                with open(filepath, "rb") as f:
                    cache_data = pickle.load(f)

                # Load each namespace
                for name, namespace_data in cache_data.items():
                    if name not in self.namespaces:
                        namespace_data.get("cache", {})

                        self.namespaces[name] = IntelligentCache(
                            max_size=namespace_data.get(
                                "max_size", self.default_max_size
                            ),
                            default_ttl=namespace_data.get(
                                "default_ttl", self.default_ttl
                            ),
                            max_memory_mb=self.max_memory_mb,
                            memory_check_interval=self.memory_check_interval,
                        )

                    # Load the cache entries
                    cache = self.namespaces[name]
                    for key, entry_data in namespace_data.get("cache", {}).items():
                        # Create CacheEntry with loaded data
                        entry = CacheEntry(
                            value=entry_data["value"],
                            ttl_seconds=entry_data["ttl_seconds"],
                        )
                        entry.created_at = entry_data["created_at"]
                        entry.accessed_at = entry_data["accessed_at"]
                        entry.access_count = entry_data["access_count"]

                        cache.cache[key] = entry

                    # Reset cache statistics for per-run tracking
                    cache.stats = {
                        "hits": 0,
                        "misses": 0,
                        "evictions": 0,
                        "size": len(cache.cache),
                    }

                    # Clean up expired entries on load
                    cache.cleanup_expired()

                self.logger.info(
                    f"Intelligent cache loaded from {filepath} ({len(self.namespaces)} namespaces)"
                )

            except Exception as e:
                self.logger.error(f"Failed to load intelligent cache: {e}")
                import traceback

                self.logger.debug(f"Cache load error details: {traceback.format_exc()}")


class CacheManager:
    """High-level cache manager with intelligent caching strategies."""

    def __init__(
        self,
        default_max_size: int = 1000,
        default_ttl: int = 3600,
        max_memory_mb: float = 50.0,
        memory_check_interval: int = 100,
        namespace_configs: Optional[Dict[str, Dict]] = None,
        # Cache configuration settings
        disable_cache: bool = False,
        clear_cache: bool = False,
        cache_dir: str = FileSystemConstants.OUTPUT_DIR_DEFAULT,
    ):
        """
        Initialize cache manager.

        Args:
            default_max_size: Default maximum cache size for namespaces
            default_ttl: Default TTL for namespaces
            max_memory_mb: Maximum memory usage in MB before triggering cleanup
            memory_check_interval: Check memory usage every N operations
            namespace_configs: Custom configuration for specific namespaces
            disable_cache: Whether to disable cache loading and saving
            clear_cache: Whether to clear existing cache files
            cache_dir: Directory to store cache files
        """
        self.cache = NamespaceCache(
            default_max_size=default_max_size,
            default_ttl=default_ttl,
            max_memory_mb=max_memory_mb,
            memory_check_interval=memory_check_interval,
            namespace_configs=namespace_configs,
        )
        self.logger = logging.getLogger(__name__)

        # Cache configuration settings
        self.disable_cache = disable_cache
        self.clear_cache_on_startup = clear_cache
        self.cache_dir = cache_dir

    def get_tmdb_id(
        self, media_id: str, external_source: str
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
        cache_key = f"{media_name}:{str(tmdb_id) if tmdb_id else 'none'}"
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
        cache_key = f"{media_name}:{str(tmdb_id) if tmdb_id else 'none'}"
        self.cache.set("sonarr_api", cache_key, (tvdb_id, ended))
        self.logger.debug(f"Cached Sonarr status: {media_name} -> {tvdb_id}, {ended}")

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics."""
        return self.cache.get_all_stats()

    def sonarr_cache_exists(self, media_name: str, tmdb_id: Optional[str]) -> bool:
        """Check if Sonarr cache entry exists without triggering access or logging."""
        cache_key = f"{media_name}:{str(tmdb_id) if tmdb_id else 'none'}"

        # Get namespace without triggering any access logic
        namespace = self.cache.namespaces.get("sonarr_api")
        if namespace:
            return cache_key in namespace.cache

        return False

    def load_cache(self):
        """Load cache from file."""
        filepath = self.get_cache_file_path(
            FileSystemConstants.INTELLIGENT_CACHE_FILENAME
        )
        self.cache.load_from_file(filepath)

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

    def get_cache_file_path(self, filename: str) -> str:
        """Get full path for cache file."""
        return os.path.join(self.cache_dir, filename)

    def get_namespace_config(self, namespace: str) -> Dict:
        """Get configuration for a specific namespace."""
        return self.cache.get_namespace_config(namespace)


# Global cache manager instance with default settings
_global_cache_manager = CacheManager()


def get_cache_manager() -> CacheManager:
    """Get the global cache manager instance."""
    return _global_cache_manager


def set_global_cache_manager(cache_manager: CacheManager) -> None:
    """Set the global cache manager instance."""
    global _global_cache_manager
    _global_cache_manager = cache_manager


def create_cache_manager_from_config(
    max_cache_size: int = 1000,
    default_cache_ttl: int = 3600,
    max_cache_memory_mb: float = 50.0,
    memory_check_interval: int = 100,
    namespace_configs: Optional[Dict[str, Dict]] = None,
    disable_cache: bool = False,
    clear_cache: bool = False,
    cache_dir: str = FileSystemConstants.OUTPUT_DIR_DEFAULT,
) -> CacheManager:
    """
    Create a new CacheManager instance with specific configuration.

    This function allows creating cache managers with custom settings,
    useful when you need multiple cache instances or want to override
    the global cache manager settings.

    Args:
        max_cache_size: Default maximum cache size for namespaces
        default_cache_ttl: Default TTL for namespaces
        max_cache_memory_mb: Maximum memory usage in MB before triggering cleanup
        memory_check_interval: Check memory usage every N operations
        namespace_configs: Custom configuration for specific namespaces
        disable_cache: Whether to disable cache loading and saving
        clear_cache: Whether to clear existing cache files
        cache_dir: Directory to store cache files

    Returns:
        Configured CacheManager instance
    """
    return CacheManager(
        default_max_size=max_cache_size,
        default_ttl=default_cache_ttl,
        max_memory_mb=max_cache_memory_mb,
        memory_check_interval=memory_check_interval,
        namespace_configs=namespace_configs,
        disable_cache=disable_cache,
        clear_cache=clear_cache,
        cache_dir=cache_dir,
    )

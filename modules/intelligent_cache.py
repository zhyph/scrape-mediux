"""
Intelligent caching system for Mediux Scraper.

This module provides smart caching capabilities with time-based expiration,
memory limits, and different strategies for various types of data.
"""

import hashlib
import logging
import os
import pickle
import threading
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

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
                "default_ttl": 43200,  # 12 hours - series status changes are moderate
                "description": "Sonarr API responses - moderate change frequency",
            },
            "scraped_yaml": {
                "max_size": 3000,
                "default_ttl": 21600,  # 6 hours - scraped data needs periodic refresh
                "description": "Scraped YAML data from Mediux website",
            },
            "bulk_yaml": {
                "max_size": 1000,
                "default_ttl": 3600,  # 1 hour - bulk data files change less frequently
                "description": "Bulk YAML data loaded from files",
            },
            "processed_yaml": {
                "max_size": 2000,
                "default_ttl": 21600,  # 6 hours - processed data needs periodic refresh
                "description": "Processed/fixed YAML data",
            },
            "yaml_data": {
                "max_size": 3000,
                "default_ttl": 21600,  # 6 hours - legacy namespace, kept for backward compatibility
                "description": "Legacy YAML data namespace - kept for backward compatibility",
            },
            "media_ids": {
                "max_size": 10000,
                "default_ttl": None,  # permanent - folder structure IDs are stable
                "description": "Media folder IDs - stable folder structure",
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
                        "stats": cache.stats,
                    }

                with open(filepath, "wb") as f:
                    pickle.dump(cache_data, f)

                self.logger.info(f"Intelligent cache saved to {filepath}")
            except Exception as e:
                self.logger.error(f"Failed to save intelligent cache: {e}")
                import traceback

                self.logger.debug(f"Cache save error details: {traceback.format_exc()}")

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
                    cache.cache = OrderedDict()

                    # Reconstruct CacheEntry objects from saved data
                    for key, entry_data in data.get("cache", {}).items():
                        if isinstance(entry_data, dict):
                            # New format with individual fields
                            entry = CacheEntry(
                                value=entry_data["value"],
                                ttl_seconds=entry_data.get("ttl_seconds"),
                            )
                            entry.created_at = entry_data.get("created_at", time.time())
                            entry.accessed_at = entry_data.get(
                                "accessed_at", time.time()
                            )
                            entry.access_count = entry_data.get("access_count", 0)
                        else:
                            # Legacy format (direct value)
                            entry = CacheEntry(value=entry_data)

                        cache.cache[key] = entry

                    # Reset statistics for fresh per-run tracking (don't preserve old stats)
                    cache.stats = {
                        "hits": 0,
                        "misses": 0,
                        "evictions": 0,
                        "size": len(cache.cache),
                    }

            self.logger.info(f"Intelligent cache loaded from {filepath}")

            # Perform cache warming for critical namespaces
            self._warm_critical_caches()

        except Exception as e:
            self.logger.error(f"Failed to load intelligent cache: {e}")
            import traceback

            self.logger.debug(f"Cache load error details: {traceback.format_exc()}")

    def _warm_critical_caches(self):
        """Warm up critical cache namespaces by cleaning expired entries."""
        critical_namespaces = ["media_ids", "tmdb_api"]

        with self.lock:
            for namespace in critical_namespaces:
                if namespace in self.namespaces:
                    cache = self.namespaces[namespace]
                    expired_count = 0

                    # Clean expired entries
                    expired_keys = []
                    for key, entry in cache.cache.items():
                        if entry.is_expired():
                            expired_keys.append(key)

                    for key in expired_keys:
                        del cache.cache[key]
                        expired_count += 1

                    if expired_count > 0:
                        self.logger.debug(
                            f"Cache warming: cleaned {expired_count} expired entries in {namespace}"
                        )


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
        cache_dir: str = "./out",
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

    def get_scraped_yaml_data(
        self,
        tmdb_id: str,
        media_type: str,
        preferred_users: Optional[List[str]] = None,
        excluded_users: Optional[List[str]] = None,
    ) -> Optional[str]:
        """Get scraped YAML data from Mediux website with caching."""
        cache_key = f"{tmdb_id}:{media_type}:{sorted(preferred_users or [])}:{sorted(excluded_users or [])}"
        result = self.cache.get("scraped_yaml", cache_key)

        if result is not None:
            self.logger.info(
                f"Using cached scraped YAML data for {media_type} {tmdb_id}"
            )
            return result
        else:
            return None

    def set_scraped_yaml_data(
        self,
        tmdb_id: str,
        media_type: str,
        yaml_data: str,
        preferred_users: Optional[List[str]] = None,
        excluded_users: Optional[List[str]] = None,
    ):
        """Set scraped YAML data from Mediux website in cache."""
        cache_key = f"{tmdb_id}:{media_type}:{sorted(preferred_users or [])}:{sorted(excluded_users or [])}"
        self.cache.set("scraped_yaml", cache_key, yaml_data)
        self.logger.debug(f"Cached scraped YAML data for {media_type} {tmdb_id}")

    def get_bulk_yaml_data(
        self, file_path: str, only_set_urls: bool = False, file_mtime: float = 0.0
    ) -> Optional[Any]:
        """Get bulk YAML data file with caching."""
        cache_key = f"bulk_data:{file_path}:{only_set_urls}:{file_mtime}"
        result = self.cache.get("bulk_yaml", cache_key)

        if result is not None:
            self.logger.debug(f"Using cached bulk YAML data for {file_path}")
            return result
        else:
            return None

    def set_bulk_yaml_data(
        self,
        file_path: str,
        yaml_data: Any,
        only_set_urls: bool = False,
        file_mtime: float = 0.0,
    ):
        """Set bulk YAML data file in cache."""
        cache_key = f"bulk_data:{file_path}:{only_set_urls}:{file_mtime}"
        self.cache.set("bulk_yaml", cache_key, yaml_data)
        self.logger.debug(f"Cached bulk YAML data for {file_path}")

    def get_processed_yaml_data(self, content_hash: str) -> Optional[Tuple[str, bool]]:
        """Get processed YAML data with caching."""
        cache_key = f"yaml_preprocess:{content_hash}"
        result = self.cache.get("processed_yaml", cache_key)

        if result is not None:
            self.logger.debug("Using cached YAML preprocessing result")
            return result
        else:
            return None

    def set_processed_yaml_data(
        self, content_hash: str, yaml_data: str, was_fixed: bool = False
    ):
        """Set processed YAML data in cache."""
        cache_key = f"yaml_preprocess:{content_hash}"
        self.cache.set("processed_yaml", cache_key, (yaml_data, was_fixed))
        self.logger.debug("Cached YAML preprocessing result")

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

    def get_cache_file_path(self, filename: str) -> str:
        """Get full path for cache file."""
        return os.path.join(self.cache_dir, filename)

    def should_load_cache(self) -> bool:
        """Determine if cache should be loaded."""
        return not self.disable_cache

    def should_save_cache(self) -> bool:
        """Determine if cache should be saved."""
        return not self.disable_cache

    def get_namespace_config(self, namespace: str) -> Dict:
        """Get configuration for a specific namespace."""
        return self.cache.get_namespace_config(namespace)

    def refresh_permanent_entries(self, namespace: str):
        """Force refresh of permanent cache entries by clearing them.

        This method clears permanent cache entries (TTL=None) that should be refreshed,
        such as when external APIs have updated their data.

        Args:
            namespace: The cache namespace to refresh (e.g., 'tmdb_api', 'media_ids')
        """
        if namespace in self.cache.namespaces:
            cache = self.cache.namespaces[namespace]
            permanent_keys = []

            with cache.lock:
                for key, entry in cache.cache.items():
                    if entry.ttl_seconds is None:  # Permanent entry
                        permanent_keys.append(key)

                for key in permanent_keys:
                    del cache.cache[key]
                    cache.stats["size"] = len(cache.cache)

            if permanent_keys:
                self.logger.info(
                    f"Refreshed {len(permanent_keys)} permanent entries in {namespace}"
                )
            else:
                self.logger.info(f"No permanent entries found in {namespace}")


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
    cache_dir: str = "./out",
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

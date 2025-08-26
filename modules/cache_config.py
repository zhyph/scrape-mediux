"""
Cache configuration module for Mediux Scraper.

This module handles cache configuration settings and management
for the Mediux scraper application.
"""

import logging
import os

logger = logging.getLogger(__name__)


class CacheConfig:
    """Configuration class for cache management settings."""

    def __init__(
        self,
        disable_cache: bool = False,
        clear_cache: bool = False,
        cache_dir: str = "./out",
    ):
        self.disable_cache = disable_cache
        self.clear_cache = clear_cache
        self.cache_dir = cache_dir

    def get_cache_file_path(self, filename: str) -> str:
        """Get full path for cache file."""
        return os.path.join(self.cache_dir, filename)

    def should_load_cache(self) -> bool:
        """Determine if cache should be loaded."""
        return not self.disable_cache

    def should_save_cache(self) -> bool:
        """Determine if cache should be saved."""
        return not self.disable_cache


# Global cache configuration instance
cache_config = CacheConfig()

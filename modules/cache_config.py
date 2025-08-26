"""
Cache configuration module for Mediux Scraper.

This module handles cache configuration settings and management
for the Mediux scraper application.
"""

import logging
import os
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class CacheConfig:
    """Configuration class for cache management settings."""

    def __init__(
        self,
        disable_cache: bool = False,
        clear_cache: bool = False,
        cache_dir: str = "./out",
        # Intelligent cache settings
        max_cache_size: int = 1000,
        default_ttl: int = 3600,
        max_memory_mb: float = 50.0,
        memory_check_interval: int = 100,
        # Namespace-specific configurations
        namespace_configs: Optional[Dict[str, Dict]] = None,
    ):
        self.disable_cache = disable_cache
        self.clear_cache = clear_cache
        self.cache_dir = cache_dir

        # Intelligent cache settings
        self.max_cache_size = max_cache_size
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
                "default_ttl": None,  # permanent
                "description": "TMDB API responses - permanent cache for stable IDs",
            },
            "sonarr_api": {
                "max_size": 2000,
                "default_ttl": 43200,  # 12 hours
                "description": "Sonarr API responses - moderate change frequency",
            },
            "yaml_data": {
                "max_size": 3000,
                "default_ttl": 21600,  # 6 hours
                "description": "Processed YAML data - periodic refresh needed",
            },
            "media_ids": {
                "max_size": 10000,
                "default_ttl": None,  # permanent
                "description": "Media folder IDs - stable folder structure",
            },
        }

    def get_namespace_config(self, namespace: str) -> Dict:
        """Get configuration for a specific namespace."""
        return self.namespace_configs.get(
            namespace,
            {
                "max_size": self.max_cache_size,
                "default_ttl": self.default_ttl,
                "description": f"Default configuration for {namespace}",
            },
        )

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

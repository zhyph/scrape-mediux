"""
Base classes and utilities for Mediux Scraper.

This module provides common base classes and utilities used across the scraper.
"""

import logging
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from modules.intelligent_cache import CacheManager


class CachedService:
    """Base class for services that need cache access.

    This class provides a standardized way to access the intelligent cache
    manager across all service classes, reducing code duplication.
    """

    def __init__(self, cache_manager: Optional['CacheManager'] = None):
        """Initialize cached service.

        Args:
            cache_manager: Optional cache manager to use. If None, gets global instance.
        """
        if cache_manager is not None:
            self.cache_manager = cache_manager
        else:
            from modules.intelligent_cache import get_cache_manager
            self.cache_manager = get_cache_manager()

        self.logger = logging.getLogger(self.__class__.__module__)


class BaseService:
    """Base class for all service classes.

    Provides common functionality like logging that all services need.
    """

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__module__)
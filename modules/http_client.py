"""
Global HTTP Client Session Manager for Mediux Scraper.

This module provides a centralized HTTP session manager that maintains
persistent connections and standardized request handling across the application.
"""

import logging
from typing import Optional
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib3

logger = logging.getLogger(__name__)


class GlobalSessionManager:
    """
    Singleton manager for global HTTP session with connection pooling and retry logic.

    This class provides a centralized requests Session that can be shared across
    all modules in the application, improving performance through connection reuse
    and providing consistent request behavior.
    """

    _instance: Optional["GlobalSessionManager"] = None
    _session: Optional[requests.Session] = None

    def __new__(cls) -> "GlobalSessionManager":
        if cls._instance is None:
            cls._instance = super(GlobalSessionManager, cls).__new__(cls)
            cls._instance._initialize_session()
        return cls._instance

    def _initialize_session(self) -> None:
        """Initialize the HTTP session with optimized settings."""
        self._session = requests.Session()
        self._session.verify = True  # Default to verify SSL

        # Configure retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=0.3,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"],
        )

        # Configure HTTP adapter with connection pooling
        http_adapter = HTTPAdapter(
            max_retries=retry_strategy, pool_connections=50, pool_maxsize=50
        )

        # Configure HTTPS adapter
        https_adapter = HTTPAdapter(
            max_retries=retry_strategy, pool_connections=50, pool_maxsize=50
        )

        # Mount adapters
        self._session.mount("http://", http_adapter)
        self._session.mount("https://", https_adapter)

        logger.debug(
            "Global HTTP session initialized with connection pooling and retry logic"
        )

    def set_verify(self, verify: bool) -> None:
        """Set SSL verification for the global session."""
        if self._session is None:
            self._initialize_session()
        assert self._session is not None  # Help type checker
        self._session.verify = verify
        logger.debug(f"SSL verification set to {verify}")

    @property
    def session(self) -> requests.Session:
        """Get the global requests session."""
        if self._session is None:
            self._initialize_session()
        assert self._session is not None  # Help type checker
        return self._session

    def get(self, url: str, **kwargs) -> requests.Response:
        """Perform a GET request using the global session."""
        return self.session.get(url, **kwargs)

    def post(self, url: str, **kwargs) -> requests.Response:
        """Perform a POST request using the global session."""
        return self.session.post(url, **kwargs)

    def put(self, url: str, **kwargs) -> requests.Response:
        """Perform a PUT request using the global session."""
        return self.session.put(url, **kwargs)

    def delete(self, url: str, **kwargs) -> requests.Response:
        """Perform a DELETE request using the global session."""
        return self.session.delete(url, **kwargs)

    def head(self, url: str, **kwargs) -> requests.Response:
        """Perform a HEAD request using the global session."""
        return self.session.head(url, **kwargs)

    def patch(self, url: str, **kwargs) -> requests.Response:
        """Perform a PATCH request using the global session."""
        return self.session.patch(url, **kwargs)

    def close(self) -> None:
        """Close the global session and cleanup resources."""
        if self._session:
            self._session.close()
            self._session = None
            logger.debug("Global HTTP session closed")

    def configure(self, **kwargs) -> None:
        """Configure the global session with provided settings."""
        if kwargs.get("disable_ssl_verification"):
            self.set_verify(False)

    def __del__(self) -> None:
        """Cleanup on object destruction."""
        self.close()


# Global instance - import this to use the shared session
global_session = GlobalSessionManager()


def get_global_session() -> requests.Session:
    """
    Get the global HTTP session instance.

    Returns:
        The shared requests.Session instance used across the application
    """
    return global_session.session


def configure_global_session(disable_ssl_verification: bool = False) -> None:
    """
    Configure the global HTTP session.

    Args:
        disable_ssl_verification: Whether to disable SSL verification
    """
    global_session.configure(disable_ssl_verification=disable_ssl_verification)

    if disable_ssl_verification:
        try:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            logger.debug("SSL certificate verification warnings suppressed")
        except ImportError:
            logger.debug("urllib3 not available, SSL warnings may still appear")

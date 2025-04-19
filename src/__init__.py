# This provides a convenient way to access key functionality directly from the main package
from .browser import init_driver, take_screenshot, login_mediux, scrape_mediux
from .config import load_config, validate_path
from .data import (
    load_cache,
    save_cache,
    load_bulk_data,
    write_data_to_files,
    extract_set_urls,
)
from .media import get_media_ids, fetch_tmdb_id
from .runner import run, schedule_run
from .services import check_series_status

__all__ = [
    # Browser module
    "init_driver",
    "take_screenshot",
    "login_mediux",
    "scrape_mediux",
    # Config module
    "load_config",
    "validate_path",
    # Data module
    "load_cache",
    "save_cache",
    "load_bulk_data",
    "write_data_to_files",
    "extract_set_urls",
    # Media module
    "get_media_ids",
    "fetch_tmdb_id",
    # Runner module
    "run",
    "schedule_run",
    # Services module
    "check_series_status",
]

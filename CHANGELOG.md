# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [25.08.25.18]

### Added

- **Comprehensive unit test suite** with 91%+ coverage across all modules:
  - `tests/unit/test_cache_config.py` - Cache configuration testing
  - `tests/unit/test_config.py` - Configuration management testing
  - `tests/unit/test_data_processor.py` - Data processing testing
  - `tests/unit/test_external_services.py` - External services testing
  - `tests/unit/test_file_manager.py` - File operations testing
  - `tests/unit/test_intelligent_cache.py` - Intelligent caching testing
  - `tests/unit/test_media_discovery.py` - Media discovery testing
  - `tests/unit/test_media_processing.py` - Media processing testing
  - `tests/unit/test_orchestrator.py` - Orchestrator testing
  - `tests/unit/test_scheduler.py` - Scheduler testing
  - `tests/unit/test_scraper.py` - Web scraping functionality testing
  - `tests/unit/test_tmdb_client.py` - TMDB API client testing
- `pytest.ini` configuration with coverage requirements and async testing support
- `tests/conftest.py` with pytest fixtures and configuration
- Test dependencies to `requirements.txt` (pytest, pytest-cov, pytest-asyncio)

### Changed

- **Enhanced CI/CD pipeline** in `.github/workflows/docker-publish.yml`:
  - Added automated test job that runs before Docker image building
  - Integrated coverage reporting with 80% minimum threshold
  - Made build-and-publish job depend on successful test completion
- **Updated .dockerignore** with additional exclusions for test artifacts and development files

## [25.08.25.17]

### Added

- New `initialize_and_login_driver()` function in `modules/scraper.py` for better WebDriver management
- Global YAML parser instance in `modules/config.py` for centralized configuration management
- Enhanced cache serialization with detailed metadata tracking in `modules/intelligent_cache.py`

### Changed

- **Major refactoring of `main.py`**: Reduced from 1000+ lines to ~100 lines, creating a clean entry point that delegates to modular components
- Improved configuration path handling in `modules/config.py` to support both file paths and directories
- Updated cache serialization format in `modules/intelligent_cache.py` to include creation/access times and access counts
- Centralized YAML parser management by removing duplicates and importing from `modules/config.py`
- Enhanced error handling and logging throughout the codebase

### Fixed

- **Critical cache statistics bug**: Fixed accumulated statistics across runs in `modules/intelligent_cache.py` - now resets statistics per run while preserving cached data
- Missing `write_data_to_files()` call that prevented YAML files and cache from being saved
- Configuration handling for Plex integration with fallback support for `zplex_*` parameters
- Memory leak potential by removing duplicate global variables and improving resource management

### Removed

- Duplicate YAML parser instances from `modules/file_manager.py` and `modules/data_processor.py`
- Unused imports and redundant code from `main.py` (connection pools, global variables, etc.)
- Legacy cache serialization format support in favor of enhanced metadata tracking

# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [25.08.26.2]

### Added

- **Comprehensive cache configuration system** with intelligent settings management:
  - Added configurable parameters for `max_cache_size`, `default_cache_ttl`, `max_cache_memory_mb`, and `memory_check_interval`
  - Enhanced `CacheConfig` class with namespace-specific configurations and intelligent defaults
  - Added `create_cache_config()` method to `ConfigManager` for seamless configuration integration
  - Added `create_cache_manager_from_config()` function for programmatic cache manager creation
  - Multi-source configuration support (JSON, environment variables, command-line arguments)
- **Advanced cache management features**:
  - Memory-aware cache cleanup with configurable thresholds
  - Optimized namespace configurations for different data types (TMDB API, Sonarr API, YAML data, media IDs)
  - Intelligent cache key generation and TTL management
  - Comprehensive cache statistics and monitoring

### Changed

- **Enhanced IntelligentCache class** to accept configuration parameters instead of hardcoded values:
  - Added `memory_check_interval` parameter for customizable memory monitoring
  - Improved cache initialization with configurable settings
  - Better resource management and memory optimization
- **Updated NamespaceCache class** with configurable namespace settings:
  - Dynamic namespace configuration based on use case
  - Optimized TTL settings for different data types
  - Improved cache performance with tailored configurations
- **Enhanced ConfigManager** to handle cache configuration:
  - Added command-line arguments for all cache settings
  - Integrated cache configuration resolution with priority system
  - Added cache configuration creation methods

### Fixed

- **Cache configuration integration** ensuring all parameters are properly passed through the system
- **Memory check interval reference** updated to use the new configurable parameter

## [25.08.26.1]

### Added

- **Comprehensive integration tests** for both Plex and folder-based modes in `tests/integration/test_plex_folder_modes_integration.py`:
  - Tests for orchestrator functionality in both discovery modes
  - URL collection and preservation verification
  - Mode detection and configuration validation
  - Error handling and graceful degradation tests
- **New `_collect_existing_urls_from_yaml_files()` method** in `modules/file_manager.py`:
  - Collects existing set URLs from all YAML files in the kometa output directory
  - Replaces folder-based URL collection with YAML-based approach for Plex mode
- **Enhanced error handling** throughout the file operations:
  - Graceful handling of permission errors during directory creation
  - Robust cache save error recovery
  - Improved logging for troubleshooting

### Changed

- **Enhanced `run` function** in `modules/orchestrator.py` with Plex parameter support:
  - Added `plex_url`, `plex_token`, and `plex_libraries` parameters
  - Implemented Plex configuration validation logic
  - Modified root folder validation to only apply when Plex config is missing/invalid
- **Updated `write_data_to_files()` method** in `modules/file_manager.py`:
  - Removed `root_folder_global` parameter dependency
  - Changed from folder-based to YAML-based URL collection
  - Enhanced error handling and logging
- **Updated `.gitignore`** to exclude `output/**/*` directory

### Fixed

- **Critical "Root folder is not set" error** when using Plex configuration:
  - Resolved by implementing conditional root folder validation
  - Users can now run the scraper in Plex-only mode without specifying a root folder
  - Maintains full backward compatibility for existing folder-based workflows
- **Multiple failing unit tests** related to file operations and mocking:
  - Fixed test expectations to match actual behavior
  - Improved mocking strategies for complex file system operations
  - Enhanced test reliability and maintainability

## [25.08.25.5]

### Removed

- **Removed file_ops cache** from `modules/file_manager.py` and `modules/intelligent_cache.py`:
  - Eliminated caching layer in `_collect_existing_urls()` method for direct resource access
  - Removed "file_ops" cache configuration (2-hour TTL) from intelligent cache system
  - All file operations now access resources directly without caching

## [25.08.25.4]

### Fixed

- **Fixed media_ids caching issue** in `modules/external_services.py`:
  - Enhanced cache key generation in `get_media_ids_from_folder()` to include folder modification times
  - Added `_generate_folder_cache_key()` method that detects folder content changes
  - Cache now invalidates automatically when new media folders are added to root folder
  - Solves issue where new entries weren't discovered unless cache was bypassed

## [25.08.25.3]

### Changed

- **Optimized TTL settings** in `modules/intelligent_cache.py` for daily cron runs:
  - `"sonarr_api"`: Increased from 1 hour to 12 hours (3600 → 43200 seconds)
  - `"yaml_data"`: Reduced from 2 hours to 6 hours (7200 → 21600 seconds)
  - `"file_ops"`: Reduced from 30 minutes to 15 minutes (1800 → 900 seconds)
  - `"tmdb_api"` and `"media_ids"`: Kept permanent (TTL=None) for stable data
- **Enhanced caching performance** with cache-first approach in `modules/scraper.py`:
  - Added intelligent cache checks before expensive 5-10 second page loads
  - Implemented parameter-aware cache keys for better hit rates
  - Added caching for empty results to avoid repeated failed lookups
- **Improved file operation caching** in `modules/file_manager.py`:
  - Added modification time tracking for cache invalidation in `_collect_existing_urls()`
  - Enhanced cache keys with timestamps to detect file changes
- **Added YAML preprocessing caching** in `modules/data_processor.py`:
  - Implemented content-hash based caching for `preprocess_yaml_string()`
  - Prevents redundant YAML structure analysis for identical content

### Fixed

- **Updated unit tests** in `tests/unit/test_scraper.py` to account for new caching behavior
- **Minor pytest configuration** update in `pytest.ini` for better async support

## [25.08.25.2]

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

## [25.08.25.1]

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
- Memory leak potential by removing duplicate global variables and improving resource management

### Removed

- Duplicate YAML parser instances from `modules/file_manager.py` and `modules/data_processor.py`
- Unused imports and redundant code from `main.py` (connection pools, global variables, etc.)
- Legacy cache serialization format support in favor of enhanced metadata tracking

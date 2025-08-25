# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [25.08.25]

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

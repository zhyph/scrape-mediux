# Mediux Poster Scraper

<!--toc:start-->

- [Mediux Poster Scraper](#mediux-poster-scraper)
  - [Features](#features)
  - [Requirements](#requirements)
  - [Installation (Local)](#installation-local)
  - [Configuration](#configuration)
    - [Copy Example Configuration](#copy-example-configuration)
    - [Plex Configuration](#plex-configuration)
    - [Configuration Fields](#configuration-fields)
      - [Field Descriptions](#field-descriptions)
  - [YAML Field Filtering](#yaml-field-filtering)
    - [How It Works](#how-it-works)
    - [Filtering Examples](#filtering-examples)
    - [Pattern Matching Rules](#pattern-matching-rules)
    - [Use Cases](#use-cases)
    - [Important Notes](#important-notes)
    - [YAML Structure Validation](#yaml-structure-validation)
  - [Troubleshooting](#troubleshooting)
    - [Cache Issues](#cache-issues)
    - [YAML Issues](#yaml-issues)
    - [Browser Issues](#browser-issues)
  - [Usage (Local)](#usage-local)
    - [Command-line Arguments (Optional)](#command-line-arguments-optional)
  - [Usage (Docker)](#usage-docker)
    - [Docker Compose](#docker-compose)
    - [Running with Docker Compose](#running-with-docker-compose)
    <!--toc:end-->

This script automates the process of scraping movie and TV show poster data from the Mediux website using IMDb, TVDB or TMDB IDs to find corresponding movies/shows. It logs in to Mediux, fetches YAML data containing poster URLs, and extracts unique set URLs to a separate file.

## Features

- **Automatic login** to Mediux.
- **Data scraping** from the Mediux website based on TMDB IDs grabbed from Plex.
- **Advanced caching system** with intelligent TTL-based cache management, memory limits, and configurable settings to avoid redundant API calls and optimize performance.
- **Progress tracking** with detailed progress bars and real-time status updates.
- **Extracts and saves** unique Mediux set URLs to a text file.
- **Handles early termination** and ensures all processed data is saved.
- **Outputs files for kometa and plex-poster-set-helper**
  - You can use the `ppsh-bulk.txt` content together with bbrown430 script [plex-poster-set-helper](https://github.com/bbrown430/plex-poster-set-helper) to automatically download the posters to your Plex library.
  - Or, you can use the `*_data.txt` content together with the [kometa](https://github.com/Kometa-Team/Kometa) script to automatically download the posters to your Plex library. For more information, check this [kometa wiki page](https://kometa.wiki/en/latest/kometa/guides/mediux/?h=mediux).
- **YAML field filtering** with path-based pattern matching to selectively remove unwanted fields from the output.
- **YAML structure validation** with automatic fix for common formatting issues.

## Requirements

- Python >=3.9 (if running locally)
- Docker (if running in a container)

By default, the script will use your Plex server configuration to fetch media IDs. See the [Plex Configuration](#plex-configuration) section below.

## Installation (Local)

1. Clone the repository:

   ```bash
   git clone https://github.com/zhyph/scrape-mediux.git
   cd scrape-mediux
   ```

2. Install the required Python packages:

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   pip install -r requirements.txt
   ```

## Configuration

Create a `config.json` file in the root directory of the project. You can use the `config.example.json` as a template. The configuration file should include the following fields:

### Copy Example Configuration

```bash
cp config.example.json config.json
```

### Plex Configuration

- `plex_url`: Your local Plex URL
- `plex_token`: Grab a token from your Plex (check [Finding an authentication token / X-Plex-Token](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/) if you are not sure how to get one)
- `plex_libraries`: At least one of your Plex Libraries (case sensitive)

### Configuration Fields

<details>
<summary>Click to expand configuration details</summary>

```json
{
  "plex_url": "http://your-plex-server:32400",
  "plex_token": "your_plex_token",
  "plex_libraries": ["Movies", "TV Shows"],
  "api_key": "your_tmdb_api_key",
  "username": "your_mediux_username",
  "password": "your_mediux_password",
  "nickname": "your_mediux_nickname",
  "headless": true,
  "sonarr_endpoint": "your_sonarr_endpoint",
  "sonarr_api_key": "your_sonarr_api_key",
  "output_dir": "/path/to/output_dir",
  "profile_path": "/path/to/chrome_profile",
  "cron": "cron_expression",
  "process_all": false,
  "TZ": "your_timezone",
  "chromedriver_path": "/path/to/chromedriver",
  "retry_on_yaml_failure": false,
  "preferred_users": ["User1", "User2"],
  "excluded_users": ["UserToIgnore1", "UserToIgnore2"],
  "discord_webhook_url": "your_discord_webhook_url",
  "disable_season_fix": false,
  "remove_paths": [],
  "disable_cache": false,
  "clear_cache": false,
  "cache_dir": "./out",
  "max_cache_size": 1000,
  "default_cache_ttl": 3600,
  "max_cache_memory_mb": 50.0,
  "memory_check_interval": 100,
  "disable_ssl_verification": false
}
```

#### Field Descriptions

- **`plex_url`**: The URL of your Plex server (required).
- **`plex_token`**: Your Plex API token (required).
- **`plex_libraries`**: List of Plex library names to scan (required).
- **`api_key`**: **NOT REQUIRED ANYMORE, WILL ACT AS A FALLBACK** _Your TMDB API Read Access Token. You can find this in your [TMDB account settings](https://www.themoviedb.org/settings/api)_.
- **`username`**: Your Mediux username used for logging into the Mediux website.
- **`password`**: Your Mediux password used for logging into the Mediux website.
- **`nickname`**: Your Mediux nickname, which is displayed after logging in.
- **`headless`**: A boolean value (`true` or `false`) to determine whether Selenium should run in headless mode. Set to `false` for debugging, but avoid minimizing or closing the browser during execution.
- **`sonarr_endpoint`**: The endpoint URL for your Sonarr instance. This is used to check the status of TV series.
- **`sonarr_api_key`**: The API key for your Sonarr instance, used for authentication.
- **`output_dir`**: The directory where output files will be saved. This is where the script will store the generated YAML and text files.
- **`profile_path`**: The path to your Chrome user profile. If omitted, the default browser profile will be used.
- **`cron`**: A cron expression for scheduling the script. If omitted, the script will not run on a schedule.
- **`process_all`**: A boolean value (`true` or `false`) to determine whether to process all items, ignoring previously processed or cached items.
- **`TZ`**: The timezone to use for scheduling and logging. This can also be passed as an environment variable.
- **`chromedriver_path`**: The path to the ChromeDriver executable. If omitted, the script will use `webdriver-manager` to automatically download and manage ChromeDriver.
- **`retry_on_yaml_failure`**: A boolean value (`true` or `false`) to determine whether the script should retry by reloading the page if the YAML button exists but an error occurs. Defaults to `false`.
- **`preferred_users`**: A list of Mediux usernames to prioritize when fetching YAML data. The script will search for YAML buttons from these users in the specified order and use the first one found. If none are found, it will use the first available YAML button. (CASE SENSITIVE)
- **`excluded_users`**: A list of Mediux usernames to ignore when fetching YAML data. The script will not use YAML buttons from any user in this list. (CASE SENSITIVE)
- **`discord_webhook_url`**: The URL for a Discord webhook. If provided, the script will send a notification listing newly processed or updated titles to this webhook.
- **`disable_season_fix`**: A boolean value (`true` or `false`) to disable the automatic fix for malformed seasons YAML structure in TV shows. When set to `true`, the script will not attempt to fix structural issues where multiple 'episodes:' blocks appear directly under 'seasons:'. Defaults to `false` (automatic fix enabled).
- **`remove_paths`**: List of YAML field path patterns to remove from the output. Supports wildcard matching with `*`. Examples: `["*.url_background", "seasons.*.url_poster"]`. Defaults to `[]` (no filtering).
- **`disable_cache`**: A boolean value (`true` or `false`) to disable loading and saving of caches (fresh start each time). Can also be set via `--disable_cache` command line option. Defaults to `false`.
- **`clear_cache`**: A boolean value (`true` or `false`) to clear existing cache files before running. Can also be set via `--clear_cache` command line option. Defaults to `false`.
- **`cache_dir`**: Directory to store cache files. Can also be set via `--cache_dir` command line option. Defaults to `"./out"`.
- **`max_cache_size`**: Maximum number of cache entries per namespace. Can also be set via `--max_cache_size` command line option. Defaults to `1000`.
- **`default_cache_ttl`**: Default TTL in seconds for cache entries. Can also be set via `--default_cache_ttl` command line option. Defaults to `3600` (1 hour).
- **`max_cache_memory_mb`**: Maximum memory usage in MB before triggering cleanup. Can also be set via `--max_cache_memory_mb` command line option. Defaults to `50.0`.
- **`memory_check_interval`**: Check memory usage every N operations. Can also be set via `--memory_check_interval` command line option. Defaults to `100`.
- **`disable_ssl_verification`**: A boolean value (`true` or `false`) to disable SSL certificate verification for HTTPS requests. Useful for local HTTPS setups or when certificate verification is causing issues. Defaults to `false`. Use with caution, as this reduces security.

</details>

## YAML Field Filtering

<details>
<summary>Click to expand YAML field filtering details</summary>

The script supports advanced YAML field filtering to selectively remove unwanted fields from the output data. This feature uses path-based pattern matching with wildcard support.

### How It Works

The filtering system allows you to specify patterns for fields you want to remove from the scraped YAML data. It supports:

- **Basic field names**: Remove fields at specific levels (e.g., `url_poster`)
- **Path patterns**: Remove fields using dot notation with wildcards (e.g., `seasons.*.url_poster`)
- **Wildcard matching**: Use `*` to match any value at a specific level

### Filtering Examples

```bash
# Remove all url_background fields globally
python main.py --remove_paths "*.url_background"

# Remove season-level url_poster fields only
python main.py --remove_paths "seasons.*.url_poster"

# Remove episode-level url_poster fields only (use full path)
python main.py --remove_paths "seasons.*.episodes.*.url_poster"

# Remove multiple field types
python main.py --remove_paths "*.url_background" "seasons.*.url_poster"
```

### Pattern Matching Rules

- **Basic patterns** (like `url_poster`): Only removes fields at the root and season levels to preserve episode structure
- **Path patterns** (like `seasons.*.episodes.*.url_poster`): Removes fields matching the exact path pattern
- **Wildcard `*`**: Matches any value at that level in the hierarchy
- **Dot notation**: Navigate through nested YAML structure

### Use Cases

- **Remove background images**: `"*.url_background"` removes all background image URLs
- **Clean season data**: `"seasons.*.url_poster"` removes season poster URLs while keeping episode posters
- **Selective filtering**: Combine multiple patterns to remove different field types
- **Preserve structure**: Basic field names preserve episode structure by not removing episode-level fields

### Important Notes

- **Comment Preservation**: When using `--remove_paths`, some YAML comments may be lost due to the technical nature of parsing and filtering YAML data. For maximum comment preservation, avoid using the filtering feature.

### YAML Structure Validation

The script automatically detects and fixes common YAML structure issues:

- **Malformed Seasons**: Fixes duplicate 'episodes:' blocks under 'seasons:'
- **Validation**: Ensures YAML structure is valid before saving
- **Logging**: Reports when fixes are applied (check logs for auto-fix messages)

</details>

## Troubleshooting

### Cache Issues

- **0% Hit Rate**: Normal for first run or after cache clearing
- **Cache Not Loading**: Check `./out/` directory permissions
- **Slow Performance**: Ensure cache files are accessible

### YAML Issues

- **Malformed Structure**: Check logs for auto-fix messages
- **Missing Data**: Verify Mediux page accessibility

### Browser Issues

- **Connection Failed**: Check Chrome/Chromium installation
- **Profile Issues**: Clear `./profile` directory if login fails

## Usage (Local)

Run the script using the following command:

```bash
python main.py --config_path /path/to/config
```

### Command-line Arguments (Optional)

When running the script, you can ignore all the arguments except `--config_path`, which is the path to the configuration file. The script will look for a `config.json` file in the specified directory.

All arguments are optional, and if not provided, the script will use the default values from the `config.json` file.

If any arguments are provided, they will override the corresponding values in the `config.json` file.

- `--config_path`: Directory to the configuration file, defaults to `/config`.
- `--plex_url`: Plex server URL.
- `--plex_token`: Plex API token.
- `--plex_libraries`: List of Plex library names to scan.
- `--api_key`: **NOT REQUIRED ANYMORE, WILL ACT AS A FALLBACK** _TMDB API Read Access Token (not API Key)._
- `--username`: Mediux username.
- `--password`: Mediux password.
- `--nickname`: Mediux nickname.
- `--profile_path`: Path to Chrome user profile.
- `--sonarr_api_key`: Sonarr API key.
- `--sonarr_endpoint`: Sonarr API endpoint.
- `--headless`: Run Selenium in headless mode.
- `--cron`: Cron expression for scheduling the script.
- `--output_dir`: Directory to copy the output files to.
- `--process_all`: Process all items regardless of whether they have been processed before.
- `--chromedriver_path`: Path to the ChromeDriver executable.
- `--retry_on_yaml_failure`: Retry by reloading the page if the YAML button exists but an error occurs. If omitted, the script will not retry.
- `--preferred_users`: List of Mediux usernames to prioritize when fetching YAML data.
- `--excluded_users`: List of Mediux usernames to exclude when fetching YAML data.
- `--discord_webhook_url`: Discord webhook URL for notifications.
- `--copy_only`: Only copy files to the output_dir and exit. This option skips the scraping process and only performs the file copying operation.
- `--disable_season_fix`: Disable automatic fix for malformed seasons YAML structure in TV shows. When enabled, the script will not attempt to automatically correct structural issues in YAML.
- `--remove_paths`: List of YAML field path patterns to remove from the output. Supports wildcard matching with `*`. Examples: `"*.url_background" "seasons.*.url_poster"`. Note: Basic field names (like `url_poster`) only remove fields at the root and season levels to preserve episode structure.
- `--disable_cache`: Disable loading and saving of caches (fresh start each time).
- `--clear_cache`: Clear existing cache files before running.
- `--cache_dir`: Directory to store cache files (default: ./out).
- `--max_cache_size`: Maximum number of cache entries per namespace (default: 1000).
- `--default_cache_ttl`: Default TTL in seconds for cache entries (default: 3600).
- `--max_cache_memory_mb`: Maximum memory usage in MB before triggering cleanup (default: 50.0).
- `--memory_check_interval`: Check memory usage every N operations (default: 100).
- `--disable_ssl_verification`: Disable SSL certificate verification for HTTPS requests (default: false).

## Usage (Docker)

You can run the scraper using Docker. A prebuilt image is available on Docker Hub.

### Docker Compose

<details>
<summary>Click to expand Docker Compose details</summary>

It's recommended to use this script with cron when running in Docker. (Just modify the `cron` field in the `config.json` file to your desired schedule.)

Here’s an example `docker-compose.yml` file (also available in the repository):

```yaml
services:
  scrape-mediux:
    image: docker.io/zhyph/scrape-mediux
    container_name: scrape-mediux
    environment:
      - TZ=Etc/UTC # Set your timezone
      - LOG_LEVEL=info # Set the log level (debug, info, warning, error), can be omitted
    volumes:
      - /path/to/config:/config # REQUIRED
      - /path/to/config/cache:/app/out # RECOMMENDED, if you don't bind this, the cache will be stored in the container and can easily be lost
      - /path/to/config/profile:/profile # RECOMMENDED, must match profile_path in config.json, if you don't bind this, the profile can be removed and you will need to login again (which is not a big deal, but it will take longer)
      - /path/to/kometa/metadata:/out # OPTIONAL, output_dir in config.json (or args) must match this
```

### Running with Docker Compose

1. Create a `config.json` file in the `/path/to/config` directory. Use the `config.example.json` as a template.
2. Update the `docker-compose.yml` file with the correct paths for your configuration, media, and output directories.
3. Start the container:

   ```bash
   docker-compose up -d
   ```

4. Check the logs to ensure the scraper is running (check if the timezone is correct and the `Time Now` is correct):

   ```bash
   docker logs -f scrape-mediux
   ```

5. If running in cron mode, you can execute the script manually and omit the cron argument:

   ```bash
   docker exec -it scrape-mediux python main.py --cron ''
   ```

</details>

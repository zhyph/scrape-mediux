# Mediux Poster Scraper

Automates scraping of movie and TV show poster metadata from [Mediux](https://mediux.pro) using TMDB IDs sourced from your Plex server. Outputs YAML for [Kometa](https://kometa.wiki/en/latest/kometa/guides/mediux/?h=mediux) and a bulk URL file for [plex-poster-set-helper](https://github.com/bbrown430/plex-poster-set-helper).

## Features

- **Automatic login** to Mediux with Chrome/Chromium
- **Plex integration** — discovers your library via TMDB IDs automatically
- **Smart caching** — TTL-based, memory-limited cache avoids redundant API calls
- **YAML field filtering** — path-based wildcard patterns to strip unwanted fields
- **YAML validation** — detects and auto-fixes malformed season structures
- **User prioritization** — prefer or exclude specific Mediux users per item
- **Discord notifications** — optional webhook alerts for newly processed titles
- **Cron scheduling** — run on a schedule directly from Docker
- **Graceful shutdown** — saves all processed data on early termination

## Requirements

- **Docker** (recommended), or **Python >= 3.9** for local installs

---

## Docker (Recommended)

A prebuilt image is available on Docker Hub: `docker.io/zhyph/scrape-mediux:latest`

**`docker-compose.yml`:**

```yaml
services:
  scrape-mediux:
    image: docker.io/zhyph/scrape-mediux:latest
    container_name: scrape-mediux
    environment:
      - TZ=Etc/UTC         # your timezone
      - LOG_LEVEL=info     # debug | info | warning | error
    volumes:
      - /path/to/config:/config          # REQUIRED — config.json lives here
      - /path/to/config/cache:/app/out   # RECOMMENDED — persists cache between runs
      - /path/to/config/profile:/profile # RECOMMENDED — persists Chrome login session
      - /path/to/kometa/metadata:/out    # OPTIONAL — must match output_dir in config
```

**Steps:**

1. Copy `config.example.json` to `config.json` inside your config directory and fill it in.
2. Update volume paths in `docker-compose.yml`.
3. Start the container:

   ```bash
   docker compose up -d
   ```

4. Tail the logs to verify the timezone and schedule are correct:

   ```bash
   docker logs -f scrape-mediux
   ```

5. To trigger a run manually while cron mode is active:

   ```bash
   docker exec -it scrape-mediux python main.py --cron ''
   ```

---

## Local Installation

```bash
git clone https://github.com/zhyph/scrape-mediux.git
cd scrape-mediux

python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**Run:**

```bash
python main.py --config_path /path/to/config
```

All CLI arguments are optional and override their `config.json` equivalents. `--config_path` defaults to `/config`.

---

## Configuration

```bash
cp config.example.json config.json
```

Edit `config.json` with your credentials and preferences. Full schema with all defaults:

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
  "cron": "0 2 * * *",
  "process_all": false,
  "TZ": "Etc/UTC",
  "chromedriver_path": "/path/to/chromedriver",
  "retry_on_yaml_failure": false,
  "preferred_users": ["User1", "User2"],
  "excluded_users": ["UserToIgnore"],
  "discord_webhook_url": "https://discord.com/api/webhooks/...",
  "disable_season_fix": false,
  "remove_paths": [],
  "disable_cache": false,
  "clear_cache": false,
  "cache_dir": "./out",
  "max_cache_size": 1000,
  "default_cache_ttl": 3600,
  "max_cache_memory_mb": 50.0,
  "memory_check_interval": 100,
  "disable_ssl_verification": false,
  "namespace_configs": {
    "tmdb_api": { "max_size": 5000, "default_ttl": null },
    "sonarr_api": { "max_size": 2000, "default_ttl": 86400 }
  }
}
```

<details>
<summary>Field reference</summary>

### Plex / Media Source

| Field | Required | Description |
|---|---|---|
| `plex_url` | yes | URL of your Plex server, e.g. `http://localhost:32400` |
| `plex_token` | yes | Plex auth token — [how to find it](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/) |
| `plex_libraries` | yes | Library names to scan (case-sensitive), e.g. `["Movies", "TV Shows"]` |

### Mediux Credentials

| Field | Required | Description |
|---|---|---|
| `username` | yes | Mediux login username |
| `password` | yes | Mediux login password |
| `nickname` | yes | Mediux display nickname (shown after login) |

### TMDB / Sonarr

| Field | Required | Description |
|---|---|---|
| `api_key` | no | TMDB API Read Access Token — fallback only. Get one from [TMDB settings](https://www.themoviedb.org/settings/api) |
| `sonarr_endpoint` | no | Sonarr base URL, used to enrich TV series data |
| `sonarr_api_key` | no | Sonarr API key |

### Browser

| Field | Default | Description |
|---|---|---|
| `headless` | `true` | Run Chrome headlessly. Set `false` to watch/debug — don't minimize the window |
| `profile_path` | — | Chrome profile directory. Persists your Mediux session to avoid re-logging in |
| `chromedriver_path` | — | Path to ChromeDriver. Omit to auto-manage via `webdriver-manager` |

### Output

| Field | Default | Description |
|---|---|---|
| `output_dir` | — | Directory where Kometa YAML and `ppsh-bulk.txt` are written |
| `remove_paths` | `[]` | YAML field patterns to strip — see [YAML Field Filtering](#yaml-field-filtering) |
| `disable_season_fix` | `false` | Skip auto-fix for malformed `seasons:` blocks in TV YAML |

### Scheduling & Behaviour

| Field | Default | Description |
|---|---|---|
| `cron` | — | Cron expression for recurring runs, e.g. `"0 2 * * *"` |
| `TZ` | — | Timezone for cron and log timestamps. Also accepted as env var |
| `process_all` | `false` | Re-process every item, ignoring cache |
| `retry_on_yaml_failure` | `false` | Reload page and retry if YAML extraction fails |
| `preferred_users` | `[]` | Mediux usernames to prefer (case-sensitive, checked in order) |
| `excluded_users` | `[]` | Mediux usernames to skip entirely (case-sensitive) |
| `discord_webhook_url` | — | Discord webhook URL for run-complete notifications |
| `disable_ssl_verification` | `false` | Skip HTTPS certificate checks. Use only for local setups |

### Cache

| Field | Default | Description |
|---|---|---|
| `disable_cache` | `false` | Disable cache entirely (fresh start every run) |
| `clear_cache` | `false` | Delete cache files before running |
| `cache_dir` | `./out` | Where cache files are stored |
| `max_cache_size` | `1000` | Max entries per cache namespace |
| `default_cache_ttl` | `3600` | Entry TTL in seconds (1 hour) |
| `max_cache_memory_mb` | `50.0` | Memory ceiling before cache cleanup triggers |
| `memory_check_interval` | `100` | Check memory every N cache operations |
| `namespace_configs` | — | Per-namespace cache overrides (e.g. `tmdb_api`, `sonarr_api`) |

</details>

---

## YAML Field Filtering

Use `remove_paths` (config) or `--remove_paths` (CLI) to strip unwanted fields from the output YAML. Patterns use dot-notation with `*` wildcards.

```bash
# Remove all background images
python main.py --remove_paths "*.url_background"

# Remove season-level posters only (keeps episode posters)
python main.py --remove_paths "seasons.*.url_poster"

# Remove episode-level posters only
python main.py --remove_paths "seasons.*.episodes.*.url_poster"

# Combine multiple patterns
python main.py --remove_paths "*.url_background" "seasons.*.url_poster"
```

**Pattern rules:**

- `*` matches any single key at that level
- Dot notation (`.`) traverses the hierarchy
- A simple name like `url_poster` removes the field at the root and season level, but **not** inside episodes (to preserve episode structure)
- A full path like `seasons.*.episodes.*.url_poster` targets that exact location

> **Note:** Using `remove_paths` may cause some YAML comments to be lost. Avoid it if comment preservation is important.

---

## Command-line Arguments

All arguments override their `config.json` counterparts. Only `--config_path` is commonly needed for local runs.

<details>
<summary>Full argument list</summary>

| Argument | Description |
|---|---|
| `--config_path` | Config directory (default: `/config`) |
| `--plex_url` | Plex server URL |
| `--plex_token` | Plex auth token |
| `--plex_libraries` | Library names to scan |
| `--api_key` | TMDB Read Access Token (fallback only) |
| `--username` | Mediux username |
| `--password` | Mediux password |
| `--nickname` | Mediux nickname |
| `--profile_path` | Chrome profile directory |
| `--sonarr_api_key` | Sonarr API key |
| `--sonarr_endpoint` | Sonarr base URL |
| `--headless` | Headless Chrome mode |
| `--cron` | Cron schedule expression |
| `--output_dir` | Output directory |
| `--process_all` | Re-process all items |
| `--chromedriver_path` | ChromeDriver path |
| `--retry_on_yaml_failure` | Retry on YAML extraction failure |
| `--preferred_users` | Preferred Mediux usernames |
| `--excluded_users` | Excluded Mediux usernames |
| `--discord_webhook_url` | Discord webhook URL |
| `--copy_only` | Only copy files to `output_dir`, skip scraping |
| `--disable_season_fix` | Disable malformed season auto-fix |
| `--remove_paths` | YAML field patterns to remove |
| `--disable_cache` | Disable cache |
| `--clear_cache` | Clear cache before run |
| `--cache_dir` | Cache directory (default: `./out`) |
| `--max_cache_size` | Max cache entries per namespace (default: `1000`) |
| `--default_cache_ttl` | Cache TTL in seconds (default: `3600`) |
| `--max_cache_memory_mb` | Memory limit for cache in MB (default: `50.0`) |
| `--memory_check_interval` | Memory check frequency in ops (default: `100`) |
| `--disable_ssl_verification` | Skip SSL certificate checks |

</details>

---

## Troubleshooting

**Cache**

- *0% hit rate* — expected on first run or after `--clear_cache`
- *Cache not loading* — check read/write permissions on `./out/`

**YAML**

- *Malformed structure* — check logs for auto-fix messages (enabled by default)
- *Missing data* — verify the Mediux page for that title is accessible in your browser

**Browser**

- *Connection failed* — verify Chrome/Chromium is installed and `chromedriver_path` is correct
- *Login issues* — delete the `./profile` directory to force a fresh login

---

## Legacy

If you rely on `root_folder`, use the `legacy_root_folder` branch or Docker tag. That feature is deprecated and will not return — the branch is frozen at the last stable version that supported it.

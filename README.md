# Mediux Poster Scraper

This script automates the process of scraping movie and TV show poster data from the Mediux website using IMDb IDs to find corresponding TMDB IDs. It logs in to Mediux, fetches YAML data containing poster URLs, and extracts unique set URLs to a separate file.

## Features

- **Automatic login** to Mediux.
- **Data scraping** from the Mediux website based on TMDB IDs retrieved via IMDb IDs.
- **Caching** to avoid redundant API calls.
- **Extracts and saves** unique Mediux set URLs to a text file.
- **Handles early termination** and ensures all processed data is saved.
- **Outputs files for kometa and plex-poster-set-helper**
  - You can use the `ppsh-bulk.txt` content together with bbrown430 script [plex-poster-set-helper](https://github.com/bbrown430/plex-poster-set-helper) to automatically download the posters to your plex library.
  - Or, you can use the `*_data.txt` content together with the [kometa](https://github.com/Kometa-Team/Kometa) script to automatically download the posters to your plex library, if you are interested check this [kometa wiki page](https://kometa.wiki/en/latest/kometa/guides/mediux/?h=mediux) for more information.

## Requirements

- Python 3.x
- Selenium
- Requests
- WebDriver Manager
- ruamel.yaml
- croniter
- tqdm
- tenacity

## Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/zhyph/scrape-mediux.git
   cd scrape-mediux
   ```

2. Install the required Python packages:

   ```bash
   pip install -r requirements.txt
   ```

## Configuration

Create a `config.json` file in the root directory of the project. You can use the `config.example.json` as a template. The configuration file should include the following fields:

```json
{
  "root_folder": "/path/to/root_folder",
  "api_key": "your_tmdb_api_key",
  "username": "your_mediux_username",
  "password": "your_mediux_password",
  "nickname": "your_mediux_nickname",
  "folders": ["folder1", "folder2"],
  "headless": true,
  "sonarr_endpoint": "your_sonarr_endpoint",
  "sonarr_api_key": "your_sonarr_api_key",
  "output_dir": "/path/to/output_dir",
  "profile_path": "/path/to/chrome_profile", // CAN BE OMITTED, WILL USE THE DEFAULT BROWSER PROFILE
  "cron": "cron_expression", // CAN BE OMITTED
  "process_all": false, // USE IF YOU WANT TO PROCESS ALL ITEMS, IGNORING PREVIOUSLY PROCESSED/CACHED ITEMS
  "TZ": "your_timezone", // CAN BE PASSED AS ENV VARIABLE, MOSTLY USED FOR CRON
  "chromedriver_path": "/path/to/chromedriver" // CAN BE OMITTED, WILL USE webdriver-manager INSTEAD
}
```

## Usage

Run the script using the following command:

```bash
python main.py --config_path /path/to/config
```

### Command-line Arguments

- `--config_path`: Directory to the configuration file, defaults to `/config`.
- `--root_folder`: Root folder containing subfolders with IMDb IDs.
- `--api_key`: TMDB API key.
- `--username`: Mediux username.
- `--password`: Mediux password.
- `--nickname`: Mediux nickname.
- `--profile_path`: Path to Chrome user profile.
- `--sonarr_api_key`: Sonarr API key.
- `--sonarr_endpoint`: Sonarr API endpoint.
- `--folders`: Specific folders to search for IMDb IDs (optional).
- `--headless`: Run Selenium in headless mode.
- `--cron`: Cron expression for scheduling the script.
- `--output_dir`: Directory to copy the output files to.
- `--process_all`: Process all items regardless of whether they have been processed before.
- `--chromedriver_path`: Path to the ChromeDriver executable.

## License

none :D

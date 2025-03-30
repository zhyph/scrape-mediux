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

- Python >=3.9

Follow the **Recommended naming scheme** from [TRaSH Guides](https://trash-guides.info/), use the following naming scheme for your folders:

- [Movies](https://trash-guides.info/Radarr/Radarr-recommended-naming-scheme/#plex)
- [TV Shows](https://trash-guides.info/Sonarr/Sonarr-recommended-naming-scheme/#optional-plex)

By default, it will only process the folders with Plex naming scheme (open a feature request if you wish to add a new type).

## Installation

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

### Configuration Fields

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
  "profile_path": "/path/to/chrome_profile",
  "cron": "cron_expression",
  "process_all": false,
  "TZ": "your_timezone",
  "chromedriver_path": "/path/to/chromedriver"
}
```

### Field Descriptions

- **`root_folder`**: The root folder containing subfolders with IMDb IDs. This is the directory where your media folders are located.
- **`api_key`**: Your TMDB API Read Access Token. You can find this in your [TMDB account settings](https://www.themoviedb.org/settings/api).
- **`username`**: Your Mediux username used for logging into the Mediux website.
- **`password`**: Your Mediux password used for logging into the Mediux website.
- **`nickname`**: Your Mediux nickname, which is displayed after logging in.
- **`folders`**: A list of specific folders to process. If left empty, all folders in the `root_folder` will be processed.
- **`headless`**: A boolean value (`true` or `false`) to determine whether Selenium should run in headless mode. Set to `false` for debugging, but avoid minimizing or closing the browser during execution.
- **`sonarr_endpoint`**: The endpoint URL for your Sonarr instance. This is used to check the status of TV series.
- **`sonarr_api_key`**: The API key for your Sonarr instance, used for authentication.
- **`output_dir`**: The directory where output files will be saved. This is where the script will store the generated YAML and text files.
- **`profile_path`**: The path to your Chrome user profile. If omitted, the default browser profile will be used.
- **`cron`**: A cron expression for scheduling the script. If omitted, the script will not run on a schedule.
- **`process_all`**: A boolean value (`true` or `false`) to determine whether to process all items, ignoring previously processed or cached items.
- **`TZ`**: The timezone to use for scheduling and logging. This can also be passed as an environment variable.
- **`chromedriver_path`**: The path to the ChromeDriver executable. If omitted, the script will use `webdriver-manager` to automatically download and manage ChromeDriver.

## Usage

Run the script using the following command:

```bash
python main.py --config_path /path/to/config
```

### Command-line Arguments (Optional)

When running the script, you can ignore all the arguments, the only argument that may be used is `--config_path`, which is the path to the configuration file. The script will look for a `config.json` file in the specified directory.

All arguments are optional, and if not provided, the script will use the default values from the `config.json` file.

If any arguments are provided, they will override the corresponding values in the `config.json` file.

- `--config_path`: Directory to the configuration file, defaults to `/config`.
- `--root_folder`: Root folder containing subfolders with IMDb IDs.
- `--api_key`: TMDB API Read Access Token (not API Key).
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

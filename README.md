# Mediux Poster Scraper

This script automates the process of scraping movie and TV show poster data from the Mediux website using IMDb IDs to find corresponding TMDB IDs. It logs in to Mediux, fetches YAML data containing poster URLs, and extracts unique set URLs to a separate file.

## Features

- **Automatic login** to Mediux.
- **Data scraping** from the Mediux website based on TMDB IDs retrieved via IMDb IDs.
- **Caching** to avoid redundant API calls.
- **Extracts and saves** unique Mediux set URLs to a text file.
- **Handles early termination** and ensures all processed data is saved.
- **Optional splitting** of YAML data into folder-specific files.

## Requirements

- Python 3.x
- Selenium
- Requests
- WebDriver Manager

## Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/zhyph/scrape-mediux.git
   cd scrape-mediux
   ```

   ***

2. Install the required Python packages:

   ```bash
   pip install -r requirements.txt
   ```

## Usage

### Arguments

- `root_folder`: Path to the folder containing subfolders with IMDb IDs.
- `api_key`: Your TMDB API key.
- `username` and `password`: Your Mediux login credentials.
- `nickname`: Your Mediux user nickname visible after login.
- `--profile_path` (optional): Path to a Chrome user data directory to persist login sessions.
- `--folders` (optional): Specific folders to search for IMDb IDs.
- `--headless` (optional): Run Selenium in headless mode.
- `--verbose` (optional): Enable verbose output.
- `--split` (optional): Split YAML data into folder-specific files.

### Running the Script

#### Verbose Mode with Split

```bash
python script_name.py "X:\media" your_tmdb_api_key your_mediux_username your_mediux_password "C:\Users\YourUsername\AppData\Local\Google\Chrome\User Data\Default" your_mediux_nickname --headless --verbose --split
```

#### Non-Verbose Mode without Split

```bash
python script_name.py "X:\media" your_tmdb_api_key your_mediux_username your_mediux_password "C:\Users\YourUsername\AppData\Local\Google\Chrome\User Data\Default" your_mediux_nickname --headless
```

### Output Files

- `bulk_data.txt`: Contains all scraped YAML data if `--split` is not used.
- `ppsh-bulk.txt`: Contains unique set URLs extracted from the YAML data.
- `*_data.txt`: Folder-specific YAML data if `--split` is used.

### Handling Early Termination

The script uses the `atexit` module to ensure that all processed data is saved to the appropriate files if the script is terminated early. This ensures no data is lost during an unexpected interruption.

## License

none :D

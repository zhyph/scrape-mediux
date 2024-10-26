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
  - Or, you can use the `*_data.txt` content together with the [kometa](https://github.com/Kometa-Team/Kometa) script to automatically download the posters to your plex library, if you are insterested check this [kometa wiki page](https://kometa.wiki/en/latest/kometa/guides/mediux/?h=mediux) for more information.

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

## License

none :D

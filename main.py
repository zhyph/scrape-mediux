import os
import re
import time
import argparse
import requests
import pickle
import atexit
from collections import defaultdict
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from ruamel.yaml import YAML
import json


CACHE_FILE = "./out/tmdb_cache.pkl"
GLOBAL_TIMEOUT = 2
CONFIG_FILE = "config.json"

new_data = defaultdict(dict)
cache = {}
verbose = False
folder_bulk_data = {}
root_folder = ""

yaml = YAML()
yaml.allow_duplicate_keys = True


def log(message, verbose):
    if verbose:
        print(message)


# Initialize Selenium WebDriver
def init_driver(headless=True, profile_path=None, verbose=False):
    log("Initializing WebDriver...", verbose)
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless")
    if profile_path:
        chrome_options.add_argument(f"--user-data-dir={profile_path}")
    service = ChromeService(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    log("WebDriver initialized.", verbose)
    return driver


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
        return config
    return {}


# Get IMDb IDs from folder names
def get_imdb_ids(root_folder, selected_folders=None, verbose=False):
    log("Fetching IMDb IDs from folder names...", verbose)
    imdb_ids = []
    folder_map = defaultdict(list)
    folders_to_search = (
        selected_folders if selected_folders else os.listdir(root_folder)
    )

    for folder in folders_to_search:
        log(f"Searching folder: {folder}", verbose)
        folder_path = os.path.join(root_folder, folder)
        if os.path.isdir(folder_path):
            subfolders = os.listdir(folder_path)
            for subfolder in subfolders:
                subfolder_path = os.path.join(folder_path, subfolder)
                if os.path.isdir(subfolder_path):
                    match = re.search(r"imdb-(tt\d+)", subfolder)
                    name_match = re.search(r"(.+?)(?=\{imdb-)", subfolder)
                    if match and name_match:
                        imdb_id = match.group(1)
                        media_name = name_match.group(1).strip()
                        imdb_ids.append((imdb_id, media_name))
                        folder_map[imdb_id].append(folder)
    log(f"Found IMDb IDs: {imdb_ids}", verbose)
    return imdb_ids, folder_map


# Fetch TMDB ID using IMDb ID with caching
def fetch_tmdb_id(imdb_id, api_key, cache, verbose=False):
    if imdb_id in cache:
        log(f"Fetching TMDB ID for IMDb ID {imdb_id} from cache.", verbose)
        return cache[imdb_id]

    log(f"Fetching TMDB ID for IMDb ID {imdb_id} from TMDB API...", verbose)
    url = f"https://api.themoviedb.org/3/find/{imdb_id}?external_source=imdb_id"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "accept": "application/json",
    }
    response = requests.get(url, headers=headers)
    data = response.json()
    if data.get("movie_results"):
        tmdb_id = data["movie_results"][0]["id"]
        media_type = "movie"
    elif data.get("tv_results"):
        tmdb_id = data["tv_results"][0]["id"]
        media_type = "tv"
    else:
        tmdb_id, media_type = None, None

    cache[imdb_id] = (tmdb_id, media_type)
    log(f"TMDB ID for IMDb ID {imdb_id}: {tmdb_id}, Media Type: {media_type}", verbose)
    return tmdb_id, media_type


# Scrape Mediux website for YAML links
def scrape_mediux(driver, tmdb_id, media_type, verbose=False):
    log(f"Scraping Mediux for TMDB ID {tmdb_id}, Media Type: {media_type}...", verbose)
    base_url = "https://mediux.pro"
    if media_type == "movie":
        url = f"{base_url}/movies/{tmdb_id}"
    else:
        url = f"{base_url}/shows/{tmdb_id}"

    driver.get(url)
    try:
        yaml_button = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (
                    By.XPATH,
                    "//button[span[contains(text(), 'YAML')]]",
                )
            )
        )

        yaml_button.click()

        # Wait for the YAML data to be fully loaded
        yaml_element = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.XPATH, "//code"))
        )
        yaml_data = ""
        while not yaml_data.strip():
            yaml_data = yaml_element.get_attribute("innerText")
            time.sleep(0.5)  # Wait before trying again

        log(f"YAML data loaded for TMDB ID {tmdb_id}.", verbose)
        return yaml_data
    except Exception as e:
        log(
            f"Error scraping TMDB ID {tmdb_id}, possible to not have YAML: {e}", verbose
        )
        return ""


# Extract set URLs from YAML data
def extract_set_urls(yaml_data):
    set_urls = set()
    lines = yaml_data.split("\n")
    for line in lines:
        match = re.search(r"#.*(https://mediux.pro/sets/\d+)", line)
        if match:
            set_urls.add(match.group(1))
    return set_urls


# Login to Mediux website (if not already logged in)
def login_mediux(driver, username, password, nickname, verbose=False):
    log("Logging into Mediux...", verbose)
    base_url = "https://mediux.pro"
    driver.get(base_url)
    try:
        time.sleep(GLOBAL_TIMEOUT)
        login_button = driver.find_element(
            By.XPATH, "//button[contains(text(), 'Sign In')]"
        )
        login_button.click()

        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, ":r0:-form-item"))
        )

        username_field = driver.find_element(By.ID, ":r0:-form-item")
        time.sleep(1)
        password_field = driver.find_element(By.ID, ":r1:-form-item")
        username_field.send_keys(username)
        password_field.send_keys(password)

        submit_button = driver.find_element(By.XPATH, "//form/button")
        submit_button.click()

        # Wait until login is successful (adjust the condition as necessary)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (
                    By.XPATH,
                    f"//button[contains(text(), '{nickname}')]",
                )  # Assuming a different button appears after login
            )
        )
        log("Logged into Mediux.", verbose)
    except Exception as e:
        log("Already logged in or login elements not found.", verbose)
        log(e, verbose)


# Load cache from file
def load_cache(cache_file, verbose=False):
    if os.path.exists(cache_file):
        log(f"Loading cache from {cache_file}...", verbose)
        with open(cache_file, "rb") as f:
            cache = pickle.load(f)
        log("Cache loaded.", verbose)
        return cache
    log("No cache file found. Initializing new cache.", verbose)
    return {}


# Save cache to file
def save_cache(updated_cache, cache_file, verbose=False):
    log(f"Saving cache to {cache_file}...", verbose)
    if os.path.exists(cache_file):
        with open(cache_file, "rb") as f:
            existing_cache = pickle.load(f)
    else:
        existing_cache = {}

    existing_cache.update(updated_cache)

    with open(cache_file, "wb") as f:
        pickle.dump(existing_cache, f)
    log("Cache saved.", verbose)


# Load existing bulk data to check for already processed IDs
def load_bulk_data(bulk_data_file, only_set_urls=False, verbose=False):
    if os.path.exists(bulk_data_file):
        if only_set_urls:
            log(f"Loading only set URLs from bulk data in {bulk_data_file}...", verbose)
        else:
            log(f"Loading bulk data from {bulk_data_file}...", verbose)

        with open(bulk_data_file, "r", encoding="utf-8") as f:
            if only_set_urls:
                bulk_data = extract_set_urls(f.read())
            else:
                bulk_data = yaml.load(f)

        if not bulk_data:
            if only_set_urls:
                log("No set URLs found in bulk data.", verbose)
                return set()
            return {"metadata": {}}

        log("Bulk data loaded.", verbose)
        return bulk_data

    if only_set_urls:
        return set()

    return {"metadata": {}}


# Integrate with Sonarr API to check if the series is ongoing
def check_series_status(media_name, sonarr_api_key, sonarr_endpoint, verbose=False):
    url = f"{sonarr_endpoint}/api/v3/series/lookup?term={media_name}"
    headers = {
        "X-Api-Key": sonarr_api_key,
        "accept": "application/json",
    }
    response = requests.get(url, headers=headers)
    data = response.json()
    if data and isinstance(data, list):
        series_info = data[0]
        tvdb_id = series_info["tvdbId"]
        ended = series_info["ended"]
        return tvdb_id, ended
    return None, None


# Write data to files
def write_data_to_files():
    global new_data, verbose, folder_bulk_data
    log("Writing data to files...", verbose)

    os.makedirs("./out/kometa", exist_ok=True)

    existing_urls = set()

    for folder in os.listdir(root_folder):
        if os.path.isdir(os.path.join(root_folder, folder)):
            file_path = f"./out/kometa/{folder}_data.yml"
            existing_urls.update(load_bulk_data(file_path, True, verbose))

    # Update the YAML files and collect new URLs
    for folder, data in new_data.items():
        file_name = f"./out/kometa/{folder}_data.yml"
        if os.path.exists(file_name):
            with open(file_name, "r", encoding="utf-8") as f:
                existing_data = yaml.load(f)
                if not existing_data:
                    existing_data = {"metadata": {}}
        else:
            existing_data = {"metadata": {}}

        for _, yaml_data in data.items():
            existing_data["metadata"].update(yaml.load(yaml_data))
            urls = extract_set_urls(yaml_data)
            existing_urls.update(urls)

        with open(file_name, "w", encoding="utf-8") as f:
            yaml.dump(existing_data, f)
        log(f"Data updated in {file_name}.", verbose)

    # Write unique URLs to ppsh-bulk.txt
    with open("./out/ppsh-bulk.txt", "w", encoding="utf-8") as f:
        for url in sorted(existing_urls):
            f.write(url + "\n")
    log("Set URLs updated in ./out/ppsh-bulk.txt.", verbose)

    save_cache(cache, CACHE_FILE, verbose)

    log("Data writing completed.", verbose)


# Main script
def run(
    api_key,
    username,
    password,
    profile_path,
    nickname,
    sonarr_api_key,
    sonarr_endpoint,
    selected_folders=None,
    headless=True,
    verbose_arg=False,
):
    global cache, new_data, verbose, folder_bulk_data, root_folder
    verbose = verbose_arg
    log("Starting script...", verbose)
    cache = load_cache(CACHE_FILE, verbose)

    folder_bulk_data = {
        folder: load_bulk_data(f"./out/kometa/{folder}_data.yml", False, verbose)
        for folder in os.listdir(root_folder)
        if os.path.isdir(os.path.join(root_folder, folder))
    }

    imdb_ids, folder_map = get_imdb_ids(root_folder, selected_folders, verbose)

    driver = init_driver(headless, profile_path, verbose)

    try:
        login_mediux(driver, username, password, nickname, verbose)
        for imdb_id, media_name in imdb_ids:
            already_processed = False
            tmdb_id, media_type = fetch_tmdb_id(imdb_id, api_key, cache, verbose)

            tvdb_id, ended = check_series_status(
                media_name, sonarr_api_key, sonarr_endpoint, verbose
            )
            for folder in folder_map[imdb_id]:
                curr_bulk_data = folder_bulk_data.get(folder, {"metadata": {}})

                if media_type == "tv":
                    if tvdb_id is not None:
                        if tvdb_id in curr_bulk_data.get("metadata", {}):
                            if not ended:
                                log(
                                    f"Series with TVDB ID {tvdb_id} is ongoing. Updating entry.",
                                    verbose,
                                )
                                del curr_bulk_data["metadata"][tvdb_id]
                            else:
                                already_processed = True
                                log(
                                    f"Series with TVDB ID {tvdb_id} has ended and already exists in YAML. Skipping entry.",
                                    verbose,
                                )

                if tmdb_id in curr_bulk_data["metadata"]:
                    already_processed = True
                    log(
                        f"Skipping TMDB ID {tmdb_id} as it is already in ./out/kometa/{folder}_data.yml",
                        verbose,
                    )

            if already_processed:
                continue

            log(
                f"IMDb ID: {imdb_id}, TMDB ID: {tmdb_id}, Media Type: {media_type}",
                verbose,
            )
            if tmdb_id:
                yaml_data = scrape_mediux(driver, tmdb_id, media_type, verbose)
                if not yaml_data:
                    log(f"No YAML data found for TMDB ID {tmdb_id}.", verbose)
                    continue

                for folder in folder_map[imdb_id]:
                    new_data[folder][tmdb_id] = yaml_data

                time.sleep(GLOBAL_TIMEOUT)  # Sleep to avoid overwhelming the server
    finally:
        log("Quitting driver...", verbose)
        driver.quit()
        log("Script finished.", verbose)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Scrape Mediux and create bulk data file."
    )
    parser.add_argument(
        "--root_folder",
        type=str,
        help="Root folder containing subfolders with IMDb IDs",
    )
    parser.add_argument("--api_key", type=str, help="TMDB API key")
    parser.add_argument("--username", type=str, help="Mediux username")
    parser.add_argument("--password", type=str, help="Mediux password")
    parser.add_argument("--nickname", type=str, help="Mediux nickname")
    parser.add_argument("--profile_path", type=str, help="Path to Chrome user profile")
    parser.add_argument("--sonarr_api_key", type=str, help="Sonarr API key")
    parser.add_argument("--sonarr_endpoint", type=str, help="Sonarr API endpoint")
    parser.add_argument(
        "--folders",
        nargs="*",
        help="Specific folders to search for IMDb IDs (optional)",
    )
    parser.add_argument(
        "--headless", action="store_true", help="Run Selenium in headless mode"
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")

    args = parser.parse_args()

    config = load_config()

    root_folder = config.get("root_folder", args.root_folder)
    api_key = config.get("api_key", args.api_key)
    username = config.get("username", args.username)
    password = config.get("password", args.password)
    nickname = config.get("nickname", args.nickname)
    profile_path = config.get("profile_path", args.profile_path)
    sonarr_api_key = config.get("sonarr_api_key", args.sonarr_api_key)
    sonarr_endpoint = config.get("sonarr_endpoint", args.sonarr_endpoint)
    selected_folders = config.get("folders", args.folders)
    headless = config.get("headless", args.headless)
    verbose_arg = config.get("verbose", args.verbose)

    atexit.register(write_data_to_files)

    run(
        api_key,
        username,
        password,
        profile_path,
        nickname,
        sonarr_api_key,
        sonarr_endpoint,
        selected_folders,
        headless,
        verbose_arg,
    )

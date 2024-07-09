import os
import re
import time
import argparse
import requests
import pickle
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

CACHE_FILE = "tmdb_cache.pkl"


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


# Get IMDb IDs from folder names
def get_imdb_ids(root_folder, selected_folders=None, verbose=False):
    log("Fetching IMDb IDs from folder names...", verbose)
    imdb_ids = []
    folders_to_search = (
        selected_folders if selected_folders else os.listdir(root_folder)
    )

    for folder in folders_to_search:
        folder_path = os.path.join(root_folder, folder)
        if os.path.isdir(folder_path):
            subfolders = os.listdir(folder_path)
            for subfolder in subfolders:
                subfolder_path = os.path.join(folder_path, subfolder)
                if os.path.isdir(subfolder_path):
                    match = re.search(r"imdb-(tt\d+)", subfolder)
                    if match:
                        imdb_ids.append(match.group(1))
    log(f"Found IMDb IDs: {imdb_ids}", verbose)
    return imdb_ids


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
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located(
            (
                By.XPATH,
                "/html/body/main/div[2]/div[2]/div/div[3]/div/div[1]/div/div[1]/div/div/div/button[2]",
            )
        )
    )
    yaml_button = driver.find_element(
        By.XPATH,
        "/html/body/main/div[2]/div[2]/div/div[3]/div/div[1]/div/div[1]/div/div/div/button[2]",
    )
    yaml_button.click()

    # Wait for the YAML data to be fully loaded
    yaml_element = WebDriverWait(driver, 20).until(
        EC.presence_of_element_located(
            (By.XPATH, "/html/body/div[2]/div[2]/div/div/pre/code")
        )
    )
    yaml_data = ""
    while not yaml_data.strip():
        yaml_data = yaml_element.get_attribute("innerText")
        time.sleep(0.5)  # Wait before trying again

    log(f"YAML data loaded for TMDB ID {tmdb_id}.", verbose)
    return yaml_data


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
        login_button = driver.find_element(
            By.XPATH, "/html/body/header/div/div/button[contains(text(), 'Sign Up')]"
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

        submit_button = driver.find_element(By.XPATH, "/html/body/div[2]/form/button")
        submit_button.click()

        # Wait until login is successful (adjust the condition as necessary)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (
                    By.XPATH,
                    f"/html/body/header/div/div/button[contains(text(), '{nickname}')]",
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
    log("No cache file found.", verbose)
    return {}


# Save cache to file
def save_cache(cache, cache_file, verbose=False):
    log(f"Saving cache to {cache_file}...", verbose)
    with open(cache_file, "wb") as f:
        pickle.dump(cache, f)
    log("Cache saved.", verbose)


# Load existing bulk data to check for already processed IDs
def load_bulk_data(bulk_data_file, verbose=False):
    if os.path.exists(bulk_data_file):
        log(f"Loading bulk data from {bulk_data_file}...", verbose)
        with open(bulk_data_file, "r") as f:
            bulk_data = f.read()
        log("Bulk data loaded.", verbose)
        return bulk_data
    log("No bulk data file found.", verbose)
    return ""


# Main script
def main(
    root_folder,
    api_key,
    username,
    password,
    profile_path,
    nickname,
    selected_folders=None,
    headless=True,
    verbose=False,
):
    log("Starting script...", verbose)
    cache = load_cache(CACHE_FILE, verbose)
    bulk_data = load_bulk_data("bulk_data.txt", verbose)
    imdb_ids = get_imdb_ids(root_folder, selected_folders, verbose)
    driver = init_driver(headless, profile_path, verbose)

    try:
        login_mediux(driver, username, password, nickname, verbose)
        new_data = []
        set_urls = set()
        for imdb_id in imdb_ids:
            tmdb_id, media_type = fetch_tmdb_id(imdb_id, api_key, cache, verbose)

            if str(tmdb_id) in bulk_data or any(
                str(tmdb_id) in item for item in new_data
            ):
                log(
                    f"Skipping TMDB ID {tmdb_id} as it is already in bulk_data.txt",
                    verbose,
                )
                continue

            log(
                f"IMDb ID: {imdb_id}, TMDB ID: {tmdb_id}, Media Type: {media_type}",
                verbose,
            )
            if tmdb_id:
                yaml_data = scrape_mediux(driver, tmdb_id, media_type, verbose)
                new_data.append(yaml_data)
                set_urls.update(extract_set_urls(yaml_data))
                time.sleep(2)  # Sleep to avoid overwhelming the server

        # Append new data to the bulk data file
        with open("bulk_data.txt", "a") as f:
            if new_data:
                f.write("\n" + "\n".join(new_data))
        log("Bulk data updated.", verbose)

        # Write set URLs to ppsh-bulk.txt
        with open("ppsh-bulk.txt", "a") as f:
            for url in set_urls:
                f.write(url + "\n")
        log("Set URLs updated in ppsh-bulk.txt.", verbose)

    finally:
        log("Quitting driver...", verbose)
        driver.quit()
        save_cache(cache, CACHE_FILE, verbose)
        log("Script finished.", verbose)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Scrape Mediux and create bulk data file."
    )
    parser.add_argument(
        "root_folder", type=str, help="Root folder containing subfolders with IMDb IDs"
    )
    parser.add_argument("api_key", type=str, help="TMDB API key")
    parser.add_argument("username", type=str, help="Mediux username")
    parser.add_argument("password", type=str, help="Mediux password")
    parser.add_argument("profile_path", type=str, help="Path to Chrome user profile")
    parser.add_argument("nickname", type=str, help="Mediux nickname")
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

    main(
        args.root_folder,
        args.api_key,
        args.username,
        args.password,
        args.profile_path,
        args.nickname,
        args.folders,
        args.headless,
        args.verbose,
    )

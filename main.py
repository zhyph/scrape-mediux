import os
import re
import time
import argparse
import requests
import pickle
import atexit
import json
import croniter
import shutil
import logging
from collections import defaultdict
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.remote.webdriver import WebDriver
from webdriver_manager.chrome import ChromeDriverManager
from ruamel.yaml import YAML
from datetime import datetime
from time import sleep
from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm
from tenacity import retry, stop_after_attempt, wait_fixed


logging_dict = {
    "INFO": 20,
    "DEBUG": 10,
    "ERROR": 40,
    "WARNING": 30,
    "NOTSET": 0,
}

logging.basicConfig(
    level=logging_dict.get(os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("scrape-mediux.log", mode="a", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


CACHE_FILE = "./out/tmdb_cache.pkl"
CONFIG_FILE = "config.json"

new_data = defaultdict(dict)
cache = {}
folder_bulk_data = {}
root_folder = ""
output_dir = None
config_path = None

yaml = YAML()
yaml.allow_duplicate_keys = True


def init_driver(headless=True, profile_path=None, chromedriver_path=None):
    logger.info("Initializing WebDriver...")
    options = Options()
    if headless:
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-software-rasterizer")
        options.add_argument("--remote-debugging-port=9222")
    if profile_path:
        options.add_argument(f"--user-data-dir={profile_path}")

    try:
        if chromedriver_path:
            driver = webdriver.Chrome(
                service=ChromeService(chromedriver_path), options=options
            )
        else:
            driver = webdriver.Chrome(
                service=ChromeService(ChromeDriverManager().install()), options=options
            )
        logger.info("WebDriver initialized successfully.")
        return driver
    except Exception as e:
        logger.error(f"Failed to initialize WebDriver: {e}")
        raise


def take_screenshot(driver: WebDriver, name: str):
    screenshot_enabled = os.environ.get("SCREENSHOT") == "1"
    if not screenshot_enabled:
        return

    screenshots_dir = os.path.join(config_path, "screenshots")
    os.makedirs(screenshots_dir, exist_ok=True)
    screenshot_path = os.path.join(screenshots_dir, f"{name}.png")
    try:
        driver.save_screenshot(screenshot_path)
        logger.info(f"Screenshot saved: {screenshot_path}")
    except Exception as e:
        logger.error(f"Failed to save screenshot: {e}")


def validate_path(path, description="Path"):
    if isinstance(path, list):
        for p in path:
            if not p:
                raise ValueError(
                    f"{description} contains an empty path. Please check your configuration."
                )
            if not os.path.exists(p):
                raise FileNotFoundError(
                    f"{description} '{p}' does not exist. Please check your configuration."
                )
            if not os.path.isdir(p):
                raise NotADirectoryError(
                    f"{description} '{p}' is not a directory. Please check your configuration."
                )
    else:
        if not path:
            raise ValueError(
                f"{description} is not set. Please check your configuration."
            )
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"{description} '{path}' does not exist. Please check your configuration."
            )
        if not os.path.isdir(path):
            raise NotADirectoryError(
                f"{description} '{path}' is not a directory. Please check your configuration."
            )


def load_config(config_path):
    full_config_path = f"{config_path}/{CONFIG_FILE}"
    if os.path.exists(full_config_path):
        logger.info(f"Loading configuration from {full_config_path}...")
        with open(full_config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        sanitized_config = {
            k: (
                "[REDACTED]"
                if k
                in [
                    "api_key",
                    "password",
                    "sonarr_api_key",
                    "username",
                    "nickname",
                    "sonarr_endpoint",
                ]
                else v
            )
            for k, v in config.items()
        }
        logger.debug(f"Configuration loaded: {sanitized_config}")
        return config
    logger.error(f"Configuration file not found at {full_config_path}.")
    exit(1)


def get_media_ids(root_folder, selected_folders=None):
    logger.info("Fetching media IDs from folder names...")

    validate_path(root_folder, "Root folder")

    media_ids = []
    folder_map = defaultdict(list)

    root_folders = root_folder if isinstance(root_folder, list) else [root_folder]

    for root in root_folders:
        folders_to_search = selected_folders if selected_folders else os.listdir(root)

        for folder in folders_to_search:
            logger.debug(f"Searching folder: {folder}")
            folder_path = os.path.join(root, folder)
            if os.path.isdir(folder_path):
                subfolders = os.listdir(folder_path)
                for subfolder in subfolders:
                    subfolder_path = os.path.join(folder_path, subfolder)
                    if os.path.isdir(subfolder_path):
                        imdb_match = re.search(r"imdb-(tt\d+)", subfolder)
                        tvdb_match = re.search(r"tvdb-(\d+)", subfolder)
                        tmdb_match = re.search(r"tmdb-(\d+)", subfolder)
                        name_match = re.search(
                            r"(.+?)(?=\{(imdb|tvdb|tmdb)-)", subfolder
                        )
                        if imdb_match and name_match:
                            media_id = imdb_match.group(1)
                            media_name = name_match.group(1).strip()
                            external_source = "imdb_id"
                        elif tvdb_match and name_match:
                            media_id = tvdb_match.group(1)
                            media_name = name_match.group(1).strip()
                            external_source = "tvdb_id"
                        elif tmdb_match and name_match:
                            media_id = tmdb_match.group(1)
                            media_name = name_match.group(1).strip()
                            external_source = "tmdb_id"
                        else:
                            continue
                        media_ids.append((media_id, media_name, external_source))
                        folder_map[media_id].append(folder)
    logger.info(f"Found media IDs: {media_ids}")
    return media_ids, folder_map


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def fetch_tmdb_id(media_id, external_source, api_key, cache):
    if external_source == "tmdb_id":
        logger.info(f"Using TMDB ID {media_id} directly.")

        url = f"https://api.themoviedb.org/3/movie/{media_id}"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "accept": "application/json",
        }
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return media_id, "movie"
        elif response.status_code == 404:
            url = f"https://api.themoviedb.org/3/tv/{media_id}"
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                return media_id, "tv"
            else:
                logger.error(f"TMDB ID {media_id} not found as movie or TV show.")
                return None, None
        else:
            response.raise_for_status()

    if media_id in cache:
        logger.info(f"Fetching TMDB ID for {external_source} {media_id} from cache.")
        return cache[media_id]

    logger.info(f"Fetching TMDB ID for {external_source} {media_id} from TMDB API...")
    url = f"https://api.themoviedb.org/3/find/{media_id}?external_source={external_source}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "accept": "application/json",
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    data = response.json()
    if data.get("movie_results"):
        tmdb_id = data["movie_results"][0]["id"]
        media_type = "movie"
    elif data.get("tv_results"):
        tmdb_id = data["tv_results"][0]["id"]
        media_type = "tv"
    else:
        tmdb_id, media_type = None, None

    cache[media_id] = (tmdb_id, media_type)
    logger.info(
        f"TMDB ID for {external_source} {media_id}: {tmdb_id}, Media Type: {media_type}"
    )
    return tmdb_id, media_type


def scrape_mediux(driver, tmdb_id, media_type):
    logger.info(f"Scraping Mediux for TMDB ID {tmdb_id}, Media Type: {media_type}...")
    base_url = "https://mediux.pro"
    if media_type == "movie":
        url = f"{base_url}/movies/{tmdb_id}"
    else:
        url = f"{base_url}/shows/{tmdb_id}"

    driver.get(url)

    try:
        yaml_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(
                (By.XPATH, "//button[span[contains(text(), 'YAML')]]")
            )
        )
        driver.execute_script("arguments[0].scrollIntoView(true);", yaml_button)
        yaml_button.click()

        yaml_element = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.XPATH, "//code"))
        )

        WebDriverWait(driver, 20).until_not(
            EC.presence_of_element_located(
                (By.XPATH, "//*[contains(text(), 'Updating')]")
            )
        )

        WebDriverWait(driver, 20).until(
            lambda d: yaml_element.get_attribute("innerText").strip() != ""
        )

        yaml_data = yaml_element.get_attribute("innerText")
        logger.info(f"YAML data loaded for TMDB ID {tmdb_id}.")
        return yaml_data
    except Exception as e:
        take_screenshot(driver, f"error_scraping_tmdb_{tmdb_id}")
        logger.error(
            f"Error scraping TMDB ID {tmdb_id}, possible to not have YAML\n"
            f"This can be normal, but, if this ID had an YAML to be extracted and the script failed, "
            f"create an issue in the script Github\n{e}"
        )
        return ""


def extract_set_urls(yaml_data):

    set_urls = set()
    lines = yaml_data.split("\n")
    for line in lines:
        match = re.search(r"#.*(https://mediux.pro/sets/\d+)", line)
        if match:
            set_urls.add(match.group(1))
    return set_urls


def login_mediux(driver, username, password, nickname):
    logger.info("Checking login status on Mediux...")
    base_url = "https://mediux.pro"
    driver.get(base_url)

    try:
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located(
                (By.XPATH, f"//button[contains(text(), '{nickname}')]")
            )
        )
        logger.info(f"User '{nickname}' is already logged in.")
        return
    except Exception:
        logger.info("User is not logged in. Proceeding with login...")

    try:
        login_button = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (By.XPATH, "//button[contains(text(), 'Sign In')]")
            )
        )
        login_button.click()
        logger.debug("Clicked on 'Sign In' button.")

        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, ":r0:-form-item"))
        )
        logger.debug("Login form loaded.")

        username_field = driver.find_element(By.ID, ":r0:-form-item")
        password_field = driver.find_element(By.ID, ":r1:-form-item")
        username_field.send_keys(username)
        password_field.send_keys(password)
        logger.debug("Entered username and password.")

        submit_button = driver.find_element(By.XPATH, "//form/button")
        submit_button.click()
        logger.debug("Clicked on 'Submit' button.")

        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (By.XPATH, f"//button[contains(text(), '{nickname}')]")
            )
        )
        logger.info("Logged into Mediux successfully.")
    except Exception as e:
        take_screenshot(driver, "error_login")
        logger.error(f"Failed to log into Mediux: {e}")
        raise


def load_cache(cache_file):
    if os.path.exists(cache_file):
        logger.info(f"Loading cache from {cache_file}...")
        with open(cache_file, "rb") as f:
            cache = pickle.load(f)
        logger.info("Cache loaded successfully.")
        return cache
    logger.info("No cache file found. Initializing new cache.")
    return {}


def save_cache(updated_cache, cache_file):
    logger.info(f"Saving cache to {cache_file}...")
    if os.path.exists(cache_file):
        with open(cache_file, "rb") as f:
            existing_cache = pickle.load(f)
    else:
        existing_cache = {}

    existing_cache.update(updated_cache)

    with open(cache_file, "wb") as f:
        pickle.dump(existing_cache, f)
    logger.info("Cache saved successfully.")


def load_bulk_data(bulk_data_file, only_set_urls=False):
    if os.path.exists(bulk_data_file):
        logger.info(f"Loading bulk data from {bulk_data_file}...")
        with open(bulk_data_file, "r", encoding="utf-8") as f:
            if only_set_urls:
                bulk_data = extract_set_urls(f.read())
                logger.info(f"Loaded {len(bulk_data)} set URLs from bulk data.")
            else:
                bulk_data = yaml.load(f)
                logger.info("Bulk data loaded successfully.")

        if not bulk_data:
            logger.warning("No data found in bulk data file.")
            return set() if only_set_urls else {"metadata": {}}

        return bulk_data

    logger.warning(f"Bulk data file {bulk_data_file} not found.")
    return set() if only_set_urls else {"metadata": {}}


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def check_series_status(media_name, sonarr_api_key, sonarr_endpoint):
    logger.info(f"Checking series status for {media_name}...")
    url = f"{sonarr_endpoint}/api/v3/series/lookup?term={media_name}"
    headers = {
        "X-Api-Key": sonarr_api_key,
        "accept": "application/json",
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    data = response.json()
    if data and isinstance(data, list):
        series_info = data[0]
        tvdb_id = series_info["tvdbId"]
        ended = series_info["ended"]
        logger.info(
            f"Series status for {media_name}: TVDB ID={tvdb_id}, Ended={ended}."
        )
        return tvdb_id, ended
    logger.warning(f"No series information found for {media_name}.")
    return None, None


def write_data_to_files():
    global new_data, folder_bulk_data, output_dir

    validate_path(root_folder, "Root folder")

    logger.info("Writing data to files...")

    os.makedirs("./out/kometa", exist_ok=True)
    logger.debug("Created output directory './out/kometa'.")

    existing_urls = set()

    root_folders = root_folder if isinstance(root_folder, list) else [root_folder]
    folder_cache = {root: os.listdir(root) for root in root_folders}

    for root, folders in folder_cache.items():
        for folder in folders:
            folder_path = os.path.join(root, folder)
            if os.path.isdir(folder_path):
                file_path = f"./out/kometa/{folder}_data.yml"
                existing_urls.update(load_bulk_data(file_path, True))

    updated_files = []
    total_urls_extracted = 0

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
            total_urls_extracted += len(urls)

        with open(file_name, "w", encoding="utf-8") as f:
            yaml.dump(existing_data, f)
        updated_files.append(file_name)

    logger.info(f"Updated {len(updated_files)} files: {', '.join(updated_files)}")
    logger.info(f"Extracted a total of {total_urls_extracted} unique set URLs.")

    with open("./out/ppsh-bulk.txt", "w", encoding="utf-8") as f:
        for url in sorted(existing_urls):
            f.write(url + "\n")
    logger.info("Set URLs updated in './out/ppsh-bulk.txt'.")

    save_cache(cache, CACHE_FILE)
    logger.info("Data writing completed.")

    if output_dir:
        logger.info(f"Copying files to {output_dir}...")
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            logger.debug(f"Created output directory {output_dir}.")

        for filename in os.listdir("./out/kometa"):
            src_file = os.path.join("./out/kometa", filename)
            dst_file = os.path.join(output_dir, filename)
            shutil.copy2(src_file, dst_file)
        logger.info(f"Files copied to {output_dir}.")


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
    process_all=False,
    chromedriver_path=None,
):
    global cache, new_data, folder_bulk_data, root_folder
    logger.info("Starting the script...")

    validate_path(root_folder, "Root folder")

    cache = load_cache(CACHE_FILE)

    root_folders = root_folder if isinstance(root_folder, list) else [root_folder]
    folder_cache = {root: os.listdir(root) for root in root_folders}

    folder_bulk_data = {}
    for root, folders in folder_cache.items():
        folder_bulk_data.update(
            {
                folder: load_bulk_data(f"./out/kometa/{folder}_data.yml", False)
                for folder in folders
                if os.path.isdir(os.path.join(root, folder))
            }
        )
    logger.debug(f"Loaded bulk data for folders: {list(folder_bulk_data.keys())}")

    media_ids, folder_map = get_media_ids(root_folder, selected_folders)
    logger.info(f"Media IDs to process: {len(media_ids)}")

    driver = init_driver(headless, profile_path, chromedriver_path)

    updated_titles = []

    try:
        login_mediux(driver, username, password, nickname)

        with logging_redirect_tqdm():
            for media_id, media_name, external_source in tqdm(
                media_ids, desc="Processing media IDs"
            ):
                already_processed = False
                try:
                    tmdb_id, media_type = fetch_tmdb_id(
                        media_id, external_source, api_key, cache
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to fetch TMDB ID for {external_source} {media_id}: {e}"
                    )
                    continue

                if media_type == "tv":
                    try:
                        tvdb_id, ended = check_series_status(
                            media_name, sonarr_api_key, sonarr_endpoint
                        )
                    except Exception as e:
                        logger.error(
                            f"Failed to check series status for {media_name}: {e}"
                        )
                        continue

                for folder in folder_map[media_id]:
                    curr_bulk_data = folder_bulk_data.get(folder, {"metadata": {}})

                    if media_type == "tv":
                        if tvdb_id is not None:
                            if (
                                tvdb_id in curr_bulk_data.get("metadata", {})
                                and not process_all
                            ):
                                if not ended:
                                    logger.info(
                                        f"Series with TVDB ID {tvdb_id} is ongoing. Updating entry."
                                    )
                                    del curr_bulk_data["metadata"][tvdb_id]
                                else:
                                    already_processed = True
                                    logger.info(
                                        f"Series with TVDB ID {tvdb_id} has ended and already exists in YAML. Skipping entry."
                                    )

                    if tmdb_id in curr_bulk_data["metadata"] and not process_all:
                        already_processed = True
                        logger.info(
                            f"Skipping TMDB ID {tmdb_id} as it is already in ./out/kometa/{folder}_data.yml"
                        )

                if already_processed:
                    continue

                logger.info(
                    f"Processing Media ID: {media_id}, TMDB ID: {tmdb_id}, Media Type: {media_type}"
                )
                if tmdb_id:
                    yaml_data = scrape_mediux(driver, tmdb_id, media_type)
                    if not yaml_data:
                        logger.warning(f"No YAML data found for TMDB ID {tmdb_id}.")
                        continue

                    for folder in folder_map[media_id]:
                        new_data[folder][tmdb_id] = yaml_data

                    updated_titles.append(media_name)
    finally:
        logger.info("Quitting WebDriver...")
        driver.quit()
        logger.info("Script finished.")

        if updated_titles:
            logger.info("Updated Titles:")
            for title in updated_titles:
                logger.info(f"- {title}")
        else:
            logger.info("No titles were updated.")


def schedule_run(cron_expression):
    logger.info(f"Scheduling script with cron expression: {cron_expression}")
    base_time = datetime.now()
    logger.info(f"Current time: {base_time}")
    logger.info(
        f"Environment Timezone: {os.environ.get('TZ', 'None is set, use the env from the docker compose or docker run to provide your TZ')}"
    )
    cron_iter = croniter.croniter(cron_expression, base_time)
    next_run = cron_iter.get_next(datetime)
    logger.info(f"Next scheduled run at: {next_run}")

    while True:
        now = datetime.now()
        if now >= next_run:
            logger.info("Scheduled run started...")
            try:
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
                )
                write_data_to_files()
            except Exception as e:
                logger.error(f"Error during scheduled run: {e}")
            next_run = cron_iter.get_next(datetime)
            logger.info(f"Next scheduled run at: {next_run}")
        sleep(60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Scrape Mediux and create bulk data file."
    )
    parser.add_argument(
        "--config_path",
        type=str,
        help="Directory to configuration file, defaults to /config",
        default=os.environ.get("CONFIG_PATH", "/config"),
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
    parser.add_argument(
        "--profile_path",
        type=str,
        help="Path to Chrome user profile",
    )
    parser.add_argument("--sonarr_api_key", type=str, help="Sonarr API key")
    parser.add_argument("--sonarr_endpoint", type=str, help="Sonarr API endpoint")
    parser.add_argument(
        "--folders",
        nargs="*",
        help="Specific folders to search for IMDb IDs (optional)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run Selenium in headless mode",
        default=None,
    )
    parser.add_argument(
        "--cron",
        type=str,
        help="Cron expression for scheduling the script",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        help="Directory to copy the output files to",
    )
    parser.add_argument(
        "--process_all",
        action=argparse.BooleanOptionalAction,
        help="Process all items regardless of whether they have been processed before",
    )
    parser.add_argument(
        "--chromedriver_path",
        type=str,
        help="Path to the ChromeDriver executable",
    )

    args = parser.parse_args()

    config = load_config(args.config_path)

    config_path = args.config_path

    if "TZ" in config:
        os.environ["TZ"] = config["TZ"]

    root_folder = (
        args.root_folder if args.root_folder is not None else config.get("root_folder")
    )
    api_key = args.api_key if args.api_key is not None else config.get("api_key")
    username = args.username if args.username is not None else config.get("username")
    password = args.password if args.password is not None else config.get("password")
    nickname = args.nickname if args.nickname is not None else config.get("nickname")
    profile_path = (
        args.profile_path
        if args.profile_path is not None
        else config.get("profile_path", "/profile")
    )
    sonarr_api_key = (
        args.sonarr_api_key
        if args.sonarr_api_key is not None
        else config.get("sonarr_api_key")
    )
    sonarr_endpoint = (
        args.sonarr_endpoint
        if args.sonarr_endpoint is not None
        else config.get("sonarr_endpoint")
    )
    selected_folders = (
        args.folders if args.folders is not None else config.get("folders")
    )
    headless = (
        args.headless if args.headless is not None else config.get("headless", True)
    )
    cron_expression = args.cron if args.cron is not None else config.get("cron")
    output_dir = (
        args.output_dir if args.output_dir is not None else config.get("output_dir")
    )
    process_all = (
        args.process_all
        if args.process_all is not None
        else config.get("process_all", False)
    )
    chromedriver_path = (
        args.chromedriver_path
        if args.chromedriver_path is not None
        else config.get("chromedriver_path")
    )

    if root_folder:
        try:
            validate_path(root_folder, "Root folder")
            atexit.register(write_data_to_files)
        except Exception as e:
            logger.error(f"Error during validation of root folder: {e}")
    else:
        logger.warning(
            "Root folder is not set. Skipping atexit registration for write_data_to_files."
        )

    try:
        if cron_expression:
            schedule_run(cron_expression)
        else:
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
                process_all,
                chromedriver_path,
            )
    except Exception as e:
        logger.error(f"Unhandled error: {e}")
        exit(1)

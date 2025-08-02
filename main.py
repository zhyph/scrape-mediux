import os
import re
import argparse
import requests
import pickle
import atexit
import json
import croniter
import shutil
import logging
import collections.abc
from collections import defaultdict
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.remote.webdriver import WebDriver
from urllib3.exceptions import ReadTimeoutError
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
root_folder_global = ""
output_dir_global = None
config_path_global = None
discord_webhook_url_global = None

yaml = YAML()
yaml.allow_duplicate_keys = True


def to_standard_dict(*, item):
    if isinstance(item, collections.abc.Mapping):
        return {k: to_standard_dict(item=v) for k, v in item.items()}
    elif isinstance(item, collections.abc.Sequence) and not isinstance(
        item, (str, bytes)
    ):
        return [to_standard_dict(item=x) for x in item]
    else:
        return item


def init_driver(*, headless=True, profile_path=None, chromedriver_path=None):
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
        logger.debug("Path to ChromeDriver: " + str(chromedriver_path))
        if chromedriver_path:
            driver = webdriver.Chrome(
                service=ChromeService(chromedriver_path), options=options
            )
        else:
            from webdriver_manager.chrome import ChromeDriverManager

            driver = webdriver.Chrome(
                service=ChromeService(ChromeDriverManager().install()), options=options
            )
        driver.set_page_load_timeout(300)  # 5 minutes
        logger.debug("WebDriver initialized successfully.")
        return driver
    except Exception as e:
        logger.error(f"Failed to initialize WebDriver: {e}")
        raise


def take_screenshot(*, driver: WebDriver, name: str):
    screenshot_enabled = os.environ.get("SCREENSHOT") == "1"
    if not screenshot_enabled:
        return

    if config_path_global is None:
        logger.warning("Configuration path is not set. Cannot save screenshot.")
        return

    screenshots_dir = os.path.join(config_path_global, "screenshots")
    os.makedirs(screenshots_dir, exist_ok=True)
    screenshot_path = os.path.join(screenshots_dir, f"{name}.png")
    try:
        driver.save_screenshot(screenshot_path)
        logger.info(f"Screenshot saved: {screenshot_path}")
    except Exception as e:
        logger.error(f"Failed to save screenshot: {e}")


def _validate_single_path(*, path, description):
    if not path:
        raise ValueError(f"{description} is not set. Please check your configuration.")
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{description} '{path}' does not exist. Please check your configuration."
        )
    if not os.path.isdir(path):
        raise NotADirectoryError(
            f"{description} '{path}' is not a directory. Please check your configuration."
        )


def validate_path(*, path, description="Path"):
    if isinstance(path, list):
        for p in path:
            _validate_single_path(path=p, description=f"{description} entry")
    else:
        _validate_single_path(path=path, description=description)


def load_config(*, config_path):
    config_path = config_path.rstrip("/")
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
                    "discord_webhook_url",
                ]
                else v
            )
            for k, v in config.items()
        }
        logger.debug(f"Configuration loaded: {sanitized_config}")
        return config
    logger.error(f"Configuration file not found at {full_config_path}.")
    exit(1)


def _extract_media_info_from_subfolder(*, subfolder):
    imdb_match = re.search(r"imdb-(tt\d+)", subfolder)
    tvdb_match = re.search(r"tvdb-(\d+)", subfolder)
    tmdb_match = re.search(r"tmdb-(\d+)", subfolder)
    name_match = re.search(r"(.+)(?=\{(imdb|tvdb|tmdb)-)", subfolder)

    if imdb_match and name_match:
        media_id = imdb_match.group(1)
        external_source = "imdb_id"
    elif tvdb_match and name_match:
        media_id = tvdb_match.group(1)
        external_source = "tvdb_id"
    elif tmdb_match and name_match:
        media_id = tmdb_match.group(1)
        external_source = "tmdb_id"
    else:
        return None

    media_name = name_match.group(1).strip()
    return media_id, media_name, external_source


def _process_subfolders(*, folder_path, folder, media_ids, folder_map):
    subfolders = os.listdir(folder_path)
    for subfolder in subfolders:
        subfolder_path = os.path.join(folder_path, subfolder)
        if os.path.isdir(subfolder_path):
            media_info = _extract_media_info_from_subfolder(subfolder=subfolder)
            if media_info:
                media_id, media_name, external_source = media_info
                media_ids.append((media_id, media_name, external_source))
                folder_map[media_id].append(folder)


from typing import List


def get_media_ids_from_plex(plex_url: str, plex_token: str, plex_libraries: List[str]):
    """
    Fetch media IDs from Plex libraries using the Plex API.
    Returns a list of (media_id, media_name, external_source) and a folder_map.
    """
    logger.info("Fetching media IDs from Plex API...")
    try:
        from plexapi.server import PlexServer
    except ImportError:
        logger.error(
            "plexapi is not installed. Please add 'plexapi' to requirements.txt."
        )
        raise

    plex = PlexServer(plex_url, plex_token)
    media_ids = []
    folder_map = defaultdict(list)

    for lib_name in plex_libraries:
        logger.info(f"Scanning Plex library: {lib_name}")
        try:
            library = plex.library.section(lib_name)
        except Exception as e:
            logger.error(f"Invalid Plex library section: {lib_name} ({e})")
            continue
        for item in library.all():
            tmdb_id = None
            imdb_id = None
            tvdb_id = None
            media_name = item.title

            for guid in item.guids:
                if "themoviedb" in guid.id:
                    tmdb_id = guid.id.split("://")[1].split("?")[0]
                elif "imdb" in guid.id:
                    imdb_id = guid.id.split("://")[1].split("?")[0]
                elif "thetvdb" in guid.id:
                    tvdb_id = guid.id.split("://")[1].split("?")[0]

            if tmdb_id:
                media_ids.append((tmdb_id, media_name, "tmdb_id"))
                folder_map[tmdb_id].append(lib_name)
            elif imdb_id:
                media_ids.append((imdb_id, media_name, "imdb_id"))
                folder_map[imdb_id].append(lib_name)
            elif tvdb_id:
                media_ids.append((tvdb_id, media_name, "tvdb_id"))
                folder_map[tvdb_id].append(lib_name)
            else:
                logger.warning(
                    f"No known ID found for '{media_name}' in Plex library '{lib_name}'"
                )

    logger.info(f"Found {len(media_ids)} media IDs from Plex.")
    return media_ids, folder_map


def get_media_ids(
    *,
    root_folder=None,
    selected_folders=None,
    plex_url=None,
    plex_token=None,
    plex_libraries=None,
):
    """
    Fetch media IDs using Plex API if configured, otherwise fallback to folder scan.
    """
    if plex_url and plex_token and plex_libraries and len(plex_libraries) > 0:
        return get_media_ids_from_plex(plex_url, plex_token, plex_libraries)
    if (
        plex_url
        and plex_token
        and root_folder
        and (not plex_libraries or len(plex_libraries) == 0)
    ):
        try:
            from plexapi.server import PlexServer

            plex = PlexServer(plex_url, plex_token)
            available = [section.title for section in plex.library.sections()]
            logger.info("Available Plex libraries:")
            for lib in available:
                logger.info(f"  - {lib}")
            logger.warning(
                "No Plex libraries specified. Please set 'plex_libraries' in your config or CLI. Using root_folder instead."
            )
        except Exception as e:
            logger.error(f"Could not connect to Plex to list libraries: {e}")
            logger.warning("Using root_folder instead.")

    if not root_folder:
        logger.error("No Plex config or root_folder provided. Nothing to do. Exiting.")
        exit(1)
    logger.info("Fetching media IDs from folder names...")
    validate_path(path=root_folder, description="Root folder")

    media_ids = []
    folder_map = defaultdict(list)
    root_folders = root_folder if isinstance(root_folder, list) else [root_folder]

    for root in root_folders:
        if not root:
            continue
        folders_to_search = selected_folders if selected_folders else os.listdir(root)

        for folder in folders_to_search:
            logger.debug(f"Searching folder: {folder}")
            folder_path = os.path.join(root, folder)
            if os.path.isdir(folder_path):
                _process_subfolders(
                    folder_path=folder_path,
                    folder=folder,
                    media_ids=media_ids,
                    folder_map=folder_map,
                )

    logger.info(f"Found media IDs: {media_ids}")
    return media_ids, folder_map


def _check_direct_tmdb_api(*, media_id, api_key):
    logger.info(f"Using TMDB ID {media_id} directly.")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "accept": "application/json",
    }

    tv_url = f"https://api.themoviedb.org/3/tv/{media_id}"
    movie_url = f"https://api.themoviedb.org/3/movie/{media_id}"
    tv_response = movie_response = None

    try:
        tv_response = requests.get(tv_url, headers=headers)
    except Exception as e:
        logger.debug(f"Error checking TV endpoint for TMDB ID {media_id}: {e}")

    try:
        movie_response = requests.get(movie_url, headers=headers)
    except Exception as e:
        logger.debug(f"Error checking movie endpoint for TMDB ID {media_id}: {e}")

    tv_exists = tv_response is not None and tv_response.status_code == 200
    movie_exists = movie_response is not None and movie_response.status_code == 200

    return tv_exists, movie_exists, tv_response, movie_response


def _resolve_direct_tmdb_conflict(*, media_id, media_name, tv_response, movie_response):
    logger.warning(
        f"TMDB ID {media_id} exists as both movie and TV show. Using media name to decide."
    )

    if not media_name:
        logger.info("No media name provided. Defaulting to TV show.")
        return media_id, "tv"

    tv_data = tv_response.json()
    movie_data = movie_response.json()

    tv_title = tv_data.get("name", "")
    movie_title = movie_data.get("title", "")

    tv_score = calculate_title_similarity(title1=media_name, title2=tv_title)
    movie_score = calculate_title_similarity(title1=media_name, title2=movie_title)

    logger.info(
        f"Title match scores - TV: '{tv_title}' ({tv_score:.2f}) vs Movie: '{movie_title}' ({movie_score:.2f})"
    )

    if tv_score > movie_score:
        logger.info(f"Selected TV show '{tv_title}' based on title similarity")
        return media_id, "tv"
    else:
        logger.info(f"Selected movie '{movie_title}' based on title similarity")
        return media_id, "movie"


def _query_external_id(*, media_id, external_source, api_key):
    logger.info(f"Fetching TMDB ID for {external_source} {media_id} from TMDB API...")
    url = f"https://api.themoviedb.org/3/find/{media_id}?external_source={external_source}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "accept": "application/json",
    }

    response = requests.get(url, headers=headers)
    response.raise_for_status()
    data = response.json()

    return data.get("movie_results", []), data.get("tv_results", [])


def _resolve_external_id_conflict(
    *, media_id, external_source, media_name, movie_result, tv_result
):
    logger.warning(f"{external_source} {media_id} matches both movie and TV show.")

    if media_name:
        tv_title = tv_result.get("name", "")
        movie_title = movie_result.get("title", "")

        tv_score = calculate_title_similarity(title1=media_name, title2=tv_title)
        movie_score = calculate_title_similarity(title1=media_name, title2=movie_title)

        logger.info(
            f"Title match scores - TV: '{tv_title}' ({tv_score:.2f}) vs Movie: '{movie_title}' ({movie_score:.2f})"
        )

        if tv_score > movie_score:
            logger.info(f"Selected TV show '{tv_title}' based on title similarity")
            return tv_result["id"], "tv"
        else:
            logger.info(f"Selected movie '{movie_title}' based on title similarity")
            return movie_result["id"], "movie"
    else:
        movie_confidence = movie_result.get("vote_count", 0) * 2 + movie_result.get(
            "popularity", 0
        )
        tv_confidence = tv_result.get("vote_count", 0) * 2 + tv_result.get(
            "popularity", 0
        )

        if tv_confidence > movie_confidence:
            logger.info(
                f"Selecting TV show (confidence score: {tv_confidence:.2f} vs {movie_confidence:.2f})"
            )
            return tv_result["id"], "tv"
        else:
            logger.info(
                f"Selecting movie (confidence score: {movie_confidence:.2f} vs {tv_confidence:.2f})"
            )
            return movie_result["id"], "movie"


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def fetch_tmdb_id(*, media_id, external_source, api_key, cache, media_name=None):
    if media_id in cache:
        logger.info(f"Fetching TMDB ID for {external_source} {media_id} from cache.")
        return cache[media_id]

    if external_source == "tmdb_id":
        tv_exists, movie_exists, tv_response, movie_response = _check_direct_tmdb_api(
            media_id=media_id, api_key=api_key
        )

        if tv_exists and movie_exists:
            return _resolve_direct_tmdb_conflict(
                media_id=media_id,
                media_name=media_name,
                tv_response=tv_response,
                movie_response=movie_response,
            )
        elif tv_exists:
            logger.info(f"TMDB ID {media_id} identified as TV show.")
            return media_id, "tv"
        elif movie_exists:
            logger.info(f"TMDB ID {media_id} identified as movie.")
            return media_id, "movie"
        else:
            logger.error(f"TMDB ID {media_id} not found as movie or TV show.")
            return None, None

    movie_results, tv_results = _query_external_id(
        media_id=media_id, external_source=external_source, api_key=api_key
    )

    if movie_results and tv_results:
        tmdb_id, media_type = _resolve_external_id_conflict(
            media_id=media_id,
            external_source=external_source,
            media_name=media_name,
            movie_result=movie_results[0],
            tv_result=tv_results[0],
        )
    elif movie_results:
        tmdb_id = movie_results[0]["id"]
        media_type = "movie"
    elif tv_results:
        tmdb_id = tv_results[0]["id"]
        media_type = "tv"
    else:
        tmdb_id, media_type = None, None

    cache[media_id] = (tmdb_id, media_type)
    logger.info(
        f"TMDB ID for {external_source} {media_id}: {tmdb_id}, Media Type: {media_type}"
    )
    return tmdb_id, media_type


def calculate_title_similarity(*, title1, title2):
    if not title1 or not title2:
        return 0

    title1 = re.sub(r"[^\w\s]", "", title1.lower())
    title2 = re.sub(r"[^\w\s]", "", title2.lower())

    words1 = set(title1.split())
    words2 = set(title2.split())

    intersection = len(words1.intersection(words2))
    union = len(words1.union(words2))

    if union == 0:
        return 0

    return intersection / union


def _get_media_url_and_texts(*, media_type, tmdb_id):
    base_url = "https://mediux.pro"
    if media_type == "movie":
        url = f"{base_url}/movies/{tmdb_id}"
        updating_text = "Updating movie data"
        success_text = "Movie updated successfully"
    else:
        url = f"{base_url}/shows/{tmdb_id}"
        updating_text = "Updating show data"
        success_text = "Show updated successfully"
    return url, updating_text, success_text


def _wait_for_update_completion(
    *, driver, updating_text, success_text, media_type, tmdb_id
):
    try:
        update_toast_xpath = (
            f"//li[contains(@class, 'toast')]//div[contains(text(), '{updating_text}')]"
        )
        success_toast_xpath = (
            f"//li[contains(@class, 'toast')]//div[contains(text(), '{success_text}')]"
        )

        logger.debug(f"Checking page status for {media_type} {tmdb_id}...")

        update_elements = driver.find_elements(By.XPATH, update_toast_xpath)
        success_elements = driver.find_elements(By.XPATH, success_toast_xpath)

        if update_elements:
            toast_text = update_elements[0].text
            logger.info(f"Page updating: '{toast_text}'")
            logger.info(f"Waiting for update completion for {media_type} {tmdb_id}...")

            WebDriverWait(driver, 30).until(
                lambda d: (len(d.find_elements(By.XPATH, update_toast_xpath)) == 0)
                or (len(d.find_elements(By.XPATH, success_toast_xpath)) > 0)
            )

            success_elements = driver.find_elements(By.XPATH, success_toast_xpath)
            if success_elements:
                logger.info(f"Update successful: '{success_elements[0].text}'")
            else:
                logger.info(f"Update process completed for {media_type} {tmdb_id}")

            sleep(1)
        else:
            if success_elements:
                logger.info(f"Update successful: '{success_elements[0].text}'")
            else:
                logger.debug(f"No update needed for {media_type} {tmdb_id}")

    except Exception as e:
        logger.warning(f"Error while waiting for update process: {e}")
        take_screenshot(driver=driver, name=f"error_wait_update_{media_type}_{tmdb_id}")


def _wait_for_refresh_completion(*, driver, media_type, tmdb_id):
    try:
        logger.debug(f"Checking for refresh operations on {media_type} {tmdb_id}...")

        refresh_spinner_xpath = "//svg[contains(@class, 'lucide-refresh-cw') and contains(@class, 'animate-spin')]"
        spinner_elements = driver.find_elements(By.XPATH, refresh_spinner_xpath)

        if spinner_elements:
            logger.info(f"Page status: Refresh in progress for {media_type} {tmdb_id}")
            logger.info(
                f"Detected refresh operation for {media_type} {tmdb_id}, waiting for completion..."
            )

            WebDriverWait(driver, 30).until(
                lambda d: len(d.find_elements(By.XPATH, refresh_spinner_xpath)) == 0
            )

            logger.info(f"Page status: Refresh completed for {media_type} {tmdb_id}")
            sleep(1)
        else:
            logger.debug(
                f"Page status: No refresh operation detected for {media_type} {tmdb_id}"
            )

    except Exception as e:
        logger.warning(f"Error while waiting for refresh spinner: {e}")
        take_screenshot(
            driver=driver, name=f"error_wait_refresh_{media_type}_{tmdb_id}"
        )


def _find_yaml_button(*, driver, yaml_xpath, preferred_users, excluded_users=None):
    yaml_button = None
    all_yaml_buttons = WebDriverWait(driver, 10).until(
        EC.presence_of_all_elements_located((By.XPATH, yaml_xpath))
    )

    if not all_yaml_buttons:
        logger.warning("No YAML buttons found on the page.")
        return None

    if excluded_users:
        logger.info(f"Excluding users: {', '.join(excluded_users)}")
        filtered_buttons = []
        for button in all_yaml_buttons:
            try:
                ancestor_div = button.find_element(
                    By.XPATH,
                    "./ancestor::div[contains(@class, 'flex') and .//a[contains(@href, '/user/')]]",
                )
                user_link_element = ancestor_div.find_element(
                    By.XPATH, ".//a[contains(@href, '/user/')]"
                )
                user_href = user_link_element.get_attribute("href")
                if user_href:
                    username_match = re.search(r"/user/([^/]+)", user_href)
                    if username_match:
                        username = username_match.group(1)
                        if username.lower() not in [
                            ex_user.lower() for ex_user in excluded_users
                        ]:
                            filtered_buttons.append(button)
                        else:
                            logger.debug(f"Excluding YAML button from user: {username}")
                    else:
                        filtered_buttons.append(button)
                else:
                    filtered_buttons.append(button)
            except Exception:
                filtered_buttons.append(button)
        all_yaml_buttons = filtered_buttons
        if not all_yaml_buttons:
            logger.warning("No YAML buttons left after filtering excluded users.")
            return None

    if preferred_users and len(preferred_users) > 0:
        logger.info(
            f"Searching for YAML from preferred users: {', '.join(preferred_users)}"
        )
        for user in preferred_users:
            for button in all_yaml_buttons:
                try:
                    ancestor_div = button.find_element(
                        By.XPATH,
                        "./ancestor::div[contains(@class, 'flex') and .//a[contains(@href, '/user/')]]",
                    )
                    user_link_element = ancestor_div.find_element(
                        By.XPATH, f".//a[@href='/user/{user.lower()}']"
                    )
                    user_button_in_link = user_link_element.find_element(
                        By.XPATH, f"./button[contains(., '{user}')]"
                    )
                    if user_button_in_link:
                        logger.info(f"Using YAML from preferred user: {user}")
                        yaml_button = button
                        break
                except Exception:
                    continue
            if yaml_button:
                break

    if not yaml_button and all_yaml_buttons:
        yaml_button = all_yaml_buttons[0]
        logger.debug("Using first available YAML button (after exclusions).")
    elif not yaml_button:
        logger.warning(
            "No suitable YAML button found after considering preferences and exclusions."
        )

    return yaml_button


def scrape_mediux(
    *,
    driver,
    tmdb_id,
    media_type,
    retry_on_yaml_failure=False,
    preferred_users=None,
    excluded_users=None,
):
    logger.info(f"Scraping Mediux for TMDB ID {tmdb_id}, Media Type: {media_type}")
    url, updating_text, success_text = _get_media_url_and_texts(
        media_type=media_type, tmdb_id=tmdb_id
    )

    try:
        driver.get(url)
    except Exception as e:
        logger.error(f"An error occurred during driver.get({url}): {e}")
        raise

    logger.debug(f"Navigated to URL: {url}")
    yaml_xpath = "//button[span[contains(text(), 'YAML')]]"
    sleep(5)
    logger.debug("Waited for page to load")

    try:
        page_title = driver.title
        logger.debug(f"Page title: {page_title}")

        toast_elements = driver.find_elements(
            By.XPATH, "//li[contains(@class, 'toast')]"
        )
        if toast_elements:
            logger.info(f"Found {len(toast_elements)} toast notifications on the page")
            for i, toast in enumerate(toast_elements):
                logger.debug(f"Toast {i+1} text: {toast.text}")
    except Exception as e:
        logger.debug(f"Error getting page info: {e}")

    _wait_for_update_completion(
        driver=driver,
        updating_text=updating_text,
        success_text=success_text,
        media_type=media_type,
        tmdb_id=tmdb_id,
    )

    _wait_for_refresh_completion(driver=driver, media_type=media_type, tmdb_id=tmdb_id)

    try:
        logger.debug(f"Looking for YAML button for {media_type} {tmdb_id}...")
        yaml_button = _find_yaml_button(
            driver=driver,
            yaml_xpath=yaml_xpath,
            preferred_users=preferred_users,
            excluded_users=excluded_users,
        )
        if not yaml_button:
            logger.warning(
                f"No suitable YAML button found for TMDB ID {tmdb_id} after filtering."
            )
            return ""
        driver.execute_script("arguments[0].scrollIntoView(true);", yaml_button)
        yaml_button.click()
        logger.info(f"Extracting YAML data for {media_type} {tmdb_id}")

        yaml_element = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.XPATH, "//code"))
        )
        WebDriverWait(driver, 20).until(
            lambda d: yaml_element.get_attribute("innerText").strip() != ""  # type: ignore
        )
        yaml_data = yaml_element.get_attribute("innerText")

        if yaml_data is None:
            logger.warning(
                f"YAML content for TMDB ID {tmdb_id} was unexpectedly None after waiting. "
                "This might indicate an issue with the page or element structure. Returning empty."
            )
            return ""

        yaml_len = len(yaml_data)
        logger.info(f"YAML data loaded successfully ({yaml_len} characters)")
        return yaml_data
    except Exception as e:
        if not driver.find_elements(By.XPATH, yaml_xpath):
            logger.warning(f"YAML button not found for TMDB ID {tmdb_id}")
            return ""

        if retry_on_yaml_failure:
            logger.warning(
                f"YAML button found but an error occurred. Retrying for TMDB ID {tmdb_id}."
            )
            driver.refresh()
            logger.debug(f"Page refreshed for TMDB ID {tmdb_id}")
            sleep(5)
            return scrape_mediux(
                driver=driver,
                tmdb_id=tmdb_id,
                media_type=media_type,
                retry_on_yaml_failure=False,
                preferred_users=preferred_users,
                excluded_users=excluded_users,
            )

        take_screenshot(driver=driver, name=f"error_scraping_tmdb_{tmdb_id}")
        logger.error(
            f"Error scraping TMDB ID {tmdb_id}. This may be normal if no YAML is available."
        )
        return ""


def extract_set_urls(*, yaml_data):
    set_urls = set()
    lines = yaml_data.split("\n")
    for line in lines:
        match = re.search(r"#.*(https://mediux.pro/sets/\d+)", line)
        if match:
            set_urls.add(match.group(1))
    return set_urls


def login_mediux(*, driver, username, password, nickname):
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
        take_screenshot(driver=driver, name="error_login")
        logger.error(f"Failed to log into Mediux: {e}")
        raise


def load_cache(*, cache_file):
    if os.path.exists(cache_file):
        logger.info(f"Loading cache from {cache_file}...")
        with open(cache_file, "rb") as f:
            cache = pickle.load(f)
        logger.info("Cache loaded successfully.")
        return cache
    logger.info("No cache file found. Initializing new cache.")
    return {}


def save_cache(*, updated_cache, cache_file):
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


def load_bulk_data(*, bulk_data_file, only_set_urls=False):
    if os.path.exists(bulk_data_file):
        logger.info(f"Loading bulk data from {bulk_data_file}...")
        with open(bulk_data_file, "r", encoding="utf-8") as f:
            if only_set_urls:
                bulk_data = extract_set_urls(yaml_data=f.read())
                logger.info(f"Loaded {len(bulk_data)} set URLs from bulk data.")
            else:
                bulk_data = yaml.load(f)
                logger.info("Bulk data loaded successfully.")

        if not bulk_data:
            logger.warning("No data found in bulk data file.")
            return set() if only_set_urls else {"metadata": {}}

        return bulk_data

    logger.debug(f"Bulk data file {bulk_data_file} not found.")
    return set() if only_set_urls else {"metadata": {}}


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def check_series_status(*, media_name, sonarr_api_key, sonarr_endpoint, tmdb_id=None):
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
        if tmdb_id:
            for series in data:
                if series.get("tmdbId") == tmdb_id:
                    logger.info(
                        f"Found matching series for '{media_name}' by TMDB ID: {tmdb_id}"
                    )
                    tvdb_id = series.get("tvdbId")
                    ended = series.get("ended")
                    logger.info(
                        f"Series status for {media_name}: TVDB ID={tvdb_id}, Ended={ended}."
                    )
                    return tvdb_id, ended
            logger.warning(
                f"No series with TMDB ID {tmdb_id} found for '{media_name}'. Falling back to first result."
            )

        series_info = data[0]
        tvdb_id = series_info.get("tvdbId")
        ended = series_info.get("ended")
        logger.info(
            f"Series status for {media_name} (from first result): TVDB ID={tvdb_id}, Ended={ended}."
        )
        return tvdb_id, ended
    logger.warning(f"No series information found for {media_name}.")
    return None, None


def _collect_existing_urls():
    existing_urls = set()

    root_folders_list = (
        root_folder_global
        if isinstance(root_folder_global, list)
        else [root_folder_global]
    )
    folder_cache = {root: os.listdir(root) for root in root_folders_list}

    for root, folders_in_root in folder_cache.items():
        for folder_item in folders_in_root:
            folder_path = os.path.join(root, folder_item)
            if os.path.isdir(folder_path):
                file_path = f"./out/kometa/{folder_item}_data.yml"
                existing_urls.update(
                    load_bulk_data(bulk_data_file=file_path, only_set_urls=True)
                )

    return existing_urls


def _update_data_file(*, folder_name, data_to_write, existing_urls_set):
    import re

    safe_folder = re.sub(r"[^\w\-]", "_", folder_name.lower())
    file_name = f"./out/kometa/{safe_folder}_data.yml"
    total_urls = 0

    file_data = {"metadata": {}}
    if os.path.exists(file_name):
        with open(file_name, "r", encoding="utf-8") as f:
            loaded_data = yaml.load(f)
            if loaded_data and "metadata" in loaded_data:
                file_data = loaded_data
            elif loaded_data:
                file_data["metadata"] = loaded_data

    for _, item_yaml_data in data_to_write.items():
        parsed_item_yaml = yaml.load(item_yaml_data)
        if parsed_item_yaml:
            file_data["metadata"].update(parsed_item_yaml)
        item_urls = extract_set_urls(yaml_data=item_yaml_data)
        existing_urls_set.update(item_urls)
        total_urls += len(item_urls)

    with open(file_name, "w", encoding="utf-8") as f:
        yaml.dump(file_data, f)

    return file_name, total_urls


def _copy_to_output_dir_local():
    if not output_dir_global:
        return

    logger.info(f"Copying files to {output_dir_global}...")
    if not os.path.exists(output_dir_global):
        os.makedirs(output_dir_global)
        logger.debug(f"Created output directory {output_dir_global}.")

    kometa_out_dir = "./out/kometa"
    if not os.path.exists(kometa_out_dir):
        logger.warning(
            f"Source directory {kometa_out_dir} does not exist. Nothing to copy."
        )
        return

    for filename in os.listdir(kometa_out_dir):
        src_file = os.path.join(kometa_out_dir, filename)
        dst_file = os.path.join(output_dir_global, filename)
        shutil.copy2(src_file, dst_file)
    logger.info(f"Files copied to {output_dir_global}.")


def write_data_to_files():
    global new_data, cache, root_folder_global

    if not root_folder_global:
        logger.error("Root folder is not set. Cannot write data.")
        return

    validate_path(path=root_folder_global, description="Root folder")
    logger.info("Writing data to files...")

    os.makedirs("./out/kometa", exist_ok=True)
    logger.debug("Ensured output directory './out/kometa' exists.")

    existing_urls = _collect_existing_urls()

    updated_files_list = []

    for folder_name, data_for_folder in new_data.items():
        file_name_str, _ = _update_data_file(
            folder_name=folder_name,
            data_to_write=data_for_folder,
            existing_urls_set=existing_urls,
        )
        updated_files_list.append(file_name_str)

    if updated_files_list:
        logger.info(
            f"Updated {len(updated_files_list)} files: {', '.join(updated_files_list)}"
        )
    else:
        logger.info("No data files were updated.")
    logger.info(f"Collected a total of {len(existing_urls)} unique set URLs.")

    with open("./out/ppsh-bulk.txt", "w", encoding="utf-8") as f:
        for url in sorted(list(existing_urls)):
            f.write(url + "\n")
    logger.info("Set URLs updated in './out/ppsh-bulk.txt'.")

    save_cache(updated_cache=cache, cache_file=CACHE_FILE)
    logger.info("Data writing completed.")
    _copy_to_output_dir_local()


def send_discord_notification(*, webhook_url, message):
    if not webhook_url:
        logger.debug("Discord webhook URL not configured. Skipping notification.")
        return

    if not message:
        logger.debug("No message content to send to Discord. Skipping notification.")
        return

    logger.info(f"Sending notification to Discord: {message[:100]}...")
    payload = {"content": message}
    try:
        response = requests.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()
        logger.info("Discord notification sent successfully.")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send Discord notification: {e}")


def _fetch_tv_series_details(
    *,
    media_name,
    sonarr_api_key,
    sonarr_endpoint,
    tmdb_id,
    external_source_id,
    external_source_type,
    logger,
):
    tvdb_id, ended = None, None
    try:
        tvdb_id, ended = check_series_status(
            media_name=media_name,
            sonarr_api_key=sonarr_api_key,
            sonarr_endpoint=sonarr_endpoint,
            tmdb_id=tmdb_id,
        )
        if not tvdb_id and external_source_type == "tvdb_id":
            tvdb_id = int(external_source_id)
            logger.info(
                f"Using TVDB ID {tvdb_id} from folder name for '{media_name}' as Sonarr lookup failed."
            )
        elif not tvdb_id:
            logger.warning(
                f"Could not determine TVDB ID for TV show '{media_name}' (TMDB: {tmdb_id}) via Sonarr."
            )
    except Exception as e:
        logger.error(
            f"Failed to check series status for '{media_name}' (TMDB: {tmdb_id}): {e}"
        )
    return tvdb_id, ended


def _get_existing_yaml_details(
    *,
    media_id_from_folder,
    media_type,
    tmdb_id,
    tvdb_id_for_tv,
    folder_map,
    folder_bulk_data,
    logger,
):
    old_parsed_yaml_content = None
    is_already_in_yaml = False
    key_for_existing_yaml_log = None

    if media_type == "tv":
        key_for_existing_yaml_log = tvdb_id_for_tv
    elif media_type == "movie":
        key_for_existing_yaml_log = tmdb_id

    if key_for_existing_yaml_log:
        for f_name_map in folder_map.get(media_id_from_folder, []):
            f_bulk_data = folder_bulk_data.get(f_name_map, {})
            metadata = f_bulk_data.get("metadata", {})

            content_found = False
            if key_for_existing_yaml_log in metadata:
                old_parsed_yaml_content = metadata[key_for_existing_yaml_log]
                content_found = True
            elif str(key_for_existing_yaml_log) in metadata:
                old_parsed_yaml_content = metadata[str(key_for_existing_yaml_log)]
                content_found = True

            if content_found:
                is_already_in_yaml = True
                logger.debug(
                    f"Found existing YAML for {media_type} ID {key_for_existing_yaml_log} in folder {f_name_map}"
                )
                break
    return old_parsed_yaml_content, is_already_in_yaml, key_for_existing_yaml_log


def _should_skip_scraping(
    *,
    media_name,
    media_type,
    tmdb_id,
    key_for_log,
    ended_status,
    is_in_yaml,
    process_all_flag,
    logger,
):
    if is_in_yaml and not process_all_flag:
        if media_type == "tv":
            if ended_status:
                logger.info(
                    f"Skipping ended TV show '{media_name}' (ID: {key_for_log}, TMDB: {tmdb_id}) as it's in YAML and not processing all."
                )
                return True
            else:
                logger.info(
                    f"Ongoing TV show '{media_name}' (ID: {key_for_log}, TMDB: {tmdb_id}) is in YAML. Will re-scrape for comparison."
                )
        elif media_type == "movie":
            logger.info(
                f"Skipping movie '{media_name}' (TMDB: {key_for_log}) as it's in YAML and not processing all."
            )
            return True
    return False


def _extract_comparable_content_from_scraped_yaml(
    *,
    raw_yaml_data,
    media_name,
    media_type,
    tmdb_id,
    tvdb_id_for_tv,
    yaml_parser,
    logger,
):
    if not raw_yaml_data:
        return None
    try:
        parsed_wrapper = yaml_parser.load(raw_yaml_data)
        if not parsed_wrapper or not isinstance(parsed_wrapper, dict):
            logger.error(
                f"Parsed new YAML for '{media_name}' (TMDB: {tmdb_id}) is not a valid dictionary or is empty."
            )
            return None

        expected_key = tvdb_id_for_tv if media_type == "tv" else tmdb_id

        actual_key_found = None
        if expected_key:
            if expected_key in parsed_wrapper:
                actual_key_found = expected_key
            elif str(expected_key) in parsed_wrapper:
                actual_key_found = str(expected_key)

        if actual_key_found:
            return parsed_wrapper[actual_key_found]
        elif len(parsed_wrapper) == 1:
            first_key = list(parsed_wrapper.keys())[0]
            logger.warning(
                f"Scraped YAML for '{media_name}' (TMDB: {tmdb_id}) was keyed by '{first_key}' instead of expected '{expected_key}'. Using content from '{first_key}'."
            )
            return parsed_wrapper[first_key]
        else:
            logger.error(
                f"Could not find expected key '{expected_key}' or a single key in newly parsed YAML for '{media_name}': {list(parsed_wrapper.keys())}"
            )
            return None
    except Exception as e:
        logger.error(
            f"Failed to parse or process newly scraped YAML for '{media_name}' (TMDB: {tmdb_id}): {e}"
        )
        return None


def _compare_yaml_and_log_changes(
    *,
    media_name,
    media_type,
    id_for_logging,
    old_content,
    new_content_to_compare,
    logger,
):
    if new_content_to_compare is None:
        logger.warning(
            f"No new YAML content to compare for '{media_name}' (ID: {id_for_logging})."
        )
        return False

    std_new_content = to_standard_dict(item=new_content_to_compare)
    id_type_str = "TVDB" if media_type == "tv" else "TMDB"

    if old_content is None:
        logger.info(
            f"New {media_type} entry for '{media_name}' ({id_type_str}: {id_for_logging}). Adding to updated titles."
        )
        return True

    std_old_content = to_standard_dict(item=old_content)
    if std_new_content != std_old_content:
        logger.info(
            f"YAML data for {media_type} '{media_name}' ({id_type_str}: {id_for_logging}) has changed."
        )
        return True
    else:
        logger.info(
            f"YAML data for {media_type} '{media_name}' ({id_type_str}: {id_for_logging}) is unchanged."
        )
        return False


def _preprocess_yaml_string(*, yaml_string: str, logger) -> tuple[str, bool]:
    """
    Pre-processes a raw YAML string to fix structural issues where multiple
    'episodes:' blocks appear directly under 'seasons:'. This is invalid YAML.
    The function uses a targeted regex to wrap each misplaced 'episodes:' block
    in a numbered season key.

    Returns:
        A tuple containing the processed YAML string and a boolean indicating
        if any changes were made.
    """
    if "seasons:" not in yaml_string or "episodes:" not in yaml_string:
        return yaml_string, False

    seasons_match = re.search(r"^(?P<indent>\s*)seasons:", yaml_string, re.MULTILINE)
    if not seasons_match:
        return yaml_string, False

    seasons_indent = seasons_match.group("indent")
    valid_season_indent = seasons_indent + "  "
    misplaced_episode_indent = valid_season_indent + "  "

    regex = re.compile(f"^{re.escape(misplaced_episode_indent)}episodes:", re.MULTILINE)
    matches = regex.findall(yaml_string)

    if not matches:
        return yaml_string, False

    season_count = 1

    def season_replacer(match):
        nonlocal season_count
        replacement = f"{valid_season_indent}{season_count}:\n{match.group(0)}"
        season_count += 1
        return replacement

    logger.info(
        f"Preprocessing YAML to fix {len(matches)} misplaced 'episodes' blocks."
    )
    processed_yaml = regex.sub(season_replacer, yaml_string)

    return processed_yaml, True


def _process_single_media_item(
    *,
    media_id_from_folder,
    media_name,
    external_source_type,
    driver,
    api_key,
    sonarr_api_key,
    sonarr_endpoint,
    process_all,
    retry_on_yaml_failure,
    preferred_users,
    excluded_users,
    folder_map_for_media,
    updated_titles_list,
    fixed_titles_list,
    disable_season_fix=False,
):
    global cache, new_data, folder_bulk_data, yaml

    if external_source_type == "tmdb_id":
        tmdb_id = media_id_from_folder
        lib_names = folder_map_for_media.get(media_id_from_folder, [])
        media_type = None
        if lib_names:
            lib_name = lib_names[0].lower()
            if "movie" in lib_name:
                media_type = "movie"
            elif "tv" in lib_name or "show" in lib_name or "series" in lib_name:
                media_type = "tv"
        if not media_type:
            try:
                tmdb_id, media_type = fetch_tmdb_id(
                    media_id=media_id_from_folder,
                    external_source=external_source_type,
                    api_key=api_key,
                    cache=cache,
                    media_name=media_name,
                )
            except Exception as e:
                logger.error(
                    f"Failed to determine media type for TMDB ID {media_id_from_folder} ('{media_name}'): {e}"
                )
                return
    else:
        try:
            tmdb_id, media_type = fetch_tmdb_id(
                media_id=media_id_from_folder,
                external_source=external_source_type,
                api_key=api_key,
                cache=cache,
                media_name=media_name,
            )
        except Exception as e:
            logger.error(
                f"Failed to fetch TMDB ID for {external_source_type} {media_id_from_folder} ('{media_name}'): {e}"
            )
            return

        if not tmdb_id:
            logger.debug(
                f"No TMDB ID found for {media_id_from_folder} ('{media_name}', {external_source_type}), skipping."
            )
            return

    tvdb_id_for_tv, ended_status = None, None
    if media_type == "tv":
        tvdb_id_for_tv, ended_status = _fetch_tv_series_details(
            media_name=media_name,
            sonarr_api_key=sonarr_api_key,
            sonarr_endpoint=sonarr_endpoint,
            tmdb_id=tmdb_id,
            external_source_id=media_id_from_folder,
            external_source_type=external_source_type,
            logger=logger,
        )

    old_yaml_content, is_already_in_yaml, key_for_log = _get_existing_yaml_details(
        media_id_from_folder=media_id_from_folder,
        media_type=media_type,
        tmdb_id=tmdb_id,
        tvdb_id_for_tv=tvdb_id_for_tv,
        folder_map=folder_map_for_media,
        folder_bulk_data=folder_bulk_data,
        logger=logger,
    )

    if _should_skip_scraping(
        media_name=media_name,
        media_type=media_type,
        tmdb_id=tmdb_id,
        key_for_log=key_for_log,
        ended_status=ended_status,
        is_in_yaml=is_already_in_yaml,
        process_all_flag=process_all,
        logger=logger,
    ):
        return

    logger.info(
        f"Processing Media: '{media_name}' (Source ID: {media_id_from_folder}, TMDB ID: {tmdb_id}, TVDB ID: {tvdb_id_for_tv if tvdb_id_for_tv else 'N/A'}, Type: {media_type})"
    )

    new_raw_yaml = scrape_mediux(
        driver=driver,
        tmdb_id=tmdb_id,
        media_type=media_type,
        retry_on_yaml_failure=retry_on_yaml_failure,
        preferred_users=preferred_users,
        excluded_users=excluded_users,
    )
    if not new_raw_yaml:
        logger.warning(
            f"No YAML data found from Mediux for '{media_name}' (TMDB ID {tmdb_id})."
        )
        return

    if media_type == "tv":
        is_malformed = False
        try:
            yaml_check_parser = YAML()
            yaml_check_parser.allow_duplicate_keys = True
            parsed_for_check = yaml_check_parser.load(new_raw_yaml)

            if parsed_for_check and isinstance(parsed_for_check, dict):
                media_id_key = next(iter(parsed_for_check))
                content = parsed_for_check.get(media_id_key)

                if content and "seasons" in content:
                    seasons_node = content.get("seasons")
                    if seasons_node and seasons_node.get("episodes", None) is not None:
                        logger.info(
                            f"Detected malformed 'seasons' block for '{media_name}'."
                        )
                        is_malformed = True
                    else:
                        logger.info(f"YAML structure for '{media_name}' appears valid.")
                else:
                    logger.info(
                        f"YAML for '{media_name}' has no 'seasons' block or empty content, structure is considered valid."
                    )
            else:
                logger.warning(
                    f"Could not parse YAML for '{media_name}' into a dictionary for checking."
                )

        except Exception as e:
            logger.error(
                f"Error while checking YAML structure for '{media_name}': {e}",
                exc_info=True,
            )
            take_screenshot(driver=driver, name=f"error_yaml_structure_check_{tmdb_id}")

        if is_malformed and not disable_season_fix:
            new_raw_yaml, was_fixed = _preprocess_yaml_string(
                yaml_string=new_raw_yaml, logger=logger
            )
            if was_fixed:
                logger.info(f"YAML for '{media_name}' was successfully fixed.")
                log_id_str = (
                    f"TVDB: {tvdb_id_for_tv}" if tvdb_id_for_tv else f"TMDB: {tmdb_id}"
                )
                fixed_titles_list.append(f"{media_name} ({log_id_str})")
            else:
                logger.warning(
                    f"Preprocessing was triggered for '{media_name}' but no changes were made by the function."
                )
        elif is_malformed and disable_season_fix:
            logger.info(
                f"Malformed YAML detected for '{media_name}' but automatic fix is disabled."
            )

    new_comparable_content = _extract_comparable_content_from_scraped_yaml(
        raw_yaml_data=new_raw_yaml,
        media_name=media_name,
        media_type=media_type,
        tmdb_id=tmdb_id,
        tvdb_id_for_tv=tvdb_id_for_tv,
        yaml_parser=yaml,
        logger=logger,
    )

    if media_type == "tv" and new_comparable_content:
        try:
            parsed_yaml_data = yaml.load(new_raw_yaml)
            from io import StringIO

            string_stream = StringIO()
            yaml.dump(parsed_yaml_data, string_stream)
            new_raw_yaml = string_stream.getvalue()

            new_comparable_content = _extract_comparable_content_from_scraped_yaml(
                raw_yaml_data=new_raw_yaml,
                media_name=media_name,
                media_type=media_type,
                tmdb_id=tmdb_id,
                tvdb_id_for_tv=tvdb_id_for_tv,
                yaml_parser=yaml,
                logger=logger,
            )
        except Exception as e:
            logger.error(f"Failed to re-process TV YAML for '{media_name}': {e}")

    id_for_comp_log = (
        tvdb_id_for_tv if media_type == "tv" and tvdb_id_for_tv else tmdb_id
    )

    title_should_be_updated_flag = _compare_yaml_and_log_changes(
        media_name=media_name,
        media_type=media_type,
        id_for_logging=id_for_comp_log,
        old_content=old_yaml_content,
        new_content_to_compare=new_comparable_content,
        logger=logger,
    )

    if title_should_be_updated_flag:
        log_id_str = (
            f"TVDB: {tvdb_id_for_tv}"
            if media_type == "tv" and tvdb_id_for_tv
            else f"TMDB: {tmdb_id}"
        )
        updated_titles_list.append(f"{media_name} ({log_id_str})")

    for folder_name in folder_map_for_media.get(media_id_from_folder, []):
        new_data[folder_name][tmdb_id] = new_raw_yaml


def _initialize_and_login_driver(
    *,
    headless,
    profile_path,
    chromedriver_path,
    username,
    password,
    nickname,
):
    driver = init_driver(
        headless=headless,
        profile_path=profile_path,
        chromedriver_path=chromedriver_path,
    )
    try:
        login_mediux(
            driver=driver,
            username=username,
            password=password,
            nickname=nickname,
        )
        return driver
    except Exception as e:
        logger.error(f"Failed to login during driver re-initialization: {e}")
        if driver:
            driver.quit()
        raise


def run(
    *,
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
    retry_on_yaml_failure=False,
    preferred_users=None,
    excluded_users=None,
    disable_season_fix=False,
):
    global cache, new_data, folder_bulk_data, root_folder_global
    logger.info("Starting Mediux scraper...")

    if preferred_users:
        logger.info(f"Preferred users configured: {', '.join(preferred_users)}")
    if excluded_users:
        logger.info(f"Excluded users configured: {', '.join(excluded_users)}")

    validate_path(path=root_folder_global, description="Root folder")
    logger.info(f"Processing media from: {root_folder_global}")

    cache = load_cache(cache_file=CACHE_FILE)

    root_folders_list = (
        root_folder_global
        if isinstance(root_folder_global, list)
        else [root_folder_global]
    )
    per_folder_cache = {
        root_path: os.listdir(root_path) for root_path in root_folders_list
    }

    folder_bulk_data.clear()
    for root_path_item, folders_in_root in per_folder_cache.items():
        for folder_item in folders_in_root:
            if os.path.isdir(os.path.join(root_path_item, folder_item)):
                folder_bulk_data[folder_item] = load_bulk_data(
                    bulk_data_file=f"./out/kometa/{folder_item}_data.yml"
                )
    logger.debug(f"Loaded bulk data for folders: {list(folder_bulk_data.keys())}")

    media_ids_to_process, folder_map_for_media = get_media_ids(
        root_folder=root_folder_global,
        selected_folders=selected_folders,
        plex_url=globals().get("app_settings", {}).get("plex_url"),
        plex_token=globals().get("app_settings", {}).get("plex_token"),
        plex_libraries=globals().get("app_settings", {}).get("plex_libraries"),
    )
    logger.info(f"Media IDs to process: {len(media_ids_to_process)}")

    driver = None
    updated_titles_list = []
    fixed_titles_list = []
    new_data.clear()

    try:
        driver = _initialize_and_login_driver(
            headless=headless,
            profile_path=profile_path,
            chromedriver_path=chromedriver_path,
            username=username,
            password=password,
            nickname=nickname,
        )

        with logging_redirect_tqdm():
            for media_id_from_folder, media_name, external_source_type in tqdm(
                media_ids_to_process, desc="Processing media IDs"
            ):
                try:
                    _process_single_media_item(
                        media_id_from_folder=media_id_from_folder,
                        media_name=media_name,
                        external_source_type=external_source_type,
                        driver=driver,
                        api_key=api_key,
                        sonarr_api_key=sonarr_api_key,
                        sonarr_endpoint=sonarr_endpoint,
                        process_all=process_all,
                        retry_on_yaml_failure=retry_on_yaml_failure,
                        preferred_users=preferred_users,
                        excluded_users=excluded_users,
                        folder_map_for_media=folder_map_for_media,
                        updated_titles_list=updated_titles_list,
                        fixed_titles_list=fixed_titles_list,
                        disable_season_fix=disable_season_fix,
                    )
                except (ReadTimeoutError, TimeoutException):
                    logger.error(
                        "A timeout error occurred. Re-initializing WebDriver and logging in again."
                    )
                    if driver:
                        driver.quit()
                    driver = _initialize_and_login_driver(
                        headless=headless,
                        profile_path=profile_path,
                        chromedriver_path=chromedriver_path,
                        username=username,
                        password=password,
                        nickname=nickname,
                    )
    finally:
        logger.info("Quitting WebDriver...")
        if driver:
            driver.quit()
        logger.info("Script finished.")

        if updated_titles_list:
            logger.info("Updated Titles:")
            for title in updated_titles_list:
                logger.info(f"- {title}")
        else:
            logger.info("No titles were updated.")

        truly_fixed_and_updated = [
            title for title in fixed_titles_list if title in updated_titles_list
        ]

        if truly_fixed_and_updated:
            logger.info("Titles with Fixed YAML Structure:")
            for title in truly_fixed_and_updated:
                logger.info(f"- {title}")

        if updated_titles_list and discord_webhook_url_global:
            max_titles_per_message = 15
            num_titles = len(updated_titles_list)

            for i in range(0, num_titles, max_titles_per_message):
                chunk = updated_titles_list[i : i + max_titles_per_message]
                message_content = "Newly processed/updated titles:\n- " + "\n- ".join(
                    chunk
                )
                if (
                    num_titles > max_titles_per_message
                    and i + max_titles_per_message < num_titles
                ):
                    message_content += f"\n...and {num_titles - (i + max_titles_per_message)} more titles."
                elif num_titles > max_titles_per_message and i == 0:
                    message_content += f"\n(Showing first {max_titles_per_message} of {num_titles} titles)"

                send_discord_notification(
                    webhook_url=discord_webhook_url_global, message=message_content
                )

        if truly_fixed_and_updated and discord_webhook_url_global:
            message_content = (
                "The following TV shows had their YAML structure automatically fixed "
                "and may require manual review:\n- "
                + "\n- ".join(truly_fixed_and_updated)
            )
            send_discord_notification(
                webhook_url=discord_webhook_url_global, message=message_content
            )


def schedule_run(*, cron_expression, args_dict):
    logger.info(f"Scheduling script with cron expression: {cron_expression}")
    base_time = datetime.now()
    logger.info(f"Current time: {base_time}")
    logger.info(
        f"Environment Timezone: {os.environ.get('TZ', 'None is set, use the env from the docker compose or docker run to provide your TZ')}"
    )
    cron_iter = croniter.croniter(cron_expression, base_time)
    next_run_time = cron_iter.get_next(datetime)
    logger.info(f"Next scheduled run at: {next_run_time}")

    while True:
        now = datetime.now()
        if now >= next_run_time:
            logger.info("Scheduled run started...")
            try:
                run(**args_dict)
                write_data_to_files()
            except Exception as e:
                logger.error(f"Error during scheduled run: {e}")
            next_run_time = cron_iter.get_next(datetime)
            logger.info(f"Next scheduled run at: {next_run_time}")
        sleep(60)


def _resolve_config_value_helper(
    *,
    arg_val,
    env_var_name,
    conf_key,
    file_config,
    default_val=None,
    is_bool=False,
    is_list=False,
):
    if arg_val is not None:
        if is_bool:
            return bool(arg_val)
        return arg_val

    env_val = os.environ.get(env_var_name)
    if env_val is not None:
        if is_bool:
            return env_val.lower() in ["true", "1", "yes"]
        if is_list:
            return [item.strip() for item in env_val.split(",")] if env_val else []
        return env_val

    file_val = file_config.get(conf_key)
    if file_val is not None:
        return file_val

    return default_val


def _parse_arguments_and_load_config():
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
        help="Root folder(s) containing subfolders with media IDs. Can be a single path or multiple paths separated by commas.",
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
        help="Specific sub-folders within root_folder(s) to process (optional)",
    )
    parser.add_argument(
        "--headless",
        action=argparse.BooleanOptionalAction,
        help="Run Selenium in headless mode",
    )
    parser.add_argument(
        "--cron", type=str, help="Cron expression for scheduling the script"
    )
    parser.add_argument(
        "--output_dir", type=str, help="Directory to copy the output files to"
    )
    parser.add_argument(
        "--process_all",
        action=argparse.BooleanOptionalAction,
        help="Process all items regardless of existing data",
    )
    parser.add_argument(
        "--chromedriver_path", type=str, help="Path to the ChromeDriver executable"
    )
    parser.add_argument(
        "--retry_on_yaml_failure",
        action=argparse.BooleanOptionalAction,
        help="Retry scraping if YAML extraction fails initially",
    )
    parser.add_argument(
        "--preferred_users",
        nargs="*",
        help="List of preferred Mediux users for YAML data",
    )
    parser.add_argument(
        "--excluded_users",
        nargs="*",
        help="List of Mediux users to exclude for YAML data",
    )
    parser.add_argument(
        "--discord_webhook_url", type=str, help="Discord webhook URL for notifications"
    )
    parser.add_argument(
        "--copy_only",
        action="store_true",
        help="Only copy files to the output_dir and exit",
    )
    parser.add_argument(
        "--disable_season_fix",
        action="store_true",
        help="Disable automatic fix for malformed seasons YAML structure",
    )
    parser.add_argument(
        "--plex_url",
        type=str,
        help="Plex server URL (optional, enables Plex API mode if provided)",
    )
    parser.add_argument(
        "--plex_token",
        type=str,
        help="Plex API token (optional, enables Plex API mode if provided)",
    )
    parser.add_argument(
        "--plex_libraries",
        nargs="*",
        help="List of Plex library names to scan (optional, enables Plex API mode if provided)",
    )

    args = parser.parse_args()

    file_config = load_config(config_path=args.config_path)

    root_folder_val = _resolve_config_value_helper(
        arg_val=args.root_folder,
        env_var_name="ROOT_FOLDER",
        conf_key="root_folder",
        file_config=file_config,
    )
    if isinstance(root_folder_val, str):
        root_folder_val = [
            rf.strip() for rf in root_folder_val.split(",") if rf.strip()
        ]
    elif root_folder_val is None:
        root_folder_val = []

    app_config = {
        "config_path_val": args.config_path,
        "root_folder_val": root_folder_val,
        "api_key": _resolve_config_value_helper(
            arg_val=args.api_key,
            env_var_name="API_KEY",
            conf_key="api_key",
            file_config=file_config,
        ),
        "username": _resolve_config_value_helper(
            arg_val=args.username,
            env_var_name="USERNAME",
            conf_key="username",
            file_config=file_config,
        ),
        "password": _resolve_config_value_helper(
            arg_val=args.password,
            env_var_name="PASSWORD",
            conf_key="password",
            file_config=file_config,
        ),
        "nickname": _resolve_config_value_helper(
            arg_val=args.nickname,
            env_var_name="NICKNAME",
            conf_key="nickname",
            file_config=file_config,
        ),
        "profile_path": _resolve_config_value_helper(
            arg_val=args.profile_path,
            env_var_name="PROFILE_PATH",
            conf_key="profile_path",
            file_config=file_config,
            default_val="/profile",
        ),
        "sonarr_api_key": _resolve_config_value_helper(
            arg_val=args.sonarr_api_key,
            env_var_name="SONARR_API_KEY",
            conf_key="sonarr_api_key",
            file_config=file_config,
        ),
        "sonarr_endpoint": _resolve_config_value_helper(
            arg_val=args.sonarr_endpoint,
            env_var_name="SONARR_ENDPOINT",
            conf_key="sonarr_endpoint",
            file_config=file_config,
        ),
        "selected_folders": _resolve_config_value_helper(
            arg_val=args.folders,
            env_var_name="FOLDERS",
            conf_key="folders",
            file_config=file_config,
            default_val=[],
            is_list=True,
        ),
        "headless": _resolve_config_value_helper(
            arg_val=args.headless,
            env_var_name="HEADLESS",
            conf_key="headless",
            file_config=file_config,
            default_val=True,
            is_bool=True,
        ),
        "cron_expression": _resolve_config_value_helper(
            arg_val=args.cron,
            env_var_name="CRON_EXPRESSION",
            conf_key="cron",
            file_config=file_config,
        ),
        "output_dir_val": _resolve_config_value_helper(
            arg_val=args.output_dir,
            env_var_name="OUTPUT_DIR",
            conf_key="output_dir",
            file_config=file_config,
        ),
        "process_all": _resolve_config_value_helper(
            arg_val=args.process_all,
            env_var_name="PROCESS_ALL",
            conf_key="process_all",
            file_config=file_config,
            default_val=False,
            is_bool=True,
        ),
        "chromedriver_path": _resolve_config_value_helper(
            arg_val=args.chromedriver_path,
            env_var_name="CHROMEDRIVER_PATH",
            conf_key="chromedriver_path",
            file_config=file_config,
        ),
        "retry_on_yaml_failure": _resolve_config_value_helper(
            arg_val=args.retry_on_yaml_failure,
            env_var_name="RETRY_ON_YAML_FAILURE",
            conf_key="retry_on_yaml_failure",
            file_config=file_config,
            default_val=False,
            is_bool=True,
        ),
        "preferred_users": _resolve_config_value_helper(
            arg_val=args.preferred_users,
            env_var_name="PREFERRED_USERS",
            conf_key="preferred_users",
            file_config=file_config,
            is_list=True,
            default_val=[],
        ),
        "excluded_users": _resolve_config_value_helper(
            arg_val=args.excluded_users,
            env_var_name="EXCLUDED_USERS",
            conf_key="excluded_users",
            file_config=file_config,
            is_list=True,
            default_val=[],
        ),
        "discord_webhook_url": _resolve_config_value_helper(
            arg_val=args.discord_webhook_url,
            env_var_name="DISCORD_WEBHOOK_URL",
            conf_key="discord_webhook_url",
            file_config=file_config,
        ),
        "plex_url": _resolve_config_value_helper(
            arg_val=args.plex_url,
            env_var_name="PLEX_URL",
            conf_key="plex_url",
            file_config=file_config,
        ),
        "plex_token": _resolve_config_value_helper(
            arg_val=args.plex_token,
            env_var_name="PLEX_TOKEN",
            conf_key="plex_token",
            file_config=file_config,
        ),
        "plex_libraries": _resolve_config_value_helper(
            arg_val=args.plex_libraries,
            env_var_name="PLEX_LIBRARIES",
            conf_key="plex_libraries",
            file_config=file_config,
            is_list=True,
            default_val=[],
        ),
        "tz": file_config.get("TZ"),
        "copy_only": _resolve_config_value_helper(
            arg_val=args.copy_only,
            env_var_name="COPY_ONLY",
            conf_key="copy_only",
            file_config=file_config,
            default_val=False,
            is_bool=True,
        ),
        "disable_season_fix": _resolve_config_value_helper(
            arg_val=args.disable_season_fix,
            env_var_name="DISABLE_SEASON_FIX",
            conf_key="disable_season_fix",
            file_config=file_config,
            default_val=False,
            is_bool=True,
        ),
    }
    return app_config


if __name__ == "__main__":
    app_settings = _parse_arguments_and_load_config()

    config_path_global = app_settings["config_path_val"]
    root_folder_global = app_settings["root_folder_val"]
    output_dir_global = app_settings["output_dir_val"]
    discord_webhook_url_global = app_settings["discord_webhook_url"]

    if app_settings.get("copy_only"):
        if not output_dir_global:
            logger.error("No output_dir specified for --copy_only mode.")
            exit(1)
        _copy_to_output_dir_local()
        logger.info("Copy-only mode complete. Exiting.")
        exit(0)

    if app_settings.get("tz"):
        os.environ["TZ"] = app_settings["tz"]

    if root_folder_global:
        try:
            validate_path(path=root_folder_global, description="Root folder(s)")
            atexit.register(write_data_to_files)
        except Exception as e:
            logger.error(
                f"Error during validation of root folder: {e}. `write_data_to_files` will not be registered with atexit."
            )
    else:
        logger.warning(
            "Root folder is not set. `write_data_to_files` will not be registered with atexit."
        )

    try:
        run_args_for_schedule = {
            "api_key": app_settings["api_key"],
            "username": app_settings["username"],
            "password": app_settings["password"],
            "profile_path": app_settings["profile_path"],
            "nickname": app_settings["nickname"],
            "sonarr_api_key": app_settings["sonarr_api_key"],
            "sonarr_endpoint": app_settings["sonarr_endpoint"],
            "selected_folders": app_settings["selected_folders"],
            "headless": app_settings["headless"],
            "process_all": app_settings["process_all"],
            "chromedriver_path": app_settings["chromedriver_path"],
            "retry_on_yaml_failure": app_settings["retry_on_yaml_failure"],
            "preferred_users": app_settings["preferred_users"],
            "excluded_users": app_settings["excluded_users"],
            "disable_season_fix": app_settings["disable_season_fix"],
        }
        if app_settings["cron_expression"]:
            schedule_run(
                cron_expression=app_settings["cron_expression"],
                args_dict=run_args_for_schedule,
            )
        else:
            run(**run_args_for_schedule)
    except SystemExit:
        logger.info("SystemExit called, script terminating.")
        raise
    except KeyboardInterrupt:
        logger.info("Script interrupted by user (KeyboardInterrupt).")
    except Exception as e:
        logger.error(f"Unhandled error in __main__: {e}", exc_info=True)
        exit(1)

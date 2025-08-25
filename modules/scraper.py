"""
Web scraping utilities for Mediux Scraper.

This module handles WebDriver management, browser automation, login functionality,
and screenshot capabilities for the Mediux scraper.
"""

import os
import re
import time
import logging
from typing import Optional, List, Tuple, Dict, Any
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement

# Import intelligent cache
from modules.intelligent_cache import get_cache_manager

logger = logging.getLogger(__name__)


class WebDriverManager:
    """Manages WebDriver initialization and lifecycle."""

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path
        self.logger = logging.getLogger(__name__)

    def init_driver(
        self,
        headless: bool = True,
        profile_path: Optional[str] = None,
        chromedriver_path: Optional[str] = None,
    ) -> WebDriver:
        """
        Initialize Chrome WebDriver with specified options.

        Args:
            headless: Whether to run browser in headless mode
            profile_path: Path to Chrome user profile directory
            chromedriver_path: Path to ChromeDriver executable

        Returns:
            Initialized WebDriver instance

        Raises:
            Exception: If WebDriver initialization fails
        """
        self.logger.debug("Initializing WebDriver...")
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
                from webdriver_manager.chrome import ChromeDriverManager

                driver = webdriver.Chrome(
                    service=ChromeService(ChromeDriverManager().install()),
                    options=options,
                )

            driver.set_page_load_timeout(300)  # 5 minutes
            self.logger.debug("WebDriver initialized successfully.")
            return driver

        except Exception as e:
            self.logger.error(f"Failed to initialize WebDriver: {e}")
            raise

    def take_screenshot(self, driver: WebDriver, name: str) -> None:
        """
        Take a screenshot and save it to the screenshots directory.

        Args:
            driver: WebDriver instance
            name: Name for the screenshot file
        """
        screenshot_enabled = os.environ.get("SCREENSHOT") == "1"
        if not screenshot_enabled:
            return

        if self.config_path is None:
            self.logger.warning(
                "Configuration path is not set. Cannot save screenshot."
            )
            return

        screenshots_dir = os.path.join(self.config_path, "screenshots")
        os.makedirs(screenshots_dir, exist_ok=True)
        screenshot_path = os.path.join(screenshots_dir, f"{name}.png")

        try:
            driver.save_screenshot(screenshot_path)
            self.logger.info(f"Screenshot saved: {screenshot_path}")
        except Exception as e:
            self.logger.error(f"Failed to save screenshot: {e}")


class MediuxLoginManager:
    """Handles Mediux login functionality."""

    def __init__(self, webdriver_manager: Optional[WebDriverManager] = None):
        self.webdriver_manager = webdriver_manager
        self.logger = logging.getLogger(__name__)

    def login(
        self, driver: WebDriver, username: str, password: str, nickname: str
    ) -> None:
        """
        Log into Mediux using provided credentials.

        Args:
            driver: WebDriver instance
            username: Mediux username
            password: Mediux password
            nickname: Mediux nickname to verify login

        Raises:
            Exception: If login fails
        """
        self.logger.debug("Checking login status on Mediux...")
        base_url = "https://mediux.pro"
        driver.get(base_url)

        try:
            # Check if already logged in
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located(
                    (By.XPATH, f"//button[contains(text(), '{nickname}')]")
                )
            )
            self.logger.info(f"User '{nickname}' is already logged in.")
            return

        except TimeoutException:
            self.logger.debug("User is not logged in. Proceeding with login...")

        try:
            # Click sign in button
            login_button = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located(
                    (By.XPATH, "//button[contains(text(), 'Sign In')]")
                )
            )
            login_button.click()

            # Wait for login form to load
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, ":r0:-form-item"))
            )

            # Enter credentials
            username_field = driver.find_element(By.ID, ":r0:-form-item")
            password_field = driver.find_element(By.ID, ":r1:-form-item")
            username_field.send_keys(username)
            password_field.send_keys(password)

            # Submit form
            submit_button = driver.find_element(By.XPATH, "//form/button")
            submit_button.click()

            # Wait for login confirmation
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located(
                    (By.XPATH, f"//button[contains(text(), '{nickname}')]")
                )
            )
            self.logger.info("Logged into Mediux successfully.")

        except Exception as e:
            if self.webdriver_manager:
                self.webdriver_manager.take_screenshot(driver, "error_login")
            self.logger.error(f"Failed to log into Mediux: {e}")
            raise


def initialize_and_login_driver(
    *,
    headless,
    profile_path,
    chromedriver_path,
    username,
    password,
    nickname,
):
    """Initialize WebDriver and login to Mediux."""
    webdriver_manager = WebDriverManager(
        None
    )  # config_path will be set later if needed
    driver = webdriver_manager.init_driver(
        headless=headless,
        profile_path=profile_path,
        chromedriver_path=chromedriver_path,
    )

    login_manager = MediuxLoginManager(webdriver_manager)
    try:
        login_manager.login(
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


class MediuxScraper:
    """Handles Mediux page scraping and YAML extraction."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.cache_manager = get_cache_manager()
        self.page_load_cache = {}  # Simple in-memory cache for page load states

    def get_media_url_and_texts(
        self, media_type: str, tmdb_id: str
    ) -> Tuple[str, str, str]:
        """
        Get URL and status text patterns for a media item.

        Args:
            media_type: Either 'movie' or 'tv'
            tmdb_id: TMDB ID of the media

        Returns:
            Tuple of (url, updating_text, success_text)
        """
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

    def wait_for_update_completion(
        self,
        driver: WebDriver,
        updating_text: str,
        success_text: str,
        media_type: str,
        tmdb_id: str,
    ) -> None:
        """
        Wait for update process to complete on Mediux page.

        Args:
            driver: WebDriver instance
            updating_text: Text indicating update in progress
            success_text: Text indicating successful update
            media_type: Type of media being processed
            tmdb_id: TMDB ID being processed
        """
        try:
            update_toast_xpath = f"//li[contains(@class, 'toast')]//div[contains(text(), '{updating_text}')]"
            success_toast_xpath = f"//li[contains(@class, 'toast')]//div[contains(text(), '{success_text}')]"

            update_elements = driver.find_elements(By.XPATH, update_toast_xpath)
            success_elements = driver.find_elements(By.XPATH, success_toast_xpath)

            if update_elements:
                toast_text = update_elements[0].text
                self.logger.debug(f"Page updating: '{toast_text}'")
                self.logger.debug(
                    f"Waiting for update completion for {media_type} {tmdb_id}..."
                )

                WebDriverWait(driver, 30).until(
                    lambda d: (
                        len(d.find_elements(By.XPATH, update_toast_xpath)) == 0
                        or len(d.find_elements(By.XPATH, success_toast_xpath)) > 0
                    )
                )

                success_elements = driver.find_elements(By.XPATH, success_toast_xpath)
                if success_elements:
                    self.logger.debug(
                        f"Update successful: '{success_elements[0].text}'"
                    )
                else:
                    self.logger.debug(
                        f"Update process completed for {media_type} {tmdb_id}"
                    )

                time.sleep(1)
            else:
                if success_elements:
                    self.logger.debug(
                        f"Update successful: '{success_elements[0].text}'"
                    )
                else:
                    self.logger.debug(f"No update needed for {media_type} {tmdb_id}")

        except Exception as e:
            self.logger.warning(f"Error while waiting for update process: {e}")

    def wait_for_refresh_completion(
        self, driver: WebDriver, media_type: str, tmdb_id: str
    ) -> None:
        """
        Wait for refresh operations to complete.

        Args:
            driver: WebDriver instance
            media_type: Type of media being processed
            tmdb_id: TMDB ID being processed
        """
        try:
            self.logger.debug(
                f"Checking for refresh operations on {media_type} {tmdb_id}..."
            )

            refresh_spinner_xpath = "//svg[contains(@class, 'lucide-refresh-cw') and contains(@class, 'animate-spin')]"
            spinner_elements = driver.find_elements(By.XPATH, refresh_spinner_xpath)

            if spinner_elements:
                self.logger.debug(
                    f"Page status: Refresh in progress for {media_type} {tmdb_id}"
                )
                self.logger.debug(
                    f"Detected refresh operation for {media_type} {tmdb_id}, waiting for completion..."
                )

                WebDriverWait(driver, 30).until(
                    lambda d: len(d.find_elements(By.XPATH, refresh_spinner_xpath)) == 0
                )

                self.logger.debug(
                    f"Page status: Refresh completed for {media_type} {tmdb_id}"
                )
                time.sleep(1)
            else:
                self.logger.debug(
                    f"Page status: No refresh operation detected for {media_type} {tmdb_id}"
                )

        except Exception as e:
            self.logger.warning(f"Error while waiting for refresh spinner: {e}")

    def find_yaml_button(
        self,
        driver: WebDriver,
        yaml_xpath: str,
        preferred_users: Optional[List[str]] = None,
        excluded_users: Optional[List[str]] = None,
    ) -> Optional[WebElement]:
        """
        Find the appropriate YAML button based on user preferences.

        Args:
            driver: WebDriver instance
            yaml_xpath: XPath selector for YAML buttons
            preferred_users: List of preferred usernames
            excluded_users: List of usernames to exclude

        Returns:
            WebElement of the selected YAML button or None
        """
        yaml_button = None

        try:
            all_yaml_buttons = WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.XPATH, yaml_xpath))
            )
        except TimeoutException:
            self.logger.warning("No YAML buttons found on the page.")
            return None

        if not all_yaml_buttons:
            self.logger.warning("No YAML buttons found on the page.")
            return None

        # Filter excluded users
        if excluded_users:
            self.logger.info(f"Excluding users: {', '.join(excluded_users)}")
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
                                self.logger.debug(
                                    f"Excluding YAML button from user: {username}"
                                )
                        else:
                            filtered_buttons.append(button)
                    else:
                        filtered_buttons.append(button)
                except Exception:
                    filtered_buttons.append(button)
            all_yaml_buttons = filtered_buttons

            if not all_yaml_buttons:
                self.logger.warning(
                    "No YAML buttons left after filtering excluded users."
                )
                return None

        # Try to find preferred user
        if preferred_users and len(preferred_users) > 0:
            self.logger.info(
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
                            self.logger.info(f"Using YAML from preferred user: {user}")
                            yaml_button = button
                            break
                    except Exception:
                        continue
                if yaml_button:
                    break

        # Fall back to first available button
        if not yaml_button and all_yaml_buttons:
            yaml_button = all_yaml_buttons[0]
            self.logger.debug("Using first available YAML button (after exclusions).")
        elif not yaml_button:
            self.logger.warning(
                "No suitable YAML button found after considering preferences and exclusions."
            )

        return yaml_button

    def scrape_mediux(
        self,
        driver: WebDriver,
        tmdb_id: str,
        media_type: str,
        retry_on_yaml_failure: bool = False,
        preferred_users: Optional[List[str]] = None,
        excluded_users: Optional[List[str]] = None,
    ) -> str:
        """
        Scrape YAML data from Mediux page with intelligent caching.

        Args:
            driver: WebDriver instance
            tmdb_id: TMDB ID to scrape
            media_type: Type of media ('movie' or 'tv')
            retry_on_yaml_failure: Whether to retry on YAML extraction failure
            preferred_users: List of preferred usernames
            excluded_users: List of usernames to exclude

        Returns:
            YAML data as string, empty string if extraction fails
        """
        # Create cache key based on parameters that affect the result
        cache_key = f"{tmdb_id}:{media_type}:{sorted(preferred_users or [])}:{sorted(excluded_users or [])}"

        # Check cache FIRST to avoid expensive 5-10 second page loads
        cached_result = self.cache_manager.cache.get("yaml_data", cache_key)
        if cached_result is not None:  # Note: empty string is a valid cached result
            self.logger.info(f"Using cached YAML data for {media_type} {tmdb_id}")
            return cached_result

        self.logger.info(
            f"Scraping Mediux for TMDB ID {tmdb_id}, Media Type: {media_type}"
        )

        url, updating_text, success_text = self.get_media_url_and_texts(
            media_type, tmdb_id
        )

        # Navigation errors should always raise exceptions (never cached)
        try:
            driver.get(url)
        except Exception as e:
            self.logger.error(f"An error occurred during driver.get({url}): {e}")
            raise

        self.logger.debug(f"Navigated to URL: {url}")
        yaml_xpath = "//button[span[contains(text(), 'YAML')]]"
        time.sleep(5)

        self.wait_for_update_completion(
            driver, updating_text, success_text, media_type, tmdb_id
        )
        self.wait_for_refresh_completion(driver, media_type, tmdb_id)

        try:
            self.logger.debug(f"Looking for YAML button for {media_type} {tmdb_id}...")
            yaml_button = self.find_yaml_button(
                driver=driver,
                yaml_xpath=yaml_xpath,
                preferred_users=preferred_users,
                excluded_users=excluded_users,
            )

            if not yaml_button:
                self.logger.warning(
                    f"No suitable YAML button found for TMDB ID {tmdb_id} after filtering."
                )
                # Cache negative result to avoid repeated failed lookups
                self.cache_manager.cache.set("yaml_data", cache_key, "")
                return ""

            driver.execute_script("arguments[0].scrollIntoView(true);", yaml_button)
            yaml_button.click()
            self.logger.info(f"Extracting YAML data for {media_type} {tmdb_id}")

            yaml_element = WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.XPATH, "//code"))
            )
            WebDriverWait(driver, 20).until(
                lambda d: (yaml_element.get_attribute("innerText") or "").strip() != ""
            )
            yaml_data = yaml_element.get_attribute("innerText")

            if yaml_data is None:
                self.logger.warning(
                    f"YAML content for TMDB ID {tmdb_id} was unexpectedly None after waiting. "
                    "This might indicate an issue with the page or element structure. Returning empty."
                )
                self.cache_manager.cache.set("yaml_data", cache_key, "")
                return ""

            yaml_len = len(yaml_data)
            self.logger.info(f"YAML data loaded successfully ({yaml_len} characters)")

            # Cache the successful result
            self.cache_manager.cache.set("yaml_data", cache_key, yaml_data)
            return yaml_data

        except Exception as e:
            if not driver.find_elements(By.XPATH, yaml_xpath):
                self.logger.warning(f"YAML button not found for TMDB ID {tmdb_id}")
                self.cache_manager.cache.set("yaml_data", cache_key, "")
                return ""

            if retry_on_yaml_failure:
                self.logger.warning(
                    f"YAML button found but an error occurred. Retrying for TMDB ID {tmdb_id}."
                )
                driver.refresh()
                self.logger.debug(f"Page refreshed for TMDB ID {tmdb_id}")
                time.sleep(5)
                # Recursive call for retry - do not cache intermediate results
                return self.scrape_mediux(
                    driver=driver,
                    tmdb_id=tmdb_id,
                    media_type=media_type,
                    retry_on_yaml_failure=False,  # Prevent infinite retry
                    preferred_users=preferred_users,
                    excluded_users=excluded_users,
                )

            self.logger.error(
                f"Error scraping TMDB ID {tmdb_id}. This may be normal if no YAML is available."
            )
            # Cache empty result for failed extractions to avoid repeated attempts
            self.cache_manager.cache.set("yaml_data", cache_key, "")
            return ""

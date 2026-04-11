"""
Web scraping utilities for Mediux Scraper.

This module handles WebDriver management, browser automation, login functionality,
and screenshot capabilities for the Mediux scraper.
"""

import logging
import os
import re
import time
from typing import List, Optional, Tuple
from selenium import webdriver
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchDriverException,
    SessionNotCreatedException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# Import intelligent cache and automation constants
from modules.intelligent_cache import get_cache_manager
from modules.base import WebAutomationConstants, MediuxConfig, WebSelectors

logger = logging.getLogger(__name__)

BROWSER_WINDOW_WIDTH = 1920
BROWSER_WINDOW_HEIGHT = 1080


class WebDriverManager:
    _instance = None
    _driver = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(WebDriverManager, cls).__new__(cls)
        return cls._instance

    def __init__(self, config_path: Optional[str] = None):
        if not hasattr(self, "initialized"):
            self.config_path = config_path
            self.logger = logging.getLogger(__name__)
            self.initialized = True

    def setup_chrome_options(
        self,
        headless: bool,
        profile_path: Optional[str] = None,
    ) -> Options:
        """Set up Chrome options optimized for stability and long-running operations."""
        options = Options()

        # Essential stability flags
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-web-security")
        options.add_argument("--disable-features=VizDisplayCompositor")
        options.add_argument("--disable-ipc-flooding-protection")
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-plugins")
        options.add_argument("--disable-images")  # Speed up page loads
        options.add_argument("--disable-javascript-harness")
        options.add_argument("--disable-component-extensions-with-background-pages")
        options.add_argument("--disable-background-timer-throttling")
        options.add_argument("--disable-backgrounding-occluded-windows")
        options.add_argument("--disable-renderer-backgrounding")
        options.add_argument("--memory-pressure-off")
        options.add_argument("--disable-low-end-device-mode")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--no-pings")
        options.add_argument("--disable-background-networking")
        options.add_argument("--disable-sync")
        options.add_argument("--disable-translate")
        options.add_argument("--hide-scrollbars")
        options.add_argument("--metrics-recording-only")
        options.add_argument("--mute-audio")
        options.add_argument("--no-crash-upload")
        options.add_argument("--disable-hang-monitor")
        options.add_argument("--disable-prompt-on-repost")
        options.add_argument("--disable-component-update")
        options.add_argument("--disable-domain-reliability")
        options.add_argument("--disable-client-side-phishing-detection")
        options.add_argument("--disable-component-extensions-with-background-pages")

        # Memory and resource management
        options.add_argument("--max_old_space_size=4096")
        options.add_argument("--memory-allocator=malloc")
        options.add_argument("--max_new_space_size=2048")
        options.add_argument(
            "--js-flags=--max_old_space_size=8192,--max_new_space_size=4096"
        )
        options.add_argument("--disable-logging")
        options.add_argument("--disable-logging-redirect")
        options.add_argument("--log-level=3")
        options.add_argument("--silent")

        # Crashpad and error reporting
        options.add_argument("--disable-crash-reporter")
        options.add_argument("--disable-in-process-stack-traces")
        options.add_argument("--disable-breakpad")

        # Performance optimizations
        options.add_argument("--prerender=disabled")
        options.add_argument("--dns-prefetch-disable")
        options.add_argument("--disable-accelerated-2d-canvas")
        options.add_argument("--accelerated-drawing=disabled")
        options.add_argument("--disable-software-rasterizer")

        # Headless and display settings
        if headless:
            options.add_argument("--headless=new")  # Use new headless mode
            options.add_argument(f"--window-size={BROWSER_WINDOW_WIDTH},{BROWSER_WINDOW_HEIGHT}")
            options.add_argument("--start-maximized")

        # Profile path
        if profile_path:
            options.add_argument(f"--user-data-dir={profile_path}")

        # GPU settings (disable to prevent crashes)
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-gpu-compositing")
        options.add_argument("--disable-gpu-rasterization")

        # Experimental options
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        return options

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
        if WebDriverManager._driver:
            return WebDriverManager._driver

        # Setup optimized Chrome options
        options = self.setup_chrome_options(
            headless=headless, profile_path=profile_path
        )

        try:
            # Create WebDriver service
            if chromedriver_path:
                service = ChromeService(chromedriver_path)
            else:
                from webdriver_manager.chrome import ChromeDriverManager

                service = ChromeService(ChromeDriverManager().install())

            # Initialize driver with retries
            max_retries = 3
            driver = None
            for attempt in range(max_retries):
                try:
                    driver = webdriver.Chrome(service=service, options=options)
                    break
                except (NoSuchDriverException, SessionNotCreatedException) as e:
                    if attempt < max_retries - 1:
                        self.logger.warning(
                            f"WebDriver initialization attempt {attempt + 1} failed: {e}"
                        )
                        time.sleep(2)
                        driver = None
                        continue
                    else:
                        raise

            # Ensure driver was created successfully
            if driver is None:
                raise RuntimeError(
                    "Failed to create WebDriver after all retry attempts"
                )

            # Configure timeouts for stability
            driver.set_page_load_timeout(WebAutomationConstants.PAGE_LOAD_TIMEOUT)
            driver.set_script_timeout(WebAutomationConstants.SCRIPT_TIMEOUT)
            driver.implicitly_wait(WebAutomationConstants.IMPLICIT_WAIT_TIMEOUT)

            # Additional stability settings
            driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {
                    "source": """
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined,
                    });
                """
                },
            )

            WebDriverManager._driver = driver
            return driver

        except Exception as e:
            self.logger.error(f"Failed to initialize WebDriver after all retries: {e}")
            raise

    def safe_quit_driver(self) -> None:
        """Safely quit the WebDriver instance and clean up processes."""
        if WebDriverManager._driver is None:
            return

        try:
            WebDriverManager._driver.quit()
            self.logger.debug("WebDriver quit successfully")
        except Exception as e:
            self.logger.warning(f"Error during driver quit: {e}")
        finally:
            WebDriverManager._driver = None

    def take_screenshot(self, name: str) -> None:
        """
        Take a screenshot and save it to the screenshots directory.

        Args:
            name: Name for the screenshot file
        """
        driver = WebDriverManager._driver
        if driver is None:
            self.logger.warning("WebDriver not initialized. Cannot take screenshot.")
            return

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

    def login(self, username: str, password: str, nickname: str) -> None:
        """
        Log into Mediux using provided credentials.

        Args:
            username: Mediux username
            password: Mediux password
            nickname: Mediux nickname to verify login

        Raises:
            Exception: If login fails
        """
        driver = WebDriverManager._driver
        if not driver:
            raise RuntimeError("WebDriver not initialized. Cannot login.")
        self.logger.debug("Checking login status on Mediux...")
        driver.get(MediuxConfig.BASE_URL)

        try:
            # Check if already logged in
            WebDriverWait(
                driver,
                WebAutomationConstants.ELEMENT_WAIT_TIMEOUT_SHORT,
            ).until(
                EC.presence_of_element_located(
                    (By.XPATH, WebSelectors.get_user_button(nickname))
                )
            )
            self.logger.info(f"User '{nickname}' is already logged in.")
            return

        except TimeoutException:
            self.logger.debug("User is not logged in. Proceeding with login...")

        try:
            # Click sign in button
            login_button = WebDriverWait(
                driver,
                WebAutomationConstants.ELEMENT_WAIT_TIMEOUT_STANDARD,
            ).until(
                EC.presence_of_element_located((By.XPATH, WebSelectors.SIGN_IN_BUTTON))
            )
            login_button.click()

            # Wait for login form to load
            WebDriverWait(
                driver,
                WebAutomationConstants.ELEMENT_WAIT_TIMEOUT_STANDARD,
            ).until(EC.presence_of_element_located((By.ID, ":r0:-form-item")))

            # Enter credentials
            username_field = driver.find_element(By.ID, ":r0:-form-item")
            password_field = driver.find_element(By.ID, ":r1:-form-item")
            username_field.send_keys(username)
            password_field.send_keys(password)

            # Submit form
            submit_button = driver.find_element(By.XPATH, "//form/button")
            submit_button.click()

            # Wait for login confirmation
            WebDriverWait(
                driver,
                WebAutomationConstants.ELEMENT_WAIT_TIMEOUT_STANDARD,
            ).until(
                EC.presence_of_element_located(
                    (By.XPATH, WebSelectors.get_user_button(nickname))
                )
            )
            self.logger.info("Logged into Mediux successfully.")

        except Exception as e:
            if self.webdriver_manager:
                self.webdriver_manager.take_screenshot("error_login")
            self.logger.error(f"Failed to log into Mediux: {e}")
            raise


class MediuxScraper:
    """Handles Mediux page scraping and YAML extraction."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.cache_manager = get_cache_manager()

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
        if media_type == "movie":
            url = MediuxConfig.get_movie_url(tmdb_id)
            updating_text = MediuxConfig.MOVIE_UPDATING_TEXT
            success_text = MediuxConfig.MOVIE_UPDATE_SUCCESS
        else:
            url = MediuxConfig.get_show_url(tmdb_id)
            updating_text = MediuxConfig.SHOW_UPDATING_TEXT
            success_text = MediuxConfig.SHOW_UPDATE_SUCCESS
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
        Wait for update process to complete on Mediux page with optimized polling.

        Args:
            driver: WebDriver instance
            updating_text: Text indicating update in progress
            success_text: Text indicating successful update
            media_type: Type of media being processed
            tmdb_id: TMDB ID being processed
        """
        # Temporarily disable implicit wait for instant checks
        original_implicit = WebAutomationConstants.IMPLICIT_WAIT_TIMEOUT
        driver.implicitly_wait(0)

        try:
            update_toast_xpath = f"//li[contains(@class, 'toast')]//div[contains(text(), '{updating_text}')]"
            success_toast_xpath = f"//li[contains(@class, 'toast')]//div[contains(text(), '{success_text}')]"

            # Quick initial check
            update_elements = driver.find_elements(By.XPATH, update_toast_xpath)
            success_elements = driver.find_elements(By.XPATH, success_toast_xpath)

            if update_elements:
                toast_text = update_elements[0].text
                self.logger.debug(f"Page updating: '{toast_text}'")
                self.logger.debug(
                    f"Waiting for update completion for {media_type} {tmdb_id}..."
                )

                # Optimized polling using Selenium's WebDriverWait for clean implementation
                wait = WebDriverWait(
                    driver,
                    WebAutomationConstants.PROCESS_WAIT_TIMEOUT,
                )
                wait.until(
                    lambda d: len(d.find_elements(By.XPATH, success_toast_xpath)) > 0
                )

                # Final state check
                success_elements = driver.find_elements(By.XPATH, success_toast_xpath)
                if success_elements:
                    self.logger.debug(
                        f"Update successful: '{success_elements[0].text}'"
                    )
                else:
                    self.logger.debug(
                        f"Update process completed for {media_type} {tmdb_id}"
                    )

                # Minimal sleep after update completion
                time.sleep(WebAutomationConstants.BRIEF_DELAY)

            else:
                if success_elements:
                    self.logger.debug(
                        f"Update successful: '{success_elements[0].text}'"
                    )
                else:
                    self.logger.debug(f"No update needed for {media_type} {tmdb_id}")

        except Exception as e:
            self.logger.warning(f"Error while waiting for update process: {e}")
        finally:
            driver.implicitly_wait(original_implicit)

    def wait_for_refresh_completion(
        self, driver: WebDriver, media_type: str, tmdb_id: str
    ) -> None:
        """
        Wait for refresh operations to complete with optimized polling.

        Args:
            driver: WebDriver instance
            media_type: Type of media being processed
            tmdb_id: TMDB ID being processed
        """
        # Temporarily disable implicit wait for instant checks
        original_implicit = WebAutomationConstants.IMPLICIT_WAIT_TIMEOUT
        driver.implicitly_wait(0)

        try:
            self.logger.debug(
                f"Checking for refresh operations on {media_type} {tmdb_id}..."
            )

            refresh_spinner_xpath = "//svg[contains(@class, 'lucide-refresh-cw') and contains(@class, 'animate-spin')]"

            # Quick initial check
            spinner_elements = driver.find_elements(By.XPATH, refresh_spinner_xpath)

            if spinner_elements:
                self.logger.debug(
                    f"Page status: Refresh in progress for {media_type} {tmdb_id}"
                )
                self.logger.debug(
                    f"Detected refresh operation for {media_type} {tmdb_id}, waiting for completion..."
                )

                # Optimized polling using Selenium's WebDriverWait for clean implementation
                wait = WebDriverWait(
                    driver,
                    WebAutomationConstants.PROCESS_WAIT_TIMEOUT,
                )
                wait.until(
                    lambda d: len(d.find_elements(By.XPATH, refresh_spinner_xpath)) == 0
                )

                self.logger.debug(
                    f"Page status: Refresh completed for {media_type} {tmdb_id}"
                )
                time.sleep(
                    WebAutomationConstants.BRIEF_DELAY
                )  # Minimal post-refresh pause
            else:
                self.logger.debug(
                    f"Page status: No refresh operation detected for {media_type} {tmdb_id}"
                )

        except Exception as e:
            self.logger.warning(f"Error while waiting for refresh spinner: {e}")
        finally:
            driver.implicitly_wait(original_implicit)

    def _apply_user_exclusions(
        self,
        buttons: List[WebElement],
        excluded_users: List[str],
    ) -> List[WebElement]:
        """Return buttons whose associated user is not in the excluded list."""
        self.logger.info(f"Excluding users: {', '.join(excluded_users)}")
        filtered = []
        for button in buttons:
            try:
                ancestor_div = button.find_element(
                    By.XPATH,
                    "./ancestor::div[contains(@class, 'flex') and .//a[contains(@href, '/user/')]]",
                )
                user_link = ancestor_div.find_element(
                    By.XPATH, ".//a[contains(@href, '/user/')]"
                )
                user_href = user_link.get_attribute("href")
                if user_href:
                    match = re.search(r"/user/([^/]+)", user_href)
                    if match:
                        username = match.group(1)
                        if username.lower() in [u.lower() for u in excluded_users]:
                            self.logger.debug(
                                f"Excluding YAML button from user: {username}"
                            )
                            continue
            except Exception:
                pass
            filtered.append(button)
        return filtered

    def _find_preferred_user_button(
        self,
        buttons: List[WebElement],
        preferred_users: List[str],
    ) -> Optional[WebElement]:
        """Return the first button belonging to a preferred user, or None."""
        self.logger.info(
            f"Searching for YAML from preferred users: {', '.join(preferred_users)}"
        )
        for user in preferred_users:
            for button in buttons:
                try:
                    ancestor_div = button.find_element(
                        By.XPATH,
                        "./ancestor::div[contains(@class, 'flex') and .//a[contains(@href, '/user/')]]",
                    )
                    user_link = ancestor_div.find_element(
                        By.XPATH, f".//a[@href='/user/{user.lower()}']"
                    )
                    if user_link.find_element(
                        By.XPATH, f"./button[contains(., '{user}')]"
                    ):
                        self.logger.info(f"Using YAML from preferred user: {user}")
                        return button
                except Exception:
                    continue
        return None

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
        original_implicit = WebAutomationConstants.IMPLICIT_WAIT_TIMEOUT
        driver.implicitly_wait(0)

        try:
            quick_buttons = driver.find_elements(By.XPATH, yaml_xpath)
            if not quick_buttons:
                self.logger.debug(
                    "No YAML buttons found instantly, likely no YAML available"
                )
                return None
            all_yaml_buttons = WebDriverWait(
                driver,
                WebAutomationConstants.ELEMENT_WAIT_TIMEOUT_STANDARD,
            ).until(EC.presence_of_all_elements_located((By.XPATH, yaml_xpath)))
        except TimeoutException:
            self.logger.warning("No YAML buttons found on the page.")
            return None
        finally:
            driver.implicitly_wait(original_implicit)

        if not all_yaml_buttons:
            self.logger.warning("No YAML buttons found on the page.")
            return None

        if excluded_users:
            all_yaml_buttons = self._apply_user_exclusions(all_yaml_buttons, excluded_users)
            if not all_yaml_buttons:
                self.logger.warning("No YAML buttons left after filtering excluded users.")
                return None

        if preferred_users:
            yaml_button = self._find_preferred_user_button(all_yaml_buttons, preferred_users)
            if yaml_button:
                return yaml_button

        if all_yaml_buttons:
            self.logger.debug("Using first available YAML button (after exclusions).")
            return all_yaml_buttons[0]

        self.logger.warning(
            "No suitable YAML button found after considering preferences and exclusions."
        )
        return None

    def _check_no_sets_available(
        self, driver: WebDriver, tmdb_id: str, media_type: str
    ) -> bool:
        """Return True if the page shows 'No Sets Available.' and YAML scraping should be skipped."""
        try:
            driver.implicitly_wait(0)
            no_sets = driver.find_elements(
                By.XPATH, "//div[text()='No Sets Available.']"
            )
            if no_sets:
                self.logger.debug(
                    f"No Sets Available for {media_type} {tmdb_id} - skipping waits"
                )
                return True
        finally:
            driver.implicitly_wait(WebAutomationConstants.IMPLICIT_WAIT_TIMEOUT)
        return False

    def _click_and_extract_yaml(
        self, driver: WebDriver, yaml_button: WebElement, tmdb_id: str
    ) -> str:
        """Click a YAML button and extract the resulting YAML content string."""
        driver.execute_script("arguments[0].scrollIntoView(true);", yaml_button)
        yaml_button.click()
        self.logger.info(f"Extracting YAML data for TMDB ID {tmdb_id}")

        yaml_element = WebDriverWait(
            driver,
            WebAutomationConstants.YAML_LOAD_TIMEOUT,
        ).until(EC.presence_of_element_located((By.XPATH, "//code")))
        WebDriverWait(
            driver,
            WebAutomationConstants.YAML_LOAD_TIMEOUT,
        ).until(
            lambda d: (yaml_element.get_attribute("innerText") or "").strip() != ""
        )
        yaml_data = yaml_element.get_attribute("innerText")

        if yaml_data is None:
            self.logger.warning(
                f"YAML content for TMDB ID {tmdb_id} was unexpectedly None after waiting. "
                "This might indicate an issue with the page or element structure. Returning empty."
            )
            return ""

        self.logger.info(f"YAML data loaded successfully ({len(yaml_data)} characters)")
        return yaml_data

    def scrape_mediux(
        self,
        tmdb_id: str,
        media_type: str,
        retry_on_yaml_failure: bool = False,
        preferred_users: Optional[List[str]] = None,
        excluded_users: Optional[List[str]] = None,
        direct_url: Optional[str] = None,
    ) -> str:
        """
        Scrape YAML data from Mediux page with intelligent caching.

        Args:
            tmdb_id: TMDB ID to scrape
            media_type: Type of media ('movie' or 'tv')
            retry_on_yaml_failure: Whether to retry on YAML extraction failure
            preferred_users: List of preferred usernames
            excluded_users: List of usernames to exclude
            direct_url: Override URL (bypasses TMDB ID → URL construction)

        Returns:
            YAML data as string, empty string if extraction fails
        """
        driver = WebDriverManager._driver
        if not driver:
            raise RuntimeError("WebDriver not initialized. Cannot scrape.")

        self.logger.info(
            f"Scraping Mediux for TMDB ID {tmdb_id}, Media Type: {media_type}"
        )

        if direct_url:
            url = direct_url
            updating_text = MediuxConfig.MOVIE_UPDATING_TEXT
            success_text = MediuxConfig.MOVIE_UPDATE_SUCCESS
            self.logger.info(f"Using direct URL: {direct_url}")
        else:
            url, updating_text, success_text = self.get_media_url_and_texts(
                media_type, tmdb_id
            )

        try:
            self.logger.debug(f"Navigating to: {url}")
            driver.get(url)
            self.logger.debug(f"Navigated to URL: {url}")
        except Exception as e:
            self.logger.error(f"An error occurred during navigation to {url}: {e}")
            raise

        if self._check_no_sets_available(driver, tmdb_id, media_type):
            return ""

        yaml_xpath = "//button[span[contains(text(), 'YAML')]]"
        time.sleep(WebAutomationConstants.BRIEF_DELAY)

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
                return ""

            return self._click_and_extract_yaml(driver, yaml_button, tmdb_id)

        except Exception:
            if not driver.find_elements(By.XPATH, yaml_xpath):
                self.logger.warning(f"YAML button not found for TMDB ID {tmdb_id}")
                return ""

            if retry_on_yaml_failure:
                self.logger.warning(
                    f"YAML button found but an error occurred. Retrying for TMDB ID {tmdb_id}."
                )
                driver.refresh()
                self.logger.debug(f"Page refreshed for TMDB ID {tmdb_id}")
                time.sleep(WebAutomationConstants.BRIEF_DELAY)
                return self.scrape_mediux(
                    tmdb_id=tmdb_id,
                    media_type=media_type,
                    retry_on_yaml_failure=False,
                    preferred_users=preferred_users,
                    excluded_users=excluded_users,
                )

            self.logger.error(
                f"Error scraping TMDB ID {tmdb_id}. This may be normal if no YAML is available."
            )
            return ""

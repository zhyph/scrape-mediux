"""
Web scraping utilities for Mediux Scraper.

This module handles WebDriver management, browser automation, login functionality,
and screenshot capabilities for the Mediux scraper.
"""

import logging
import os
import re
import signal
import socket
import subprocess
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


class WebDriverManager:
    """Manages WebDriver initialization and lifecycle with enhanced stability."""

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path
        self.logger = logging.getLogger(__name__)
        self.current_driver = None

    def _find_free_port(self) -> int:
        """Find a free port for Chrome debugging."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            s.listen(1)
            port = s.getsockname()[1]
        return port

    def cleanup_orphaned_webdriver_processes(
        self, target_pid: Optional[int] = None
    ) -> None:
        """
        Conservative cleanup focusing only on WebDriver-related processes.
        Avoids killing regular user Chrome browser instances.

        Args:
            target_pid: Optional specific process ID to clean up (for Windows compatibility)
        """
        if target_pid is not None:
            # Windows-compatible specific PID cleanup
            try:
                os.kill(target_pid, signal.SIGTERM)
                time.sleep(0.2)
                try:
                    os.kill(target_pid, signal.SIGKILL)  # Force kill if needed
                except ProcessLookupError:
                    pass  # Process already terminated
                self.logger.debug(f"Cleaned up specific process PID: {target_pid}")
            except OSError as e:
                self.logger.debug(
                    f"Process {target_pid} already terminated or inaccessible: {e}"
                )
            return

        try:
            self.logger.debug("Performing conservative WebDriver process cleanup...")

            # Only kill chromedriver processes - these are definitely WebDriver-related
            chromedriver_processes = subprocess.run(
                ["pgrep", "-f", "chromedriver"], capture_output=True, text=True
            )

            chromedriver_killed = 0
            if chromedriver_processes.stdout:
                driver_pids = chromedriver_processes.stdout.strip().split("\n")
                for pid in driver_pids:
                    if not pid.strip():
                        continue
                    try:
                        pid_int = int(pid.strip())
                        # Verify it's actually chromedriver before killing
                        try:
                            process_cmdline = subprocess.run(
                                ["ps", "-p", str(pid_int), "-o", "comm="],
                                capture_output=True,
                                text=True,
                                timeout=2,
                            )
                            if process_cmdline.stdout.strip() == "chromedriver":
                                os.kill(pid_int, signal.SIGTERM)
                                chromedriver_killed += 1
                                time.sleep(0.1)  # Brief delay between kills
                        except subprocess.SubprocessError:
                            # If we can't verify, be conservative and skip
                            continue
                    except (ValueError, OSError) as e:
                        if "No such process" not in str(e):
                            self.logger.warning(
                                f"Error killing chromedriver process {pid}: {e}"
                            )

            # Selectively clean ONLY WebDriver-controlled Chrome instances
            # (those with --remote-debugging-port flag)
            chrome_webdriver_processes = subprocess.run(
                ["pgrep", "-f", "--remote-debugging-port"],
                capture_output=True,
                text=True,
            )

            chrome_killed = 0
            if chrome_webdriver_processes.stdout:
                chrome_pids = chrome_webdriver_processes.stdout.strip().split("\n")
                for pid in chrome_pids:
                    if not pid.strip():
                        continue
                    try:
                        pid_int = int(pid.strip())
                        # Verify this Chrome instance has WebDriver flags before killing
                        try:
                            process_cmdline = subprocess.run(
                                ["ps", "-p", str(pid_int), "-o", "args="],
                                capture_output=True,
                                text=True,
                                timeout=2,
                            )
                            if "--remote-debugging-port" in process_cmdline.stdout:
                                os.kill(pid_int, signal.SIGTERM)
                                chrome_killed += 1
                                time.sleep(0.1)
                        except subprocess.SubprocessError:
                            continue
                    except (ValueError, OSError) as e:
                        if "No such process" not in str(e):
                            self.logger.warning(
                                f"Error killing WebDriver Chrome process {pid}: {e}"
                            )

            time.sleep(0.5)  # Allow processes time to terminate
            if chromedriver_killed > 0 or chrome_killed > 0:
                self.logger.debug(
                    f"Cleaned up {chromedriver_killed} chromedriver and {chrome_killed} WebDriver Chrome processes"
                )
            else:
                self.logger.debug("No orphaned WebDriver processes found to clean up")

        except (subprocess.SubprocessError, OSError) as e:
            # This is normal on systems without pgrep (like Windows) or other OS differences
            self.logger.warning(
                f"Process cleanup not fully available on this system: {e}"
            )
            self.logger.info("This is normal and doesn't affect functionality")

    def setup_chrome_options(
        self,
        headless: bool,
        profile_path: Optional[str] = None,
        port: Optional[int] = None,
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

        # Performance optimizations
        options.add_argument("--prerender=disabled")
        options.add_argument("--dns-prefetch-disable")
        options.add_argument("--disable-accelerated-2d-canvas")
        options.add_argument("--accelerated-drawing=disabled")
        options.add_argument("--disable-software-rasterizer")

        # Headless and display settings
        if headless:
            options.add_argument("--headless=new")  # Use new headless mode
            if port is None:
                port = self._find_free_port()
            options.add_argument(f"--remote-debugging-port={port}")
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--start-maximized")

        # Profile path
        if profile_path:
            options.add_argument(f"--user-data-dir={profile_path}")

        # GPU settings (disable to prevent crashes)
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-gpu-compositing")
        options.add_argument("--disable-gpu-rasterization")

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

        # Clean up any existing processes before starting
        self.cleanup_orphaned_webdriver_processes()

        # Get a free port for debugging
        debug_port = self._find_free_port()

        # Setup optimized Chrome options
        options = self.setup_chrome_options(
            headless=headless, profile_path=profile_path, port=debug_port
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
                        # Clean up and try again
                        self.cleanup_orphaned_webdriver_processes()
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

            self.current_driver = driver
            return driver

        except Exception as e:
            self.logger.error(f"Failed to initialize WebDriver after all retries: {e}")
            # Final cleanup attempt
            self.cleanup_orphaned_webdriver_processes()
            raise

    def safe_quit_driver(self, driver: Optional[WebDriver] = None) -> None:
        """Safely quit a WebDriver instance and clean up processes."""
        target_driver = driver or self.current_driver

        if target_driver is None:
            return

        try:
            target_driver.quit()
            self.logger.debug("WebDriver quit successfully")
        except Exception as e:
            self.logger.warning(f"Error during driver quit: {e}")
        finally:
            # Always perform cleanup
            self.cleanup_orphaned_webdriver_processes()
            if target_driver == self.current_driver:
                self.current_driver = None

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
        driver.get(MediuxConfig.BASE_URL)

        try:
            # Check if already logged in
            WebDriverWait(
                driver, WebAutomationConstants.ELEMENT_WAIT_TIMEOUT_SHORT
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
                driver, WebAutomationConstants.ELEMENT_WAIT_TIMEOUT_MEDIUM
            ).until(
                EC.presence_of_element_located((By.XPATH, WebSelectors.SIGN_IN_BUTTON))
            )
            login_button.click()

            # Wait for login form to load
            WebDriverWait(
                driver, WebAutomationConstants.ELEMENT_WAIT_TIMEOUT_MEDIUM
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
                driver, WebAutomationConstants.ELEMENT_WAIT_TIMEOUT_MEDIUM
            ).until(
                EC.presence_of_element_located(
                    (By.XPATH, WebSelectors.get_user_button(nickname))
                )
            )
            self.logger.info("Logged into Mediux successfully.")

        except Exception as e:
            if self.webdriver_manager:
                self.webdriver_manager.take_screenshot(driver, "error_login")
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

                WebDriverWait(
                    driver, WebAutomationConstants.PROCESS_WAIT_TIMEOUT
                ).until(
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

                WebDriverWait(
                    driver, WebAutomationConstants.PROCESS_WAIT_TIMEOUT
                ).until(
                    lambda d: len(d.find_elements(By.XPATH, refresh_spinner_xpath)) == 0
                )

                self.logger.debug(
                    f"Page status: Refresh completed for {media_type} {tmdb_id}"
                )
                time.sleep(WebAutomationConstants.BRIEF_DELAY)
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
            all_yaml_buttons = WebDriverWait(
                driver, WebAutomationConstants.ELEMENT_WAIT_TIMEOUT_MEDIUM
            ).until(EC.presence_of_all_elements_located((By.XPATH, yaml_xpath)))
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

        self.logger.info(
            f"Scraping Mediux for TMDB ID {tmdb_id}, Media Type: {media_type}"
        )

        url, updating_text, success_text = self.get_media_url_and_texts(
            media_type, tmdb_id
        )

        # Navigation errors should always raise exceptions (never cached)
        try:
            # Simple health check - try to access driver property
            _ = driver.current_url
            driver.get(url)
        except Exception as e:
            self.logger.error(f"An error occurred during driver.get({url}): {e}")
            raise

        self.logger.debug(f"Navigated to URL: {url}")
        yaml_xpath = "//button[span[contains(text(), 'YAML')]]"
        time.sleep(WebAutomationConstants.STANDARD_DELAY)

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

            driver.execute_script("arguments[0].scrollIntoView(true);", yaml_button)
            yaml_button.click()
            self.logger.info(f"Extracting YAML data for {media_type} {tmdb_id}")

            yaml_element = WebDriverWait(
                driver, WebAutomationConstants.ELEMENT_WAIT_TIMEOUT_LONG
            ).until(EC.presence_of_element_located((By.XPATH, "//code")))
            WebDriverWait(
                driver, WebAutomationConstants.ELEMENT_WAIT_TIMEOUT_LONG
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

            yaml_len = len(yaml_data)
            self.logger.info(f"YAML data loaded successfully ({yaml_len} characters)")

            return yaml_data

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
                time.sleep(WebAutomationConstants.STANDARD_DELAY)
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
            return ""

import os
import logging
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.remote.webdriver import WebDriver
from webdriver_manager.chrome import ChromeDriverManager

logger = logging.getLogger(__name__)


def init_driver(headless=True, profile_path=None, chromedriver_path=None):
    """
    Initialize and configure a Chrome WebDriver instance.

    Args:
        headless (bool): Whether to run Chrome in headless mode
        profile_path (str): Path to Chrome user profile directory
        chromedriver_path (str): Path to ChromeDriver executable

    Returns:
        WebDriver: Configured Chrome WebDriver instance
    """
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


# Modify the take_screenshot function
def take_screenshot(driver: WebDriver, name: str, config_path=None):
    """
    Take a screenshot of the current browser state if SCREENSHOT=1 is set.

    Args:
        driver (WebDriver): Selenium WebDriver instance
        name (str): Base name for the screenshot file
        config_path (str): Path to save screenshots
    """
    from src.config.paths import get_screenshot_dir

    screenshot_enabled = os.environ.get("SCREENSHOT") == "1"
    if not screenshot_enabled:
        return

    screenshots_dir = get_screenshot_dir(config_path)
    screenshot_path = os.path.join(screenshots_dir, f"{name}.png")
    try:
        driver.save_screenshot(screenshot_path)
        logger.info(f"Screenshot saved: {screenshot_path}")
    except Exception as e:
        logger.error(f"Failed to save screenshot: {e}")

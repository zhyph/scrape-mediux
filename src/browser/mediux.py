import logging
from time import sleep
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.remote.webdriver import WebDriver
from .driver import take_screenshot

logger = logging.getLogger(__name__)


def scrape_mediux(
    driver, tmdb_id, media_type, retry_on_yaml_failure=False, config_path=None
):
    """
    Scrape YAML data from Mediux for a specific movie or TV show.

    Args:
        driver (WebDriver): Selenium WebDriver instance
        tmdb_id (str): TMDB ID of the media to scrape
        media_type (str): Type of media ('movie' or 'tv')
        retry_on_yaml_failure (bool): Whether to retry on YAML loading failure
        config_path (str): Path to save screenshots if needed

    Returns:
        str: YAML data from Mediux or empty string if not found
    """
    logger.info(f"Scraping Mediux for TMDB ID {tmdb_id}, Media Type: {media_type}...")
    base_url = "https://mediux.pro"
    if media_type == "movie":
        url = f"{base_url}/movies/{tmdb_id}"
    else:
        url = f"{base_url}/shows/{tmdb_id}"

    driver.get(url)

    yaml_xpath = "//button[span[contains(text(), 'YAML')]]"

    try:
        WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, yaml_xpath))
        )
        yaml_button = driver.find_element(By.XPATH, yaml_xpath)
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
        if not driver.find_elements(By.XPATH, yaml_xpath):
            logger.warning(f"YAML button not found for TMDB ID {tmdb_id}")
            return ""

        if retry_on_yaml_failure:
            logger.warning(
                f"YAML button found but an error occurred. Retrying by reloading the page for TMDB ID {tmdb_id}."
            )
            driver.refresh()
            sleep(5)
            return scrape_mediux(
                driver,
                tmdb_id,
                media_type,
                retry_on_yaml_failure=False,
                config_path=config_path,
            )

        take_screenshot(driver, f"error_scraping_tmdb_{tmdb_id}", config_path)
        logger.error(
            f"Error scraping TMDB ID {tmdb_id}, possible to not have YAML\n"
            f"This can be normal, but, if this ID had an YAML to be extracted and the script failed, "
            f"create an issue in the script Github\n{e}"
        )
        return ""


def login_mediux(driver, username, password, nickname, config_path=None):
    """
    Check if already logged in to Mediux and log in if needed.

    Args:
        driver (WebDriver): Selenium WebDriver instance
        username (str): Mediux username
        password (str): Mediux password
        nickname (str): Mediux user nickname to check if logged in
        config_path (str): Path to save screenshots if needed

    Raises:
        Exception: If login fails
    """
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
        take_screenshot(driver, "error_login", config_path)
        logger.error(f"Failed to log into Mediux: {e}")
        raise

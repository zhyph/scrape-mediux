"""
Unit tests for scraper.py module.

This module tests WebDriver management, login functionality, and YAML scraping capabilities.
"""

import pytest
import time
from unittest.mock import Mock, patch, MagicMock, call
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement

from modules.scraper import (
    WebDriverManager,
    MediuxLoginManager,
    MediuxScraper,
    initialize_and_login_driver,
)

# Import re for regex operations in tests
import re


def test_scraper_module_imports():
    """Test that all required imports are available."""
    # This test ensures the module can be imported without ChromeDriverManager issues
    from modules.scraper import WebDriverManager, MediuxLoginManager, MediuxScraper

    # Verify classes can be instantiated
    manager = WebDriverManager()
    assert manager is not None

    scraper = MediuxScraper()
    assert scraper is not None


class TestWebDriverManager:
    """Test cases for WebDriverManager class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.manager = WebDriverManager("/test/config")

    def test_init(self):
        """Test WebDriverManager initialization."""
        # Test with config path
        manager = WebDriverManager("/test/config")
        assert manager.config_path == "/test/config"
        assert manager.logger is not None

        # Test without config path
        manager_none = WebDriverManager()
        assert manager_none.config_path is None

    @patch("modules.scraper.webdriver.Chrome")
    @patch("modules.scraper.ChromeService")
    def test_init_driver_with_chromedriver_path(self, mock_service, mock_chrome):
        """Test WebDriver initialization with custom chromedriver path."""
        # Setup mocks
        mock_driver = Mock()
        mock_chrome.return_value = mock_driver
        mock_options = Mock()
        mock_options.arguments = ["--headless", "--user-data-dir=/test/profile"]

        # Execute
        result = self.manager.init_driver(
            headless=True,
            profile_path="/test/profile",
            chromedriver_path="/test/chromedriver",
        )

        # Verify
        mock_service.assert_called_once_with("/test/chromedriver")
        mock_chrome.assert_called_once()

        # Check that Chrome was called with service and options
        call_args = mock_chrome.call_args
        assert call_args is not None

        mock_driver.set_page_load_timeout.assert_called_once_with(300)
        assert result == mock_driver

    def test_init_driver_without_chromedriver_path(self):
        """Test WebDriver initialization using ChromeDriverManager."""
        # Setup mocks
        mock_driver = Mock()

        with patch("modules.scraper.webdriver.Chrome") as mock_chrome:
            with patch("modules.scraper.ChromeService") as mock_service:
                with patch(
                    "webdriver_manager.chrome.ChromeDriverManager"
                ) as mock_manager:
                    # Setup ChromeDriverManager mock
                    mock_driver_manager = Mock()
                    mock_driver_manager.install.return_value = "/auto/chromedriver"
                    mock_manager.return_value = mock_driver_manager

                    mock_chrome.return_value = mock_driver

                    # Execute
                    result = self.manager.init_driver(headless=False)

                    # Verify
                    mock_manager.assert_called_once()
                    mock_driver_manager.install.assert_called_once()
                    mock_driver.set_page_load_timeout.assert_called_once_with(300)
                    assert result == mock_driver

    @patch("modules.scraper.webdriver.Chrome")
    @patch("modules.scraper.ChromeService")
    def test_init_driver_exception_handling(self, mock_service, mock_chrome):
        """Test WebDriver initialization exception handling."""
        # Setup mock to raise exception
        mock_chrome.side_effect = Exception("Chrome initialization failed")

        # Execute and verify exception is raised
        with pytest.raises(Exception, match="Chrome initialization failed"):
            self.manager.init_driver()

    @patch("os.environ.get")
    def test_take_screenshot_disabled(self, mock_env_get):
        """Test screenshot functionality when disabled."""
        # Setup
        mock_env_get.return_value = None  # SCREENSHOT != "1"
        mock_driver = Mock()

        # Execute
        self.manager.take_screenshot(mock_driver, "test")

        # Verify - no screenshot taken
        mock_driver.save_screenshot.assert_not_called()

    @patch("os.environ.get")
    @patch("os.path.join")
    @patch("os.makedirs")
    def test_take_screenshot_no_config_path(
        self, mock_makedirs, mock_join, mock_env_get
    ):
        """Test screenshot functionality with no config path."""
        # Setup
        mock_env_get.return_value = "1"  # SCREENSHOT = "1"
        mock_driver = Mock()

        manager = WebDriverManager()  # No config path

        # Execute
        manager.take_screenshot(mock_driver, "test")

        # Verify - no screenshot taken, warning logged
        mock_driver.save_screenshot.assert_not_called()

    @patch("os.environ.get")
    @patch("os.path.join")
    @patch("os.makedirs")
    def test_take_screenshot_success(self, mock_makedirs, mock_join, mock_env_get):
        """Test successful screenshot capture."""
        # Setup
        mock_env_get.return_value = "1"  # SCREENSHOT = "1"
        mock_join.side_effect = [
            "/test/config/screenshots",
            "/test/config/screenshots/test.png",
        ]
        mock_driver = Mock()

        # Execute
        self.manager.take_screenshot(mock_driver, "test")

        # Verify
        mock_makedirs.assert_called_once_with("/test/config/screenshots", exist_ok=True)
        mock_driver.save_screenshot.assert_called_once_with(
            "/test/config/screenshots/test.png"
        )

    @patch("os.environ.get")
    @patch("os.path.join")
    @patch("os.makedirs")
    def test_take_screenshot_exception_handling(
        self, mock_makedirs, mock_join, mock_env_get
    ):
        """Test screenshot exception handling."""
        # Setup
        mock_env_get.return_value = "1"  # SCREENSHOT = "1"
        mock_join.side_effect = [
            "/test/config/screenshots",
            "/test/config/screenshots/test.png",
        ]
        mock_driver = Mock()
        mock_driver.save_screenshot.side_effect = Exception("Screenshot failed")

        # Execute
        self.manager.take_screenshot(mock_driver, "test")

        # Verify - exception was handled gracefully
        mock_driver.save_screenshot.assert_called_once()


class TestMediuxLoginManager:
    """Test cases for MediuxLoginManager class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_webdriver_manager = Mock()
        self.login_manager = MediuxLoginManager(self.mock_webdriver_manager)

    def test_init(self):
        """Test MediuxLoginManager initialization."""
        # Test with webdriver manager
        manager = MediuxLoginManager(self.mock_webdriver_manager)
        assert manager.webdriver_manager == self.mock_webdriver_manager

        # Test without webdriver manager
        manager_none = MediuxLoginManager()
        assert manager_none.webdriver_manager is None

    @patch("modules.scraper.WebDriverWait")
    @patch("modules.scraper.EC")
    def test_login_already_logged_in(self, mock_ec, mock_wait):
        """Test login when user is already logged in."""
        # Setup mocks
        mock_driver = Mock()
        mock_wait_instance = Mock()
        mock_wait.return_value = mock_wait_instance

        # Mock the presence_of_element_located to succeed (user already logged in)
        mock_wait_instance.until.return_value = Mock()  # Button found

        # Execute
        self.login_manager.login(mock_driver, "user", "pass", "TestUser")

        # Verify - no login attempt made
        mock_driver.find_element.assert_not_called()
        mock_driver.get.assert_called_once_with("https://mediux.pro")

    @patch("modules.scraper.WebDriverWait")
    @patch("modules.scraper.EC")
    def test_login_successful_flow(self, mock_ec, mock_wait):
        """Test successful login flow."""
        # Setup mocks
        mock_driver = Mock()
        mock_wait_instance = Mock()
        mock_wait.return_value = mock_wait_instance

        # Mock user not logged in initially
        mock_wait_instance.until.side_effect = [
            TimeoutException("Not logged in"),  # First wait fails
            Mock(),  # Sign in button found
            Mock(),  # Form loaded
            Mock(),  # Login successful
        ]

        # Mock form elements
        mock_username_field = Mock()
        mock_password_field = Mock()
        mock_submit_button = Mock()
        mock_driver.find_element.side_effect = [
            mock_username_field,
            mock_password_field,
            mock_submit_button,
        ]

        # Execute
        self.login_manager.login(mock_driver, "testuser", "testpass", "TestUser")

        # Verify login flow
        assert mock_driver.get.call_count == 1
        assert mock_username_field.send_keys.call_args[0][0] == "testuser"
        assert mock_password_field.send_keys.call_args[0][0] == "testpass"
        mock_submit_button.click.assert_called_once()

    @patch("modules.scraper.WebDriverWait")
    @patch("modules.scraper.EC")
    def test_login_exception_handling(self, mock_ec, mock_wait):
        """Test login exception handling."""
        # Setup mocks
        mock_driver = Mock()
        mock_wait_instance = Mock()
        mock_wait.return_value = mock_wait_instance

        # Mock all waits to fail
        mock_wait_instance.until.side_effect = TimeoutException("Login failed")

        # Execute and verify exception is raised
        with pytest.raises(TimeoutException):
            self.login_manager.login(mock_driver, "user", "pass", "TestUser")

        # Verify screenshot was taken on error
        self.mock_webdriver_manager.take_screenshot.assert_called_once_with(
            mock_driver, "error_login"
        )


class TestMediuxScraper:
    """Test cases for MediuxScraper class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.scraper = MediuxScraper()

    def test_init(self):
        """Test MediuxScraper initialization."""
        scraper = MediuxScraper()
        assert scraper.logger is not None

    def test_get_media_url_and_texts_movie(self):
        """Test URL and text generation for movies."""
        url, updating_text, success_text = self.scraper.get_media_url_and_texts(
            "movie", "12345"
        )

        assert url == "https://mediux.pro/movies/12345"
        assert updating_text == "Updating movie data"
        assert success_text == "Movie updated successfully"

    def test_get_media_url_and_texts_tv(self):
        """Test URL and text generation for TV shows."""
        url, updating_text, success_text = self.scraper.get_media_url_and_texts(
            "tv", "67890"
        )

        assert url == "https://mediux.pro/shows/67890"
        assert updating_text == "Updating show data"
        assert success_text == "Show updated successfully"

    @patch("modules.scraper.WebDriverWait")
    def test_wait_for_update_completion_with_update(self, mock_wait):
        """Test update completion waiting when update is in progress."""
        # Setup mocks
        mock_driver = Mock()
        mock_wait_instance = Mock()
        mock_wait.return_value = mock_wait_instance

        # Mock update elements found
        mock_update_elements = [Mock()]
        mock_update_elements[0].text = "Updating movie data"
        mock_success_elements = []

        mock_driver.find_elements.side_effect = [
            mock_update_elements,  # Update elements found
            mock_success_elements,  # No success elements initially
            mock_success_elements,  # Success elements after wait
        ]

        # Execute
        self.scraper.wait_for_update_completion(
            mock_driver,
            "Updating movie data",
            "Movie updated successfully",
            "movie",
            "12345",
        )

        # Verify WebDriverWait was called
        assert mock_wait.call_count == 1

    @patch("modules.scraper.WebDriverWait")
    def test_wait_for_update_completion_no_update(self, mock_wait):
        """Test update completion waiting when no update is needed."""
        # Setup mocks
        mock_driver = Mock()
        mock_wait_instance = Mock()
        mock_wait.return_value = mock_wait_instance

        # Mock no update elements found
        mock_driver.find_elements.return_value = []

        # Execute
        self.scraper.wait_for_update_completion(
            mock_driver,
            "Updating movie data",
            "Movie updated successfully",
            "movie",
            "12345",
        )

        # Verify WebDriverWait was not called
        mock_wait.assert_not_called()

    @patch("modules.scraper.time.sleep")
    def test_wait_for_refresh_completion_with_spinner(self, mock_sleep):
        """Test refresh completion waiting when spinner is present."""
        # Setup mocks
        mock_driver = Mock()
        mock_wait_instance = Mock()

        with patch("modules.scraper.WebDriverWait") as mock_wait:
            mock_wait.return_value = mock_wait_instance

            # Mock spinner elements found initially, then gone
            mock_spinner_elements = [Mock()]
            mock_driver.find_elements.side_effect = [
                mock_spinner_elements,  # Spinner found
                [],  # Spinner gone after wait
            ]

            # Execute
            self.scraper.wait_for_refresh_completion(mock_driver, "movie", "12345")

            # Verify WebDriverWait was called
            assert mock_wait.call_count == 1
            mock_sleep.assert_called_once_with(1)

    @patch("modules.scraper.WebDriverWait")
    def test_wait_for_refresh_completion_no_spinner(self, mock_wait):
        """Test refresh completion waiting when no spinner is present."""
        # Setup mocks
        mock_driver = Mock()
        mock_wait_instance = Mock()
        mock_wait.return_value = mock_wait_instance

        # Mock no spinner elements found
        mock_driver.find_elements.return_value = []

        # Execute
        self.scraper.wait_for_refresh_completion(mock_driver, "movie", "12345")

        # Verify WebDriverWait was not called
        mock_wait.assert_not_called()

    @patch("modules.scraper.WebDriverWait")
    def test_find_yaml_button_no_buttons(self, mock_wait):
        """Test YAML button finding when no buttons exist."""
        # Setup mocks
        mock_driver = Mock()
        mock_wait_instance = Mock()
        mock_wait.return_value = mock_wait_instance

        # Mock timeout - no buttons found
        mock_wait_instance.until.side_effect = TimeoutException("No buttons")

        # Execute
        result = self.scraper.find_yaml_button(
            mock_driver, "//button[contains(text(), 'YAML')]"
        )

        # Verify
        assert result is None

    @patch("modules.scraper.WebDriverWait")
    def test_find_yaml_button_with_buttons(self, mock_wait):
        """Test YAML button finding with available buttons."""
        # Setup mocks
        mock_driver = Mock()
        mock_wait_instance = Mock()
        mock_wait.return_value = mock_wait_instance

        # Mock buttons found
        mock_button = Mock()
        mock_wait_instance.until.return_value = [mock_button]

        # Execute
        result = self.scraper.find_yaml_button(
            mock_driver, "//button[contains(text(), 'YAML')]"
        )

        # Verify
        assert result == mock_button

    @patch("modules.scraper.WebDriverWait")
    def test_find_yaml_button_with_excluded_users(self, mock_wait):
        """Test YAML button finding with user exclusions."""
        # Setup mocks
        mock_driver = Mock()
        mock_wait_instance = Mock()
        mock_wait.return_value = mock_wait_instance

        # Mock buttons with user links
        mock_button1 = Mock()
        mock_button2 = Mock()
        mock_buttons = [mock_button1, mock_button2]

        # Mock user extraction for button1 (excluded user)
        mock_ancestor_div1 = Mock()
        mock_user_link1 = Mock()
        mock_user_link1.get_attribute.return_value = "/user/excluded_user"
        mock_ancestor_div1.find_element.return_value = mock_user_link1
        mock_button1.find_element.return_value = mock_ancestor_div1

        # Mock user extraction for button2 (allowed user)
        mock_ancestor_div2 = Mock()
        mock_user_link2 = Mock()
        mock_user_link2.get_attribute.return_value = "/user/allowed_user"
        mock_ancestor_div2.find_element.return_value = mock_user_link2
        mock_button2.find_element.return_value = mock_ancestor_div2

        mock_wait_instance.until.return_value = mock_buttons

        # Execute
        result = self.scraper.find_yaml_button(
            mock_driver,
            "//button[contains(text(), 'YAML')]",
            excluded_users=["excluded_user"],
        )

        # Verify - should return allowed button
        assert result == mock_button2

    def test_find_yaml_button_with_preferred_users(self):
        """Test YAML button finding with preferred users."""
        # Setup mocks
        mock_driver = Mock()

        with patch("modules.scraper.WebDriverWait") as mock_wait:
            mock_wait_instance = Mock()
            mock_wait.return_value = mock_wait_instance

            # Mock buttons with user links
            mock_button1 = Mock()
            mock_button2 = Mock()
            mock_buttons = [mock_button1, mock_button2]

            # Mock button1 (non-preferred user) - will raise exception
            mock_button1.find_element.side_effect = Exception("User not found")

            # Mock button2 (preferred user) - will succeed
            mock_ancestor_div2 = Mock()
            mock_user_link2 = Mock()
            mock_user_link2.get_attribute.return_value = "/user/preferred_user"
            mock_user_button2 = Mock()
            mock_ancestor_div2.find_element.side_effect = [
                mock_user_link2,
                mock_user_button2,
            ]
            mock_button2.find_element.return_value = mock_ancestor_div2

            mock_wait_instance.until.return_value = mock_buttons

            # Execute
            result = self.scraper.find_yaml_button(
                mock_driver,
                "//button[contains(text(), 'YAML')]",
                preferred_users=["preferred_user"],
            )

            # Verify - should return preferred user button
            assert result == mock_button2

    @patch("modules.scraper.time.sleep")
    @patch("modules.scraper.WebDriverWait")
    def test_scrape_mediux_success(self, mock_wait, mock_sleep):
        """Test successful YAML scraping."""
        # Setup mocks
        mock_driver = Mock()
        mock_wait_instance = Mock()
        mock_wait.return_value = mock_wait_instance

        # Mock URL navigation and YAML extraction
        mock_yaml_element = Mock()
        mock_yaml_element.get_attribute.return_value = "test yaml data"
        mock_wait_instance.until.return_value = mock_yaml_element

        # Mock find_yaml_button to return a button
        with patch.object(self.scraper, "find_yaml_button", return_value=Mock()):
            with patch.object(
                self.scraper,
                "get_media_url_and_texts",
                return_value=("https://mediux.pro/movies/123", "updating", "success"),
            ):
                with patch.object(self.scraper, "wait_for_update_completion"):
                    with patch.object(self.scraper, "wait_for_refresh_completion"):

                        # Execute
                        result = self.scraper.scrape_mediux(mock_driver, "123", "movie")

                        # Verify
                        assert result == "test yaml data"
                        mock_driver.get.assert_called_once_with(
                            "https://mediux.pro/movies/123"
                        )

    @patch("modules.scraper.time.sleep")
    @patch("modules.scraper.WebDriverWait")
    def test_scrape_mediux_no_yaml_button(self, mock_wait, mock_sleep):
        """Test YAML scraping when no button is found."""
        # Setup mocks
        mock_driver = Mock()
        mock_wait_instance = Mock()
        mock_wait.return_value = mock_wait_instance

        # Mock cache to return None (no cached data)
        with patch.object(self.scraper.cache_manager.cache, "get", return_value=None):
            # Mock find_yaml_button to return None
            with patch.object(self.scraper, "find_yaml_button", return_value=None):
                with patch.object(
                    self.scraper,
                    "get_media_url_and_texts",
                    return_value=(
                        "https://mediux.pro/movies/123",
                        "updating",
                        "success",
                    ),
                ):
                    with patch.object(self.scraper, "wait_for_update_completion"):
                        with patch.object(self.scraper, "wait_for_refresh_completion"):

                            # Execute
                            result = self.scraper.scrape_mediux(
                                mock_driver, "123", "movie"
                            )

                            # Verify
                            assert result == ""

    def test_scrape_mediux_with_retry(self):
        """Test YAML scraping with retry on failure."""
        # Setup mocks
        mock_driver = Mock()
        mock_button = Mock()

        # Mock cache to return None (no cached data) so we test the actual retry logic
        with patch.object(self.scraper.cache_manager.cache, "get", return_value=None):
            # Mock find_yaml_button to return a button initially, then None on retry
            def mock_find_yaml_button(*args, **kwargs):
                if mock_driver.refresh.call_count == 0:
                    return mock_button  # Return button first time
                else:
                    return None  # Return None on retry

            with patch("modules.scraper.time.sleep"):
                with patch.object(
                    self.scraper, "find_yaml_button", side_effect=mock_find_yaml_button
                ):
                    with patch.object(
                        self.scraper,
                        "get_media_url_and_texts",
                        return_value=(
                            "https://mediux.pro/movies/123",
                            "updating",
                            "success",
                        ),
                    ):
                        with patch.object(self.scraper, "wait_for_update_completion"):
                            with patch.object(
                                self.scraper, "wait_for_refresh_completion"
                            ):
                                with patch(
                                    "modules.scraper.WebDriverWait"
                                ) as mock_wait:
                                    mock_wait_instance = Mock()
                                    mock_wait.return_value = mock_wait_instance

                                    # Mock YAML buttons found on page
                                    mock_driver.find_elements.return_value = [
                                        mock_button
                                    ]

                                    # Mock YAML element timeout on first attempt (triggering retry)
                                    mock_wait_instance.until.side_effect = [
                                        Mock(),  # First wait succeeds (YAML button click)
                                        TimeoutException(
                                            "No YAML element"
                                        ),  # Second wait fails (YAML content)
                                    ]

                                    # Execute with retry enabled
                                    result = self.scraper.scrape_mediux(
                                        mock_driver,
                                        "123",
                                        "movie",
                                        retry_on_yaml_failure=True,
                                    )

                                    # Verify
                                    assert result == ""
                                    assert mock_driver.refresh.call_count == 1

    @patch("modules.scraper.time.sleep")
    def test_scrape_mediux_navigation_error(self, mock_sleep):
        """Test YAML scraping when navigation fails."""
        # Setup mocks
        mock_driver = Mock()
        mock_driver.get.side_effect = Exception("Navigation failed")

        # Mock cache to return None (no cached data) so navigation is attempted
        with patch.object(self.scraper.cache_manager.cache, "get", return_value=None):
            # Execute and verify exception is raised
            with pytest.raises(Exception, match="Navigation failed"):
                self.scraper.scrape_mediux(mock_driver, "123", "movie")


class TestInitializeAndLoginDriver:
    """Test cases for initialize_and_login_driver function."""

    @patch("modules.scraper.WebDriverManager")
    @patch("modules.scraper.MediuxLoginManager")
    def test_initialize_and_login_success(self, mock_login_class, mock_webdriver_class):
        """Test successful driver initialization and login."""
        # Setup mocks
        mock_webdriver_manager = Mock()
        mock_driver = Mock()
        mock_webdriver_manager.init_driver.return_value = mock_driver
        mock_webdriver_class.return_value = mock_webdriver_manager

        mock_login_manager = Mock()
        mock_login_class.return_value = mock_login_manager

        # Execute
        result = initialize_and_login_driver(
            headless=True,
            profile_path="/test/profile",
            chromedriver_path="/test/driver",
            username="user",
            password="pass",
            nickname="User",
        )

        # Verify
        assert result == mock_driver
        mock_webdriver_manager.init_driver.assert_called_once_with(
            headless=True,
            profile_path="/test/profile",
            chromedriver_path="/test/driver",
        )
        mock_login_manager.login.assert_called_once_with(
            driver=mock_driver, username="user", password="pass", nickname="User"
        )

    @patch("modules.scraper.WebDriverManager")
    @patch("modules.scraper.MediuxLoginManager")
    def test_initialize_and_login_failure(self, mock_login_class, mock_webdriver_class):
        """Test driver initialization and login failure."""
        # Setup mocks
        mock_webdriver_manager = Mock()
        mock_driver = Mock()
        mock_webdriver_manager.init_driver.return_value = mock_driver
        mock_webdriver_class.return_value = mock_webdriver_manager

        mock_login_manager = Mock()
        mock_login_manager.login.side_effect = Exception("Login failed")
        mock_login_class.return_value = mock_login_manager

        # Execute and verify exception is raised
        with pytest.raises(Exception, match="Login failed"):
            initialize_and_login_driver(
                headless=False,
                profile_path=None,
                chromedriver_path=None,
                username="user",
                password="pass",
                nickname="User",
            )

        # Verify driver was quit on login failure
        mock_driver.quit.assert_called_once()

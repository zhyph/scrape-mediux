"""
Tests for external_services.py module.
"""

from unittest.mock import Mock, patch

import pytest
from requests.exceptions import RequestException, Timeout

from modules.external_services import (
    DiscordNotifier,
    MediaDiscoveryService,
    PlexClient,
    SonarrClient,
)


class TestDiscordNotifier:
    """Test cases for DiscordNotifier class."""

    def test_init(self):
        """Test DiscordNotifier initialization."""
        notifier = DiscordNotifier()
        assert notifier is not None
        assert hasattr(notifier, "logger")

    def test_send_notification_with_webhook(self):
        """Test send_notification with valid webhook."""
        notifier = DiscordNotifier()

        with patch("requests.post") as mock_post:
            mock_response = Mock()
            mock_response.raise_for_status.return_value = None
            mock_post.return_value = mock_response

            with patch.object(notifier, "logger") as mock_logger:
                notifier.send_notification(
                    "https://discord.com/api/webhooks/test", "Test message"
                )

                mock_post.assert_called_once()
                args, kwargs = mock_post.call_args
                assert args[0] == "https://discord.com/api/webhooks/test"
                assert kwargs["json"]["content"] == "Test message"
                assert kwargs["timeout"] == 10
                mock_logger.info.assert_called()

    def test_send_notification_no_webhook(self):
        """Test send_notification with no webhook provided."""
        notifier = DiscordNotifier()

        with patch.object(notifier, "logger") as mock_logger:
            notifier.send_notification(None, "Test message")

            mock_logger.debug.assert_called_with(
                "Discord webhook URL not configured. Skipping notification."
            )

    def test_send_notification_empty_message(self):
        """Test send_notification with empty message."""
        notifier = DiscordNotifier()

        with patch.object(notifier, "logger") as mock_logger:
            notifier.send_notification("https://discord.com/api/webhooks/test", "")

            mock_logger.debug.assert_called_with(
                "No message content to send to Discord. Skipping notification."
            )

    def test_send_notification_request_exception(self):
        """Test send_notification with request exception."""
        notifier = DiscordNotifier()

        with patch("requests.post") as mock_post:
            mock_post.side_effect = RequestException("Connection failed")

            with patch.object(notifier, "logger") as mock_logger:
                notifier.send_notification(
                    "https://discord.com/api/webhooks/test", "Test message"
                )

                mock_logger.error.assert_called_with(
                    "Failed to send Discord notification: Connection failed"
                )

    def test_send_notification_timeout(self):
        """Test send_notification with timeout."""
        notifier = DiscordNotifier()

        with patch("requests.post") as mock_post:
            mock_post.side_effect = Timeout("Request timed out")

            with patch.object(notifier, "logger") as mock_logger:
                notifier.send_notification(
                    "https://discord.com/api/webhooks/test", "Test message"
                )

                mock_logger.error.assert_called()


class TestSonarrClient:
    """Test cases for SonarrClient class."""

    def test_init(self):
        """Test SonarrClient initialization."""
        client = SonarrClient("api_key", "http://sonarr:8989")
        assert client.api_key == "api_key"
        assert client.endpoint == "http://sonarr:8989"
        assert client.headers["X-Api-Key"] == "api_key"
        assert hasattr(client, "logger")

    @patch("modules.external_services.get_cache_manager")
    def test_check_series_status_cache_hit(self, mock_get_cache_manager):
        """Test check_series_status with cache hit."""
        mock_cache_manager = Mock()
        mock_cache_manager.get_sonarr_status.return_value = ("tvdb123", True)
        mock_get_cache_manager.return_value = mock_cache_manager

        client = SonarrClient("api_key", "http://sonarr:8989")

        with patch.object(client, "logger") as mock_logger:
            result = client.check_series_status("Test Show", "tmdb123")

            assert result == ("tvdb123", True)
            mock_logger.info.assert_called_with("Sonarr cache hit for Test Show")

    @patch("modules.external_services.get_cache_manager")
    def test_check_series_status_success(self, mock_get_cache_manager):
        """Test check_series_status successful API call."""
        mock_cache_manager = Mock()
        mock_cache_manager.get_sonarr_status.return_value = None
        mock_get_cache_manager.return_value = mock_cache_manager

        client = SonarrClient("api_key", "http://sonarr:8989")

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"tvdbId": 12345, "tmdbId": 123, "ended": True}
        ]

        with patch("requests.get", return_value=mock_response):
            with patch.object(client, "logger") as mock_logger:
                result = client.check_series_status("Test Show", "123")

                assert result == ("12345", True)
                mock_cache_manager.set_sonarr_status.assert_called_once_with(
                    "Test Show", "123", "12345", True
                )
                mock_logger.info.assert_called()

    @patch("modules.external_services.get_cache_manager")
    def test_check_series_status_tmdb_match(self, mock_get_cache_manager):
        """Test check_series_status with TMDB ID matching."""
        mock_cache_manager = Mock()
        mock_cache_manager.get_sonarr_status.return_value = None
        mock_get_cache_manager.return_value = mock_cache_manager

        client = SonarrClient("api_key", "http://sonarr:8989")

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"tvdbId": 12345, "tmdbId": 123, "ended": True},
            {"tvdbId": 67890, "tmdbId": 456, "ended": False},
        ]

        with patch("requests.get", return_value=mock_response):
            with patch.object(client, "logger") as mock_logger:
                result = client.check_series_status("Test Show", "123")

                assert result == ("12345", True)
                # Check that both expected log messages were called
                expected_calls = [
                    "Found matching series for 'Test Show' by TMDB ID: 123",
                    "Series status for Test Show: TVDB ID=12345, Ended=True.",
                ]
                actual_calls = [call[0][0] for call in mock_logger.info.call_args_list]
                for expected in expected_calls:
                    assert expected in actual_calls

    @patch("modules.external_services.get_cache_manager")
    def test_check_series_status_fallback_to_first(self, mock_get_cache_manager):
        """Test check_series_status falling back to first result."""
        mock_cache_manager = Mock()
        mock_cache_manager.get_sonarr_status.return_value = None
        mock_get_cache_manager.return_value = mock_cache_manager

        client = SonarrClient("api_key", "http://sonarr:8989")

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"tvdbId": 12345, "tmdbId": 999, "ended": True}
        ]

        with patch("requests.get", return_value=mock_response):
            with patch.object(client, "logger") as mock_logger:
                result = client.check_series_status(
                    "Test Show", "123"
                )  # TMDB ID doesn't match

                assert result == ("12345", True)
                mock_logger.warning.assert_called_with(
                    "No series with TMDB ID 123 found for 'Test Show'. Falling back to first result."
                )

    @patch("modules.external_services.get_cache_manager")
    def test_check_series_status_no_results(self, mock_get_cache_manager):
        """Test check_series_status with no results."""
        mock_cache_manager = Mock()
        mock_cache_manager.get_sonarr_status.return_value = None
        mock_get_cache_manager.return_value = mock_cache_manager

        client = SonarrClient("api_key", "http://sonarr:8989")

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []

        with patch("requests.get", return_value=mock_response):
            with patch.object(client, "logger") as mock_logger:
                result = client.check_series_status("Test Show")

                assert result == (None, None)
                mock_cache_manager.set_sonarr_status.assert_called_with(
                    "Test Show", None, None, None
                )
                mock_logger.warning.assert_called_with(
                    "No series information found for Test Show."
                )

    @patch("modules.external_services.get_cache_manager")
    def test_check_series_status_request_exception(self, mock_get_cache_manager):
        """Test check_series_status with request exception."""
        mock_cache_manager = Mock()
        mock_cache_manager.get_sonarr_status.return_value = None
        mock_get_cache_manager.return_value = mock_cache_manager

        client = SonarrClient("api_key", "http://sonarr:8989")

        with patch("requests.get", side_effect=RequestException("Connection failed")):
            with patch.object(client, "logger") as mock_logger:
                with pytest.raises(
                    Exception
                ):  # tenacity.RetryError wraps the original exception
                    client.check_series_status("Test Show")

    def test_check_series_status_retry_decorator(self):
        """Test check_series_status retry decorator."""
        # Test that the method has the retry decorator applied
        client = SonarrClient("api_key", "http://sonarr:8989")

        # Check that the method has the retry decorator by checking for wrapped function
        assert hasattr(client.check_series_status, "__wrapped__")

        # Verify the original function has the retry decorator
        import inspect

        source = inspect.getsource(client.check_series_status)
        assert "@retry(" in source


class TestPlexClient:
    """Test cases for PlexClient class."""

    def test_init(self):
        """Test PlexClient initialization."""
        client = PlexClient("http://plex:32400", "token123")
        assert client.url == "http://plex:32400"
        assert client.token == "token123"
        assert hasattr(client, "logger")

    @patch("modules.external_services.get_cache_manager")
    def test_get_media_ids_from_plex_cache_hit(self, mock_get_cache_manager):
        """Test get_media_ids_from_plex with cache hit."""
        mock_cache_manager = Mock()
        mock_cache_manager.cache.get.return_value = (["media1"], {"map": "data"})
        mock_get_cache_manager.return_value = mock_cache_manager

        client = PlexClient("http://plex:32400", "token123")

        with patch.object(client, "logger") as mock_logger:
            result = client.get_media_ids_from_plex(["Movies"])

            assert result == (["media1"], {"map": "data"})
            mock_logger.info.assert_called_with("Plex media IDs cache hit")

    @patch("modules.external_services.get_cache_manager")
    def test_get_media_ids_from_plex_success(self, mock_get_cache_manager):
        """Test get_media_ids_from_plex successful API call."""
        mock_cache_manager = Mock()
        mock_cache_manager.cache.get.return_value = None
        mock_get_cache_manager.return_value = mock_cache_manager

        client = PlexClient("http://plex:32400", "token123")

        # Mock Plex server and library
        mock_guid = Mock()
        mock_guid.id = "tmdb://123"

        mock_item = Mock()
        mock_item.title = "Test Movie"
        mock_item.guids = [mock_guid]

        mock_library = Mock()
        mock_library.type = "movie"
        mock_library.all.return_value = [mock_item]

        mock_plex = Mock()
        mock_plex.library.section.return_value = mock_library

        with patch("plexapi.server.PlexServer", return_value=mock_plex):
            with patch.object(client, "logger") as mock_logger:
                result = client.get_media_ids_from_plex(["Movies"])

                media_ids, folder_map = result
                assert len(media_ids) == 1
                assert media_ids[0][0] == "123"  # TMDB ID
                assert media_ids[0][1] == "Test Movie"
                assert media_ids[0][2] == "tmdb_id"
                assert media_ids[0][3] == "movie"

                mock_logger.info.assert_called_with("Found 1 media IDs from Plex.")

    @patch("modules.external_services.get_cache_manager")
    def test_get_media_ids_from_plex_multiple_guids(self, mock_get_cache_manager):
        """Test get_media_ids_from_plex with multiple GUIDs."""
        mock_cache_manager = Mock()
        mock_cache_manager.cache.get.return_value = None
        mock_get_cache_manager.return_value = mock_cache_manager

        client = PlexClient("http://plex:32400", "token123")

        # Mock multiple GUIDs with different priorities
        mock_guids = [
            Mock(id="tmdb://123"),  # TMDB (highest priority)
            Mock(id="imdb://tt0111161"),
            Mock(id="tvdb://456"),
        ]

        mock_item = Mock()
        mock_item.title = "Test Movie"
        mock_item.guids = mock_guids

        mock_library = Mock()
        mock_library.type = "movie"
        mock_library.all.return_value = [mock_item]

        mock_plex = Mock()
        mock_plex.library.section.return_value = mock_library

        with patch("plexapi.server.PlexServer", return_value=mock_plex):
            result = client.get_media_ids_from_plex(["Movies"])

            media_ids, folder_map = result
            assert len(media_ids) == 1
            assert media_ids[0][0] == "123"  # Should use TMDB ID (highest priority)
            assert media_ids[0][2] == "tmdb_id"

    @patch("modules.external_services.get_cache_manager")
    def test_get_media_ids_from_plex_no_guids(self, mock_get_cache_manager):
        """Test get_media_ids_from_plex with no usable GUIDs."""
        mock_cache_manager = Mock()
        mock_cache_manager.cache.get.return_value = None
        mock_get_cache_manager.return_value = mock_cache_manager

        client = PlexClient("http://plex:32400", "token123")

        mock_item = Mock()
        mock_item.title = "Test Movie"
        mock_item.guids = []  # No GUIDs

        mock_library = Mock()
        mock_library.type = "movie"
        mock_library.all.return_value = [mock_item]

        mock_plex = Mock()
        mock_plex.library.section.return_value = mock_library

        with patch("plexapi.server.PlexServer", return_value=mock_plex):
            with patch.object(client, "logger") as mock_logger:
                result = client.get_media_ids_from_plex(["Movies"])

                media_ids, folder_map = result
                assert len(media_ids) == 0
                mock_logger.warning.assert_called_with(
                    "No usable ID found for 'Test Movie' in Plex library 'Movies'"
                )

    def test_get_media_ids_from_plex_missing_plexapi(self):
        """Test get_media_ids_from_plex with missing plexapi."""
        client = PlexClient("http://plex:32400", "token123")

        with patch.dict("sys.modules", {"plexapi.server": None}):
            with patch(
                "builtins.__import__",
                side_effect=ImportError("No module named 'plexapi'"),
            ):
                with pytest.raises(ImportError):
                    client.get_media_ids_from_plex(["Movies"])

    def test_get_media_ids_from_plex_invalid_library(self):
        """Test get_media_ids_from_plex with invalid library."""
        client = PlexClient("http://plex:32400", "token123")

        mock_plex = Mock()
        mock_plex.library.section.side_effect = Exception("Invalid library")

        with patch("plexapi.server.PlexServer", return_value=mock_plex):
            with patch.object(client, "logger") as mock_logger:
                result = client.get_media_ids_from_plex(["InvalidLibrary"])

                media_ids, folder_map = result
                assert len(media_ids) == 0
                mock_logger.error.assert_called_with(
                    "Invalid Plex library section: InvalidLibrary (Invalid library)"
                )

    def test_list_available_libraries(self):
        """Test list_available_libraries method."""
        client = PlexClient("http://plex:32400", "token123")

        mock_section1 = Mock()
        mock_section1.title = "Movies"

        mock_section2 = Mock()
        mock_section2.title = "TV Shows"

        mock_plex = Mock()
        mock_plex.library.sections.return_value = [mock_section1, mock_section2]

        with patch("plexapi.server.PlexServer", return_value=mock_plex):
            with patch.object(client, "logger") as mock_logger:
                result = client.list_available_libraries()

                assert result == ["Movies", "TV Shows"]
                mock_logger.info.assert_called()

    def test_list_available_libraries_missing_plexapi(self):
        """Test list_available_libraries with missing plexapi."""
        client = PlexClient("http://plex:32400", "token123")

        with patch.dict("sys.modules", {"plexapi.server": None}):
            with patch(
                "builtins.__import__",
                side_effect=ImportError("No module named 'plexapi'"),
            ):
                with pytest.raises(ImportError):
                    client.list_available_libraries()


class TestMediaDiscoveryService:
    """Test cases for MediaDiscoveryService class."""

    def test_init(self):
        """Test MediaDiscoveryService initialization."""
        service = MediaDiscoveryService()
        assert service is not None
        assert hasattr(service, "logger")

    def test_extract_media_info_from_subfolder_imdb(self):
        """Test extract_media_info_from_subfolder with IMDB ID."""
        service = MediaDiscoveryService()

        result = service._extract_media_info_from_subfolder(
            "Movie.Name{imdb-tt0111161}"
        )
        assert result == ("tt0111161", "Movie.Name", "imdb_id")

    def test_extract_media_info_from_subfolder_tvdb(self):
        """Test extract_media_info_from_subfolder with TVDB ID."""
        service = MediaDiscoveryService()

        result = service._extract_media_info_from_subfolder("TV.Show.Name{tvdb-12345}")
        assert result == ("12345", "TV.Show.Name", "tvdb_id")

    def test_extract_media_info_from_subfolder_tmdb(self):
        """Test extract_media_info_from_subfolder with TMDB ID."""
        service = MediaDiscoveryService()

        result = service._extract_media_info_from_subfolder("Movie.Name{tmdb-123}")
        assert result == ("123", "Movie.Name", "tmdb_id")

    def test_extract_media_info_from_subfolder_no_match(self):
        """Test extract_media_info_from_subfolder with no pattern match."""
        service = MediaDiscoveryService()

        result = service._extract_media_info_from_subfolder("Movie.Name")
        assert result is None

    def test_extract_media_info_from_subfolder_malformed(self):
        """Test extract_media_info_from_subfolder with malformed pattern."""
        service = MediaDiscoveryService()

        result = service._extract_media_info_from_subfolder("Movie.Name{imdb}")
        assert result is None

    @patch("os.listdir")
    @patch("os.path.isdir")
    @patch(
        "modules.external_services.MediaDiscoveryService._extract_media_info_from_subfolder"
    )
    def test_process_subfolders(self, mock_extract, mock_isdir, mock_listdir):
        """Test _process_subfolders method."""
        service = MediaDiscoveryService()

        # Setup mocks
        mock_listdir.return_value = ["subfolder1", "subfolder2"]
        mock_isdir.return_value = True
        mock_extract.side_effect = [
            ("tt0111161", "Movie 1", "imdb_id"),
            ("tt0111162", "Movie 2", "imdb_id"),
        ]

        media_ids = []
        folder_map = {}
        # Pre-initialize the folder_map with expected keys to avoid KeyError
        folder_map.setdefault("tt0111161", [])
        folder_map.setdefault("tt0111162", [])

        service._process_subfolders("/test/path", "TestFolder", media_ids, folder_map)

        assert len(media_ids) == 2
        assert media_ids[0] == ("tt0111161", "Movie 1", "imdb_id", None)
        assert media_ids[1] == ("tt0111162", "Movie 2", "imdb_id", None)
        assert folder_map["tt0111161"] == ["TestFolder"]
        assert folder_map["tt0111162"] == ["TestFolder"]

    @patch("os.listdir")
    @patch("os.path.isdir")
    @patch(
        "modules.external_services.MediaDiscoveryService._extract_media_info_from_subfolder"
    )
    def test_process_subfolders_no_info(self, mock_extract, mock_isdir, mock_listdir):
        """Test _process_subfolders with no media info extracted."""
        service = MediaDiscoveryService()

        # Setup mocks
        mock_listdir.return_value = ["subfolder1"]
        mock_isdir.return_value = True
        mock_extract.return_value = None  # No media info found

        media_ids = []
        folder_map = {}

        service._process_subfolders("/test/path", "TestFolder", media_ids, folder_map)

        assert len(media_ids) == 0
        assert len(folder_map) == 0

    @patch("modules.external_services.get_cache_manager")
    def test_get_media_ids_from_folder_cache_hit(self, mock_get_cache_manager):
        """Test get_media_ids_from_folder with cache hit."""
        mock_cache_manager = Mock()
        mock_cache_manager.cache.get.return_value = (["media1"], {"map": "data"})
        mock_get_cache_manager.return_value = mock_cache_manager

        service = MediaDiscoveryService()

        with patch.object(service, "logger") as mock_logger:
            result = service.get_media_ids_from_folder("/test/folder")

            assert result == (["media1"], {"map": "data"})
            mock_logger.info.assert_called_with("Media IDs cache hit for folder scan")

    def test_extract_media_info_from_subfolder_edge_cases(self):
        """Test extract_media_info_from_subfolder with edge cases."""
        service = MediaDiscoveryService()

        # Test empty string
        result = service._extract_media_info_from_subfolder("")
        assert result is None

        # Test string without braces
        result = service._extract_media_info_from_subfolder("Just a movie name")
        assert result is None

        # Test string with braces but no valid format
        result = service._extract_media_info_from_subfolder(
            "Movie.Name{invalid-format}"
        )
        assert result is None

        # Test string with incomplete braces
        result = service._extract_media_info_from_subfolder("Movie.Name{imdb-")
        assert result is None

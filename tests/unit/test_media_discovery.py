"""
Unit tests for media_discovery.py module.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from modules.media_discovery import get_media_ids


class TestGetMediaIds:
    """Test cases for get_media_ids function."""

    def test_get_media_ids_from_plex_success(self, mock_plex_client):
        """Test successful media ID retrieval from Plex."""
        expected_ids = ["tt0111161", "tt0068646", "tt0071562"]

        with patch("modules.external_services.PlexClient") as mock_plex_class:
            mock_plex_class.return_value = mock_plex_client
            mock_plex_client.get_media_ids_from_plex.return_value = expected_ids

            result = get_media_ids(
                plex_url="http://plex.example.com",
                plex_token="test_token",
                plex_libraries=["Movies", "TV Shows"],
            )

            assert result == expected_ids
            mock_plex_class.assert_called_once_with(
                "http://plex.example.com", "test_token"
            )
            mock_plex_client.get_media_ids_from_plex.assert_called_once_with(
                ["Movies", "TV Shows"]
            )

    def test_get_media_ids_from_plex_exception_fallback_to_folder(
        self, mock_discovery_service
    ):
        """Test Plex failure falls back to folder scanning."""
        expected_ids = ["tt0111161", "tt0068646"]

        with patch("modules.external_services.PlexClient") as mock_plex_class, patch(
            "modules.external_services.MediaDiscoveryService"
        ) as mock_discovery_class:

            mock_plex_class.side_effect = Exception("Plex connection failed")
            mock_discovery_class.return_value = mock_discovery_service
            mock_discovery_service.get_media_ids_from_folder.return_value = expected_ids

            result = get_media_ids(
                root_folder="/path/to/media",
                plex_url="http://plex.example.com",
                plex_token="test_token",
                plex_libraries=["Movies"],
            )

            assert result == expected_ids
            mock_discovery_class.assert_called_once()
            mock_discovery_service.get_media_ids_from_folder.assert_called_once_with(
                "/path/to/media", None
            )

    def test_get_media_ids_partial_plex_config_fallback_to_folder(
        self, mock_discovery_service, caplog
    ):
        """Test fallback to folder scanning when Plex libraries are empty."""
        expected_ids = ["tt0111161", "tt0068646"]

        with patch(
            "modules.external_services.MediaDiscoveryService"
        ) as mock_discovery_class:
            mock_discovery_class.return_value = mock_discovery_service
            mock_discovery_service.get_media_ids_from_folder.return_value = expected_ids

            result = get_media_ids(
                root_folder="/path/to/media",
                plex_url="http://plex.example.com",
                plex_token="test_token",
                plex_libraries=[],
            )

            assert result == expected_ids
            mock_discovery_service.get_media_ids_from_folder.assert_called_once_with(
                "/path/to/media", None
            )

            # Check that fallback warning was logged
            assert "Could not connect to Plex to list libraries" in caplog.text
            assert "Using root_folder instead" in caplog.text

    def test_get_media_ids_partial_plex_config_exception_fallback(
        self, mock_discovery_service, caplog
    ):
        """Test Plex exception during library listing falls back to folder."""
        with patch("modules.external_services.PlexClient") as mock_plex_class, patch(
            "modules.external_services.MediaDiscoveryService"
        ) as mock_discovery_class:

            mock_plex_class.side_effect = Exception("Connection failed")
            mock_discovery_class.return_value = mock_discovery_service
            mock_discovery_service.get_media_ids_from_folder.return_value = [
                "tt0111161"
            ]

            result = get_media_ids(
                root_folder="/path/to/media",
                plex_url="http://plex.example.com",
                plex_token="test_token",
                plex_libraries=[],
            )

            mock_discovery_service.get_media_ids_from_folder.assert_called_once_with(
                "/path/to/media", None
            )
            assert "Could not connect to Plex to list libraries" in caplog.text

    def test_get_media_ids_folder_scanning_success(self, mock_discovery_service):
        """Test successful folder scanning when no Plex config provided."""
        expected_ids = ["tt0111161", "tt0068646", "tt0071562"]

        with patch(
            "modules.external_services.MediaDiscoveryService"
        ) as mock_discovery_class:
            mock_discovery_class.return_value = mock_discovery_service
            mock_discovery_service.get_media_ids_from_folder.return_value = expected_ids

            result = get_media_ids(root_folder="/path/to/media")

            assert result == expected_ids
            mock_discovery_class.assert_called_once()
            mock_discovery_service.get_media_ids_from_folder.assert_called_once_with(
                "/path/to/media", None
            )

    def test_get_media_ids_folder_scanning_with_selected_folders(
        self, mock_discovery_service
    ):
        """Test folder scanning with selected folders filter."""
        expected_ids = ["tt0111161", "tt0068646"]
        selected_folders = ["Movies", "TV Shows"]

        with patch(
            "modules.external_services.MediaDiscoveryService"
        ) as mock_discovery_class:
            mock_discovery_class.return_value = mock_discovery_service
            mock_discovery_service.get_media_ids_from_folder.return_value = expected_ids

            result = get_media_ids(
                root_folder="/path/to/media", selected_folders=selected_folders
            )

            assert result == expected_ids
            mock_discovery_service.get_media_ids_from_folder.assert_called_once_with(
                "/path/to/media", selected_folders
            )

    def test_get_media_ids_no_plex_no_folder_exits(self, caplog):
        """Test that function exits when neither Plex nor folder is available."""
        with pytest.raises(SystemExit) as exc_info:
            get_media_ids()

        assert exc_info.value.code == 1
        assert "No Plex config or root_folder provided" in caplog.text

    def test_get_media_ids_empty_plex_libraries_no_root_folder_exits(self, caplog):
        """Test that function exits when empty libraries and no root folder."""
        with pytest.raises(SystemExit) as exc_info:
            get_media_ids(plex_libraries=[])

        assert exc_info.value.code == 1

    def test_get_media_ids_partial_plex_no_root_folder_exits(
        self, mock_plex_client, caplog
    ):
        """Test that function exits when partial Plex config and no root folder."""
        with patch("modules.external_services.PlexClient") as mock_plex_class:
            mock_plex_class.return_value = mock_plex_client

            with pytest.raises(SystemExit) as exc_info:
                get_media_ids(
                    plex_url="http://plex.example.com", plex_token="test_token"
                )

            assert exc_info.value.code == 1

    def test_get_media_ids_plex_success_empty_libraries_no_root_folder(
        self, mock_plex_client
    ):
        """Test that function exits when Plex succeeds but empty libraries and no root folder."""
        with patch("modules.external_services.PlexClient") as mock_plex_class:
            mock_plex_class.return_value = mock_plex_client

            with pytest.raises(SystemExit) as exc_info:
                get_media_ids(
                    plex_url="http://plex.example.com",
                    plex_token="test_token",
                    plex_libraries=[],
                )

            assert exc_info.value.code == 1

    def test_get_media_ids_plex_exception_no_fallback_folder_exits(self, caplog):
        """Test that function exits when Plex fails and no root folder provided."""
        with patch("modules.external_services.PlexClient") as mock_plex_class:
            mock_plex_class.side_effect = Exception("Plex connection failed")

            with pytest.raises(SystemExit) as exc_info:
                get_media_ids(
                    plex_url="http://plex.example.com",
                    plex_token="test_token",
                    plex_libraries=["Movies"],
                )

            assert exc_info.value.code == 1
            assert "Plex connection failed" in caplog.text

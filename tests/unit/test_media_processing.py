"""
Unit tests for media_processing.py module.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from collections import defaultdict
from modules.media_processing import should_skip_scraping, process_single_media_item


class TestShouldSkipScraping:
    """Test cases for should_skip_scraping function."""

    def test_should_skip_scraping_ended_tv_show_already_in_yaml_no_process_all(
        self, caplog
    ):
        """Test skipping ended TV show that's already in YAML when process_all is False."""
        # Set logging level to capture INFO messages
        import logging

        logger = logging.getLogger("modules.media_processing")
        logger.setLevel(logging.INFO)

        result = should_skip_scraping(
            media_name="Breaking Bad",
            media_type="tv",
            tmdb_id="1396",
            key_for_log="81189",
            ended_status=True,
            is_in_yaml=True,
            process_all_flag=False,
        )

        assert result is True
        assert "SKIPPING: Breaking Bad" in caplog.text
        assert "ENDED series already in YAML" in caplog.text

    def test_should_skip_scraping_ongoing_tv_show_in_yaml_no_process_all(self, caplog):
        """Test not skipping ongoing TV show that's in YAML when process_all is False."""
        # Set logging level to capture INFO messages
        import logging

        logger = logging.getLogger("modules.media_processing")
        logger.setLevel(logging.INFO)

        result = should_skip_scraping(
            media_name="The Mandalorian",
            media_type="tv",
            tmdb_id="82856",
            key_for_log="82856",
            ended_status=False,
            is_in_yaml=True,
            process_all_flag=False,
        )

        assert result is False
        assert "ONGOING TV SHOW: The Mandalorian" in caplog.text
        assert "Will re-scrape for comparison" in caplog.text

    def test_should_skip_scraping_movie_already_in_yaml_no_process_all(self, caplog):
        """Test skipping movie that's already in YAML when process_all is False."""
        # Set logging level to capture INFO messages
        import logging

        logger = logging.getLogger("modules.media_processing")
        logger.setLevel(logging.INFO)

        result = should_skip_scraping(
            media_name="Inception",
            media_type="movie",
            tmdb_id="27205",
            key_for_log="27205",
            ended_status=None,
            is_in_yaml=True,
            process_all_flag=False,
        )

        assert result is True
        assert "SKIPPING: Inception" in caplog.text
        assert "Movie already in YAML" in caplog.text

    def test_should_skip_scraping_not_in_yaml(self, caplog):
        """Test not skipping when media is not in YAML."""
        result = should_skip_scraping(
            media_name="Unknown Movie",
            media_type="movie",
            tmdb_id="12345",
            key_for_log="12345",
            ended_status=None,
            is_in_yaml=False,
            process_all_flag=False,
        )

        assert result is False
        # Should not log skipping messages
        assert "SKIPPING:" not in caplog.text

    def test_should_skip_scraping_process_all_flag_true(self, caplog):
        """Test not skipping when process_all flag is True, regardless of YAML status."""
        result = should_skip_scraping(
            media_name="Breaking Bad",
            media_type="tv",
            tmdb_id="1396",
            key_for_log="81189",
            ended_status=True,
            is_in_yaml=True,
            process_all_flag=True,
        )

        assert result is False
        # Should not log skipping messages when process_all is True
        assert "SKIPPING:" not in caplog.text

    def test_should_skip_scraping_tv_show_not_in_yaml(self, caplog):
        """Test not skipping TV show that's not in YAML."""
        result = should_skip_scraping(
            media_name="New Series",
            media_type="tv",
            tmdb_id="99999",
            key_for_log="99999",
            ended_status=False,
            is_in_yaml=False,
            process_all_flag=False,
        )

        assert result is False
        assert "SKIPPING:" not in caplog.text

    def test_should_skip_scraping_movie_not_in_yaml(self, caplog):
        """Test not skipping movie that's not in YAML."""
        result = should_skip_scraping(
            media_name="New Movie",
            media_type="movie",
            tmdb_id="88888",
            key_for_log="88888",
            ended_status=None,
            is_in_yaml=False,
            process_all_flag=False,
        )

        assert result is False
        assert "SKIPPING:" not in caplog.text


class TestProcessSingleMediaItem:
    """Test cases for process_single_media_item function."""

    def setup_method(self):
        """Set up test fixtures."""
        # Reset global variables
        import modules.media_processing as mp

        mp.cache = {}
        mp.new_data = defaultdict(dict)
        mp.folder_bulk_data = {}

    def test_process_single_media_item_tmdb_id_resolution(self):
        """Test TMDB ID resolution for direct TMDB ID input."""
        with patch("modules.tmdb_client.TMDBClient") as mock_tmdb_class, patch(
            "modules.data_processor.YAMLStructureProcessor"
        ) as mock_structure_class, patch(
            "modules.data_processor.DataComparisonEngine"
        ) as mock_comparison_class, patch(
            "modules.scraper.MediuxScraper"
        ) as mock_scraper_class:

            # Setup mocks
            mock_tmdb_client = Mock()
            mock_tmdb_class.return_value = mock_tmdb_client
            mock_tmdb_client.fetch_tmdb_id.return_value = ("12345", "movie")

            mock_structure_client = Mock()
            mock_structure_class.return_value = mock_structure_client

            mock_comparison_client = Mock()
            mock_comparison_class.return_value = mock_comparison_client

            mock_scraper = Mock()
            mock_scraper_class.return_value = mock_scraper
            mock_scraper.scrape_mediux.return_value = "test_yaml_data"

            # Test data
            folder_map = {"tt0111161": ["folder1"]}
            updated_titles = []
            fixed_titles = []

            # Execute function without providing media_type_from_plex to force TMDB lookup
            process_single_media_item(
                media_id_from_folder="12345",
                media_name="Test Movie",
                external_source_type="tmdb_id",
                driver=Mock(),
                api_key="test_key",
                sonarr_api_key=None,
                sonarr_endpoint=None,
                process_all=True,
                retry_on_yaml_failure=False,
                preferred_users=[],
                excluded_users=[],
                folder_map_for_media=folder_map,
                updated_titles_list=updated_titles,
                fixed_titles_list=fixed_titles,
                # media_type_from_plex=None,  # Force TMDB lookup
            )

            # Verify TMDB client was called to get media type
            mock_tmdb_class.assert_called_once_with("test_key")
            mock_tmdb_client.fetch_tmdb_id.assert_called_once_with(
                media_id="12345",
                external_source="tmdb_id",
                cache={},
                media_name="Test Movie",
            )

    def test_process_single_media_item_external_id_resolution(self):
        """Test external ID resolution (non-TMDB direct input)."""
        with patch("modules.tmdb_client.TMDBClient") as mock_tmdb_class, patch(
            "modules.data_processor.YAMLStructureProcessor"
        ) as mock_structure_class, patch(
            "modules.data_processor.DataComparisonEngine"
        ) as mock_comparison_class, patch(
            "modules.scraper.MediuxScraper"
        ) as mock_scraper_class:

            # Setup mocks
            mock_tmdb_client = Mock()
            mock_tmdb_class.return_value = mock_tmdb_client
            mock_tmdb_client.fetch_tmdb_id.return_value = ("12345", "movie")

            mock_structure_client = Mock()
            mock_structure_class.return_value = mock_structure_client

            mock_comparison_client = Mock()
            mock_comparison_class.return_value = mock_comparison_client

            mock_scraper = Mock()
            mock_scraper_class.return_value = mock_scraper
            mock_scraper.scrape_mediux.return_value = "test_yaml_data"

            # Test data
            folder_map = {"tt0111161": ["folder1"]}
            updated_titles = []
            fixed_titles = []

            # Execute function
            process_single_media_item(
                media_id_from_folder="tt0111161",
                media_name="Test Movie",
                external_source_type="imdb_id",
                driver=Mock(),
                api_key="test_key",
                sonarr_api_key=None,
                sonarr_endpoint=None,
                process_all=True,
                retry_on_yaml_failure=False,
                preferred_users=[],
                excluded_users=[],
                folder_map_for_media=folder_map,
                updated_titles_list=updated_titles,
                fixed_titles_list=fixed_titles,
            )

            # Verify TMDB client was called correctly
            mock_tmdb_client.fetch_tmdb_id.assert_called_once_with(
                media_id="tt0111161",
                external_source="imdb_id",
                cache={},
                media_name="Test Movie",
            )

    def test_process_single_media_item_tmdb_resolution_failure(self, caplog):
        """Test handling of TMDB ID resolution failure."""
        with patch("modules.tmdb_client.TMDBClient") as mock_tmdb_class:
            # Setup mock to raise exception
            mock_tmdb_client = Mock()
            mock_tmdb_class.return_value = mock_tmdb_client
            mock_tmdb_client.fetch_tmdb_id.side_effect = Exception("TMDB API error")

            # Test data
            folder_map = {"tt0111161": ["folder1"]}
            updated_titles = []
            fixed_titles = []

            # Execute function
            process_single_media_item(
                media_id_from_folder="tt0111161",
                media_name="Test Movie",
                external_source_type="imdb_id",
                driver=Mock(),
                api_key="test_key",
                sonarr_api_key=None,
                sonarr_endpoint=None,
                process_all=True,
                retry_on_yaml_failure=False,
                preferred_users=[],
                excluded_users=[],
                folder_map_for_media=folder_map,
                updated_titles_list=updated_titles,
                fixed_titles_list=fixed_titles,
            )

            # Verify error was logged
            assert "Error fetching TMDB ID" in caplog.text
            assert "TMDB API error" in caplog.text

    def test_process_single_media_item_sonarr_check_for_tv(self):
        """Test Sonarr integration for TV shows."""
        with patch("modules.tmdb_client.TMDBClient") as mock_tmdb_class, patch(
            "modules.external_services.SonarrClient"
        ) as mock_sonarr_class, patch(
            "modules.data_processor.YAMLStructureProcessor"
        ) as mock_structure_class, patch(
            "modules.data_processor.DataComparisonEngine"
        ) as mock_comparison_class, patch(
            "modules.scraper.MediuxScraper"
        ) as mock_scraper_class:

            # Setup mocks
            mock_tmdb_client = Mock()
            mock_tmdb_class.return_value = mock_tmdb_client
            mock_tmdb_client.fetch_tmdb_id.return_value = ("12345", "tv")

            mock_sonarr_client = Mock()
            mock_sonarr_class.return_value = mock_sonarr_client
            mock_sonarr_client.check_series_status.return_value = ("tvdb_123", False)

            mock_structure_client = Mock()
            mock_structure_class.return_value = mock_structure_client

            mock_comparison_client = Mock()
            mock_comparison_class.return_value = mock_comparison_client

            mock_scraper = Mock()
            mock_scraper_class.return_value = mock_scraper
            mock_scraper.scrape_mediux.return_value = "test_yaml_data"

            # Test data
            folder_map = {"tt0111161": ["folder1"]}
            updated_titles = []
            fixed_titles = []

            # Execute function
            process_single_media_item(
                media_id_from_folder="tt0111161",
                media_name="Test TV Show",
                external_source_type="imdb_id",
                driver=Mock(),
                api_key="test_key",
                sonarr_api_key="sonarr_key",
                sonarr_endpoint="http://sonarr:8989",
                process_all=True,
                retry_on_yaml_failure=False,
                preferred_users=[],
                excluded_users=[],
                folder_map_for_media=folder_map,
                updated_titles_list=updated_titles,
                fixed_titles_list=fixed_titles,
                media_type_from_plex="tv",
            )

            # Verify Sonarr client was called
            mock_sonarr_class.assert_called_once_with(
                "sonarr_key", "http://sonarr:8989"
            )
            mock_sonarr_client.check_series_status.assert_called_once_with(
                media_name="Test TV Show",
                tmdb_id="12345",
            )

    def test_process_single_media_item_scraping_failure(self, caplog):
        """Test handling of scraping failure (no YAML returned)."""
        with patch("modules.tmdb_client.TMDBClient") as mock_tmdb_class, patch(
            "modules.data_processor.YAMLStructureProcessor"
        ) as mock_structure_class, patch(
            "modules.data_processor.DataComparisonEngine"
        ) as mock_comparison_class, patch(
            "modules.scraper.MediuxScraper"
        ) as mock_scraper_class:

            # Setup mocks
            mock_tmdb_client = Mock()
            mock_tmdb_class.return_value = mock_tmdb_client
            mock_tmdb_client.fetch_tmdb_id.return_value = ("12345", "movie")

            mock_structure_client = Mock()
            mock_structure_class.return_value = mock_structure_client

            mock_comparison_client = Mock()
            mock_comparison_class.return_value = mock_comparison_client

            mock_scraper = Mock()
            mock_scraper_class.return_value = mock_scraper
            mock_scraper.scrape_mediux.return_value = None  # No YAML data

            # Test data
            folder_map = {"tt0111161": ["folder1"]}
            updated_titles = []
            fixed_titles = []

            # Execute function
            process_single_media_item(
                media_id_from_folder="tt0111161",
                media_name="Test Movie",
                external_source_type="imdb_id",
                driver=Mock(),
                api_key="test_key",
                sonarr_api_key=None,
                sonarr_endpoint=None,
                process_all=True,
                retry_on_yaml_failure=False,
                preferred_users=[],
                excluded_users=[],
                folder_map_for_media=folder_map,
                updated_titles_list=updated_titles,
                fixed_titles_list=fixed_titles,
            )

            # Verify warning was logged
            assert "No YAML data found from Mediux" in caplog.text

    def test_process_single_media_item_yaml_filtering(self):
        """Test YAML filtering functionality."""
        with patch("modules.tmdb_client.TMDBClient") as mock_tmdb_class, patch(
            "modules.data_processor.YAMLStructureProcessor"
        ) as mock_structure_class, patch(
            "modules.data_processor.DataComparisonEngine"
        ) as mock_comparison_class, patch(
            "modules.data_processor.YAMLDataFilter"
        ) as mock_filter_class, patch(
            "modules.scraper.MediuxScraper"
        ) as mock_scraper_class, patch(
            "modules.media_processing.yaml_parser"
        ) as mock_parser:

            # Setup mocks
            mock_tmdb_client = Mock()
            mock_tmdb_class.return_value = mock_tmdb_client
            mock_tmdb_client.fetch_tmdb_id.return_value = ("12345", "movie")

            mock_structure_client = Mock()
            mock_structure_class.return_value = mock_structure_client

            mock_comparison_client = Mock()
            mock_comparison_class.return_value = mock_comparison_client

            mock_scraper = Mock()
            mock_scraper_class.return_value = mock_scraper
            mock_scraper.scrape_mediux.return_value = "original_yaml"

            mock_filter = Mock()
            mock_filter_class.return_value = mock_filter
            mock_filter.filter_yaml_data_by_paths.return_value = {"filtered": "data"}

            mock_parser.load.return_value = {"tt0111161": {"title": "Test"}}
            mock_parser.dump.return_value = None

            # Test data
            folder_map = {"tt0111161": ["folder1"]}
            updated_titles = []
            fixed_titles = []
            remove_paths = ["*.url_background"]

            # Execute function
            process_single_media_item(
                media_id_from_folder="tt0111161",
                media_name="Test Movie",
                external_source_type="imdb_id",
                driver=Mock(),
                api_key="test_key",
                sonarr_api_key=None,
                sonarr_endpoint=None,
                process_all=True,
                retry_on_yaml_failure=False,
                preferred_users=[],
                excluded_users=[],
                folder_map_for_media=folder_map,
                updated_titles_list=updated_titles,
                fixed_titles_list=fixed_titles,
                remove_paths=remove_paths,
            )

            # Verify filtering was attempted
            mock_filter_class.assert_called_once()
            mock_filter.filter_yaml_data_by_paths.assert_called_once_with(
                yaml_data={"tt0111161": {"title": "Test"}},
                remove_paths=remove_paths,
            )

    def test_process_single_media_item_shared_resources(self):
        """Test using shared resources instead of globals."""
        with patch("modules.tmdb_client.TMDBClient") as mock_tmdb_class, patch(
            "modules.data_processor.YAMLStructureProcessor"
        ) as mock_structure_class, patch(
            "modules.data_processor.DataComparisonEngine"
        ) as mock_comparison_class, patch(
            "modules.scraper.MediuxScraper"
        ) as mock_scraper_class:

            # Setup mocks
            mock_tmdb_client = Mock()
            mock_tmdb_class.return_value = mock_tmdb_client
            mock_tmdb_client.fetch_tmdb_id.return_value = ("12345", "movie")

            mock_structure_client = Mock()
            mock_structure_class.return_value = mock_structure_client

            mock_comparison_client = Mock()
            mock_comparison_class.return_value = mock_comparison_client

            mock_scraper = Mock()
            mock_scraper_class.return_value = mock_scraper
            mock_scraper.scrape_mediux.return_value = "test_yaml_data"

            # Test data with shared resources
            shared_cache = {"test": "cache"}
            shared_new_data = defaultdict(dict)
            shared_folder_bulk_data = {"test": "bulk_data"}
            folder_map = {"tt0111161": ["folder1"]}
            updated_titles = []
            fixed_titles = []

            # Execute function with shared resources
            process_single_media_item(
                media_id_from_folder="tt0111161",
                media_name="Test Movie",
                external_source_type="imdb_id",
                driver=Mock(),
                api_key="test_key",
                sonarr_api_key=None,
                sonarr_endpoint=None,
                process_all=True,
                retry_on_yaml_failure=False,
                preferred_users=[],
                excluded_users=[],
                folder_map_for_media=folder_map,
                updated_titles_list=updated_titles,
                fixed_titles_list=fixed_titles,
                shared_cache=shared_cache,
                shared_new_data=shared_new_data,
                shared_folder_bulk_data=shared_folder_bulk_data,
            )

            # Verify TMDB client was called with shared cache
            mock_tmdb_client.fetch_tmdb_id.assert_called_once_with(
                media_id="tt0111161",
                external_source="imdb_id",
                cache=shared_cache,  # Should use shared cache
                media_name="Test Movie",
            )

    def test_process_single_media_item_missing_tmdb_id_or_type(self, caplog):
        """Test handling when TMDB ID or media type cannot be resolved."""
        with patch("modules.tmdb_client.TMDBClient") as mock_tmdb_class:
            # Setup mock to return None values
            mock_tmdb_client = Mock()
            mock_tmdb_class.return_value = mock_tmdb_client
            mock_tmdb_client.fetch_tmdb_id.return_value = (None, None)

            # Test data
            folder_map = {"tt0111161": ["folder1"]}
            updated_titles = []
            fixed_titles = []

            # Execute function
            process_single_media_item(
                media_id_from_folder="tt0111161",
                media_name="Test Movie",
                external_source_type="imdb_id",
                driver=Mock(),
                api_key="test_key",
                sonarr_api_key=None,
                sonarr_endpoint=None,
                process_all=True,
                retry_on_yaml_failure=False,
                preferred_users=[],
                excluded_users=[],
                folder_map_for_media=folder_map,
                updated_titles_list=updated_titles,
                fixed_titles_list=fixed_titles,
            )

            # Function should return early without error
            assert len(updated_titles) == 0
            assert len(fixed_titles) == 0

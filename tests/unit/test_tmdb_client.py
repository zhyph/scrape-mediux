"""
Tests for tmdb_client.py module.
"""

from unittest.mock import Mock, patch

import pytest
from requests.exceptions import RequestException

from modules.tmdb_client import TitleSimilarityCalculator, TMDBClient, to_standard_dict


class TestTitleSimilarityCalculator:
    """Test cases for TitleSimilarityCalculator class."""

    def test_init(self):
        """Test TitleSimilarityCalculator initialization."""
        calculator = TitleSimilarityCalculator()
        assert calculator is not None

    def test_calculate_similarity_identical_titles(self):
        """Test similarity calculation with identical titles."""
        calculator = TitleSimilarityCalculator()

        similarity = calculator.calculate_similarity("The Matrix", "The Matrix")
        assert similarity == 1.0

    def test_calculate_similarity_different_titles(self):
        """Test similarity calculation with different titles."""
        calculator = TitleSimilarityCalculator()

        similarity = calculator.calculate_similarity("The Matrix", "Inception")
        assert similarity < 1.0
        assert similarity >= 0.0

    def test_calculate_similarity_partial_overlap(self):
        """Test similarity calculation with partial word overlap."""
        calculator = TitleSimilarityCalculator()

        similarity = calculator.calculate_similarity("The Matrix", "Matrix Reloaded")
        # Should have some similarity due to "Matrix"
        assert similarity > 0.0
        assert similarity < 1.0

    def test_calculate_similarity_case_insensitive(self):
        """Test similarity calculation is case insensitive."""
        calculator = TitleSimilarityCalculator()

        similarity1 = calculator.calculate_similarity("The Matrix", "the matrix")
        similarity2 = calculator.calculate_similarity("The Matrix", "THE MATRIX")

        assert similarity1 == 1.0
        assert similarity2 == 1.0

    def test_calculate_similarity_punctuation_ignored(self):
        """Test similarity calculation ignores punctuation."""
        calculator = TitleSimilarityCalculator()

        similarity = calculator.calculate_similarity("The Matrix!", "The Matrix?")
        assert similarity == 1.0

    def test_calculate_similarity_empty_titles(self):
        """Test similarity calculation with empty titles."""
        calculator = TitleSimilarityCalculator()

        similarity = calculator.calculate_similarity("", "")
        assert similarity == 0.0

    def test_calculate_similarity_one_empty_title(self):
        """Test similarity calculation with one empty title."""
        calculator = TitleSimilarityCalculator()

        similarity = calculator.calculate_similarity("The Matrix", "")
        assert similarity == 0.0

    def test_calculate_similarity_none_titles(self):
        """Test similarity calculation with None titles."""
        calculator = TitleSimilarityCalculator()

        # The function handles None by checking 'if not title1 or not title2'
        similarity = calculator.calculate_similarity(None, None)  # type: ignore
        assert similarity == 0.0


class TestTMDBClient:
    """Test cases for TMDBClient class."""

    def test_init(self):
        """Test TMDBClient initialization."""
        client = TMDBClient("test_api_key")
        assert client.api_key == "test_api_key"
        assert client.BASE_URL == "https://api.themoviedb.org/3"
        assert isinstance(client.similarity_calculator, TitleSimilarityCalculator)
        assert hasattr(client, "logger")

    def test_check_direct_tmdb_api_both_exist(self):
        """Test checking TMDB ID that exists as both movie and TV."""
        client = TMDBClient("test_api_key")

        # Mock responses
        mock_tv_response = Mock()
        mock_tv_response.status_code = 200
        mock_tv_response.json.return_value = {"name": "Test Show"}

        mock_movie_response = Mock()
        mock_movie_response.status_code = 200
        mock_movie_response.json.return_value = {"title": "Test Movie"}

        with patch("requests.get") as mock_get:
            mock_get.side_effect = [mock_tv_response, mock_movie_response]

            tv_exists, movie_exists, tv_resp, movie_resp = (
                client._check_direct_tmdb_api("123")
            )

            assert tv_exists is True
            assert movie_exists is True
            assert tv_resp == mock_tv_response
            assert movie_resp == mock_movie_response

    def test_check_direct_tmdb_api_tv_only(self):
        """Test checking TMDB ID that exists as TV show only."""
        client = TMDBClient("test_api_key")

        mock_tv_response = Mock()
        mock_tv_response.status_code = 200
        mock_tv_response.json.return_value = {"name": "Test Show"}

        mock_movie_response = Mock()
        mock_movie_response.status_code = 404

        with patch("requests.get") as mock_get:
            mock_get.side_effect = [mock_tv_response, mock_movie_response]

            tv_exists, movie_exists, tv_resp, movie_resp = (
                client._check_direct_tmdb_api("123")
            )

            assert tv_exists is True
            assert movie_exists is False

    def test_check_direct_tmdb_api_error_handling(self):
        """Test error handling in direct TMDB API check."""
        client = TMDBClient("test_api_key")

        with patch("requests.get") as mock_get:
            mock_get.side_effect = RequestException("Connection error")

            tv_exists, movie_exists, tv_resp, movie_resp = (
                client._check_direct_tmdb_api("123")
            )

            assert tv_exists is False
            assert movie_exists is False
            assert tv_resp is None
            assert movie_resp is None

    def test_resolve_direct_tmdb_conflict_with_media_name(self):
        """Test resolving conflict when media name is provided."""
        client = TMDBClient("test_api_key")

        mock_tv_response = Mock()
        mock_tv_response.json.return_value = {"name": "The Matrix TV Show"}

        mock_movie_response = Mock()
        mock_movie_response.json.return_value = {"title": "The Matrix"}

        media_name = "The Matrix"

        tmdb_id, media_type = client._resolve_direct_tmdb_conflict(
            "123", media_name, mock_tv_response, mock_movie_response
        )

        # Should select movie due to exact title match
        assert tmdb_id == "123"
        assert media_type == "movie"

    def test_resolve_direct_tmdb_conflict_without_media_name(self):
        """Test resolving conflict when no media name is provided."""
        client = TMDBClient("test_api_key")

        mock_tv_response = Mock()
        mock_tv_response.json.return_value = {"name": "Test Show"}

        mock_movie_response = Mock()
        mock_movie_response.json.return_value = {"title": "Test Movie"}

        tmdb_id, media_type = client._resolve_direct_tmdb_conflict(
            "123", None, mock_tv_response, mock_movie_response
        )

        # Should default to TV show
        assert tmdb_id == "123"
        assert media_type == "tv"

    def test_query_external_id_success(self):
        """Test successful external ID query."""
        client = TMDBClient("test_api_key")

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "movie_results": [{"id": "123", "title": "Test Movie"}],
            "tv_results": [{"id": "456", "name": "Test Show"}],
        }

        with patch("requests.get", return_value=mock_response):
            movie_results, tv_results = client._query_external_id(
                "tt0111161", "imdb_id"
            )

            assert len(movie_results) == 1
            assert len(tv_results) == 1
            assert movie_results[0]["id"] == "123"
            assert tv_results[0]["id"] == "456"

    def test_query_external_id_request_exception(self):
        """Test external ID query with request exception."""
        client = TMDBClient("test_api_key")

        with patch("requests.get", side_effect=RequestException("Connection error")):
            with pytest.raises(RequestException):
                client._query_external_id("tt0111161", "imdb_id")

    def test_resolve_external_id_conflict_with_similarity(self):
        """Test resolving external ID conflict using title similarity."""
        client = TMDBClient("test_api_key")

        media_name = "The Matrix"
        movie_result = {"id": "123", "title": "The Matrix"}
        tv_result = {"id": "456", "name": "Matrix TV Show"}

        tmdb_id, media_type = client._resolve_external_id_conflict(
            "tt0111161", "imdb_id", media_name, movie_result, tv_result
        )

        # Should select movie due to exact title match
        assert tmdb_id == "123"
        assert media_type == "movie"

    def test_resolve_external_id_conflict_with_confidence(self):
        """Test resolving external ID conflict using confidence scoring."""
        client = TMDBClient("test_api_key")

        # No media name provided, should use confidence scoring
        movie_result = {
            "id": "123",
            "title": "Test Movie",
            "vote_count": 100,
            "popularity": 10,
        }
        tv_result = {
            "id": "456",
            "name": "Test Show",
            "vote_count": 50,
            "popularity": 5,
        }

        tmdb_id, media_type = client._resolve_external_id_conflict(
            "tt0111161", "imdb_id", None, movie_result, tv_result
        )

        # Should select movie due to higher confidence score
        assert tmdb_id == "123"
        assert media_type == "movie"

    @patch("modules.tmdb_client.get_cache_manager")
    def test_fetch_tmdb_id_direct_tmdb_success(self, mock_get_cache_manager):
        """Test successful fetch of direct TMDB ID."""
        mock_cache_manager = Mock()
        mock_cache_manager.get_tmdb_id.return_value = None
        mock_get_cache_manager.return_value = mock_cache_manager

        client = TMDBClient("test_api_key")

        # Mock successful direct TMDB lookup
        with patch.object(client, "_check_direct_tmdb_api") as mock_check:
            mock_check.return_value = (False, True, None, Mock())  # Movie exists

            result = client.fetch_tmdb_id("123", "tmdb_id", cache={})

            assert result == ("123", "movie")
            mock_cache_manager.set_tmdb_id.assert_called_once()

    @patch("modules.tmdb_client.get_cache_manager")
    def test_fetch_tmdb_id_external_id_success(self, mock_get_cache_manager):
        """Test successful fetch using external ID."""
        mock_cache_manager = Mock()
        mock_cache_manager.get_tmdb_id.return_value = None
        mock_get_cache_manager.return_value = mock_cache_manager

        client = TMDBClient("test_api_key")

        with patch.object(client, "_query_external_id") as mock_query:
            mock_query.return_value = ([{"id": "123", "title": "Test Movie"}], [])

            result = client.fetch_tmdb_id("tt0111161", "imdb_id", cache={})

            assert result == ("123", "movie")
            mock_cache_manager.set_tmdb_id.assert_called_once()

    @patch("modules.tmdb_client.get_cache_manager")
    def test_fetch_tmdb_id_cache_hit(self, mock_get_cache_manager):
        """Test fetch with cache hit."""
        mock_cache_manager = Mock()
        mock_cache_manager.get_tmdb_id.return_value = ("123", "movie")
        mock_get_cache_manager.return_value = mock_cache_manager

        client = TMDBClient("test_api_key")

        result = client.fetch_tmdb_id("tt0111161", "imdb_id", cache={})

        assert result == ("123", "movie")
        # Should not call external APIs when cache hit

    @patch("modules.tmdb_client.get_cache_manager")
    def test_fetch_tmdb_id_no_results(self, mock_get_cache_manager):
        """Test fetch when no results found."""
        mock_cache_manager = Mock()
        mock_cache_manager.get_tmdb_id.return_value = None
        mock_get_cache_manager.return_value = mock_cache_manager

        client = TMDBClient("test_api_key")

        with patch.object(client, "_query_external_id") as mock_query:
            mock_query.return_value = ([], [])  # No results

            result = client.fetch_tmdb_id("tt0111161", "imdb_id", cache={})

            assert result == (None, None)

    @patch("modules.tmdb_client.get_cache_manager")
    def test_fetch_tmdb_id_conflict_resolution(self, mock_get_cache_manager):
        """Test fetch with conflict resolution."""
        mock_cache_manager = Mock()
        mock_cache_manager.get_tmdb_id.return_value = None
        mock_get_cache_manager.return_value = mock_cache_manager

        client = TMDBClient("test_api_key")

        # Mock conflict scenario
        with patch.object(client, "_check_direct_tmdb_api") as mock_check:
            mock_tv_response = Mock()
            mock_tv_response.json.return_value = {"name": "Test TV"}
            mock_movie_response = Mock()
            mock_movie_response.json.return_value = {"title": "Test Movie"}

            mock_check.return_value = (
                True,
                True,
                mock_tv_response,
                mock_movie_response,
            )

            with patch.object(client, "_resolve_direct_tmdb_conflict") as mock_resolve:
                mock_resolve.return_value = ("123", "movie")

                result = client.fetch_tmdb_id(
                    "123", "tmdb_id", cache={}, media_name="Test Movie"
                )

                assert result == ("123", "movie")
                mock_resolve.assert_called_once()


class TestToStandardDict:
    """Test cases for to_standard_dict function."""

    def test_to_standard_dict_simple_dict(self):
        """Test converting simple dictionary."""
        from collections import OrderedDict

        input_dict = OrderedDict([("key1", "value1"), ("key2", "value2")])
        result = to_standard_dict(input_dict)

        assert isinstance(result, dict)
        assert result == {"key1": "value1", "key2": "value2"}

    def test_to_standard_dict_nested_dict(self):
        """Test converting nested dictionary."""
        from collections import OrderedDict

        input_dict = OrderedDict(
            [
                ("key1", "value1"),
                ("nested", OrderedDict([("inner_key", "inner_value")])),
            ]
        )
        result = to_standard_dict(input_dict)

        assert isinstance(result, dict)
        assert isinstance(result["nested"], dict)
        assert result["nested"]["inner_key"] == "inner_value"

    def test_to_standard_dict_with_list(self):
        """Test converting dictionary with list values."""
        from collections import OrderedDict

        input_dict = OrderedDict([("key1", "value1"), ("list_key", ["item1", "item2"])])
        result = to_standard_dict(input_dict)

        assert isinstance(result, dict)
        assert isinstance(result["list_key"], list)
        assert result["list_key"] == ["item1", "item2"]

    def test_to_standard_dict_with_nested_list(self):
        """Test converting dictionary with nested list."""
        from collections import OrderedDict

        input_dict = OrderedDict(
            [("list_key", [OrderedDict([("nested_key", "nested_value")])])]
        )
        result = to_standard_dict(input_dict)

        assert isinstance(result["list_key"][0], dict)
        assert result["list_key"][0]["nested_key"] == "nested_value"

    def test_to_standard_dict_primitive_values(self):
        """Test converting dictionary with primitive values."""
        input_dict = {
            "string": "value",
            "number": 42,
            "boolean": True,
            "none_value": None,
        }
        result = to_standard_dict(input_dict)

        assert result == input_dict

    def test_to_standard_dict_empty_dict(self):
        """Test converting empty dictionary."""
        result = to_standard_dict({})
        assert result == {}

    def test_to_standard_dict_none(self):
        """Test converting None."""
        result = to_standard_dict(None)
        assert result is None

    def test_to_standard_dict_string(self):
        """Test converting string."""
        result = to_standard_dict("test_string")
        assert result == "test_string"

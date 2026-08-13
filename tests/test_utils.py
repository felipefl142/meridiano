"""
Tests for utility functions.
"""

import os
import sys
from datetime import datetime
from unittest.mock import MagicMock, patch

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from meridiano.utils import (
    fetch_article_content_and_og_image,
    format_datetime,
    html_fragment_to_text,
    looks_like_bot_challenge,
)


class TestFormatDatetime:
    """Tests for datetime formatting."""

    def test_format_datetime_none(self):
        """Test formatting None value."""
        result = format_datetime(None)
        assert result == "N/A"

    def test_format_datetime_datetime_object(self):
        """Test formatting datetime object."""
        dt = datetime(2024, 1, 15, 14, 30, 45)
        result = format_datetime(dt)
        assert result == "2024-01-15 14:30"

    def test_format_datetime_datetime_custom_format(self):
        """Test formatting datetime with custom format."""
        dt = datetime(2024, 1, 15, 14, 30, 45)
        result = format_datetime(dt, "%Y-%m-%d")
        assert result == "2024-01-15"

    def test_format_datetime_string(self):
        """Test formatting ISO format string."""
        iso_string = "2024-01-15T14:30:45"
        result = format_datetime(iso_string)
        assert result == "2024-01-15 14:30"

    def test_format_datetime_invalid_string(self):
        """Test formatting invalid string (should return original)."""
        invalid_string = "not-a-date"
        result = format_datetime(invalid_string)
        assert result == invalid_string

    def test_format_datetime_empty_string(self):
        """Test formatting empty string."""
        result = format_datetime("")
        assert result == ""


class TestLooksLikeBotChallenge:
    """A bot wall's interstitial must never be stored as article content."""

    def test_detects_the_ars_technica_interstitial(self):
        """Test the exact page that was being saved as 273 Ars Technica articles."""
        page = (
            "JavaScript is disabled\nIn order to continue, we need to verify that "
            "you're not a robot. This requires JavaScript. Enable JavaScript and "
            "then reload the page."
        )
        assert looks_like_bot_challenge(page) is True

    def test_detects_cloudflare_style_interstitials(self):
        """Test that other common wall wordings are caught too."""
        assert looks_like_bot_challenge("Just a moment...") is True
        assert looks_like_bot_challenge("Checking your browser before accessing") is True

    def test_a_real_article_about_javascript_is_not_a_challenge(self):
        """Test that length guards the markers, so real coverage survives."""
        article = (
            "A new browser release changes what happens when JavaScript is disabled. "
            "The team argued that asking users to verify that you're not a robot has "
            "become routine. " + ("Further analysis of the rollout followed. " * 30)
        )
        assert len(article) > 600, "this test needs an article past the length guard"
        assert looks_like_bot_challenge(article) is False

    def test_empty_extraction(self):
        """Test that no content is not mistaken for a challenge."""
        assert looks_like_bot_challenge(None) is False
        assert looks_like_bot_challenge("") is False


class TestHtmlFragmentToText:
    """RSS bodies arrive as HTML fragments, not documents."""

    def test_flattens_a_fragment(self):
        """Test that tags are stripped and text is kept."""
        assert html_fragment_to_text("<p>First para.</p><p>Second para.</p>") == "First para.\nSecond para."

    def test_empty_input(self):
        """Test that nothing in means nothing out."""
        assert html_fragment_to_text(None) is None
        assert html_fragment_to_text("") is None

    def test_markup_without_text(self):
        """Test that a fragment of pure markup yields None, not an empty string."""
        assert html_fragment_to_text("<div><img src='x.png'></div>") is None


class TestFetchArticleContentAndOgImage:
    """The fetch must reject anything that is not the article itself."""

    def _response(self, status_code, text):
        response = MagicMock()
        response.status_code = status_code
        response.text = text
        response.raise_for_status = MagicMock()
        return response

    def test_rejects_a_202_challenge(self):
        """Test the Ars Technica case: HTTP 202 passes raise_for_status but is not content."""
        html = "<html><body><p>JavaScript is disabled</p></body></html>"

        with patch("meridiano.utils.requests.get", return_value=self._response(202, html)):
            result = fetch_article_content_and_og_image("https://arstechnica.com/some-article/")

        assert result == {"content": None, "og_image": None}

    def test_rejects_a_challenge_served_as_200(self):
        """Test that a wall which answers 200 is still caught by the wording."""
        html = (
            "<html><body><article><p>In order to continue, we need to verify that "
            "you're not a robot. This requires JavaScript.</p></article></body></html>"
        )

        with patch("meridiano.utils.requests.get", return_value=self._response(200, html)):
            result = fetch_article_content_and_og_image("https://example.com/walled/")

        assert result["content"] is None

    def test_accepts_a_normal_article(self):
        """Test that an ordinary page still yields its content and og:image."""
        body = "This is the first paragraph of a perfectly ordinary article. " * 8
        html = (
            "<html><head><meta property='og:image' content='/img/hero.png'></head>"
            f"<body><article><p>{body}</p></article></body></html>"
        )

        with patch("meridiano.utils.requests.get", return_value=self._response(200, html)):
            result = fetch_article_content_and_og_image("https://example.com/news/story/")

        assert result["content"] is not None
        assert "perfectly ordinary article" in result["content"]
        assert result["og_image"] == "https://example.com/img/hero.png"

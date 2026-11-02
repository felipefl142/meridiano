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
    decode_html_response,
    extract_full_article_html,
    fetch_article_content_and_og_image,
    format_datetime,
    html_fragment_to_text,
    looks_like_bot_challenge,
    repair_mojibake,
    sanitize_article_html,
    simplify_figures,
    word_vocabulary,
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
        response.content = text.encode()
        response.headers = {"Content-Type": "text/html; charset=utf-8"}
        response.raise_for_status = MagicMock()
        return response

    def test_rejects_a_202_challenge(self):
        """Test the Ars Technica case: HTTP 202 passes raise_for_status but is not content."""
        html = "<html><body><p>JavaScript is disabled</p></body></html>"

        with patch("meridiano.utils.requests.get", return_value=self._response(202, html)):
            result = fetch_article_content_and_og_image("https://arstechnica.com/some-article/")

        assert result == {"content": None, "og_image": None, "full_html": None}

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


class TestSanitizeArticleHtml:
    """Full-article HTML is rendered with |safe, so the sanitizer is the guard."""

    def test_strips_scripts_handlers_and_unsafe_urls(self):
        html = (
            '<p onclick="x()">Hi <a href="javascript:alert(1)">bad</a> <a href="/rel">ok</a></p>'
            '<script>alert(1)</script><iframe src="https://evil.example"></iframe>'
            '<img src="data:image/gif;base64,AAA"><img src="/pic.jpg" onerror="alert(1)" style="x">'
        )
        result = sanitize_article_html(html, "https://example.com/a/b")

        assert "script" not in result
        assert "iframe" not in result
        assert "onclick" not in result
        assert "onerror" not in result
        assert "style" not in result
        assert "javascript:" not in result
        assert "data:image" not in result
        assert 'href="https://example.com/rel"' in result
        assert 'src="https://example.com/pic.jpg"' in result
        assert 'rel="noopener noreferrer nofollow"' in result

    def test_converts_trafilatura_graphics_and_tables(self):
        html = '<graphic src="/a.jpg"/><table><row><cell role="head">H</cell></row><row><cell>v</cell></row></table>'
        result = sanitize_article_html(html, "https://example.com/")

        assert '<img src="https://example.com/a.jpg"' in result
        assert "<th>H</th>" in result
        assert "<td>v</td>" in result

    def test_dedupes_the_same_image_across_schemes(self):
        html = '<img src="https://cdn.example.com/a.jpg"><img src="http://cdn.example.com/a.jpg">'
        assert sanitize_article_html(html, "https://example.com/").count("<img") == 1

    def test_empty_results_are_none(self):
        assert sanitize_article_html(None, "https://example.com/") is None
        assert sanitize_article_html("<script>x</script>", "https://example.com/") is None


class TestExtractFullArticleHtml:
    def test_keeps_body_images_and_drops_page_chrome(self):
        body = "Sentence of a real article body. " * 30
        html = (
            "<html><body><nav>Site menu</nav><article><h1>Title</h1>"
            f'<p>{body}</p><figure><img src="/photo.jpg" alt="Photo"></figure><p>{body}</p>'
            "</article><footer>Footer links</footer></body></html>"
        )
        result = extract_full_article_html(html, "https://example.com/story")

        assert result is not None
        assert "<html" not in result
        assert "<body" not in result
        assert 'src="https://example.com/photo.jpg"' in result
        assert "Site menu" not in result


class TestDecodeHtmlResponse:
    def _response(self, body, content_type):
        response = MagicMock()
        response.headers = {"Content-Type": content_type}
        response.content = body
        response.text = body.decode("latin-1")  # what requests guesses without a charset
        response.apparent_encoding = "windows-1252"
        return response

    def test_utf8_page_without_charset_is_not_latin1(self):
        """Folha serves UTF-8 as plain 'text/html'; requests would yield 'vegetaÃ§Ã£o'."""
        response = self._response("vegetação".encode(), "text/html")
        assert decode_html_response(response) == "vegetação"

    def test_latin1_page_without_charset_falls_back_to_detection(self):
        response = self._response("vegetação".encode("latin-1"), "text/html")
        assert decode_html_response(response) == "vegetação"

    def test_declared_charset_is_trusted(self):
        response = self._response(b"x", "text/html; charset=ISO-8859-1")
        response.text = "declared"
        assert decode_html_response(response) == "declared"


class TestRepairMojibake:
    def test_reversible_sequences(self):
        assert repair_mojibake("vegetaÃ§Ã£o e coraÃ§Ã£o, Ã©") == "vegetação e coração, é"

    def test_lossy_leftovers(self):
        """Stripped soft hyphen (í) and NBSP (à) leave a lone 'Ã'."""
        assert repair_mojibake("PacÃfico, paraÃso, LÃbano e Ã BBC") == "Pacífico, paraíso, Líbano e à BBC"

    def test_lost_uppercase_resolved_by_vocabulary(self):
        vocabulary = word_vocabulary(["África também mês justiça são"])
        assert repair_mojibake("na Ãfrica, TAMBÃM no MÃS da JUSTIÃA", vocabulary) == (
            "na África, TAMBÉM no MÊS da JUSTIÇA"
        )

    def test_real_a_tilde_is_kept(self):
        vocabulary = word_vocabulary(["são não"])
        assert repair_mojibake("SÃO PAULO diz NÃO", vocabulary) == "SÃO PAULO diz NÃO"

    def test_clean_text_untouched(self):
        assert repair_mojibake("Coração “aspas” — ok") == "Coração “aspas” — ok"
        assert repair_mojibake(None) is None


class TestSimplifyFigures:
    def test_lazy_image_in_widget_wrapper_survives_extraction(self):
        """Folha wraps photos in div.widget-image, which trafilatura drops as boilerplate."""
        body = "Texto do corpo do artigo com bastante conteúdo. " * 25
        html = (
            f"<html><body><article><p>{body}</p>"
            '<div class="widget-image"><figure><div class="ratio">'
            '<img class="c-lazyload" data-src="https://cdn.example.com/foto_md.jpg" alt="Foto">'
            '<noscript><img src="https://cdn.example.com/foto_md.jpg"></noscript>'
            '</div><figcaption>Legenda <span>Crédito</span></figcaption></figure></div>'
            f"<p>{body}</p></article></body></html>"
        )
        assert 'class="widget-image"' not in simplify_figures(html)

        result = extract_full_article_html(html, "https://example.com/story")
        assert result.count("<img") == 1
        assert 'src="https://cdn.example.com/foto_md.jpg"' in result
        assert "Legenda Crédito" in result

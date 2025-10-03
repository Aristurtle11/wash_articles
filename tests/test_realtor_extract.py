from __future__ import annotations

from src.utils.realtor_extract import extract_feed_content


def test_extract_feed_content_parses_order_and_sequences():
    html = (
        "<p>First paragraph.</p>"
        "<figure><img src=\"/images/a.jpg\" alt=\"Alt\"/>"
        "<figcaption>Caption text</figcaption></figure>"
        "<p>Second paragraph.</p>"
    )

    content = extract_feed_content(
        html,
        "https://example.com/article",
        hero_url="https://cdn.example.com/cover.jpg",
    )

    assert content[0]["kind"] == "image"
    assert content[0]["sequence"] == 1
    assert content[0]["url"] == "https://cdn.example.com/cover.jpg"

    assert content[1]["kind"] == "paragraph"
    assert content[1]["index"] == 1
    assert content[1]["text"] == "First paragraph."

    assert content[2]["kind"] == "image"
    assert content[2]["sequence"] == 2
    assert content[2]["url"] == "https://example.com/images/a.jpg"
    assert content[2]["caption"] == "Caption text"
    assert content[2]["alt"] == "Alt"

    assert content[3]["kind"] == "paragraph"
    assert content[3]["index"] == 2
    assert content[3]["text"] == "Second paragraph."


def test_extract_feed_content_handles_missing_hero():
    html = "<img src=\"/img.jpg\" alt=\"Sample\"/>"

    content = extract_feed_content(html, "https://example.com/article")

    assert content[0]["kind"] == "image"
    assert content[0]["sequence"] == 1
    assert content[0]["url"] == "https://example.com/img.jpg"

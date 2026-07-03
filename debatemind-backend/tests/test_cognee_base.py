"""
Unit tests for debatemind.cognee._base.filter_out_patterns — the mastery
exclusion filter shared by recall.py and agents/opponent.py's cache re-filter.
"""

from debatemind.cognee._base import filter_out_patterns


def test_filter_out_patterns_drops_matching_pattern_type():
    items = [
        {"text": "a", "pattern_type": "StrawMan"},
        {"text": "b", "pattern_type": "AdHominem"},
    ]
    result = filter_out_patterns(items, {"StrawMan"})
    assert result == [{"text": "b", "pattern_type": "AdHominem"}]


def test_filter_out_patterns_returns_all_when_patterns_falsy():
    items = [{"text": "a", "pattern_type": "StrawMan"}]
    assert filter_out_patterns(items, None) == items
    assert filter_out_patterns(items, set()) == items


def test_filter_out_patterns_keeps_items_with_no_pattern_type():
    """Session-summary records carry no pattern_type — always kept."""
    items = [{"text": "session summary"}]
    assert filter_out_patterns(items, {"StrawMan"}) == items

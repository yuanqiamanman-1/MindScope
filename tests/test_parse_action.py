import pytest

from core.agent import parse_action, ParseError


def test_plain_json():
    o = parse_action('{"thought":"t","action":{"tool":"calc","args":{"expr":"1+1"}}}')
    assert o["action"]["tool"] == "calc"
    assert o["action"]["args"]["expr"] == "1+1"


def test_fenced_with_noise():
    text = 'blah blah\n```json\n{"thought":"t","final_answer":"42"}\n```\ntail'
    o = parse_action(text)
    assert o["final_answer"] == "42"


def test_repair_trailing_comma():
    o = parse_action('{"thought":"t","final_answer":"x",}')
    assert o["final_answer"] == "x"


def test_invalid_raises():
    with pytest.raises(ParseError):
        parse_action("not json at all")


def test_missing_keys_raises():
    with pytest.raises(ParseError):
        parse_action('{"thought":"t"}')

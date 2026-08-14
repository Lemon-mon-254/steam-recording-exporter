import pytest

from exporter import vdf


def test_loads_basic():
    text = '"key" "value"'
    assert vdf.loads(text) == {"key": "value"}


def test_loads_nested_object():
    text = '''
"InstallConfigStore"
{
    "Software"
    {
        "Valve"
        {
            "Steam"
            {
                "Accounts"
                {
                    "76561198000000000"
                    {
                        "SteamID"    "76561198000000000"
                    }
                }
            }
        }
    }
}
'''
    root = vdf.loads(text)
    assert (
        root["InstallConfigStore"]["Software"]["Valve"]["Steam"]["Accounts"][
            "76561198000000000"
        ]["SteamID"]
        == "76561198000000000"
    )


def test_loads_multiple_top_level_keys():
    text = '"a" "1" "b" "2"'
    assert vdf.loads(text) == {"a": "1", "b": "2"}


def test_loads_escaped_quotes():
    text = r'"key" "say \"hi\" \\\n"'
    assert vdf.loads(text) == {"key": 'say "hi" \\n'}


def test_loads_missing_value():
    assert vdf.loads('"key"') == {"key": ""}


def test_loads_empty_input():
    assert vdf.loads("") == {}
    assert vdf.loads("  \n  ") == {}


def test_load(tmp_path):
    path = tmp_path / "test.acf"
    path.write_text('"AppState" { "appid" "123" "name" "Test Game" }', encoding="utf-8")
    assert vdf.load(str(path)) == {"AppState": {"appid": "123", "name": "Test Game"}}

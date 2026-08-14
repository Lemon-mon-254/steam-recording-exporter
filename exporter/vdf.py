
import re

__all__ = ["VDFParseError", "loads", "load"]


class VDFParseError(ValueError):
    pass


_TOKEN_RE = re.compile(r'"(?:\\.|[^"\\])*"|\{|\}')

_UNESCAPE_RE = re.compile(r"\\(.)")


def _unescape(value: str) -> str:
    return _UNESCAPE_RE.sub(r"\1", value)


def _tokenize(text: str):
    return [match.group(0) for match in _TOKEN_RE.finditer(text)]


def _parse_object(tokens, index: int):
    result = {}
    while index < len(tokens):
        token = tokens[index]
        index += 1
        if token == "}":
            break
        if token == "{":
            continue
        key = _unescape(token[1:-1])

        if index >= len(tokens):
            result[key] = ""
            break
        value_token = tokens[index]
        index += 1
        if value_token == "{":
            nested, index = _parse_object(tokens, index)
            result[key] = nested
        elif value_token == "}":
            result[key] = ""
            break
        else:
            result[key] = _unescape(value_token[1:-1])
    return result, index


def loads(text: str) -> dict:
    tokens = _tokenize(text)
    if not tokens:
        return {}
    if tokens[0] == "{":
        result, _ = _parse_object(tokens, 1)
        return result

    result, _ = _parse_object(tokens, 0)
    return result


def load(path: str) -> dict:
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return loads(handle.read())

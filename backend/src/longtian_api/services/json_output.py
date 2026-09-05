"""Conservative syntax repair; never infer missing model content."""

import ast
import json
import re

from json_repair import repair_json

from longtian_api.services.ai_client import decode_model_json

_TOKEN = re.compile(
    r"""\s*("(?:[^"\\\x00-\x1f]|\\.)*"|'(?:[^'\\\x00-\x1f]|\\.)*'|"""
    r"""-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?|"""
    r"""true|false|null|[{}\[\]:,])"""
)


def _tokens(text):
    result, position, stack = [], 0, []
    previous = None
    while position < len(text.rstrip()):
        match = _TOKEN.match(text, position)
        if match is None:
            raise ValueError("ambiguous JSON")
        value = match[1]
        position = match.end()
        if value == "," and (not result or previous in (",", "{", "[", ":")):
            raise ValueError("ambiguous empty value")
        if value in ("{", "["):
            stack.append(value)
            if len(stack) > 64:
                raise ValueError("JSON too deep")
        elif value in ("}", "]"):
            if not stack or stack.pop() != ("{" if value == "}" else "["):
                raise ValueError("unbalanced JSON")
        if value.startswith('"'):
            result.append(("string", json.loads(value)))
        elif value.startswith("'"):
            try:
                result.append(("string", ast.literal_eval(value)))
            except SyntaxError:
                raise ValueError("invalid string") from None
        elif value != ",":
            result.append(("token", value))
        previous = value
    if stack or not result or result[0] != ("token", "{"):
        raise ValueError("incomplete JSON object")
    return result


def decode_answer(text):
    try:
        return decode_model_json(text)
    except json.JSONDecodeError:
        # Duplicate keys and non-finite numbers raise ValueError, not syntax
        # errors, and must never reach the repair library.
        before = _tokens(text)
        repaired = repair_json(text, ensure_ascii=False, skip_json_loads=True)
        if _tokens(repaired) != before:
            raise ValueError("repair changed content or structure") from None
        # Still reject duplicate keys, NaN and Infinity after punctuation repair.
        return decode_model_json(repaired)

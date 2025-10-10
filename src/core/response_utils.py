"""Shared helpers for formatting MCP tool responses consistently."""

from typing import List, Dict, Any
import json


def make_mcp_text_response(content: str, is_error: bool = False) -> List[Dict[str, Any]]:
    """Return MCP content list with a single text item, avoiding double-wrapping.

    If content is already a JSON-serialized MCP content list (e.g.,
    '[{"type":"text","text":"..."}]'), it will be parsed and returned as-is
    instead of wrapping again.
    """
    try:
        if isinstance(content, str) and content.startswith("[") and '"type"' in content and '"text"' in content:
            parsed = json.loads(content)
            if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict) and "text" in parsed[0]:
                return parsed
    except Exception:
        # Fall back to normal wrapping if any parsing fails
        pass
    return [{"type": "text", "text": content}]




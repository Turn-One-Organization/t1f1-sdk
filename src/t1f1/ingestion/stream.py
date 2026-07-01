"""Parsers for the F1 live-timing static feed formats.

The feed serves three shapes, none of which is a valid JSON array:

* ``.json``         — a single JSON document (with a UTF-8 BOM).
* ``.jsonStream``   — line-delimited records: ``"HH:MM:SS.mmm" + <json>`` per line.
* ``.z.jsonStream`` — same, but the payload is Base64 -> raw-deflate (``wbits=-15``).

These are pure functions over already-fetched **text** so they are trivially testable
without hitting the network. They are ports of ``F1StaticClient``'s
``parse_jsonstream_simple`` / ``decompress_z_entry`` / ``parse_compressed_stream``
from the TurnOneTelemetry backend.
"""

from __future__ import annotations

import base64
import json
import zlib
from typing import Any

#: Marks the session-relative timestamp prefix we attach to each parsed record.
TIMESTAMP_KEY = "_timestamp"


def _split_lines(content: str) -> list[str]:
    """Normalise line endings and split into non-empty, stripped lines."""
    normalised = content.replace("\r\n", "\n").strip()
    return [line.strip() for line in normalised.split("\n") if line.strip()]


def _find_json_start(line: str) -> int:
    """Return the index of the first ``{`` or ``[`` in ``line``, or ``-1``."""
    for idx, char in enumerate(line):
        if char in "{[":
            return idx
    return -1


def parse_jsonstream(content: str, limit: int | None = None) -> list[dict[str, Any]]:
    """Parse a ``.jsonStream`` document (line-delimited ``timestamp + json`` records).

    Each returned record carries its session-relative timestamp string under
    :data:`TIMESTAMP_KEY`. Lines that do not contain JSON are skipped.
    """
    records: list[dict[str, Any]] = []
    for line in _split_lines(content):
        if limit is not None and len(records) >= limit:
            break
        start = _find_json_start(line)
        if start == -1:
            continue
        timestamp = line[:start].strip()
        try:
            obj = json.loads(line[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            if timestamp:
                obj[TIMESTAMP_KEY] = timestamp
            records.append(obj)
        else:
            records.append({TIMESTAMP_KEY: timestamp, "data": obj})
    return records


def decompress_z_entry(encoded_data: str) -> str:
    """Decode a single ``.z`` payload: Base64 -> raw-deflate zlib -> UTF-8 text.

    F1 uses raw deflate streams (no zlib header), hence ``wbits=-15``.
    """
    compressed = base64.b64decode(encoded_data)
    return zlib.decompress(compressed, wbits=-15).decode("utf-8-sig")


def parse_compressed_stream(content: str, limit: int | None = None) -> list[dict[str, Any]]:
    """Parse a ``.z.jsonStream`` document into decoded JSON records.

    Line shape is ``HH:MM:SS.mmm"<base64>"``: the payload is the quoted Base64 blob
    following the timestamp. Each record carries its timestamp under
    :data:`TIMESTAMP_KEY`. Undecodable lines are skipped.
    """
    records: list[dict[str, Any]] = []
    for line in _split_lines(content):
        if limit is not None and len(records) >= limit:
            break
        if '"' not in line:
            continue
        timestamp, _, remainder = line.partition('"')
        base64_data = remainder.strip().strip('"')
        if not base64_data:
            continue
        try:
            decoded = decompress_z_entry(base64_data)
            obj = json.loads(decoded)
        except (ValueError, zlib.error):
            continue
        if isinstance(obj, dict):
            obj[TIMESTAMP_KEY] = timestamp.strip()
            records.append(obj)
        else:
            records.append({TIMESTAMP_KEY: timestamp.strip(), "data": obj})
    return records

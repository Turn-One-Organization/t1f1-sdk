"""Parsers for the F1 stream formats (pure, no network)."""

from __future__ import annotations

import json

from t1f1.ingestion.stream import (
    TIMESTAMP_KEY,
    decompress_z_entry,
    parse_compressed_stream,
    parse_jsonstream,
)

from .conftest import compress_z


def test_parse_jsonstream_attaches_timestamp():
    content = (
        '00:00:01.000{"Lines": {"1": {"Position": 1}}}\n'
        '00:00:02.000{"Lines": {"1": {"Position": 2}}}\n'
    )
    records = parse_jsonstream(content)
    assert len(records) == 2
    assert records[0][TIMESTAMP_KEY] == "00:00:01.000"
    assert records[1]["Lines"]["1"]["Position"] == 2


def test_parse_jsonstream_skips_junk_and_honours_limit():
    content = "not json at all\n" '00:00:01.000{"a": 1}\n' '00:00:02.000{"a": 2}\n'
    assert len(parse_jsonstream(content)) == 2
    assert len(parse_jsonstream(content, limit=1)) == 1


def test_decompress_z_entry_roundtrip():
    payload = {"Entries": [{"Utc": "2024-08-31T13:00:01.000Z", "Cars": {}}]}
    encoded = compress_z(payload)
    assert json.loads(decompress_z_entry(encoded)) == payload


def test_parse_compressed_stream_decodes_lines():
    line_payload = {"Entries": [{"Utc": "2024-08-31T13:00:01.000Z"}]}
    content = f'00:00:01.000"{compress_z(line_payload)}"'
    records = parse_compressed_stream(content)
    assert len(records) == 1
    assert records[0][TIMESTAMP_KEY] == "00:00:01.000"
    assert records[0]["Entries"][0]["Utc"].endswith("Z")


def test_parse_compressed_stream_skips_undecodable_lines():
    content = '00:00:01.000"!!!not-base64!!!"\n' "no-quote-here\n"
    assert parse_compressed_stream(content) == []

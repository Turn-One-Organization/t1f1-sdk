# Overview

The SDK is designed around one primary workflow: create a client, open a session, and request
the data products you need.

## Core ideas

- Session data is fetched lazily.
- Raw telemetry always comes from the free F1 feed.
- Derived analysis may come from premium services when available.
- All outputs are normal `polars.DataFrame` objects unless a method documents a different type.

For the exact routing rules, read [Free vs Premium](free-vs-premium.md).
"""Ergonomic, chainable accessors layered on top of the SDK's typed polars frames.

Composition, not subclassing: polars discourages subclassing ``DataFrame`` (its
methods return plain ``DataFrame``, which would break the subclass chain), so these
wrappers hold a ``.frame``/``.to_polars()`` escape hatch instead of locking users in.
"""

from __future__ import annotations

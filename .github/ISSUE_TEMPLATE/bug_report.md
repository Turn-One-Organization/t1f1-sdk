---
name: Bug report
about: Something in t1f1-sdk isn't behaving correctly
title: "fix: "
labels: bug
---

## Session that triggered it

- Year / GP / session (e.g. `2024, "Monza", "Q"`):
- Free tier or premium (`api_key` set)?

## What happened

<!-- Actual behavior, including the full traceback if there's an exception. -->

## What you expected

## Minimal repro

```python
from t1f1 import Client

with Client() as client:
    session = client.session(2024, "Monza", "Q")
    ...  # the call that fails
```

## Environment

- `t1f1-sdk` version (`python -c "import t1f1; print(t1f1.__version__)"`):
- Python version:
- OS:

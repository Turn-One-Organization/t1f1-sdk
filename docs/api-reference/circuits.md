# Circuits API

Circuit reference data (corners, marshal lights/sectors, rotation) — **premium
only**. Unlike every other analysis method, there's no free-tier fallback here at
all: the free F1 live-timing feed carries no static circuit geometry, so a free
client calling either method below raises `AuthError` immediately.

```python
from t1f1 import Client
client = Client(api_key="YOUR_T1API_KEY")
```

> **Not live-verified.** T1API's own docs describe `/circuits/{id}/data` only as
> "full circuit data incl. layout files -> `{"data": ...}`" with no field-level
> shape, and this SDK's test environment has no T1API credentials to check a real
> response against. Parsing targets fastf1's well-known `CircuitInfo` shape
> defensively (tries a few plausible key-name casings: `corners`/`Corners`,
> `x`/`X`, etc.) — treat the exact fields as unverified until checked against a
> live response.

## `circuit_info(circuit_id: int | str, *, year: int | None = None) -> CircuitInfo`

```python
info = client.circuit_info("monza", year=2024)
```

Returns a `CircuitInfo` object:

| Attribute | Type | Meaning |
|---|---|---|
| `corners` | `pl.DataFrame` | Schema: `number, letter, x, y, angle, distance` (`t1f1.schemas.CIRCUIT_CORNER_SCHEMA`) — fastf1's well-known corner-point shape. |
| `marshal_lights` | `pl.DataFrame` | Loosely-typed — whatever columns the payload actually had (see caveat above, no rigid schema imposed). |
| `marshal_sectors` | `pl.DataFrame` | Same, loosely-typed. |
| `rotation` | `float \| None` | Track-map rotation angle, if the payload included one. |

```python
info = client.circuit_info("monza", year=2024)
print(info.corners.select("number", "letter", "distance"))
print(info.rotation)
```

## `circuits(year: int) -> list[dict]`

The circuit catalogue for a season — raw entries (T1API's response records
passed through as-is, since there's no verified field shape to cast against yet).

```python
circuits = client.circuits(2024)
for c in circuits:
    print(c)
```

## Behavior notes

- Both methods raise `t1f1.AuthError` if the client was constructed without
  `api_key` — there is no degraded/free behavior to fall back to.
- Neither method appears on `Session`/`AsyncSession` — they're season/circuit-level
  lookups on `Client`/`AsyncClient` directly, not scoped to one session.

```python
from t1f1 import Client, AuthError

with Client() as free_client:  # no api_key
    try:
        free_client.circuit_info("monza")
    except AuthError as exc:
        print(f"needs a key: {exc}")
```

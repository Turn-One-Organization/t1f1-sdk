# Data Shapes

Most SDK methods return `polars.DataFrame` objects.

## Why this matters

- `polars` gives you typed columns and fast columnar operations.
- The SDK keeps return values explicit rather than hiding them behind custom objects.
- You can chain downstream transforms immediately after a call.

## Common shapes

- Telemetry data: per-sample speed, throttle, gear, and related timing fields.
- Lap data: one row per lap or lap summary.
- Results data: session classification and standings-style tables.
- Event data: season schedules and session metadata.

When you need exact column names, use the reference page for the relevant method and inspect the frame
with `head()` or `schema`.
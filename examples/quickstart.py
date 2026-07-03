"""Free-tier basics: telemetry, laps, and locally-computed analysis. No API key needed."""

from t1f1 import Client

with Client() as client:
    session = client.session(2024, "Monza", "Q")

    telemetry = session.telemetry("VER")
    print(telemetry.head())

    laps = session.laps().pick_drivers("VER").pick_quicklaps()
    print(laps.to_polars().select("lap_number", "lap_time", "compound"))

    print(session.driver_pace())
    print(session.tyre_stints())

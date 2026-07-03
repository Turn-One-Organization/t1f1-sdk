"""Premium tier: routing, graceful fallback, and quota/source introspection.

Requires a T1API key (set T1F1_API_KEY). Without one, session.driver_pace() below
computes locally instead — that's the same fallback path this example demonstrates,
just triggered by "no key" rather than "premium had an outage".
"""

import os

from t1f1 import Client

api_key = os.environ.get("T1F1_API_KEY")

with Client(api_key=api_key) as client:
    session = client.session(2024, "Monza", "Q")

    pace = session.driver_pace()
    print(f"served by: {session.last_source}")  # "t1api" or "free"
    print(pace)

    if client.is_premium:
        print("quota:", client.quota)  # None until a premium request has hit the network

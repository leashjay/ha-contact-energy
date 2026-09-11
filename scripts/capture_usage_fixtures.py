#!/usr/bin/env python3
"""Capture raw Contact Energy usage API responses for use as test fixtures.

Logs in with the account configured in .env and walks back over a range of
days (mirroring the sensor's historical backfill), saving each day's raw
JSON response to raw_data/usage/. Re-run this any time real fixture data
needs to be repopulated (e.g. after the API's response shape changes, or to
capture new edge cases such as null dollarValue/offpeakValue days).

raw_data/ is gitignored — it holds real account data and should not be
committed. Hand-pick and redact interesting responses into tests/fixtures
if they're needed for the automated test suite.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

env_file = REPO / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"'))

from custom_components.contact_energy.api import ContactEnergyApi  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--days", type=int, default=365, help="Number of days to walk back (default: 365)"
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=REPO / "raw_data" / "usage",
        help="Directory to write raw JSON responses to",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.2,
        help="Seconds to sleep between requests (default: 0.2)",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip days that already have a saved response file",
    )
    args = parser.parse_args()

    email = os.environ.get("CONTACT_ENERGY_EMAIL")
    password = os.environ.get("CONTACT_ENERGY_PASSWORD")
    if not email or not password:
        print(
            "ERROR: CONTACT_ENERGY_EMAIL / CONTACT_ENERGY_PASSWORD must be set",
            file=sys.stderr,
        )
        sys.exit(1)

    args.out_dir.mkdir(parents=True, exist_ok=True)

    api = ContactEnergyApi(email, password)
    print(f"Logging in as {email}...")
    if not api.login():
        print("Login failed", file=sys.stderr)
        sys.exit(1)
    print(f"Logged in. Account: {api._accountId}  Contract: {api._contractId}")

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    saved, empty, errors, skipped = 0, 0, 0, 0
    for i in range(args.days):
        day = today - timedelta(days=args.days - i)
        out_file = args.out_dir / f"{day.date()}.json"

        if args.skip_existing and out_file.exists():
            skipped += 1
            continue

        resp = api.get_usage(day.year, day.month, day.day)

        if resp is False:
            errors += 1
            out_file.write_text(json.dumps({"error": "http_error"}, indent=2))
            print(f"{day.date()}: HTTP error")
        elif not resp:
            empty += 1
            out_file.write_text(json.dumps([], indent=2))
        else:
            saved += 1
            out_file.write_text(json.dumps(resp, indent=2, default=str))

        if (i + 1) % 30 == 0:
            print(f"...{i + 1}/{args.days} days processed")

        time.sleep(args.delay)

    print("\n" + "=" * 60)
    print(f"Saved {saved} days with data, {empty} empty, {errors} errors, {skipped} skipped")
    print(f"Output: {args.out_dir}")


if __name__ == "__main__":
    main()

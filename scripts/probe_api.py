#!/usr/bin/env python3
"""Probe the Contact Energy API and dump raw responses for schema inspection."""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests

# Load .env from repo root if present
env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"'))

EMAIL = os.environ.get("CONTACT_ENERGY_EMAIL")
PASSWORD = os.environ.get("CONTACT_ENERGY_PASSWORD")

if not EMAIL or not PASSWORD:
    print("ERROR: CONTACT_ENERGY_EMAIL and CONTACT_ENERGY_PASSWORD must be set", file=sys.stderr)
    sys.exit(1)

URL_BASE = "https://api.contact-digital-prod.net"
API_KEY = "z840P4lQCH9TqcjC9L2pP157DZcZJMcr5tVQCvyx"
HEADERS_BASE = {"x-api-key": API_KEY}


def step(label):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")


def dump(data):
    print(json.dumps(data, indent=2, default=str))


# --- Login ---
step("POST /login/v2")
r = requests.post(
    f"{URL_BASE}/login/v2",
    json={"username": EMAIL, "password": PASSWORD},
    headers=HEADERS_BASE,
    timeout=(10, 30),
)
print(f"Status: {r.status_code}")
if r.status_code != 200:
    print(f"FAILED: {r.text}")
    sys.exit(1)
login_data = r.json()
api_token = login_data.get("token", "")
print("Fields returned:", list(login_data.keys()))

# --- Refresh session ---
step("POST /login/v2/refresh")
r = requests.post(
    f"{URL_BASE}/login/v2/refresh",
    json={"username": EMAIL, "password": PASSWORD},
    headers=HEADERS_BASE,
    timeout=(10, 30),
)
print(f"Status: {r.status_code}")
if r.status_code != 200:
    print(f"FAILED: {r.text}")
    sys.exit(1)
refresh_data = r.json()
api_session = refresh_data.get("session", "")
print("Fields returned:", list(refresh_data.keys()))

# --- Get accounts ---
step("GET /customer/v2?fetchAccounts=true")
r = requests.get(
    f"{URL_BASE}/customer/v2?fetchAccounts=true",
    headers={**HEADERS_BASE, "session": api_session},
    timeout=(10, 30),
)
print(f"Status: {r.status_code}")
if r.status_code != 200:
    print(f"FAILED: {r.text}")
    sys.exit(1)
customer_data = r.json()
print("Top-level fields:", list(customer_data.keys()))

accounts = customer_data.get("accounts", [])
print(f"Accounts found: {len(accounts)}")
if not accounts:
    print("No accounts returned — cannot continue")
    sys.exit(1)

account_id = accounts[0]["id"]
contract_id = accounts[0]["contracts"][0]["contractId"]
print(f"Using account_id={account_id}, contract_id={contract_id}")

# --- Get usage (yesterday) ---
# API has a ~2-day lag; yesterday typically returns empty
today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
target = today - timedelta(days=2)
date_str = f"{target.year}-{str(target.month).zfill(2)}-{str(target.day).zfill(2)}"

step(f"POST /usage/v2/{contract_id} (date={date_str}, interval=hourly)")
url = (
    f"{URL_BASE}/usage/v2/{contract_id}"
    f"?ba={account_id}&interval=hourly&from={date_str}&to={date_str}"
)
r = requests.post(
    url,
    headers={**HEADERS_BASE, "authorization": api_token},
    timeout=(10, 30),
)
print(f"Status: {r.status_code}")
if r.status_code != 200:
    print(f"FAILED: {r.text}")
    sys.exit(1)

usage_data = r.json()
print(f"Records returned: {len(usage_data)}")

if usage_data:
    print("\n--- First record (full) ---")
    dump(usage_data[0])

    print("\n--- All field names seen across all records ---")
    all_keys = sorted({k for record in usage_data for k in record.keys()})
    print(all_keys)

    print("\n--- Sample values for key fields (first non-null per field) ---")
    interesting = ["value", "offpeakValue", "dollarValue", "offpeakDollarValue",
                   "unchargedValue", "currency", "unit", "percentage", "date", "timezone"]
    for field in interesting:
        sample = next((r[field] for r in usage_data if field in r and r[field] is not None), "NOT FOUND")
        print(f"  {field}: {sample!r}")
else:
    print("No usage data returned for yesterday — try a different date or check the account")
    print("\nRaw response:")
    dump(usage_data)

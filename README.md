# Contact Energy for Home Assistant

[![CI](https://github.com/leashjay/ha-contact-energy/actions/workflows/ci.yml/badge.svg)](https://github.com/leashjay/ha-contact-energy/actions/workflows/ci.yml)

View your Contact Energy electricity usage in Home Assistant, including kWh consumption and NZD cost statistics in the Energy Dashboard.

This is a maintained fork of the archived [codyc1515/ha-contact-energy](https://github.com/codyc1515/ha-contact-energy) integration.

---

## Requirements

- Home Assistant 2026.5 or later
- A Contact Energy account (electricity; gas is not yet tested — see [Future scope](#future-scope))

---

## Installation

### Via HACS (recommended)

1. Install [HACS](https://hacs.xyz/docs/use/download/download/) if you haven't already.
2. In Home Assistant, open **HACS → Integrations**.
3. Click the **⋮ menu** (top right) and choose **Custom repositories**.
4. Paste `https://github.com/leashjay/ha-contact-energy` and select category **Integration**, then click **Add**.
5. Search for **Contact Energy** in HACS and click **Download**.
6. Restart Home Assistant.

### Manually

1. Copy the `custom_components/contact_energy/` folder to your HA config directory:

   ```text
   /config/custom_components/contact_energy/
   ```

2. Restart Home Assistant.

---

## Setup

After installation and restart:

1. Go to **Settings → Devices & Services → Add Integration**.
2. Search for **Contact Energy**.
3. Enter your Contact Energy account **email address** and **password**.
4. Optionally adjust **Days of usage history to fetch** (default: 10).

No `configuration.yaml` changes are needed.

---

## What it adds

Three long-term statistics appear in the **Energy Dashboard** under *Individual devices* once data has been fetched:

| Statistic ID | Description |
| --- | --- |
| `contact_energy:energy_consumption` | Standard-rate kWh (billed hours) |
| `contact_energy:energy_consumption_dollars` | NZD cost for billed hours |
| `contact_energy:free_energy_consumption` | Off-peak / free kWh |

> **Note:** The Contact Energy API has a roughly two-day lag. Don't be concerned if today's and yesterday's data don't appear immediately.

---

## Known issues

- **Free (off-peak) electricity** is tracked in kWh only. The API returns `$0.000` for all free-hour cost fields, so no dollar statistic is generated for those hours.
- **Gas metering** may be available via the same API but has not been tested — contributions welcome.

---

## Future scope

The following are tracked but not yet implemented:

- **Config options flow** — change `usage_days` after initial setup without re-adding the integration.
- **Gas usage** — the Contact Energy API likely supports gas meter readings but requires a gas account to verify the response schema.
- **Solar / feed-in (sold energy)** — tracking energy exported to the grid.
- **Pricing / tariff sensors** — exposing the current rate per kWh.
- **Multi-account support** — the integration currently uses the first account returned by the API.
- **Async HTTP client** — migrate from `requests` to `aiohttp` using HA's managed session.
- **HACS default store** — submit to the HACS default store once the integration is stable.

---

## Contributing

Issues and pull requests are welcome at [github.com/leashjay/ha-contact-energy](https://github.com/leashjay/ha-contact-energy/issues).

The dev container includes everything needed to run a local HA instance:

```bash
cp .env.example .env        # fill in your Contact Energy credentials
scripts/develop             # starts Home Assistant on http://localhost:8123
scripts/lint                # run Ruff linter
python -m pytest tests/     # run unit tests
```

# Contact Energy for Home Assistant

[![CI](https://github.com/leashjay/ha-contact-energy/actions/workflows/ci.yml/badge.svg)](https://github.com/leashjay/ha-contact-energy/actions/workflows/ci.yml)

Track your Contact Energy electricity usage directly in Home Assistant — kWh consumption and NZD cost, hour by hour, in the Energy Dashboard.

---

## Requirements

- Home Assistant 2026.5 or later
- A Contact Energy account (electricity; gas is untested — see [Roadmap](#roadmap))

---

## Installation

### Via HACS

1. Install [HACS](https://hacs.xyz/docs/use/download/download/) if you haven't already.
2. In Home Assistant, go to **HACS → Integrations**.
3. Click the **⋮ menu** (top right) → **Custom repositories**.
4. Paste `https://github.com/leashjay/ha-contact-energy`, set category to **Integration**, click **Add**, then close the dialog.
5. **Contact Energy** will appear in your HACS integrations list — click it, then click **Download**.
6. Restart Home Assistant.

### Manually

Copy the `custom_components/contact_energy/` folder into your HA config directory and restart:

```text
/config/custom_components/contact_energy/
```

---

## Setup

1. Go to **Settings → Devices & Services → Add Integration**.
2. Search for **Contact Energy**.
3. Enter your Contact Energy **email** and **password**.
4. Optionally set **Days of usage history** (default: 10).

No changes to `configuration.yaml` are needed.

---

## Energy Dashboard

Go to **Settings → Dashboards → Energy → Configure** and add:

| Field | Value |
| --- | --- |
| Electricity consumed (grid) | **Contact Energy** |
| Free hours / off-peak (if applicable) | **Contact Energy (Free Hours)** |
| Cost | **Contact Energy Cost** (appears automatically once data is available) |

> **Data lag:** The Contact Energy API has a ~2 day lag. Today's and yesterday's usage won't appear — this is normal.

---

## Known issues

- **Gas metering** — untested; requires a gas account to verify. Contributions welcome.

---

## Roadmap

- Config options flow — change days of history after initial setup
- Gas usage support
- Solar / feed-in (exported energy) tracking
- Pricing / tariff sensors
- Multi-account support
- HACS default store submission

---

## Contributing

Issues and pull requests welcome at [github.com/leashjay/ha-contact-energy](https://github.com/leashjay/ha-contact-energy/issues).

### Development

The dev container includes a full local HA instance:

```bash
cp .env.example .env    # add your Contact Energy credentials
scripts/develop          # start Home Assistant at http://localhost:8123
scripts/lint             # run Ruff linter
python -m pytest tests/  # run unit tests
```

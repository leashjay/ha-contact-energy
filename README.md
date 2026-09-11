# Contact Energy for Home Assistant

[![CI](https://github.com/leashjay/ha-contact-energy/actions/workflows/ci.yml/badge.svg)](https://github.com/leashjay/ha-contact-energy/actions/workflows/ci.yml)

Track your Contact Energy usage directly in Home Assistant - kWh consumption and NZD cost in the Energy Dashboard: hourly for electricity, monthly for gas (dual-fuel accounts).

---

## Requirements

- Home Assistant 2026.5 or later
- A Contact Energy account (electricity; gas is supported for dual-fuel accounts)

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
4. Optionally set **Days of usage history to backfill** (default: 90) - this data will be loaded in the background after you complete setup, it may take a while.
5. If you have a dual-fuel (electricity + gas) account, tick **Enable gas usage tracking**, and optionally set a **gas price per kWh** to track gas cost (see [Energy Dashboard](#energy-dashboard) below - Contact Energy's API reports no gas cost data, so this is the only way to get one).

No changes to `configuration.yaml` are needed.

All of the above can be changed later from **Settings → Devices & Services → Contact Energy → Configure**, without needing to remove and re-add the integration. Increasing "Days of usage history to backfill" backfills the extra history in the background rather than blocking.

---

## Energy Dashboard

Go to **Settings → Dashboards → Energy → Configure** and add:

| Field | Value |
| --- | --- |
| Electricity consumed (grid) | **Electricity Usage** — total consumption, both peak and off-peak |
| Cost | **Electricity Cost** (appears automatically once data is available) |
| Gas consumed | **Gas Usage** (if gas tracking is enabled) |
| Gas cost | **Use a statistic** → **Gas Cost** (only if a gas price is configured — see below) |

There's also a **Special Rates** statistic (electricity only) — an informational subset showing how much of your usage was at the special/off-peak/free rate. It's *included in*, not separate from, "Electricity Usage"/"Electricity Cost" — don't add it as its own Energy Dashboard source, or that usage would be double-counted.

> **Data lag:** The Contact Energy API has a ~2 day lag. Today's and yesterday's usage won't appear — this is normal.

> **Off-peak/free rates:** if your plan has a genuinely free period, those hours contribute to "Electricity Usage" (kWh) but not "Electricity Cost" (no charge). If your plan just has a discounted off-peak *rate* rather than a free period, that cost is included in "Electricity Cost" like any other usage — it isn't free, just cheaper.

> **Gas cost is an estimate, not billing data:** Contact Energy's API never returns a gas dollar cost, so the integration computes one locally from the price you set in **Configure** (kWh × price). Changing that price later recalculates your *entire* gas cost history at the new price, since there's no way to know what the price was on any given day — it isn't a record of what you actually paid if your price has changed over time.

---

## Known issues

- **Gas contract detection is a heuristic.** The API gives no field that identifies a contract's fuel type. If your account has a second contract alongside the electricity one, it's assumed to be gas. This matches every dual-fuel account tested so far, but if your second contract is something else (e.g. a second meter), enabling gas tracking may create a sensor with no data, or fail quietly. Please open an issue if you hit this.

---

## Roadmap

- Solar / feed-in (exported energy) tracking
- Pricing / tariff sensors
- Multi-account support
- HACS default store submission

---

## Contributing

Issues and pull requests welcome at [github.com/leashjay/ha-contact-energy](https://github.com/leashjay/ha-contact-energy/issues).

### Development

Opening this repo in VS Code with the [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers) sets up a full local HA instance automatically (installs dependencies via `scripts/setup` on container creation). Then:

```bash
cp .env.example .env    # add your Contact Energy credentials
scripts/develop          # start Home Assistant at http://localhost:8123
scripts/lint             # run Ruff linter
python -m pytest tests/  # run unit tests
```

Without the dev container (plain local Python), create a virtual environment and install dependencies first:

```bash
python3 -m venv .venv && source .venv/bin/activate
scripts/setup             # pip install -r requirements.txt
cp .env.example .env      # add your Contact Energy credentials
scripts/develop            # start Home Assistant at http://localhost:8123
```

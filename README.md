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
4. Optionally set **Days of usage history to backfill** (default: 90, from 1 to 365) - this data will be loaded in the background after you complete setup, it may take a while. You can leave it alone: recent days are kept up to date automatically whatever you choose.
5. If you have a dual-fuel (electricity + gas) account, tick **Enable gas usage tracking**, and optionally set a **gas price per kWh** to track gas cost (see [Energy Dashboard](#energy-dashboard) below - Contact Energy's API reports no gas cost data, so this is the only way to get one).

No changes to `configuration.yaml` are needed.

All of the above can be changed later from **Settings → Devices & Services → Contact Energy → Configure**, without needing to remove and re-add the integration. Increasing "Days of usage history to backfill" backfills the extra history in the background rather than blocking.

---

## How it works

- Every 6 hours the integration signs in to Contact Energy and re-reads the last 7 days (the most recent days are still being finalised, so it keeps re-checking them). If Contact Energy rejects the login token it signs in again by itself.
- The numbers go into Home Assistant's **long-term statistics**, not into a sensor. That's why the **Contact Energy Usage** (and **Gas Usage**) entity is hidden by default and always reads `0` — it only exists to trigger the update. To see your data, use the [Energy Dashboard](#energy-dashboard) or **Developer tools → Statistics**.
- Each refresh carries on from the totals already stored, so re-reading recent days never makes earlier history jump or go negative.

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

## Upgrading from 2.0.1 or earlier

Older versions treated any hour with an off-peak/free rate as separate and **left it out of "Contact Energy" (now "Electricity Usage")** and its cost, so your totals were too low. Now every kWh counts toward Electricity Usage. The statistic IDs are unchanged, so your Energy Dashboard keeps working, but only the days that get re-read are restated. To fix older history too, open **Configure** and raise **Days of usage history to backfill** (up to 365); it's refetched in the background. Compare a day with the Contact Energy website to check it matches.

Older versions also exposed a "Contact Energy Usage" sensor with a `total` state class, which produced meaningless zero statistics. After upgrading you may see a "no longer provided" fix under **Developer tools → Statistics**; it's safe to delete those entries.

---

## Known issues

- **Gas contract detection is a heuristic.** The API gives no field that identifies a contract's fuel type. If your account has a second contract alongside the electricity one, it's assumed to be gas. This matches every dual-fuel account tested so far, but if your second contract is something else (e.g. a second meter), enabling gas tracking may create a sensor with no data, or fail quietly. Please open an issue if you hit this.
- **Only one account is read**: the first account on your login, and its first contract for electricity.
- **Gas is monthly.** Contact Energy reports gas once a month, so the Energy Dashboard shows each month's gas in a single spike at the start of that month, not spread over the days.
- **Up to ~2 days of lag** in everything, set by Contact Energy.

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

The code targets Python 3.14 (as Home Assistant does). Opening this repo in VS Code with the [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers) sets up a full local HA instance automatically (installs dependencies via `scripts/setup` on container creation). Then:

```bash
cp .env.example .env    # add your Contact Energy credentials
bash scripts/develop     # start Home Assistant at http://localhost:8123
bash scripts/lint        # run Ruff linter
python -m pytest tests/  # run unit tests
```

Without the dev container (plain local Python), create a virtual environment and install dependencies first:

```bash
python3 -m venv .venv && source .venv/bin/activate
bash scripts/setup       # pip install -r requirements.txt
cp .env.example .env      # add your Contact Energy credentials
bash scripts/develop      # start Home Assistant at http://localhost:8123
```

The tests stub out Home Assistant, so they can't prove an HA call is real: check any Home Assistant API you add against HA's own source.

#### Capturing real API responses

`scripts/capture_usage_fixtures.py` logs in with the account in `.env` and saves each day's raw usage response as JSON, to help write tests against real data or spot API changes:

```bash
python3 scripts/capture_usage_fixtures.py --days 30 --skip-existing
```

It only talks to Contact Energy's API and writes to `raw_data/usage/`, which is gitignored because it contains **your real usage data**. Never commit or share it; redact anything you copy into `tests/` as a fixture.

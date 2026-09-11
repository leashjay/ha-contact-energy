"""Contact Energy sensors."""

import asyncio
from datetime import datetime, timedelta
import logging

from homeassistant.components import persistent_notification
from homeassistant.components.recorder import get_instance as get_recorder_instance
from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMetaData,
    StatisticMeanType,
)
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    statistics_during_period,
)
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, UnitOfEnergy
from homeassistant.core import HomeAssistant

from .api import ContactEnergyApi
from .const import (
    CONF_ENABLE_GAS,
    CONF_GAS_PRICE_PER_KWH,
    CONF_USAGE_DAYS,
    DEFAULT_USAGE_DAYS,
    DOMAIN,
    MAX_USAGE_DAYS,
    SENSOR_GAS_USAGE_NAME,
    SENSOR_USAGE_NAME,
)

_LOGGER = logging.getLogger(__name__)

# The API has a ~2 day data lag (see README), so polling more often than
# this can't surface anything new — it would just re-check the same settling
# window sooner than the data can actually change.
SCAN_INTERVAL = timedelta(hours=6)

# Spacing between per-day usage requests during backfill, to avoid bursting
# the API with hundreds of back-to-back requests (e.g. a 365-day history load).
_USAGE_REQUEST_DELAY_SECONDS = 0.2

# Gas meters are read monthly, so a single wide-range request each poll is
# enough — how many months of history to request each time.
_GAS_LOOKBACK_MONTHS = 24

# How many trailing days of usage are (re)computed on each pass. Used both
# for the fast synchronous fetch during setup (see async_setup_entry) and
# for every routine scheduled poll (see ContactEnergyUsageSensor.async_update)
# — cumulative sums are seeded from already-recorded statistics (see
# async_refresh_usage), so a poll never needs to re-walk the full usage_days
# window; only the one-time background backfill does that. Set well beyond
# the ~2 day data lag as a safety margin for occasional late-settling data.
_RECENT_SYNC_DAYS = 7
_PROGRESS_NOTIFY_EVERY_DAYS = 20
_PROGRESS_NOTIFICATION_ID = "contact_energy_usage_backfill"

KWH_STATISTIC_ID = f"{DOMAIN}:energy_consumption"
DOLLAR_STATISTIC_ID = f"{DOMAIN}:energy_consumption_dollars"
OFFPEAK_KWH_STATISTIC_ID = f"{DOMAIN}:free_energy_consumption"
GAS_KWH_STATISTIC_ID = f"{DOMAIN}:gas_consumption"
GAS_DOLLAR_STATISTIC_ID = f"{DOMAIN}:gas_consumption_dollars"

# How far back to look for the running total that a refresh continues from.
# (Reading the whole history on every poll would get slower every year.)
_BASELINE_LOOKBACK = timedelta(days=60)


async def _async_baseline_sums(
    hass: HomeAssistant, statistic_ids: set[str], window_start: datetime
) -> dict[str, float]:
    """Return the cumulative sum already recorded just before window_start.

    Used to seed a (re)computed window's running total, so overwriting
    only the hours in that window doesn't reset the series to zero and
    corrupt everything recorded before it.
    """
    rows = await get_recorder_instance(hass).async_add_executor_job(
        statistics_during_period,
        hass,
        window_start - _BASELINE_LOOKBACK,
        window_start,
        statistic_ids,
        "hour",
        None,
        {"sum"},
    )
    baselines = {}
    for statistic_id in statistic_ids:
        stored = [r for r in rows.get(statistic_id, []) if r.get("sum") is not None]
        baselines[statistic_id] = float(stored[-1]["sum"]) if stored else 0.0
    return baselines


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up Contact Energy sensors from a config entry."""
    email = config_entry.data[CONF_EMAIL]
    password = config_entry.data[CONF_PASSWORD]
    try:
        usage_days = int(
            config_entry.options.get(
                CONF_USAGE_DAYS,
                config_entry.data.get(CONF_USAGE_DAYS, DEFAULT_USAGE_DAYS),
            )
        )
    except TypeError, ValueError:
        usage_days = DEFAULT_USAGE_DAYS
    usage_days = max(1, min(MAX_USAGE_DAYS, usage_days))
    enable_gas = config_entry.options.get(
        CONF_ENABLE_GAS, config_entry.data.get(CONF_ENABLE_GAS, False)
    )
    gas_price_per_kwh = config_entry.options.get(
        CONF_GAS_PRICE_PER_KWH, config_entry.data.get(CONF_GAS_PRICE_PER_KWH, 0.0)
    )
    api = ContactEnergyApi(email, password)

    usage_sensor = ContactEnergyUsageSensor(SENSOR_USAGE_NAME, api, usage_days, email)
    entities = [usage_sensor]
    if enable_gas:
        gas_sensor = ContactEnergyGasUsageSensor(
            SENSOR_GAS_USAGE_NAME, api, email, gas_price_per_kwh
        )
        entities.append(gas_sensor)
    else:
        gas_sensor = None

    if usage_days > _RECENT_SYNC_DAYS:
        # Register entities immediately, fetch just the fast initial window
        # synchronously, then hand the rest of the configured history off to
        # a background task tied to this config entry's lifecycle.
        async_add_entities(entities, False)
        # Home Assistant attaches `hass` when it finishes adding the entities;
        # we use the sensors before that, so don't depend on the timing.
        for entity in entities:
            entity.hass = hass
        await usage_sensor.async_refresh_usage(_RECENT_SYNC_DAYS)
        if gas_sensor is not None:
            await gas_sensor.async_update()
        config_entry.async_create_background_task(
            hass,
            usage_sensor.async_backfill_remaining_history(),
            name=f"{DOMAIN}_usage_backfill",
        )
    else:
        async_add_entities(entities, True)


class ContactEnergyUsageSensor(SensorEntity):
    """Contact Energy electricity usage sensor."""

    def __init__(self, name, api, usage_days, email):
        """Initialise the sensor."""
        self._name = name
        self._icon = "mdi:meter-electric"
        self._state = 0
        self._unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._unique_id = f"{DOMAIN}_{email.lower()}"
        self._state_attributes = {}
        self._usage_days = usage_days
        self._api = api
        self._relogin_failed = False

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def icon(self):
        """Icon to use in the frontend."""
        return self._icon

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def extra_state_attributes(self):
        """Return state attributes."""
        return self._state_attributes

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return self._unit_of_measurement

    @property
    def unique_id(self):
        """Return the unique id."""
        return self._unique_id

    @property
    def entity_registry_visible_default(self):
        """Hide by default.

        This entity's own state is never meaningful (always 0) — its only
        job is to trigger polling. The real data is in external statistics
        (see async_refresh_usage), so this shouldn't be offered anywhere a
        user picks an entity or statistic.
        """
        return False

    async def async_update(self) -> None:
        """Fetch new usage data from Contact Energy (the regular scheduled poll).

        Only the trailing _RECENT_SYNC_DAYS are re-fetched — enough to catch
        the API's ~2 day data lag settling — not the full usage_days window.
        Cumulative sums are seeded from already-recorded statistics (see
        async_refresh_usage), so this can't drift out of sync with the full
        history established by the one-time setup/backfill.
        """
        _LOGGER.debug("Beginning usage update")
        await self.async_refresh_usage(min(self._usage_days, _RECENT_SYNC_DAYS))

    async def async_backfill_remaining_history(self) -> None:
        """Fetch the rest of the configured history window in the background.

        Run once after setup when usage_days exceeds _RECENT_SYNC_DAYS, to
        avoid blocking Home Assistant startup on a large history request.
        """
        _LOGGER.debug("Beginning background usage history backfill")
        await self.async_refresh_usage(self._usage_days, show_progress=True)

    async def _async_get_usage(self, day):
        """Fetch one day of usage, signing in again once if the token was rejected."""
        args = (day.year, day.month, day.day)
        response = await self.hass.async_add_executor_job(self._api.get_usage, *args)
        if response is False and not self._api._api_token and not self._relogin_failed:
            _LOGGER.info("Signing in again after the login token was rejected")
            if await self.hass.async_add_executor_job(self._api.login):
                response = await self.hass.async_add_executor_job(
                    self._api.get_usage, *args
                )
            else:
                # Don't keep submitting a password that was just refused.
                self._relogin_failed = True
        return response

    async def async_refresh_usage(
        self, days: int, *, show_progress: bool = False
    ) -> None:
        """Log in if needed, fetch `days` of usage ending today, and push statistics.

        Only the requested window is (re)computed, so each cumulative sum is
        seeded from whatever was already recorded just before that window
        (see _async_baseline_sums) instead of restarting at zero — otherwise
        a partial-window refresh (e.g. the routine poll's small trailing
        window) would wipe out everything recorded before it.
        """
        self._relogin_failed = False
        if not self._api._api_token or not self._api._contractId:
            _LOGGER.info("Not logged in, authenticating now")
            result = await self.hass.async_add_executor_job(self._api.login)
            if not result:
                _LOGGER.error("Login failed — usage will not be updated")
                return

        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        window_start = (today - timedelta(days=days)).astimezone()

        baselines = await _async_baseline_sums(
            self.hass,
            {KWH_STATISTIC_ID, DOLLAR_STATISTIC_ID, OFFPEAK_KWH_STATISTIC_ID},
            window_start,
        )
        kWh_stats: list[StatisticData] = []
        kWh_sum = baselines[KWH_STATISTIC_ID]
        dollar_stats: list[StatisticData] = []
        dollar_sum = baselines[DOLLAR_STATISTIC_ID]
        offpeak_kWh_stats: list[StatisticData] = []
        offpeak_kWh_sum = baselines[OFFPEAK_KWH_STATISTIC_ID]
        currency = "NZD"

        for i in range(days):
            if i > 0:
                await asyncio.sleep(_USAGE_REQUEST_DELAY_SECONDS)

            if show_progress and (
                i % _PROGRESS_NOTIFY_EVERY_DAYS == 0 or i == days - 1
            ):
                percent = round((i + 1) / days * 100)
                persistent_notification.async_create(
                    self.hass,
                    f"Fetched {i + 1} of {days} days ({percent}%).",
                    title="Contact Energy — loading usage history",
                    notification_id=_PROGRESS_NOTIFICATION_ID,
                )

            previous_day = today - timedelta(days=days - i)
            response = await self._async_get_usage(previous_day)
            if not response:
                continue

            for point in response:
                currency = point.get("currency", currency)
                value = point.get("value")
                if not value:
                    continue

                try:
                    start = datetime.strptime(point["date"], "%Y-%m-%dT%H:%M:%S.%f%z")
                    kwh = float(value)
                    dollar_value = point.get("dollarValue")
                    dollars = None if dollar_value is None else float(dollar_value)
                    offpeak_raw = point.get("offpeakValue")
                    offpeak_kwh = float(offpeak_raw) if offpeak_raw else 0.0
                except KeyError, TypeError, ValueError:
                    _LOGGER.warning("Skipping a usage point that could not be read")
                    continue

                # value is total kWh for the hour, regardless of rate — always
                # counts toward total grid consumption.
                kWh_sum += kwh
                kWh_stats.append(StatisticData(start=start, sum=kWh_sum))

                # dollarValue is the total cost for the hour (both peak and
                # off-peak portions combined). It's only ever null when the
                # whole hour was genuinely free — not merely off-peak-priced.
                if dollars is not None:
                    dollar_sum += dollars
                    dollar_stats.append(StatisticData(start=start, sum=dollar_sum))

                # offpeakValue is the *portion* of value (kWh) billed at the
                # off-peak rate — not a flag that the whole hour was free.
                # Tracked separately as an informational subset only; it's
                # already included above in the main consumption/cost totals.
                if offpeak_kwh > 0:
                    offpeak_kWh_sum += offpeak_kwh
                    offpeak_kWh_stats.append(
                        StatisticData(start=start, sum=offpeak_kWh_sum)
                    )

        if show_progress:
            persistent_notification.async_dismiss(self.hass, _PROGRESS_NOTIFICATION_ID)

        async_add_external_statistics(
            self.hass,
            StatisticMetaData(
                has_mean=False,
                mean_type=StatisticMeanType.NONE,
                has_sum=True,
                name="Electricity Usage",
                source=DOMAIN,
                statistic_id=f"{DOMAIN}:energy_consumption",
                unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
                unit_class="energy",
            ),
            kWh_stats,
        )

        async_add_external_statistics(
            self.hass,
            StatisticMetaData(
                has_mean=False,
                mean_type=StatisticMeanType.NONE,
                has_sum=True,
                name="Electricity Cost",
                source=DOMAIN,
                statistic_id=f"{DOMAIN}:energy_consumption_dollars",
                unit_of_measurement=currency,
                unit_class=None,
            ),
            dollar_stats,
        )

        async_add_external_statistics(
            self.hass,
            StatisticMetaData(
                has_mean=False,
                mean_type=StatisticMeanType.NONE,
                has_sum=True,
                name="Special Rates",
                source=DOMAIN,
                statistic_id=f"{DOMAIN}:free_energy_consumption",
                unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
                unit_class="energy",
            ),
            offpeak_kWh_stats,
        )


class ContactEnergyGasUsageSensor(SensorEntity):
    """Contact Energy gas usage sensor.

    Gas usage is billed monthly, and Contact Energy's API does not report a
    cost for it — only consumption in kWh. If a gas price is configured, cost
    is computed locally (kWh × price) and published as a second statistic;
    otherwise only consumption is tracked.
    """

    def __init__(self, name, api, email, gas_price_per_kwh=0.0):
        """Initialise the sensor."""
        self._name = name
        self._icon = "mdi:meter-gas"
        self._state = 0
        self._unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._unique_id = f"{DOMAIN}_{email.lower()}_gas"
        self._state_attributes = {}
        self._api = api
        self._gas_price_per_kwh = gas_price_per_kwh

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def icon(self):
        """Icon to use in the frontend."""
        return self._icon

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def extra_state_attributes(self):
        """Return state attributes."""
        return self._state_attributes

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return self._unit_of_measurement

    @property
    def unique_id(self):
        """Return the unique id."""
        return self._unique_id

    @property
    def entity_registry_visible_default(self):
        """Hide by default.

        This entity's own state is never meaningful (always 0) — its only
        job is to trigger polling. The real data is in external statistics,
        so this shouldn't be offered anywhere a user picks an entity or
        statistic.
        """
        return False

    async def async_update(self) -> None:
        """Fetch new gas usage data from Contact Energy."""
        _LOGGER.debug("Beginning gas usage update")

        if not self._api._api_token or not self._api._accountId:
            _LOGGER.info("Not logged in, authenticating now")
            result = await self.hass.async_add_executor_job(self._api.login)
            if not result:
                _LOGGER.error("Login failed — gas usage will not be updated")
                return

        if not self._api._gas_contract_id:
            _LOGGER.debug("No gas contract found on this account — skipping")
            return

        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        window_start = today - timedelta(days=30 * _GAS_LOOKBACK_MONTHS)
        date_from = window_start.strftime("%Y-%m-%d")
        date_to = today.strftime("%Y-%m-%d")

        response = await self.hass.async_add_executor_job(
            self._api.get_gas_usage, date_from, date_to
        )
        if response is False and not self._api._api_token:
            _LOGGER.info("Signing in again after the login token was rejected")
            if await self.hass.async_add_executor_job(self._api.login):
                response = await self.hass.async_add_executor_job(
                    self._api.get_gas_usage, date_from, date_to
                )
        if not response:
            return

        points = []
        currency = "NZD"
        for point in response:
            try:
                value = float(point.get("value") or 0)
                start = datetime.strptime(point["date"], "%Y-%m-%dT%H:%M:%S.%f%z")
            except KeyError, TypeError, ValueError, AttributeError:
                _LOGGER.warning("Skipping a gas usage point that could not be read")
                continue
            if not value:
                continue
            currency = point.get("currency", currency)
            points.append((start, value))
        points.sort(key=lambda p: p[0])

        # Continue from the total already recorded before this window, so the
        # oldest month in it isn't stored as a drop (negative usage) once the
        # window has moved past the start of the history.
        baselines = await _async_baseline_sums(
            self.hass,
            {GAS_KWH_STATISTIC_ID, GAS_DOLLAR_STATISTIC_ID},
            window_start.astimezone(),
        )
        kWh_stats: list[StatisticData] = []
        kWh_sum = baselines[GAS_KWH_STATISTIC_ID]
        dollar_stats: list[StatisticData] = []
        dollar_sum = baselines[GAS_DOLLAR_STATISTIC_ID]

        for start, value in points:
            kWh_sum += value
            kWh_stats.append(StatisticData(start=start, sum=kWh_sum))

            if self._gas_price_per_kwh > 0:
                dollar_sum += value * self._gas_price_per_kwh
                dollar_stats.append(StatisticData(start=start, sum=dollar_sum))

        async_add_external_statistics(
            self.hass,
            StatisticMetaData(
                has_mean=False,
                mean_type=StatisticMeanType.NONE,
                has_sum=True,
                name="Gas Usage",
                source=DOMAIN,
                statistic_id=GAS_KWH_STATISTIC_ID,
                unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
                unit_class="energy",
            ),
            kWh_stats,
        )

        if self._gas_price_per_kwh > 0:
            async_add_external_statistics(
                self.hass,
                StatisticMetaData(
                    has_mean=False,
                    mean_type=StatisticMeanType.NONE,
                    has_sum=True,
                    name="Gas Cost",
                    source=DOMAIN,
                    statistic_id=GAS_DOLLAR_STATISTIC_ID,
                    unit_of_measurement=currency,
                    unit_class=None,
                ),
                dollar_stats,
            )

"""Contact Energy sensors."""

from datetime import datetime, timedelta
import logging

from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMetaData,
    StatisticMeanType,
)
from homeassistant.components.recorder import get_instance
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
    CONF_USAGE_DAYS,
    DEFAULT_USAGE_DAYS,
    DOMAIN,
    MAX_USAGE_DAYS,
    SENSOR_USAGE_NAME,
)

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(hours=3)

KWH_STATISTIC_ID = f"{DOMAIN}:energy_consumption"
DOLLAR_STATISTIC_ID = f"{DOMAIN}:energy_consumption_dollars"
FREE_KWH_STATISTIC_ID = f"{DOMAIN}:free_energy_consumption"

# How far back to look for the running total that a refresh continues from.
BASELINE_LOOKBACK = timedelta(days=60)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up Contact Energy sensors from a config entry."""
    email = config_entry.data[CONF_EMAIL]
    password = config_entry.data[CONF_PASSWORD]
    try:
        usage_days = int(config_entry.data.get(CONF_USAGE_DAYS, DEFAULT_USAGE_DAYS))
    except TypeError, ValueError:
        usage_days = DEFAULT_USAGE_DAYS
    usage_days = max(1, min(MAX_USAGE_DAYS, usage_days))
    api = ContactEnergyApi(email, password)
    async_add_entities(
        [ContactEnergyUsageSensor(SENSOR_USAGE_NAME, api, usage_days, email)], True
    )


class ContactEnergyUsageSensor(SensorEntity):
    """Contact Energy electricity usage sensor."""

    def __init__(self, name, api, usage_days, email):
        """Initialise the sensor."""
        self._name = name
        self._icon = "mdi:meter-electric"
        self._state = 0
        self._unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._unique_id = f"{DOMAIN}_{email.lower()}"
        self._device_class = "energy"
        self._state_class = "total"
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
    def state_class(self):
        """Return the state class."""
        return self._state_class

    @property
    def device_class(self):
        """Return the device class."""
        return self._device_class

    @property
    def unique_id(self):
        """Return the unique id."""
        return self._unique_id

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

    async def _async_baseline_sums(self, before):
        """Return the last stored running total of each statistic before `before`.

        A refresh only re-reads the last few days, so it must carry on from the
        total already stored for the day before them. Starting again from zero
        makes the oldest refreshed day look like negative usage.
        """
        ids = {KWH_STATISTIC_ID, DOLLAR_STATISTIC_ID, FREE_KWH_STATISTIC_ID}
        rows = await get_instance(self.hass).async_add_executor_job(
            statistics_during_period,
            self.hass,
            before - BASELINE_LOOKBACK,
            before,
            ids,
            "hour",
            None,
            {"sum"},
        )
        baselines = {}
        for statistic_id in ids:
            stored = [r for r in rows.get(statistic_id, []) if r.get("sum") is not None]
            baselines[statistic_id] = float(stored[-1]["sum"]) if stored else 0.0
        return baselines

    async def async_update(self) -> None:
        """Fetch new usage data from Contact Energy."""
        _LOGGER.debug("Beginning usage update")

        if not self._api._api_token or not self._api._contractId:
            _LOGGER.info("Not logged in, authenticating now")
            result = await self.hass.async_add_executor_job(self._api.login)
            if not result:
                _LOGGER.error("Login failed — usage will not be updated")
                return

        self._relogin_failed = False
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        points = []
        currency = "NZD"
        for i in range(self._usage_days):
            previous_day = today - timedelta(days=self._usage_days - i)
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
                    dollars = float(point.get("dollarValue", "0"))
                except KeyError, TypeError, ValueError:
                    _LOGGER.warning("Skipping a usage point that could not be read")
                    continue
                points.append((start, kwh, dollars, point.get("offpeakValue", "0.00")))

        if points:
            baselines = await self._async_baseline_sums(min(p[0] for p in points))
        else:
            baselines = {}

        kWh_stats: list[StatisticData] = []
        kWh_sum = baselines.get(KWH_STATISTIC_ID, 0.0)
        dollar_stats: list[StatisticData] = []
        dollar_sum = baselines.get(DOLLAR_STATISTIC_ID, 0.0)
        free_kWh_stats: list[StatisticData] = []
        free_kWh_sum = baselines.get(FREE_KWH_STATISTIC_ID, 0.0)

        for start, kwh, dollars, offpeak in points:
            # offpeakValue is non-zero when energy was at the free/off-peak rate
            if offpeak == "0.00":
                kWh_sum += kwh
                dollar_sum += dollars
                kWh_stats.append(StatisticData(start=start, sum=kWh_sum))
                dollar_stats.append(StatisticData(start=start, sum=dollar_sum))
            else:
                free_kWh_sum += kwh
                free_kWh_stats.append(StatisticData(start=start, sum=free_kWh_sum))

        async_add_external_statistics(
            self.hass,
            StatisticMetaData(
                has_mean=False,
                mean_type=StatisticMeanType.NONE,
                has_sum=True,
                name="Contact Energy",
                source=DOMAIN,
                statistic_id=KWH_STATISTIC_ID,
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
                name="Contact Energy Cost",
                source=DOMAIN,
                statistic_id=DOLLAR_STATISTIC_ID,
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
                name="Contact Energy (Free Hours)",
                source=DOMAIN,
                statistic_id=FREE_KWH_STATISTIC_ID,
                unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
                unit_class="energy",
            ),
            free_kWh_stats,
        )

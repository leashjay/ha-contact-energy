"""Contact Energy sensors."""

from datetime import datetime, timedelta
import logging

from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMetaData,
    StatisticMeanType,
)
from homeassistant.components.recorder.statistics import async_add_external_statistics
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, UnitOfEnergy
from homeassistant.core import HomeAssistant

from .api import ContactEnergyApi
from .const import CONF_USAGE_DAYS, DOMAIN, SENSOR_USAGE_NAME

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(hours=3)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up Contact Energy sensors from a config entry."""
    email = config_entry.data[CONF_EMAIL]
    password = config_entry.data[CONF_PASSWORD]
    usage_days = config_entry.data.get(CONF_USAGE_DAYS, 10)
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

    async def async_update(self) -> None:
        """Fetch new usage data from Contact Energy."""
        _LOGGER.debug("Beginning usage update")

        if not self._api._api_token:
            _LOGGER.info("Not logged in, authenticating now")
            result = await self.hass.async_add_executor_job(self._api.login)
            if not result:
                _LOGGER.error("Login failed — usage will not be updated")
                return

        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        kWh_stats: list[StatisticData] = []
        kWh_sum = 0.0
        dollar_stats: list[StatisticData] = []
        dollar_sum = 0.0
        free_kWh_stats: list[StatisticData] = []
        free_kWh_sum = 0.0
        currency = "NZD"

        for i in range(self._usage_days):
            previous_day = today - timedelta(days=self._usage_days - i)
            response = await self.hass.async_add_executor_job(
                self._api.get_usage,
                previous_day.year,
                previous_day.month,
                previous_day.day,
            )
            if not response:
                continue

            for point in response:
                currency = point.get("currency", currency)
                value = point.get("value")
                if not value:
                    continue

                start = datetime.strptime(point["date"], "%Y-%m-%dT%H:%M:%S.%f%z")

                # offpeakValue is non-zero when energy was at the free/off-peak rate
                if point.get("offpeakValue", "0.00") == "0.00":
                    kWh_sum += float(value)
                    dollar_sum += float(point.get("dollarValue", "0"))
                    kWh_stats.append(StatisticData(start=start, sum=kWh_sum))
                    dollar_stats.append(StatisticData(start=start, sum=dollar_sum))
                else:
                    free_kWh_sum += float(value)
                    free_kWh_stats.append(StatisticData(start=start, sum=free_kWh_sum))

        async_add_external_statistics(
            self.hass,
            StatisticMetaData(
                has_mean=False,
                mean_type=StatisticMeanType.NONE,
                has_sum=True,
                name="ContactEnergy",
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
                name="ContactEnergyDollars",
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
                name="FreeContactEnergy",
                source=DOMAIN,
                statistic_id=f"{DOMAIN}:free_energy_consumption",
                unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
                unit_class="energy",
            ),
            free_kWh_stats,
        )

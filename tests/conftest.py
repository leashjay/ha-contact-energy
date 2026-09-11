"""Stub out Home Assistant modules so tests run without a full HA install."""

import sys
from enum import Enum
from unittest.mock import AsyncMock, MagicMock


class _UnitOfEnergy:
    KILO_WATT_HOUR = "kWh"


class _StatisticMeanType(Enum):
    NONE = "none"


class _StatisticData:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _StatisticMetaData:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


# config_entries stub — ConfigFlow base class used by config_flow.py
class _ConfigFlow:
    """Minimal ConfigFlow base for testing."""

    hass = None

    def __init_subclass__(cls, domain=None, **kwargs):
        super().__init_subclass__(**kwargs)
        if domain is not None:
            cls.DOMAIN = domain

    async def async_set_unique_id(self, unique_id):
        pass

    def _abort_if_unique_id_configured(self):
        pass

    def async_create_entry(self, *, title, data):
        return {"type": "create_entry", "title": title, "data": data}

    def async_show_form(self, *, step_id, data_schema, errors=None):
        return {
            "type": "form",
            "step_id": step_id,
            "data_schema": data_schema,
            "errors": errors or {},
        }

    def async_abort(self, *, reason):
        return {"type": "abort", "reason": reason}


class _OptionsFlow:
    """Minimal OptionsFlow base for testing."""

    config_entry = None

    def async_create_entry(self, *, title, data):
        return {"type": "create_entry", "title": title, "data": data}

    def async_show_form(self, *, step_id, data_schema, errors=None):
        return {
            "type": "form",
            "step_id": step_id,
            "data_schema": data_schema,
            "errors": errors or {},
        }


_config_entries_mod = MagicMock()
_config_entries_mod.ConfigFlow = _ConfigFlow
_config_entries_mod.OptionsFlow = _OptionsFlow

_sensor_mod = MagicMock()
_sensor_mod.SensorEntity = object

_recorder_models = MagicMock()
_recorder_models.StatisticData = _StatisticData
_recorder_models.StatisticMetaData = _StatisticMetaData
_recorder_models.StatisticMeanType = _StatisticMeanType

_recorder_stats = MagicMock()
# Default to "nothing recorded yet" so tests that don't care about baseline
# seeding (most of them) keep computing sums from zero, as before.
_recorder_stats.statistics_during_period = MagicMock(return_value={})

# get_instance(hass).async_add_executor_job(...) — the recorder-safe
# executor required for any statistics query — mirrors the
# hass.async_add_executor_job(f, *args) side_effect used elsewhere in tests.
_recorder_instance = MagicMock()
_recorder_instance.async_add_executor_job = AsyncMock(
    side_effect=lambda f, *args: f(*args)
)
_recorder_mod = MagicMock()
_recorder_mod.get_instance = MagicMock(return_value=_recorder_instance)
_recorder_mod.models = _recorder_models
_recorder_mod.statistics = _recorder_stats

_ha_const = MagicMock()
_ha_const.CONF_EMAIL = "email"
_ha_const.CONF_PASSWORD = "password"
_ha_const.UnitOfEnergy = _UnitOfEnergy

_ha_core = MagicMock()
_ha_core.HomeAssistant = object

_ha = MagicMock()
_ha.components.sensor = _sensor_mod
_ha.components.recorder = _recorder_mod
_ha.const = _ha_const
_ha.config_entries = _config_entries_mod
_ha.core = _ha_core

sys.modules.update(
    {
        "homeassistant": _ha,
        "homeassistant.components": _ha.components,
        "homeassistant.components.sensor": _sensor_mod,
        "homeassistant.components.recorder": _recorder_mod,
        "homeassistant.components.recorder.models": _recorder_models,
        "homeassistant.components.recorder.statistics": _recorder_stats,
        "homeassistant.config_entries": _config_entries_mod,
        "homeassistant.const": _ha_const,
        "homeassistant.core": _ha_core,
        "homeassistant.helpers": _ha.helpers,
        "homeassistant.helpers.config_validation": _ha.helpers.config_validation,
        "voluptuous": MagicMock(),
    }
)

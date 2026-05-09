"""Stub out Home Assistant modules so tests run without a full HA install."""

import sys
from enum import Enum
from unittest.mock import MagicMock


class _UnitOfEnergy:
    KILO_WATT_HOUR = "kWh"


class _StatisticMeanType(Enum):
    NONE = "none"


# Minimal StatisticData / StatisticMetaData stand-ins that preserve kwargs.
class _StatisticData:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _StatisticMetaData:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


# Build a PLATFORM_SCHEMA stub whose .extend() returns itself so the module-
# level assignment in sensor.py doesn't blow up.
_platform_schema = MagicMock()
_platform_schema.extend.return_value = _platform_schema

_sensor_mod = MagicMock()
_sensor_mod.PLATFORM_SCHEMA = _platform_schema
_sensor_mod.SensorEntity = object  # sensors inherit from this

_recorder_models = MagicMock()
_recorder_models.StatisticData = _StatisticData
_recorder_models.StatisticMetaData = _StatisticMetaData
_recorder_models.StatisticMeanType = _StatisticMeanType

_recorder_stats = MagicMock()

_ha_const = MagicMock()
_ha_const.CONF_EMAIL = "email"
_ha_const.CONF_PASSWORD = "password"
_ha_const.UnitOfEnergy = _UnitOfEnergy

_ha = MagicMock()
_ha.components.sensor = _sensor_mod
_ha.components.recorder.models = _recorder_models
_ha.components.recorder.statistics = _recorder_stats
_ha.const = _ha_const

sys.modules.update(
    {
        "homeassistant": _ha,
        "homeassistant.components": _ha.components,
        "homeassistant.components.sensor": _sensor_mod,
        "homeassistant.components.recorder": _ha.components.recorder,
        "homeassistant.components.recorder.models": _recorder_models,
        "homeassistant.components.recorder.statistics": _recorder_stats,
        "homeassistant.const": _ha_const,
        "homeassistant.helpers": _ha.helpers,
        "homeassistant.helpers.config_validation": _ha.helpers.config_validation,
        "voluptuous": MagicMock(),
    }
)

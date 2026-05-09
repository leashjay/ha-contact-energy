"""Tests for ContactEnergyUsageSensor update logic."""

from unittest.mock import MagicMock, patch

import pytest

from custom_components.contact_energy.sensor import ContactEnergyUsageSensor


def _make_sensor(usage_days=1):
    api = MagicMock()
    api._api_token = "token"
    sensor = ContactEnergyUsageSensor("Contact Energy Usage", api, usage_days)
    sensor.hass = MagicMock()
    return sensor, api


def _point(value, offpeak="0.12", date="2026-05-01T00:00:00.000+1200"):
    return {"date": date, "value": value, "offpeakValue": offpeak}


# ---------------------------------------------------------------------------
# Sensor properties
# ---------------------------------------------------------------------------


class TestSensorProperties:
    def test_name(self):
        sensor, _ = _make_sensor()
        assert sensor.name == "Contact Energy Usage"

    def test_unique_id(self):
        sensor, _ = _make_sensor()
        assert sensor.unique_id == "contact_energy"

    def test_device_class(self):
        sensor, _ = _make_sensor()
        assert sensor.device_class == "energy"

    def test_state_class(self):
        sensor, _ = _make_sensor()
        assert sensor.state_class == "total"

    def test_unit_of_measurement(self):
        sensor, _ = _make_sensor()
        assert sensor.unit_of_measurement == "kWh"

    def test_initial_state_is_zero(self):
        sensor, _ = _make_sensor()
        assert sensor.state == 0


# ---------------------------------------------------------------------------
# update() — login / authentication path
# ---------------------------------------------------------------------------


class TestUpdateAuth:
    def test_skips_login_when_token_present(self):
        sensor, api = _make_sensor()
        api._api_token = "existing"
        api.get_usage.return_value = []

        sensor.update()

        api.login.assert_not_called()

    def test_logs_in_when_no_token(self):
        sensor, api = _make_sensor()
        api._api_token = ""
        api.login.return_value = True
        api.get_usage.return_value = []

        sensor.update()

        api.login.assert_called_once()

    def test_returns_false_on_login_failure(self):
        sensor, api = _make_sensor()
        api._api_token = ""
        api.login.return_value = False

        result = sensor.update()

        assert result is False
        api.get_usage.assert_not_called()


# ---------------------------------------------------------------------------
# update() — statistics accumulation
# ---------------------------------------------------------------------------


class TestUpdateStatistics:
    @patch("custom_components.contact_energy.sensor.async_add_external_statistics")
    def test_paid_energy_accumulated_when_offpeak_not_zero(self, mock_stats):
        """When offpeakValue != '0.00', usage goes to the free (off-peak) bucket."""
        sensor, api = _make_sensor(usage_days=1)
        api.get_usage.return_value = [
            _point("2.0", offpeak="0.12"),
            _point("3.0", offpeak="0.10"),
        ]

        sensor.update()

        # Second call is the free stat
        _, free_metadata, free_data = mock_stats.call_args_list[1][0]
        assert free_data[-1].sum == pytest.approx(5.0)

    @patch("custom_components.contact_energy.sensor.async_add_external_statistics")
    def test_offpeak_zero_goes_to_kwh_bucket(self, mock_stats):
        """When offpeakValue == '0.00', usage goes to the main kWh bucket."""
        sensor, api = _make_sensor(usage_days=1)
        api.get_usage.return_value = [
            _point("1.5", offpeak="0.00"),
            _point("2.5", offpeak="0.00"),
        ]

        sensor.update()

        _, kwh_metadata, kwh_data = mock_stats.call_args_list[0][0]
        assert kwh_data[-1].sum == pytest.approx(4.0)

    @patch("custom_components.contact_energy.sensor.async_add_external_statistics")
    def test_running_sums_are_cumulative(self, mock_stats):
        """Each StatisticData.sum must be the running total, not a per-point value."""
        sensor, api = _make_sensor(usage_days=1)
        api.get_usage.return_value = [
            _point("1.0", offpeak="0.00"),
            _point("2.0", offpeak="0.00"),
            _point("3.0", offpeak="0.00"),
        ]

        sensor.update()

        _, _, kwh_data = mock_stats.call_args_list[0][0]
        sums = [d.sum for d in kwh_data]
        assert sums == pytest.approx([1.0, 3.0, 6.0])

    @patch("custom_components.contact_energy.sensor.async_add_external_statistics")
    def test_skips_points_with_falsy_value(self, mock_stats):
        """Points with value=None or '' must be ignored."""
        sensor, api = _make_sensor(usage_days=1)
        api.get_usage.return_value = [
            {"date": "2026-05-01T00:00:00.000+1200", "value": None, "offpeakValue": "0.00"},
            _point("2.0", offpeak="0.00"),
        ]

        sensor.update()

        _, _, kwh_data = mock_stats.call_args_list[0][0]
        assert len(kwh_data) == 1
        assert kwh_data[0].sum == pytest.approx(2.0)

    @patch("custom_components.contact_energy.sensor.async_add_external_statistics")
    def test_empty_day_response_produces_no_statistics(self, mock_stats):
        sensor, api = _make_sensor(usage_days=1)
        api.get_usage.return_value = []

        sensor.update()

        _, _, kwh_data = mock_stats.call_args_list[0][0]
        assert kwh_data == []

    @patch("custom_components.contact_energy.sensor.async_add_external_statistics")
    def test_false_response_is_skipped(self, mock_stats):
        """API returning False (network error) for a day should not raise."""
        sensor, api = _make_sensor(usage_days=1)
        api.get_usage.return_value = False

        sensor.update()

        _, _, kwh_data = mock_stats.call_args_list[0][0]
        assert kwh_data == []

    @patch("custom_components.contact_energy.sensor.async_add_external_statistics")
    def test_multi_day_usage_accumulates_across_days(self, mock_stats):
        sensor, api = _make_sensor(usage_days=2)
        api.get_usage.side_effect = [
            [_point("1.0", offpeak="0.00")],
            [_point("2.0", offpeak="0.00")],
        ]

        sensor.update()

        _, _, kwh_data = mock_stats.call_args_list[0][0]
        assert kwh_data[-1].sum == pytest.approx(3.0)

    @patch("custom_components.contact_energy.sensor.async_add_external_statistics")
    def test_statistic_ids_are_correct(self, mock_stats):
        sensor, api = _make_sensor(usage_days=1)
        api.get_usage.return_value = [_point("1.0", offpeak="0.00")]

        sensor.update()

        _, kwh_meta, _ = mock_stats.call_args_list[0][0]
        _, free_meta, _ = mock_stats.call_args_list[1][0]
        assert kwh_meta.statistic_id == "contact_energy:energy_consumption"
        assert free_meta.statistic_id == "contact_energy:free_energy_consumption"

    @patch("custom_components.contact_energy.sensor.async_add_external_statistics")
    def test_metadata_has_mean_type_none(self, mock_stats):
        from tests.conftest import _StatisticMeanType

        sensor, api = _make_sensor(usage_days=1)
        api.get_usage.return_value = [_point("1.0", offpeak="0.00")]

        sensor.update()

        _, kwh_meta, _ = mock_stats.call_args_list[0][0]
        assert kwh_meta.mean_type == _StatisticMeanType.NONE

    @patch("custom_components.contact_energy.sensor.async_add_external_statistics")
    def test_metadata_has_unit_class_energy(self, mock_stats):
        sensor, api = _make_sensor(usage_days=1)
        api.get_usage.return_value = [_point("1.0", offpeak="0.00")]

        sensor.update()

        _, kwh_meta, _ = mock_stats.call_args_list[0][0]
        assert kwh_meta.unit_class == "energy"

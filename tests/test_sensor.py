"""Tests for ContactEnergyUsageSensor."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.contact_energy.sensor import ContactEnergyUsageSensor


def _make_sensor(usage_days=1, email="user@example.com"):
    api = MagicMock()
    api._api_token = "token"
    sensor = ContactEnergyUsageSensor("Contact Energy Usage", api, usage_days, email)
    sensor.hass = MagicMock()
    # async_add_executor_job calls the given function with its args synchronously
    sensor.hass.async_add_executor_job = AsyncMock(
        side_effect=lambda f, *args: f(*args)
    )
    return sensor, api


def _point(value, offpeak="0.12", date="2026-05-01T00:00:00.000+1200"):
    return {
        "date": date,
        "value": value,
        "offpeakValue": offpeak,
        "dollarValue": "0.10",
        "currency": "NZD",
    }


# ---------------------------------------------------------------------------
# Sensor properties
# ---------------------------------------------------------------------------


class TestSensorProperties:
    def test_name(self):
        sensor, _ = _make_sensor()
        assert sensor.name == "Contact Energy Usage"

    def test_unique_id_includes_email(self):
        sensor, _ = _make_sensor(email="user@example.com")
        assert sensor.unique_id == "contact_energy_user@example.com"

    def test_unique_id_is_lowercase(self):
        sensor, _ = _make_sensor(email="User@Example.COM")
        assert sensor.unique_id == "contact_energy_user@example.com"

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
# async_update() — login / authentication path
# ---------------------------------------------------------------------------


class TestUpdateAuth:
    async def test_skips_login_when_token_present(self):
        sensor, api = _make_sensor()
        api._api_token = "existing"
        api.get_usage.return_value = []

        await sensor.async_update()

        api.login.assert_not_called()

    async def test_logs_in_when_no_token(self):
        sensor, api = _make_sensor()
        api._api_token = ""
        api.login.return_value = True
        api.get_usage.return_value = []

        await sensor.async_update()

        api.login.assert_called_once()

    async def test_returns_early_on_login_failure(self):
        sensor, api = _make_sensor()
        api._api_token = ""
        api.login.return_value = False

        await sensor.async_update()

        api.get_usage.assert_not_called()


# ---------------------------------------------------------------------------
# async_update() — statistics accumulation
# ---------------------------------------------------------------------------


class TestUpdateStatistics:
    @patch("custom_components.contact_energy.sensor.async_add_external_statistics")
    async def test_paid_energy_goes_to_kwh_bucket(self, mock_stats):
        """offpeakValue == '0.00' → standard rate → kWh + dollar buckets."""
        sensor, api = _make_sensor(usage_days=1)
        api.get_usage.return_value = [
            _point("2.0", offpeak="0.00"),
            _point("3.0", offpeak="0.00"),
        ]

        await sensor.async_update()

        _, kwh_meta, kwh_data = mock_stats.call_args_list[0][0]
        assert kwh_data[-1].sum == pytest.approx(5.0)
        assert kwh_meta.statistic_id == "contact_energy:energy_consumption"

    @patch("custom_components.contact_energy.sensor.async_add_external_statistics")
    async def test_free_energy_goes_to_free_bucket(self, mock_stats):
        """offpeakValue != '0.00' → off-peak/free rate → free kWh bucket."""
        sensor, api = _make_sensor(usage_days=1)
        api.get_usage.return_value = [
            _point("1.5", offpeak="1.5"),
            _point("2.5", offpeak="2.5"),
        ]

        await sensor.async_update()

        _, free_meta, free_data = mock_stats.call_args_list[2][0]
        assert free_data[-1].sum == pytest.approx(4.0)
        assert free_meta.statistic_id == "contact_energy:free_energy_consumption"

    @patch("custom_components.contact_energy.sensor.async_add_external_statistics")
    async def test_dollar_stats_accumulate_for_paid_hours(self, mock_stats):
        sensor, api = _make_sensor(usage_days=1)
        api.get_usage.return_value = [
            {
                "date": "2026-05-01T00:00:00.000+1200",
                "value": "1.0",
                "offpeakValue": "0.00",
                "dollarValue": "0.50",
                "currency": "NZD",
            },
            {
                "date": "2026-05-01T01:00:00.000+1200",
                "value": "2.0",
                "offpeakValue": "0.00",
                "dollarValue": "1.00",
                "currency": "NZD",
            },
        ]

        await sensor.async_update()

        _, dollar_meta, dollar_data = mock_stats.call_args_list[1][0]
        assert dollar_data[-1].sum == pytest.approx(1.50)
        assert dollar_meta.statistic_id == "contact_energy:energy_consumption_dollars"

    @patch("custom_components.contact_energy.sensor.async_add_external_statistics")
    async def test_free_hours_produce_no_dollar_entries(self, mock_stats):
        """Free hours (offpeak != 0.00) should not appear in dollar stats."""
        sensor, api = _make_sensor(usage_days=1)
        api.get_usage.return_value = [
            _point("3.0", offpeak="3.0"),  # free hour
        ]

        await sensor.async_update()

        _, _, dollar_data = mock_stats.call_args_list[1][0]
        assert dollar_data == []

    @patch("custom_components.contact_energy.sensor.async_add_external_statistics")
    async def test_running_sums_are_cumulative(self, mock_stats):
        sensor, api = _make_sensor(usage_days=1)
        api.get_usage.return_value = [
            _point("1.0", offpeak="0.00"),
            _point("2.0", offpeak="0.00"),
            _point("3.0", offpeak="0.00"),
        ]

        await sensor.async_update()

        _, _, kwh_data = mock_stats.call_args_list[0][0]
        assert [d.sum for d in kwh_data] == pytest.approx([1.0, 3.0, 6.0])

    @patch("custom_components.contact_energy.sensor.async_add_external_statistics")
    async def test_skips_points_with_falsy_value(self, mock_stats):
        sensor, api = _make_sensor(usage_days=1)
        api.get_usage.return_value = [
            {
                "date": "2026-05-01T00:00:00.000+1200",
                "value": None,
                "offpeakValue": "0.00",
                "dollarValue": "0",
                "currency": "NZD",
            },
            _point("2.0", offpeak="0.00"),
        ]

        await sensor.async_update()

        _, _, kwh_data = mock_stats.call_args_list[0][0]
        assert len(kwh_data) == 1
        assert kwh_data[0].sum == pytest.approx(2.0)

    @patch("custom_components.contact_energy.sensor.async_add_external_statistics")
    async def test_false_api_response_is_skipped(self, mock_stats):
        sensor, api = _make_sensor(usage_days=1)
        api.get_usage.return_value = False

        await sensor.async_update()

        _, _, kwh_data = mock_stats.call_args_list[0][0]
        assert kwh_data == []

    @patch("custom_components.contact_energy.sensor.async_add_external_statistics")
    async def test_multi_day_sums_accumulate_across_days(self, mock_stats):
        sensor, api = _make_sensor(usage_days=2)
        api.get_usage.side_effect = [
            [_point("1.0", offpeak="0.00")],
            [_point("2.0", offpeak="0.00")],
        ]

        await sensor.async_update()

        _, _, kwh_data = mock_stats.call_args_list[0][0]
        assert kwh_data[-1].sum == pytest.approx(3.0)

    @patch("custom_components.contact_energy.sensor.async_add_external_statistics")
    async def test_currency_read_from_response(self, mock_stats):
        sensor, api = _make_sensor(usage_days=1)
        api.get_usage.return_value = [
            {
                "date": "2026-05-01T00:00:00.000+1200",
                "value": "1.0",
                "offpeakValue": "0.00",
                "dollarValue": "0.50",
                "currency": "AUD",
            },
        ]

        await sensor.async_update()

        _, dollar_meta, _ = mock_stats.call_args_list[1][0]
        assert dollar_meta.unit_of_measurement == "AUD"

    @patch("custom_components.contact_energy.sensor.async_add_external_statistics")
    async def test_three_statistics_always_submitted(self, mock_stats):
        """async_update must always call async_add_external_statistics three times."""
        sensor, api = _make_sensor(usage_days=1)
        api.get_usage.return_value = []

        await sensor.async_update()

        assert mock_stats.call_count == 3

    @patch("custom_components.contact_energy.sensor.async_add_external_statistics")
    async def test_metadata_mean_type_none(self, mock_stats):
        from tests.conftest import _StatisticMeanType

        sensor, api = _make_sensor(usage_days=1)
        api.get_usage.return_value = [_point("1.0", offpeak="0.00")]

        await sensor.async_update()

        _, kwh_meta, _ = mock_stats.call_args_list[0][0]
        assert kwh_meta.mean_type == _StatisticMeanType.NONE

    @patch("custom_components.contact_energy.sensor.async_add_external_statistics")
    async def test_kwh_metadata_unit_class_energy(self, mock_stats):
        sensor, api = _make_sensor(usage_days=1)
        api.get_usage.return_value = [_point("1.0", offpeak="0.00")]

        await sensor.async_update()

        _, kwh_meta, _ = mock_stats.call_args_list[0][0]
        assert kwh_meta.unit_class == "energy"

    @patch("custom_components.contact_energy.sensor.async_add_external_statistics")
    async def test_dollar_metadata_unit_class_none(self, mock_stats):
        sensor, api = _make_sensor(usage_days=1)
        api.get_usage.return_value = [_point("1.0", offpeak="0.00")]

        await sensor.async_update()

        _, dollar_meta, _ = mock_stats.call_args_list[1][0]
        assert dollar_meta.unit_class is None


# ---------------------------------------------------------------------------
# async_update() — carrying on from the stored running total
# ---------------------------------------------------------------------------

_STATS = "custom_components.contact_energy.sensor.async_add_external_statistics"
_DURING = "custom_components.contact_energy.sensor.statistics_during_period"


def _stored(kwh=None, dollars=None, free=None):
    """What statistics_during_period returns for the hour before the window."""
    rows = {}
    for statistic_id, total in (
        ("contact_energy:energy_consumption", kwh),
        ("contact_energy:energy_consumption_dollars", dollars),
        ("contact_energy:free_energy_consumption", free),
    ):
        if total is not None:
            rows[statistic_id] = [
                {"start": 0.0, "sum": 1.0},
                {"start": 1.0, "sum": total},
            ]
    return rows


class TestBaselineSums:
    """Regression: a refresh restarted its totals at zero, so the oldest refreshed
    day was stored as negative usage (e.g. -7.97 kWh)."""

    @patch(_DURING)
    @patch(_STATS)
    async def test_sums_continue_from_stored_total(self, mock_stats, mock_during):
        mock_during.return_value = _stored(kwh=100.0, dollars=50.0, free=20.0)
        sensor, api = _make_sensor(usage_days=1)
        api.get_usage.return_value = [
            _point("2.0", offpeak="0.00"),
            _point("3.0", offpeak="1.0", date="2026-05-01T01:00:00.000+1200"),
        ]

        await sensor.async_update()

        _, _, kwh = mock_stats.call_args_list[0][0]
        _, _, dollars = mock_stats.call_args_list[1][0]
        _, _, free = mock_stats.call_args_list[2][0]
        assert kwh[0].sum == pytest.approx(102.0)
        assert dollars[0].sum == pytest.approx(50.10)
        assert free[0].sum == pytest.approx(23.0)

    @patch(_DURING)
    @patch(_STATS)
    async def test_first_refreshed_hour_is_never_below_stored_total(
        self, mock_stats, mock_during
    ):
        mock_during.return_value = _stored(kwh=24.3)
        sensor, api = _make_sensor(usage_days=1)
        api.get_usage.return_value = [_point("0.5", offpeak="0.00")]

        await sensor.async_update()

        _, _, kwh = mock_stats.call_args_list[0][0]
        assert kwh[0].sum - 24.3 == pytest.approx(0.5)  # change is positive

    @patch(_DURING)
    @patch(_STATS)
    async def test_no_stored_total_starts_from_zero(self, mock_stats, mock_during):
        mock_during.return_value = {}
        sensor, api = _make_sensor(usage_days=1)
        api.get_usage.return_value = [_point("2.0", offpeak="0.00")]

        await sensor.async_update()

        _, _, kwh = mock_stats.call_args_list[0][0]
        assert kwh[0].sum == pytest.approx(2.0)

    @patch(_DURING)
    @patch(_STATS)
    async def test_baseline_is_read_before_the_first_refreshed_hour(
        self, mock_stats, mock_during
    ):
        mock_during.return_value = {}
        sensor, api = _make_sensor(usage_days=1)
        api.get_usage.return_value = [
            _point("1.0", offpeak="0.00", date="2026-05-01T05:00:00.000+1200"),
            _point("1.0", offpeak="0.00", date="2026-05-01T03:00:00.000+1200"),
        ]

        await sensor.async_update()

        args = mock_during.call_args[0]
        window_start = _parse("2026-05-01T03:00:00.000+1200")
        assert args[2] == window_start  # end_time: the earliest refreshed hour
        assert args[3] == {
            "contact_energy:energy_consumption",
            "contact_energy:energy_consumption_dollars",
            "contact_energy:free_energy_consumption",
        }
        assert args[4] == "hour"
        assert args[6] == {"sum"}

    @patch(_DURING)
    @patch(_STATS)
    async def test_stored_rows_without_a_sum_are_ignored(self, mock_stats, mock_during):
        mock_during.return_value = {
            "contact_energy:energy_consumption": [
                {"start": 0.0, "sum": 7.0},
                {"start": 1.0, "sum": None},
            ]
        }
        sensor, api = _make_sensor(usage_days=1)
        api.get_usage.return_value = [_point("1.0", offpeak="0.00")]

        await sensor.async_update()

        _, _, kwh = mock_stats.call_args_list[0][0]
        assert kwh[0].sum == pytest.approx(8.0)

    @patch(_DURING)
    @patch(_STATS)
    async def test_no_usage_means_no_baseline_lookup(self, mock_stats, mock_during):
        sensor, api = _make_sensor(usage_days=1)
        api.get_usage.return_value = []

        await sensor.async_update()

        mock_during.assert_not_called()
        assert mock_stats.call_count == 3


def _parse(text):
    from datetime import datetime

    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S.%f%z")


# ---------------------------------------------------------------------------
# async_update() — bad data and expired logins
# ---------------------------------------------------------------------------


class TestRobustness:
    @patch(_STATS)
    async def test_unreadable_point_is_skipped_not_fatal(self, mock_stats):
        sensor, api = _make_sensor(usage_days=1)
        api.get_usage.return_value = [
            {
                "date": "not a date",
                "value": "1.0",
                "offpeakValue": "0.00",
                "dollarValue": "0.1",
            },
            {
                "date": "2026-05-01T00:00:00.000+1200",
                "value": "abc",
                "offpeakValue": "0.00",
            },
            _point("2.0", offpeak="0.00"),
        ]

        await sensor.async_update()

        _, _, kwh = mock_stats.call_args_list[0][0]
        assert [d.sum for d in kwh] == pytest.approx([2.0])

    @patch(_STATS)
    async def test_logs_in_again_when_token_was_rejected(self, mock_stats):
        sensor, api = _make_sensor(usage_days=1)

        def get_usage(*args):
            return [_point("1.0", offpeak="0.00")] if api._api_token else False

        def login():
            api._api_token = "fresh"
            return True

        api._api_token = "stale"
        api.get_usage.side_effect = lambda *a: (
            api.__setattr__("_api_token", "") or False
            if api._api_token == "stale"
            else get_usage(*a)
        )
        api.login.side_effect = login

        await sensor.async_update()

        api.login.assert_called_once()
        _, _, kwh = mock_stats.call_args_list[0][0]
        assert len(kwh) == 1

    @patch(_STATS)
    async def test_does_not_retry_a_refused_login_for_every_day(self, mock_stats):
        sensor, api = _make_sensor(usage_days=5)

        def rejected(*args):
            api._api_token = ""
            return False

        api.get_usage.side_effect = rejected
        api.login.return_value = False

        await sensor.async_update()

        assert api.login.call_count == 1

    @patch(_STATS)
    async def test_logs_in_when_account_was_never_found(self, mock_stats):
        sensor, api = _make_sensor(usage_days=1)
        api._api_token = "token"
        api._contractId = ""
        api.login.return_value = True
        api.get_usage.return_value = []

        await sensor.async_update()

        api.login.assert_called_once()

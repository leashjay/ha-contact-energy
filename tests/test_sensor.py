"""Tests for ContactEnergyUsageSensor."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.contact_energy.sensor import (
    ContactEnergyGasUsageSensor,
    ContactEnergyUsageSensor,
    _RECENT_SYNC_DAYS,
    async_setup_entry,
)


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


def _make_gas_sensor(
    email="user@example.com", gas_contract_id="99999", gas_price_per_kwh=0.0
):
    api = MagicMock()
    api._api_token = "token"
    api._gas_contract_id = gas_contract_id
    sensor = ContactEnergyGasUsageSensor(
        "Contact Energy Gas Usage", api, email, gas_price_per_kwh
    )
    sensor.hass = MagicMock()
    sensor.hass.async_add_executor_job = AsyncMock(
        side_effect=lambda f, *args: f(*args)
    )
    return sensor, api


def _gas_point(value, date="2025-07-01T00:00:00.000+1200"):
    return {
        "date": date,
        "value": value,
        "dollarValue": None,
        "offpeakValue": "0.00",
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

    def test_not_advertised_as_energy_entity(self):
        # The entity's own state never reflects real usage — that's pushed
        # to external statistics instead — so it must not set device_class
        # or state_class, or Home Assistant's Energy Dashboard picker would
        # offer it as a (permanently zero) grid consumption source.
        sensor, _ = _make_sensor()
        assert not hasattr(sensor, "device_class")
        assert not hasattr(sensor, "state_class")

    def test_hidden_by_default(self):
        # Purely an internal polling trigger — real data lives in external
        # statistics — so it shouldn't clutter dashboards or entity/statistic
        # pickers (some of which filter by unit compatibility rather than
        # device_class, so hiding it is the more reliable of the two).
        sensor, _ = _make_sensor()
        assert sensor.entity_registry_visible_default is False

    def test_unit_of_measurement(self):
        sensor, _ = _make_sensor()
        assert sensor.unit_of_measurement == "kWh"

    def test_initial_state_is_zero(self):
        sensor, _ = _make_sensor()
        assert sensor.state == 0


# ---------------------------------------------------------------------------
# async_setup_entry() — options override initial setup data
# ---------------------------------------------------------------------------


def _make_config_entry(data=None, options=None):
    full_data = {"email": "user@example.com", "password": "secret"}
    full_data.update(data or {})
    return MagicMock(data=full_data, options=options or {})


class TestAsyncSetupEntry:
    async def test_usage_days_falls_back_to_setup_data(self):
        entry = _make_config_entry(data={"usage_days": 5}, options={})
        added = []
        await async_setup_entry(
            MagicMock(), entry, lambda entities, _: added.extend(entities)
        )
        assert added[0]._usage_days == 5

    async def test_enable_gas_prefers_options_over_setup_data(self):
        entry = _make_config_entry(
            data={"usage_days": 5, "enable_gas": False}, options={"enable_gas": True}
        )
        added = []
        await async_setup_entry(
            MagicMock(), entry, lambda entities, _: added.extend(entities)
        )
        assert len(added) == 2
        assert isinstance(added[1], ContactEnergyGasUsageSensor)

    async def test_gas_price_prefers_options_over_setup_data(self):
        entry = _make_config_entry(
            data={"usage_days": 5, "enable_gas": True, "gas_price_per_kwh": 0.0},
            options={"gas_price_per_kwh": 0.15},
        )
        added = []
        await async_setup_entry(
            MagicMock(), entry, lambda entities, _: added.extend(entities)
        )
        assert added[1]._gas_price_per_kwh == 0.15


# ---------------------------------------------------------------------------
# async_setup_entry() — usage_days beyond the fast initial sync backfills
# in the background instead of blocking setup
# ---------------------------------------------------------------------------


def _make_hass():
    hass = MagicMock()
    hass.async_add_executor_job = AsyncMock(side_effect=lambda f, *args: f(*args))
    return hass


class TestAsyncSetupEntryLargeBackfill:
    @patch("custom_components.contact_energy.sensor.asyncio.sleep", new_callable=AsyncMock)
    @patch("custom_components.contact_energy.sensor.ContactEnergyApi")
    async def test_usage_days_prefers_options_over_setup_data(
        self, mock_api_cls, _mock_sleep
    ):
        mock_api_cls.return_value._api_token = "token"
        mock_api_cls.return_value.get_usage.return_value = []

        entry = _make_config_entry(data={"usage_days": 10}, options={"usage_days": 365})
        hass = _make_hass()
        added = []

        def fake_add_entities(entities, _update_before_add):
            for entity in entities:
                entity.hass = hass
            added.extend(entities)

        await async_setup_entry(hass, entry, fake_add_entities)

        assert added[0]._usage_days == 365
        entry.async_create_background_task.call_args.args[1].close()

    @patch("custom_components.contact_energy.sensor.asyncio.sleep", new_callable=AsyncMock)
    @patch("custom_components.contact_energy.sensor.ContactEnergyApi")
    async def test_registers_entities_without_blocking_on_full_history(
        self, mock_api_cls, _mock_sleep
    ):
        mock_api = mock_api_cls.return_value
        mock_api._api_token = "token"
        mock_api.get_usage.return_value = []

        entry = _make_config_entry(data={"usage_days": 10}, options={"usage_days": 365})
        hass = _make_hass()
        update_before_add_calls = []

        def fake_add_entities(entities, update_before_add):
            for entity in entities:
                entity.hass = hass
            update_before_add_calls.append(update_before_add)

        await async_setup_entry(hass, entry, fake_add_entities)

        # Entities are registered without HA waiting on a full update...
        assert update_before_add_calls == [False]
        # ...and only the fast initial window was fetched synchronously,
        # not the full 365-day window.
        assert mock_api.get_usage.call_count == _RECENT_SYNC_DAYS
        entry.async_create_background_task.call_args.args[1].close()

    @patch("custom_components.contact_energy.sensor.asyncio.sleep", new_callable=AsyncMock)
    @patch("custom_components.contact_energy.sensor.ContactEnergyApi")
    async def test_background_task_backfills_the_full_window(
        self, mock_api_cls, _mock_sleep
    ):
        mock_api = mock_api_cls.return_value
        mock_api._api_token = "token"
        mock_api.get_usage.return_value = []

        entry = _make_config_entry(data={"usage_days": 10}, options={"usage_days": 365})
        hass = _make_hass()

        def fake_add_entities(entities, _update_before_add):
            for entity in entities:
                entity.hass = hass

        await async_setup_entry(hass, entry, fake_add_entities)

        entry.async_create_background_task.assert_called_once()
        args, kwargs = entry.async_create_background_task.call_args
        assert args[0] is hass
        assert kwargs["name"] == "contact_energy_usage_backfill"

        mock_api.get_usage.reset_mock()
        await args[1]
        assert mock_api.get_usage.call_count == 365

    async def test_small_usage_days_blocks_and_skips_background_task(self):
        entry = _make_config_entry(data={"usage_days": 5}, options={})
        entry.async_create_background_task = MagicMock()
        added = []

        await async_setup_entry(
            MagicMock(), entry, lambda entities, _: added.extend(entities)
        )

        entry.async_create_background_task.assert_not_called()


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
    async def test_offpeak_kwh_goes_to_offpeak_bucket(self, mock_stats):
        """offpeakValue is the off-peak-priced kWh portion of each hour —
        tracked as an informational subset, in addition to (not instead of)
        the main consumption/cost totals."""
        sensor, api = _make_sensor(usage_days=1)
        api.get_usage.return_value = [
            _point("1.5", offpeak="1.5"),
            _point("2.5", offpeak="2.5"),
        ]

        await sensor.async_update()

        _, offpeak_meta, offpeak_data = mock_stats.call_args_list[2][0]
        assert offpeak_data[-1].sum == pytest.approx(4.0)
        assert offpeak_meta.statistic_id == "contact_energy:free_energy_consumption"
        assert offpeak_meta.name == "Special Rates"

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
    async def test_genuinely_free_hour_produces_no_dollar_entry(self, mock_stats):
        """dollarValue: null means genuinely free — no cost to record."""
        sensor, api = _make_sensor(usage_days=1)
        api.get_usage.return_value = [
            {
                "date": "2026-05-01T00:00:00.000+1200",
                "value": "3.0",
                "offpeakValue": "3.0",
                "dollarValue": None,
                "currency": "NZD",
            },
        ]

        await sensor.async_update()

        _, _, dollar_data = mock_stats.call_args_list[1][0]
        assert dollar_data == []

    @patch("custom_components.contact_energy.sensor.async_add_external_statistics")
    async def test_offpeak_hour_with_a_real_price_still_counts_toward_cost(
        self, mock_stats
    ):
        """A merely-discounted off-peak hour has a real dollarValue and must
        still count toward the main cost total — it's not free."""
        sensor, api = _make_sensor(usage_days=1)
        api.get_usage.return_value = [
            _point("3.0", offpeak="3.0"),  # off-peak-priced, not free
        ]

        await sensor.async_update()

        _, kwh_meta, kwh_data = mock_stats.call_args_list[0][0]
        assert kwh_meta.statistic_id == "contact_energy:energy_consumption"
        assert kwh_data[-1].sum == pytest.approx(3.0)

        _, dollar_meta, dollar_data = mock_stats.call_args_list[1][0]
        assert dollar_meta.statistic_id == "contact_energy:energy_consumption_dollars"
        assert dollar_data[-1].sum == pytest.approx(0.10)

        _, offpeak_meta, offpeak_data = mock_stats.call_args_list[2][0]
        assert offpeak_meta.statistic_id == "contact_energy:free_energy_consumption"
        assert offpeak_data[-1].sum == pytest.approx(3.0)

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
    async def test_null_dollar_value_produces_no_dollar_entry(self, mock_stats):
        """dollarValue: null means no cost data for that hour — skip it,
        don't record an explicit zero (kWh consumption is still recorded)."""
        sensor, api = _make_sensor(usage_days=1)
        api.get_usage.return_value = [
            {
                "date": "2026-05-01T00:00:00.000+1200",
                "value": "1.0",
                "offpeakValue": "0.00",
                "dollarValue": None,
                "currency": "NZD",
            },
        ]

        await sensor.async_update()

        _, _, kwh_data = mock_stats.call_args_list[0][0]
        assert kwh_data[-1].sum == pytest.approx(1.0)

        _, _, dollar_data = mock_stats.call_args_list[1][0]
        assert dollar_data == []

    @patch("custom_components.contact_energy.sensor.async_add_external_statistics")
    async def test_null_offpeak_value_treated_as_paid(self, mock_stats):
        """API sometimes returns offpeakValue: null instead of '0.00'."""
        sensor, api = _make_sensor(usage_days=1)
        api.get_usage.return_value = [
            {
                "date": "2026-05-01T00:00:00.000+1200",
                "value": "1.0",
                "offpeakValue": None,
                "dollarValue": "0.30",
                "currency": "NZD",
            },
        ]

        await sensor.async_update()

        _, _, kwh_data = mock_stats.call_args_list[0][0]
        assert kwh_data[-1].sum == pytest.approx(1.0)

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
# Baseline seeding — a routine poll only (re)computes a trailing window, so
# it must continue from whatever was already recorded, not restart at zero.
# ---------------------------------------------------------------------------


class TestBaselineSeeding:
    @patch("custom_components.contact_energy.sensor.async_add_external_statistics")
    @patch("custom_components.contact_energy.sensor.statistics_during_period")
    async def test_kwh_sum_continues_from_last_recorded_total(
        self, mock_stats_query, mock_add_stats
    ):
        mock_stats_query.return_value = {
            "contact_energy:energy_consumption": [{"start": 0.0, "sum": 500.0}]
        }
        sensor, api = _make_sensor(usage_days=1)
        api.get_usage.return_value = [_point("2.0", offpeak="0.00")]

        await sensor.async_update()

        _, kwh_meta, kwh_data = mock_add_stats.call_args_list[0][0]
        assert kwh_meta.statistic_id == "contact_energy:energy_consumption"
        assert kwh_data[-1].sum == pytest.approx(502.0)

    @patch("custom_components.contact_energy.sensor.async_add_external_statistics")
    @patch("custom_components.contact_energy.sensor.statistics_during_period")
    async def test_no_prior_statistic_seeds_from_zero(
        self, mock_stats_query, mock_add_stats
    ):
        mock_stats_query.return_value = {}
        sensor, api = _make_sensor(usage_days=1)
        api.get_usage.return_value = [_point("2.0", offpeak="0.00")]

        await sensor.async_update()

        _, _, kwh_data = mock_add_stats.call_args_list[0][0]
        assert kwh_data[-1].sum == pytest.approx(2.0)

    @patch("custom_components.contact_energy.sensor.async_add_external_statistics")
    @patch("custom_components.contact_energy.sensor.statistics_during_period")
    async def test_queries_baseline_for_each_of_the_three_statistics(
        self, mock_stats_query, _mock_add_stats
    ):
        mock_stats_query.return_value = {}
        sensor, api = _make_sensor(usage_days=1)
        api.get_usage.return_value = []

        await sensor.async_update()

        queried_ids = set()
        for call in mock_stats_query.call_args_list:
            queried_ids.update(call.args[3])
        assert queried_ids == {
            "contact_energy:energy_consumption",
            "contact_energy:energy_consumption_dollars",
            "contact_energy:free_energy_consumption",
        }

    @patch("custom_components.contact_energy.sensor.asyncio.sleep", new_callable=AsyncMock)
    async def test_routine_poll_only_fetches_recent_days_not_full_usage_days(
        self, _mock_sleep
    ):
        sensor, api = _make_sensor(usage_days=365)
        api.get_usage.return_value = []

        await sensor.async_update()

        assert api.get_usage.call_count == _RECENT_SYNC_DAYS


# ---------------------------------------------------------------------------
# async_update() — backfill progress notifications
# ---------------------------------------------------------------------------


class TestBackfillProgressNotification:
    # Progress notifications are tied only to the one-time background
    # backfill (async_backfill_remaining_history) — the regular scheduled
    # poll (async_update) never shows one, however large usage_days is,
    # since it would otherwise fire repeatedly on every scheduled poll.

    @patch("custom_components.contact_energy.sensor.persistent_notification")
    @patch("custom_components.contact_energy.sensor.asyncio.sleep", new_callable=AsyncMock)
    async def test_background_backfill_creates_and_dismisses_notification(
        self, _mock_sleep, mock_notify
    ):
        sensor, api = _make_sensor(usage_days=40)
        api.get_usage.return_value = []

        await sensor.async_backfill_remaining_history()

        assert mock_notify.async_create.called
        first_call_kwargs = mock_notify.async_create.call_args_list[0].kwargs
        assert first_call_kwargs["notification_id"] == "contact_energy_usage_backfill"
        mock_notify.async_dismiss.assert_called_once_with(
            sensor.hass, "contact_energy_usage_backfill"
        )

    @patch("custom_components.contact_energy.sensor.persistent_notification")
    @patch("custom_components.contact_energy.sensor.asyncio.sleep", new_callable=AsyncMock)
    async def test_regular_poll_never_notifies_even_with_large_usage_days(
        self, _mock_sleep, mock_notify
    ):
        sensor, api = _make_sensor(usage_days=40)
        api.get_usage.return_value = []

        await sensor.async_update()

        mock_notify.async_create.assert_not_called()
        mock_notify.async_dismiss.assert_not_called()

    @patch("custom_components.contact_energy.sensor.persistent_notification")
    async def test_small_update_does_not_notify(self, mock_notify):
        sensor, api = _make_sensor(usage_days=5)
        api.get_usage.return_value = []

        await sensor.async_update()

        mock_notify.async_create.assert_not_called()
        mock_notify.async_dismiss.assert_not_called()


# ---------------------------------------------------------------------------
# ContactEnergyGasUsageSensor
# ---------------------------------------------------------------------------


class TestGasSensorProperties:
    def test_name(self):
        sensor, _ = _make_gas_sensor()
        assert sensor.name == "Contact Energy Gas Usage"

    def test_unique_id_includes_email_and_gas_suffix(self):
        sensor, _ = _make_gas_sensor(email="user@example.com")
        assert sensor.unique_id == "contact_energy_user@example.com_gas"

    def test_not_advertised_as_energy_entity(self):
        # Same reasoning as the electricity sensor: real usage is pushed to
        # external statistics, so this entity must not claim device_class
        # "energy" or it would wrongly appear as a gas source candidate.
        sensor, _ = _make_gas_sensor()
        assert not hasattr(sensor, "device_class")
        assert not hasattr(sensor, "state_class")

    def test_hidden_by_default(self):
        sensor, _ = _make_gas_sensor()
        assert sensor.entity_registry_visible_default is False

    def test_unit_of_measurement(self):
        sensor, _ = _make_gas_sensor()
        assert sensor.unit_of_measurement == "kWh"


class TestGasSensorUpdate:
    async def test_logs_in_when_no_token(self):
        sensor, api = _make_gas_sensor()
        api._api_token = ""
        api.login.return_value = True
        api.get_gas_usage.return_value = []

        await sensor.async_update()

        api.login.assert_called_once()

    async def test_returns_early_on_login_failure(self):
        sensor, api = _make_gas_sensor()
        api._api_token = ""
        api.login.return_value = False

        await sensor.async_update()

        api.get_gas_usage.assert_not_called()

    async def test_skips_when_no_gas_contract(self):
        sensor, api = _make_gas_sensor(gas_contract_id="")

        await sensor.async_update()

        api.get_gas_usage.assert_not_called()

    @patch("custom_components.contact_energy.sensor.async_add_external_statistics")
    async def test_no_dollar_stats_submitted_without_a_price(self, mock_stats):
        """Contact Energy's API has no gas cost data — without a configured
        price, only the consumption statistic should be submitted."""
        sensor, api = _make_gas_sensor()
        api.get_gas_usage.return_value = [_gas_point("733.543")]

        await sensor.async_update()

        assert mock_stats.call_count == 1
        _, meta, _ = mock_stats.call_args_list[0][0]
        assert meta.statistic_id == "contact_energy:gas_consumption"

    @patch("custom_components.contact_energy.sensor.async_add_external_statistics")
    async def test_dollar_stats_submitted_when_price_configured(self, mock_stats):
        sensor, api = _make_gas_sensor(gas_price_per_kwh=0.10)
        api.get_gas_usage.return_value = [
            _gas_point("100.0", date="2025-07-01T00:00:00.000+1200"),
            _gas_point("150.0", date="2025-08-01T00:00:00.000+1200"),
        ]

        await sensor.async_update()

        assert mock_stats.call_count == 2
        _, dollar_meta, dollar_data = mock_stats.call_args_list[1][0]
        assert dollar_meta.statistic_id == "contact_energy:gas_consumption_dollars"
        assert dollar_meta.name == "Gas Cost"
        assert dollar_meta.unit_of_measurement == "NZD"
        assert [d.sum for d in dollar_data] == pytest.approx([10.0, 25.0])

    @patch("custom_components.contact_energy.sensor.async_add_external_statistics")
    async def test_null_dollar_value_does_not_crash(self, mock_stats):
        """Regression: gas usage points always have dollarValue: null."""
        sensor, api = _make_gas_sensor()
        api.get_gas_usage.return_value = [_gas_point("733.543")]

        await sensor.async_update()

        _, _, kwh_data = mock_stats.call_args_list[0][0]
        assert kwh_data[-1].sum == pytest.approx(733.543)

    @patch("custom_components.contact_energy.sensor.async_add_external_statistics")
    async def test_running_sums_are_cumulative_across_months(self, mock_stats):
        sensor, api = _make_gas_sensor()
        api.get_gas_usage.return_value = [
            _gas_point("100.0", date="2025-07-01T00:00:00.000+1200"),
            _gas_point("150.0", date="2025-08-01T00:00:00.000+1200"),
        ]

        await sensor.async_update()

        _, _, kwh_data = mock_stats.call_args_list[0][0]
        assert [d.sum for d in kwh_data] == pytest.approx([100.0, 250.0])

    @patch("custom_components.contact_energy.sensor.async_add_external_statistics")
    async def test_out_of_order_points_are_sorted_by_date(self, mock_stats):
        sensor, api = _make_gas_sensor()
        api.get_gas_usage.return_value = [
            _gas_point("150.0", date="2025-08-01T00:00:00.000+1200"),
            _gas_point("100.0", date="2025-07-01T00:00:00.000+1200"),
        ]

        await sensor.async_update()

        _, _, kwh_data = mock_stats.call_args_list[0][0]
        assert [d.sum for d in kwh_data] == pytest.approx([100.0, 250.0])

    @patch("custom_components.contact_energy.sensor.async_add_external_statistics")
    async def test_empty_response_submits_no_stats(self, mock_stats):
        sensor, api = _make_gas_sensor()
        api.get_gas_usage.return_value = []

        await sensor.async_update()

        mock_stats.assert_not_called()

    @patch("custom_components.contact_energy.sensor.async_add_external_statistics")
    async def test_false_response_submits_no_stats(self, mock_stats):
        sensor, api = _make_gas_sensor()
        api.get_gas_usage.return_value = False

        await sensor.async_update()

        mock_stats.assert_not_called()

"""Tests for Contact Energy config flow."""

from unittest.mock import AsyncMock, MagicMock, patch

import voluptuous as vol

from custom_components.contact_energy.config_flow import (
    ContactEnergyConfigFlow,
    ContactEnergyOptionsFlow,
)
from custom_components.contact_energy.const import (
    CONF_ENABLE_GAS,
    CONF_GAS_PRICE_PER_KWH,
    CONF_USAGE_DAYS,
    DOMAIN,
)


def _make_flow():
    flow = ContactEnergyConfigFlow()
    flow.hass = MagicMock()
    flow.hass.async_add_executor_job = AsyncMock(side_effect=lambda f, *args: f(*args))
    return flow


class TestConfigFlowStructure:
    def test_domain(self):
        assert ContactEnergyConfigFlow.DOMAIN == DOMAIN

    def test_version(self):
        assert ContactEnergyConfigFlow.VERSION == 1


class TestAsyncStepUser:
    async def test_shows_form_with_no_input(self):
        flow = _make_flow()
        result = await flow.async_step_user()
        assert result["type"] == "form"
        assert result["step_id"] == "user"
        assert result["errors"] == {}

    async def test_valid_credentials_create_entry(self):
        flow = _make_flow()
        with patch(
            "custom_components.contact_energy.config_flow.ContactEnergyApi"
        ) as mock_api_cls:
            mock_api_cls.return_value.login.return_value = True
            result = await flow.async_step_user(
                {"email": "user@example.com", "password": "secret", "usage_days": 10}
            )

        assert result["type"] == "create_entry"
        assert result["title"] == "user@example.com"
        assert result["data"]["email"] == "user@example.com"

    async def test_enable_gas_defaults_stored_in_entry(self):
        flow = _make_flow()
        with patch(
            "custom_components.contact_energy.config_flow.ContactEnergyApi"
        ) as mock_api_cls:
            mock_api_cls.return_value.login.return_value = True
            result = await flow.async_step_user(
                {
                    "email": "user@example.com",
                    "password": "secret",
                    "usage_days": 10,
                    "enable_gas": True,
                }
            )

        assert result["data"]["enable_gas"] is True

    async def test_bad_credentials_show_invalid_auth_error(self):
        flow = _make_flow()
        with patch(
            "custom_components.contact_energy.config_flow.ContactEnergyApi"
        ) as mock_api_cls:
            mock_api_cls.return_value.login.return_value = False
            result = await flow.async_step_user(
                {"email": "user@example.com", "password": "wrong", "usage_days": 10}
            )

        assert result["type"] == "form"
        assert result["errors"]["base"] == "invalid_auth"

    async def test_api_exception_shows_cannot_connect_error(self):
        flow = _make_flow()
        with patch(
            "custom_components.contact_energy.config_flow.ContactEnergyApi"
        ) as mock_api_cls:
            mock_api_cls.return_value.login.side_effect = Exception("timeout")
            result = await flow.async_step_user(
                {"email": "user@example.com", "password": "secret", "usage_days": 10}
            )

        assert result["type"] == "form"
        assert result["errors"]["base"] == "cannot_connect"


def _make_options_flow(data=None, options=None):
    flow = ContactEnergyOptionsFlow()
    flow.config_entry = MagicMock(
        data=data or {"email": "user@example.com", "password": "secret"},
        options=options or {},
    )
    return flow


class TestOptionsFlow:
    def test_get_options_flow_returns_options_flow(self):
        result = ContactEnergyConfigFlow.async_get_options_flow(MagicMock())
        assert isinstance(result, ContactEnergyOptionsFlow)

    async def test_shows_form_with_no_input(self):
        flow = _make_options_flow()
        result = await flow.async_step_init()
        assert result["type"] == "form"
        assert result["step_id"] == "init"

    async def test_form_defaults_fall_back_to_original_setup_data(self):
        flow = _make_options_flow(
            data={"usage_days": 10, "enable_gas": False, "gas_price_per_kwh": 0.0},
            options={},
        )
        vol.Optional.reset_mock()
        await flow.async_step_init()
        defaults = {
            call.args[0]: call.kwargs.get("default")
            for call in vol.Optional.call_args_list
        }
        assert defaults[CONF_USAGE_DAYS] == 10
        assert defaults[CONF_ENABLE_GAS] is False
        assert defaults[CONF_GAS_PRICE_PER_KWH] == 0.0

    async def test_form_defaults_prefer_existing_options_over_setup_data(self):
        flow = _make_options_flow(
            data={"usage_days": 10, "enable_gas": False, "gas_price_per_kwh": 0.0},
            options={"usage_days": 90, "enable_gas": True, "gas_price_per_kwh": 0.12},
        )
        vol.Optional.reset_mock()
        await flow.async_step_init()
        defaults = {
            call.args[0]: call.kwargs.get("default")
            for call in vol.Optional.call_args_list
        }
        assert defaults[CONF_USAGE_DAYS] == 90
        assert defaults[CONF_ENABLE_GAS] is True
        assert defaults[CONF_GAS_PRICE_PER_KWH] == 0.12

    async def test_submitting_creates_entry_with_new_options(self):
        flow = _make_options_flow()
        result = await flow.async_step_init(
            {"usage_days": 365, "enable_gas": True}
        )
        assert result["type"] == "create_entry"
        assert result["data"] == {"usage_days": 365, "enable_gas": True}

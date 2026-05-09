"""Tests for Contact Energy config flow."""

from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.contact_energy.config_flow import ContactEnergyConfigFlow
from custom_components.contact_energy.const import DOMAIN


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

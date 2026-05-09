"""Config flow for Contact Energy."""

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD

from .api import ContactEnergyApi
from .const import CONF_USAGE_DAYS, DOMAIN

_SETUP_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_USAGE_DAYS, default=10): int,
    }
)


class ContactEnergyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Contact Energy."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial setup step."""
        errors = {}

        if user_input is not None:
            api = ContactEnergyApi(user_input[CONF_EMAIL], user_input[CONF_PASSWORD])
            try:
                result = await self.hass.async_add_executor_job(api.login)
                if result:
                    await self.async_set_unique_id(user_input[CONF_EMAIL].lower())
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=user_input[CONF_EMAIL],
                        data=user_input,
                    )
                errors["base"] = "invalid_auth"
            except Exception:  # noqa: BLE001
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=_SETUP_SCHEMA,
            errors=errors,
        )

"""Config flow for Contact Energy."""

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD

from .api import ContactEnergyApi
from .const import (
    CONF_ENABLE_GAS,
    CONF_GAS_PRICE_PER_KWH,
    CONF_USAGE_DAYS,
    DEFAULT_USAGE_DAYS,
    DOMAIN,
    MAX_USAGE_DAYS,
)

_USAGE_DAYS_VALIDATOR = vol.All(int, vol.Range(min=1, max=MAX_USAGE_DAYS))

# 0 means "don't track gas cost" — Contact Energy's API reports no gas cost
# data, so this is the only way to get a gas cost statistic at all.
_GAS_PRICE_VALIDATOR = vol.All(vol.Coerce(float), vol.Range(min=0))

_SETUP_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(
            CONF_USAGE_DAYS, default=DEFAULT_USAGE_DAYS
        ): _USAGE_DAYS_VALIDATOR,
        vol.Optional(CONF_ENABLE_GAS, default=False): bool,
        vol.Optional(CONF_GAS_PRICE_PER_KWH, default=0.0): _GAS_PRICE_VALIDATOR,
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

    @staticmethod
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return ContactEnergyOptionsFlow()


class ContactEnergyOptionsFlow(config_entries.OptionsFlow):
    """Handle Contact Energy options after initial setup."""

    async def async_step_init(self, user_input=None):
        """Manage usage-history and gas-tracking options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_usage_days = self.config_entry.options.get(
            CONF_USAGE_DAYS,
            self.config_entry.data.get(CONF_USAGE_DAYS, DEFAULT_USAGE_DAYS),
        )
        current_enable_gas = self.config_entry.options.get(
            CONF_ENABLE_GAS,
            self.config_entry.data.get(CONF_ENABLE_GAS, False),
        )
        current_gas_price = self.config_entry.options.get(
            CONF_GAS_PRICE_PER_KWH,
            self.config_entry.data.get(CONF_GAS_PRICE_PER_KWH, 0.0),
        )

        options_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_USAGE_DAYS, default=current_usage_days
                ): _USAGE_DAYS_VALIDATOR,
                vol.Optional(CONF_ENABLE_GAS, default=current_enable_gas): bool,
                vol.Optional(
                    CONF_GAS_PRICE_PER_KWH, default=current_gas_price
                ): _GAS_PRICE_VALIDATOR,
            }
        )

        return self.async_show_form(step_id="init", data_schema=options_schema)

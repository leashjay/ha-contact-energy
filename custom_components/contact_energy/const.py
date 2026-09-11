"""Constants for the Contact Energy integration."""

DOMAIN = "contact_energy"
SENSOR_USAGE_NAME = "Contact Energy Usage"
SENSOR_GAS_USAGE_NAME = "Contact Energy Gas Usage"
CONF_USAGE_DAYS = "usage_days"
CONF_ENABLE_GAS = "enable_gas"
CONF_GAS_PRICE_PER_KWH = "gas_price_per_kwh"
DEFAULT_USAGE_DAYS = 90
# Upper bound for "days of usage": stops a typo sending thousands of requests to Contact.
MAX_USAGE_DAYS = 365

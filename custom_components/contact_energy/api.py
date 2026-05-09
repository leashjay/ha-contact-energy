"""Contact Energy API."""

import logging

import requests

_LOGGER = logging.getLogger(__name__)

# Shared platform key extracted from myaccount.contact.co.nz — public, not a user secret,
# but may be rotated by Contact Energy without notice.
CONTACT_ENERGY_API_KEY = "z840P4lQCH9TqcjC9L2pP157DZcZJMcr5tVQCvyx"


class ContactEnergyApi:
    """Class for Contact Energy API."""

    def __init__(self, email, password):
        """Initialise Contact Energy API."""
        self._api_token = ""
        self._api_session = ""
        self._contractId = ""
        self._accountId = ""
        self._url_base = "https://api.contact-digital-prod.net"
        self._email = email
        self._password = password

    def login(self):
        """Login to the Contact Energy API."""
        headers = {"x-api-key": CONTACT_ENERGY_API_KEY}
        data = {"username": self._email, "password": self._password}
        result = requests.post(
            self._url_base + "/login/v2", json=data, headers=headers, timeout=(10, 30)
        )
        if result.status_code == requests.codes.ok:
            self._api_token = result.json()["token"]
            _LOGGER.debug("Logged in")
            self.refresh_session()
            return True
        _LOGGER.error("Failed to login: HTTP %s", result.status_code)
        return False

    def refresh_session(self):
        """Refresh the session."""
        headers = {"x-api-key": CONTACT_ENERGY_API_KEY}
        data = {"username": self._email, "password": self._password}
        result = requests.post(
            self._url_base + "/login/v2/refresh",
            json=data,
            headers=headers,
            timeout=(10, 30),
        )
        if result.status_code == requests.codes.ok:
            self._api_session = result.json()["session"]
            _LOGGER.debug("Refreshed session")
            self.get_accounts()
            return True
        _LOGGER.error("Failed to refresh session: HTTP %s", result.status_code)
        return False

    def get_accounts(self):
        """Get the first account."""
        headers = {"x-api-key": CONTACT_ENERGY_API_KEY, "session": self._api_session}
        result = requests.get(
            self._url_base + "/customer/v2?fetchAccounts=true",
            headers=headers,
            timeout=(10, 30),
        )
        if result.status_code == requests.codes.ok:
            _LOGGER.debug("Retrieved accounts")
            data = result.json()
            self._accountId = data["accounts"][0]["id"]
            self._contractId = data["accounts"][0]["contracts"][0]["contractId"]
        else:
            _LOGGER.error("Failed to fetch customer accounts: HTTP %s", result.status_code)
            return False

    def get_usage(self, year, month, day):
        """Fetch hourly usage data for a single day."""
        headers = {"x-api-key": CONTACT_ENERGY_API_KEY, "authorization": self._api_token}
        date = f"{year}-{str(month).zfill(2)}-{str(day).zfill(2)}"
        url = (
            f"{self._url_base}/usage/v2/{self._contractId}"
            f"?ba={self._accountId}&interval=hourly&from={date}&to={date}"
        )
        response = requests.post(url, headers=headers, timeout=(10, 30))
        if response.status_code == requests.codes.ok:
            data = response.json()
            if not data:
                _LOGGER.info("No usage data returned for %s/%s/%s", year, month, day)
            return data
        _LOGGER.error(
            "Failed to fetch usage for %s/%s/%s: HTTP %s",
            year,
            month,
            day,
            response.status_code,
        )
        return False

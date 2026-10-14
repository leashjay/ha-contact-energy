"""Tests for ContactEnergyApi."""

from unittest.mock import MagicMock, patch

import pytest

from custom_components.contact_energy.api import ContactEnergyApi


@pytest.fixture()
def api():
    return ContactEnergyApi("user@example.com", "secret")


# ---------------------------------------------------------------------------
# login()
# ---------------------------------------------------------------------------


class TestLogin:
    @patch("custom_components.contact_energy.api.requests.post")
    def test_success_stores_token_and_calls_refresh(self, mock_post, api):
        mock_post.return_value = MagicMock(
            status_code=200, json=lambda: {"token": "tok123"}
        )
        with patch.object(api, "refresh_session", return_value=True) as mock_refresh:
            result = api.login()

        assert result is True
        assert api._api_token == "tok123"
        mock_refresh.assert_called_once()

    @patch("custom_components.contact_energy.api.requests.post")
    def test_failure_returns_false(self, mock_post, api):
        mock_post.return_value = MagicMock(status_code=401, text="Unauthorized")
        assert api.login() is False
        assert api._api_token == ""


# ---------------------------------------------------------------------------
# refresh_session()
# ---------------------------------------------------------------------------


class TestRefreshSession:
    @patch("custom_components.contact_energy.api.requests.post")
    def test_success_stores_session_and_calls_get_accounts(self, mock_post, api):
        mock_post.return_value = MagicMock(
            status_code=200, json=lambda: {"session": "sess456"}
        )
        with patch.object(api, "get_accounts") as mock_accounts:
            result = api.refresh_session()

        assert result is True
        assert api._api_session == "sess456"
        mock_accounts.assert_called_once()

    @patch("custom_components.contact_energy.api.requests.post")
    def test_failure_returns_false(self, mock_post, api):
        mock_post.return_value = MagicMock(status_code=403, text="Forbidden")
        assert api.refresh_session() is False


# ---------------------------------------------------------------------------
# get_accounts()
# ---------------------------------------------------------------------------


class TestGetAccounts:
    @patch("custom_components.contact_energy.api.requests.get")
    def test_stores_account_and_contract_ids(self, mock_get, api):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "accounts": [{"id": 11111, "contracts": [{"contractId": 22222}]}]
            },
        )
        api.get_accounts()

        assert api._accountId == 11111
        assert api._contractId == 22222

    @patch("custom_components.contact_energy.api.requests.get")
    def test_failure_returns_false(self, mock_get, api):
        mock_get.return_value = MagicMock(status_code=500, text="Error")
        assert api.get_accounts() is False


# ---------------------------------------------------------------------------
# get_usage()
# ---------------------------------------------------------------------------


class TestGetUsage:
    def _make_api(self, contract_id=12345, account_id=67890):
        a = ContactEnergyApi("u@example.com", "p")
        a._contractId = contract_id
        a._accountId = account_id
        a._api_token = "token"
        return a

    @patch("custom_components.contact_energy.api.requests.post")
    def test_success_returns_data(self, mock_post):
        payload = [
            {
                "date": "2026-05-01T00:00:00.000+12:00",
                "value": "1.5",
                "offpeakValue": "0.12",
            }
        ]
        mock_post.return_value = MagicMock(status_code=200, json=lambda: payload)

        result = self._make_api().get_usage(2026, 5, 1)

        assert result == payload

    @patch("custom_components.contact_energy.api.requests.post")
    def test_failure_returns_false(self, mock_post):
        mock_post.return_value = MagicMock(status_code=500)
        assert self._make_api().get_usage(2026, 5, 1) is False

    @patch("custom_components.contact_energy.api.requests.post")
    def test_url_contains_contract_and_account(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: [])
        api = self._make_api(contract_id=99999, account_id=88888)
        api.get_usage(2026, 5, 1)

        url = mock_post.call_args[0][0]
        assert "99999" in url
        assert "88888" in url

    @patch("custom_components.contact_energy.api.requests.post")
    def test_month_and_day_are_zero_padded(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: [])
        self._make_api().get_usage(2026, 3, 5)

        url = mock_post.call_args[0][0]
        assert "2026-03-05" in url

    @patch("custom_components.contact_energy.api.requests.post")
    def test_integer_contract_and_account_ids_do_not_raise(self, mock_post):
        """Regression: API returns integer IDs; string concatenation must not fail."""
        mock_post.return_value = MagicMock(status_code=200, json=lambda: [])
        api = self._make_api(contract_id=12345, account_id=67890)
        # Both IDs are already integers — this was the original TypeError
        result = api.get_usage(2026, 1, 1)
        assert result is not False

    @patch("custom_components.contact_energy.api.requests.post")
    def test_from_and_to_dates_match(self, mock_post):
        """from= and to= should be the same date for a single-day query."""
        mock_post.return_value = MagicMock(status_code=200, json=lambda: [])
        self._make_api().get_usage(2026, 11, 30)

        url = mock_post.call_args[0][0]
        assert "from=2026-11-30" in url
        assert "to=2026-11-30" in url

    @patch("custom_components.contact_energy.api.requests.post")
    def test_interval_is_hourly(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: [])
        self._make_api().get_usage(2026, 5, 1)

        url = mock_post.call_args[0][0]
        assert "interval=hourly" in url

    @patch("custom_components.contact_energy.api.requests.post")
    def test_empty_response_returns_empty_list(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: [])
        result = self._make_api().get_usage(2026, 5, 1)
        assert result == []

    @patch("custom_components.contact_energy.api.requests.post")
    def test_auth_header_uses_api_token(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: [])
        api = self._make_api()
        api._api_token = "mytoken"
        api.get_usage(2026, 5, 1)

        headers = mock_post.call_args[1]["headers"]
        assert headers["authorization"] == "mytoken"


# ---------------------------------------------------------------------------
# Failures must come back as False, never as exceptions
# ---------------------------------------------------------------------------


class TestNetworkAndBadResponses:
    @patch("custom_components.contact_energy.api.requests.post")
    def test_login_network_error_returns_false(self, mock_post, api):
        import requests

        mock_post.side_effect = requests.ConnectionError("boom")
        assert api.login() is False

    @patch("custom_components.contact_energy.api.requests.post")
    def test_login_without_token_in_response_returns_false(self, mock_post, api):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {})
        assert api.login() is False
        assert api._api_token == ""

    @patch("custom_components.contact_energy.api.requests.post")
    def test_refresh_network_error_returns_false(self, mock_post, api):
        import requests

        mock_post.side_effect = requests.Timeout("slow")
        assert api.refresh_session() is False

    @patch("custom_components.contact_energy.api.requests.get")
    def test_get_accounts_success_returns_true(self, mock_get, api):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"accounts": [{"id": 1, "contracts": [{"contractId": 2}]}]},
        )
        assert api.get_accounts() is True

    @patch("custom_components.contact_energy.api.requests.get")
    def test_get_accounts_with_no_accounts_returns_false(self, mock_get, api):
        mock_get.return_value = MagicMock(
            status_code=200, json=lambda: {"accounts": []}
        )
        assert api.get_accounts() is False
        assert api._contractId == ""

    @patch("custom_components.contact_energy.api.requests.get")
    def test_get_accounts_network_error_returns_false(self, mock_get, api):
        import requests

        mock_get.side_effect = requests.ConnectionError("boom")
        assert api.get_accounts() is False

    @patch("custom_components.contact_energy.api.requests.post")
    def test_usage_network_error_returns_false(self, mock_post):
        import requests

        mock_post.side_effect = requests.ConnectionError("boom")
        assert TestGetUsage()._make_api().get_usage(2026, 5, 1) is False

    @patch("custom_components.contact_energy.api.requests.post")
    def test_usage_invalid_json_returns_false(self, mock_post):
        def bad():
            raise ValueError("not json")

        mock_post.return_value = MagicMock(status_code=200, json=bad)
        assert TestGetUsage()._make_api().get_usage(2026, 5, 1) is False

    @patch("custom_components.contact_energy.api.requests.post")
    def test_usage_without_known_account_does_not_call_api(self, mock_post, api):
        assert api.get_usage(2026, 5, 1) is False
        mock_post.assert_not_called()

    @pytest.mark.parametrize("status", [401, 403])
    @patch("custom_components.contact_energy.api.requests.post")
    def test_rejected_token_is_cleared_so_caller_logs_in_again(self, mock_post, status):
        mock_post.return_value = MagicMock(status_code=status)
        api = TestGetUsage()._make_api()

        assert api.get_usage(2026, 5, 1) is False
        assert api._api_token == ""

    @patch("custom_components.contact_energy.api.requests.post")
    def test_server_error_keeps_the_token(self, mock_post):
        mock_post.return_value = MagicMock(status_code=500)
        api = TestGetUsage()._make_api()

        api.get_usage(2026, 5, 1)

        assert api._api_token == "token"

    @patch("custom_components.contact_energy.api.requests.post")
    def test_network_error_text_is_not_logged(self, mock_post, api, caplog):
        import requests

        mock_post.side_effect = requests.ConnectionError("https://secret-url/?ba=123")
        api.login()

        assert "secret-url" not in caplog.text

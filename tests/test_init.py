"""Tests for integration setup, options reload and unload."""

from unittest.mock import AsyncMock, MagicMock

from custom_components.contact_energy import (
    PLATFORMS,
    _async_update_listener,
    async_setup_entry,
    async_unload_entry,
)


def _hass():
    hass = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=None)
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    hass.config_entries.async_reload = AsyncMock(return_value=None)
    return hass


async def test_setup_forwards_platforms_and_listens_for_option_changes():
    hass, entry = _hass(), MagicMock()

    assert await async_setup_entry(hass, entry) is True

    hass.config_entries.async_forward_entry_setups.assert_awaited_once_with(
        entry, PLATFORMS
    )
    entry.add_update_listener.assert_called_once_with(_async_update_listener)
    # the listener is removed again when the entry unloads
    entry.async_on_unload.assert_called_once_with(
        entry.add_update_listener.return_value
    )


async def test_changing_options_reloads_the_entry():
    hass, entry = _hass(), MagicMock(entry_id="abc")

    await _async_update_listener(hass, entry)

    hass.config_entries.async_reload.assert_awaited_once_with("abc")


async def test_unload_unloads_the_platforms():
    hass, entry = _hass(), MagicMock()

    assert await async_unload_entry(hass, entry) is True

    hass.config_entries.async_unload_platforms.assert_awaited_once_with(
        entry, PLATFORMS
    )

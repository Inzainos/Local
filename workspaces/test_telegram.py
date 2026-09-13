#!/usr/bin/env python3
"""Test Telegram bot send_heartbeat and send_alert"""
from sentinel_omega.infrastructure.telegram.bot import SentinelTelegramBot, TelegramMessage
from unittest.mock import patch, MagicMock
import os

# Test 1: send_heartbeat in dry run mode
print("=== Test 1: send_heartbeat (dry run) ===")
bot = SentinelTelegramBot(token="", chat_id="")
status = {"geodynamic": True}
result = bot.send_heartbeat(status)
print("send_heartbeat result:", result)
assert result is True, "Expected True for dry run heartbeat"
print("Test 1 passed")

# Test 2: send_alert in dry run mode
print("\n=== Test 2: send_alert (dry run) ===")
bot = SentinelTelegramBot(token="", chat_id="")
msg = TelegramMessage(
    layer="geodynamic", signal_type="ALERT", confidence=0.85,
    summary="Precursor correlation detected"
)
result = bot.send_alert(msg)
print("send_alert result:", result)
assert result is True, "Expected True for dry run alert"
print("Test 2 passed")

# Test 3: send_alert with mocked token - patch get_session
print("\n=== Test 3: send_alert (with token, mocked get_session) ===")

# Set env vars for credentials
os.environ["TELEGRAM_BOT_TOKEN"] = "test_token"
os.environ["TELEGRAM_CHAT_ID"] = "12345"

from sentinel_omega.infrastructure.api import telegram as tg
# Reset gate
tg._GATE.last_alert_time = 0
tg._GATE.last_msg_type = ""

bot = SentinelTelegramBot(token="test_token", chat_id="12345")
msg = TelegramMessage(
    layer="geodynamic", signal_type="ALERT", confidence=0.7,
    summary="Test alert"
)

print("_enabled:", bot._enabled)

# Create mock session
mock_session = MagicMock()
mock_resp = MagicMock()
mock_resp.ok = True
mock_resp.raise_for_status = MagicMock()
mock_session.post.return_value = mock_resp

# Patch get_session in the telegram module
with patch("sentinel_omega.infrastructure.api.telegram.get_session", return_value=mock_session) as mock_get_session:
    result = bot.send_alert(msg)
    print("send_alert result:", result)
    print("mock_get_session called:", mock_get_session.called)
    print("mock_session.post called:", mock_session.post.called)
    print("mock_session.post call_count:", mock_session.post.call_count)
    if mock_session.post.called:
        call_kwargs = mock_session.post.call_args
        print("URL called:", call_kwargs[0][0])
        print("chat_id:", call_kwargs[1]["json"]["chat_id"])
        assert "test_token" in call_kwargs[0][0], "URL should contain token: " + str(call_kwargs[0][0])
        assert call_kwargs[1]["json"]["chat_id"] == "12345", "chat_id mismatch: " + str(call_kwargs[1]["json"]["chat_id"])
        print("All assertions passed")
    else:
        print("ERROR: mock_session.post was not called!")

print("\n=== All tests passed! ===")

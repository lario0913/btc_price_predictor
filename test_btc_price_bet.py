"""
Tests for BTCPriceBet Intelligent Contract
Run with: pytest test_btc_price_bet.py -v
"""

import pytest
from unittest.mock import patch, MagicMock
from btc_price_bet import BTCPriceBet


# ── Helpers ────────────────────────────────────────────────────────────────────

THRESHOLD = 70_000
STAKE_GEN = 1
STAKE_WEI = 1 * 10**18

# Addresses stored as plain strings (how GenLayer stores them after str(sender_address))
ADDR_HIGH  = "0xAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
ADDR_LOW   = "0xBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB"
ADDR_THIRD = "0xCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC"

COINDESK_ABOVE = '{"bpi": {"USD": {"rate": "75,000.00"}}}'  # $75k → HIGH wins
COINDESK_BELOW = '{"bpi": {"USD": {"rate": "60,000.00"}}}'  # $60k → LOW wins


def make_contract(threshold=THRESHOLD, stake_gen=STAKE_GEN):
    return BTCPriceBet(threshold, stake_gen)


def join_both(contract, addr_high=ADDR_HIGH, addr_low=ADDR_LOW):
    """Join both sides. Patches sender_address (not sender) per the fixed contract."""
    with patch("genlayer.gl.message") as msg:
        msg.sender_address = addr_high   # ← sender_address, not sender
        msg.value          = STAKE_WEI
        contract.join("high")

    with patch("genlayer.gl.message") as msg:
        msg.sender_address = addr_low
        msg.value          = STAKE_WEI
        contract.join("low")


# ── Constructor tests ──────────────────────────────────────────────────────────

class TestConstructor:

    def test_valid_deployment(self):
        c = make_contract()
        status = c.get_status()
        assert status["threshold_usd"] == THRESHOLD
        assert status["stake_wei"]     == STAKE_WEI
        # "" sentinel converts to None in get_status()
        assert status["player_high"]   is None
        assert status["player_low"]    is None
        assert status["resolved"]      is False

    def test_zero_threshold_raises(self):
        with pytest.raises(Exception, match="Threshold must be"):
            BTCPriceBet(0, STAKE_GEN)

    def test_negative_threshold_raises(self):
        with pytest.raises(Exception):
            BTCPriceBet(-1, STAKE_GEN)

    def test_zero_stake_raises(self):
        with pytest.raises(Exception, match="Stake must be positive"):
            BTCPriceBet(THRESHOLD, 0)

    def test_internal_sentinel_is_empty_string(self):
        """Storage fields start as "" (not None) — verify the raw state."""
        c = make_contract()
        assert c.player_high == ""
        assert c.player_low  == ""
        assert c.winner      == ""


# ── Join tests ─────────────────────────────────────────────────────────────────

class TestJoin:

    def test_join_high_records_player(self):
        c = make_contract()
        with patch("genlayer.gl.message") as msg:
            msg.sender_address = ADDR_HIGH
            msg.value          = STAKE_WEI
            c.join("high")
        # get_status() returns the str address (or None if "")
        assert c.get_status()["player_high"] == ADDR_HIGH

    def test_join_low_records_player(self):
        c = make_contract()
        with patch("genlayer.gl.message") as msg:
            msg.sender_address = ADDR_LOW
            msg.value          = STAKE_WEI
            c.join("low")
        assert c.get_status()["player_low"] == ADDR_LOW

    def test_wrong_stake_raises(self):
        c = make_contract()
        with pytest.raises(Exception, match="exactly"):
            with patch("genlayer.gl.message") as msg:
                msg.sender_address = ADDR_HIGH
                msg.value          = STAKE_WEI // 2
                c.join("high")

    def test_invalid_side_raises(self):
        c = make_contract()
        with pytest.raises(Exception, match="'high' or 'low'"):
            with patch("genlayer.gl.message") as msg:
                msg.sender_address = ADDR_HIGH
                msg.value          = STAKE_WEI
                c.join("moon")

    def test_duplicate_high_raises(self):
        c = make_contract()
        with patch("genlayer.gl.message") as msg:
            msg.sender_address = ADDR_HIGH
            msg.value          = STAKE_WEI
            c.join("high")
        with pytest.raises(Exception, match="already taken"):
            with patch("genlayer.gl.message") as msg:
                msg.sender_address = ADDR_THIRD
                msg.value          = STAKE_WEI
                c.join("high")

    def test_ready_to_resolve_false_with_one_player(self):
        c = make_contract()
        with patch("genlayer.gl.message") as msg:
            msg.sender_address = ADDR_HIGH
            msg.value          = STAKE_WEI
            c.join("high")
        assert c.get_status()["ready_to_resolve"] is False

    def test_ready_to_resolve_true_with_both_players(self):
        c = make_contract()
        join_both(c)
        assert c.get_status()["ready_to_resolve"] is True


# ── Resolve tests ──────────────────────────────────────────────────────────────

class TestResolve:

    def _resolve_with_price(self, contract, coindesk_json):
        """Helper: patch web fetch + transfer, call resolve(), return mock."""
        mock_proxy = MagicMock()
        with patch("genlayer.gl.nondet.web.get_text", return_value=coindesk_json), \
             patch("genlayer.gl.get_contract_at", return_value=mock_proxy):
            contract.resolve()
        return mock_proxy

    def test_resolve_pays_high_when_above_threshold(self):
        c = make_contract()
        join_both(c)
        mock_proxy = self._resolve_with_price(c, COINDESK_ABOVE)

        status = c.get_status()
        assert status["resolved"]        is True
        assert status["winner"]          == ADDR_HIGH
        assert status["final_price_usd"] == 75_000

        # transfer() called with full pot on "finalized"
        mock_proxy.transfer.assert_called_once_with(
            value=STAKE_WEI * 2, on="finalized"
        )

    def test_resolve_pays_low_when_below_threshold(self):
        c = make_contract()
        join_both(c)
        mock_proxy = self._resolve_with_price(c, COINDESK_BELOW)

        status = c.get_status()
        assert status["resolved"]        is True
        assert status["winner"]          == ADDR_LOW
        assert status["final_price_usd"] == 60_000

        mock_proxy.transfer.assert_called_once_with(
            value=STAKE_WEI * 2, on="finalized"
        )

    def test_resolve_fails_without_both_players(self):
        c = make_contract()
        with patch("genlayer.gl.message") as msg:
            msg.sender_address = ADDR_HIGH
            msg.value          = STAKE_WEI
            c.join("high")
        with pytest.raises(Exception, match="Both players must join"):
            c.resolve()

    def test_double_resolve_raises(self):
        c = make_contract()
        join_both(c)
        self._resolve_with_price(c, COINDESK_ABOVE)
        with pytest.raises(Exception, match="Already resolved"):
            c.resolve()

    def test_join_after_resolve_raises(self):
        c = make_contract()
        join_both(c)
        self._resolve_with_price(c, COINDESK_ABOVE)
        with pytest.raises(Exception, match="already resolved"):
            with patch("genlayer.gl.message") as msg:
                msg.sender_address = ADDR_THIRD
                msg.value          = STAKE_WEI
                c.join("high")

    def test_exact_threshold_goes_to_low(self):
        """Price exactly at threshold is not above — low player wins."""
        c = make_contract(threshold=75_000)
        join_both(c)
        coindesk_exact = '{"bpi": {"USD": {"rate": "75,000.00"}}}'
        self._resolve_with_price(c, coindesk_exact)
        assert c.get_status()["winner"] == ADDR_LOW

    def test_winner_stored_as_string(self):
        """winner is stored as a str in storage, not an Address object."""
        c = make_contract()
        join_both(c)
        self._resolve_with_price(c, COINDESK_ABOVE)
        assert isinstance(c.winner, str)
        assert c.winner == ADDR_HIGH

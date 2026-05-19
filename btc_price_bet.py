# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *
import json

# ─────────────────────────────────────────────
#  BTC Price Bet — 2-player Intelligent Contract
#
#  How it works:
#   1. Creator deploys with a price threshold and a stake amount.
#   2. Player A calls join("high") + sends stake  → bets BTC > threshold
#   3. Player B calls join("low")  + sends stake  → bets BTC < threshold
#   4. Anyone calls resolve() once both players are in.
#      The contract fetches the live BTC price, decides the winner,
#      and sends the full pot to them.
# ─────────────────────────────────────────────

class BTCPriceBet(gl.Contract):

    # ── State ──────────────────────────────────────────────────────────
    threshold:   u256          # price boundary in USD (whole dollars)
    stake:       u256          # GEN wei each player must send
    player_high: Address | None   # bets BTC > threshold
    player_low:  Address | None   # bets BTC < threshold
    resolved:    bool          # prevents double-resolution
    winner:      Address | None   # set after resolution
    final_price: u256          # BTC price recorded at resolution

    # ── Constructor ────────────────────────────────────────────────────
    def __init__(self, threshold_usd: int, stake_gen: int) -> None:
        """
        Deploy the bet.

        Args:
            threshold_usd: The BTC price boundary in whole USD.
                           e.g. 70000 means the bet is "above or below $70,000"
            stake_gen:     How many GEN (not wei) each player must stake.
                           e.g. 1 means each player sends 1 GEN (= 10^18 wei)
        """
        if threshold_usd <= 0:
            raise Exception("Threshold must be a positive USD price")
        if stake_gen <= 0:
            raise Exception("Stake must be positive")

        # Store stake internally as wei (1 GEN = 10^18 wei)
        self.threshold   = u256(threshold_usd)
        self.stake       = u256(stake_gen) * u256(10 ** 18)
        self.player_high = None
        self.player_low  = None
        self.resolved    = False
        self.winner      = None
        self.final_price = u256(0)

    # ── Join ───────────────────────────────────────────────────────────
    @gl.public.write.payable
    def join(self, side: str) -> None:
        """
        Join the bet by picking a side and sending the exact stake.

        Args:
            side: "high"  → you bet BTC will be ABOVE threshold at resolution
                  "low"   → you bet BTC will be BELOW threshold at resolution
        """
        if self.resolved:
            raise Exception("Bet is already resolved")

        if side not in ("high", "low"):
            raise Exception("Side must be 'high' or 'low'")

        if gl.message.value != self.stake:
            raise Exception(
                f"You must send exactly {self.stake} wei "
                f"({self.stake // u256(10**18)} GEN)"
            )

        if side == "high":
            if self.player_high is not None:
                raise Exception("The 'high' side is already taken")
            self.player_high = gl.message.sender
        else:
            if self.player_low is not None:
                raise Exception("The 'low' side is already taken")
            self.player_low = gl.message.sender

    # ── Resolve ────────────────────────────────────────────────────────
    @gl.public.write
    def resolve(self) -> None:
        """
        Fetch the live BTC price and pay out the winner.
        Can be called by anyone once both players have joined.
        """
        if self.resolved:
            raise Exception("Already resolved")
        if self.player_high is None or self.player_low is None:
            raise Exception("Both players must join before resolving")

        # ── Non-deterministic block ────────────────────────────────────
        # The leader fetches the price; each validator independently
        # fetches it too and checks the result is within 1% tolerance.
        # State writes happen AFTER this block returns.

        threshold = int(self.threshold)   # capture for closure

        def leader_fn():
            raw = gl.nondet.web.get_text(
                "https://api.coindesk.com/v1/bpi/currentprice.json"
            )
            data = json.loads(raw)
            # CoinDesk returns the rate as a string like "65,432.10"
            rate_str = data["bpi"]["USD"]["rate"].replace(",", "")
            price = float(rate_str)
            above = price > threshold
            return {"price": price, "above": above}

        def validator_fn(leaders_res) -> bool:
            if not isinstance(leaders_res, gl.vm.Return):
                return False
            my_result = leader_fn()
            leader_price = leaders_res.calldata["price"]
            my_price     = my_result["price"]
            # Accept if prices differ by at most 1% (market moves fast)
            price_ok = abs(leader_price - my_price) / leader_price <= 0.01
            # The "above/below" decision must match exactly
            decision_ok = leaders_res.calldata["above"] == my_result["above"]
            return price_ok and decision_ok

        result = gl.vm.run_nondet_unsafe(leader_fn, validator_fn)

        # ── Deterministic: write state + send funds ────────────────────
        self.resolved    = True
        self.final_price = u256(int(result["price"]))

        winner = self.player_high if result["above"] else self.player_low
        self.winner = winner

        # Send the full pot (both stakes) to the winner
        pot = self.stake * u256(2)
        gl.get_contract_at(winner).emit_transfer(value=pot, on="finalized")

    # ── Views ──────────────────────────────────────────────────────────
    @gl.public.view
    def get_status(self) -> dict:
        """Returns the full current state of the bet."""
        return {
            "threshold_usd": int(self.threshold),
            "stake_wei":     int(self.stake),
            "player_high":   str(self.player_high) if self.player_high else None,
            "player_low":    str(self.player_low)  if self.player_low  else None,
            "resolved":      self.resolved,
            "winner":        str(self.winner)      if self.winner      else None,
            "final_price":   int(self.final_price),
            "ready_to_resolve": (
                self.player_high is not None and
                self.player_low  is not None and
                not self.resolved
            )
        }

    @gl.public.view
    def get_threshold(self) -> int:
        return int(self.threshold)

    @gl.public.view
    def get_stake_wei(self) -> int:
        return int(self.stake)

# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *
import json

class BTCPriceBet(gl.Contract):

    # Address | None is NOT supported in GenLayer storage.
    # Use str with "" as the "not set" sentinel instead.
    threshold:   u256
    stake:       u256
    player_high: str    # "" means not joined yet
    player_low:  str    # "" means not joined yet
    resolved:    bool
    winner:      str    # "" before resolution
    final_price: u256

    def __init__(self, threshold_usd: int, stake_gen: int) -> None:
        if threshold_usd <= 0:
            raise gl.vm.UserError("Threshold must be a positive USD price")
        if stake_gen <= 0:
            raise gl.vm.UserError("Stake must be positive")

        self.threshold   = u256(threshold_usd)
        self.stake       = u256(stake_gen) * u256(10 ** 18)
        self.player_high = ""
        self.player_low  = ""
        self.resolved    = False
        self.winner      = ""
        self.final_price = u256(0)

    @gl.public.write.payable
    def join(self, side: str) -> None:
        if self.resolved:
            raise gl.vm.UserError("Bet is already resolved")
        if side not in ("high", "low"):
            raise gl.vm.UserError("side must be 'high' or 'low'")
        if gl.message.value != self.stake:
            raise gl.vm.UserError(
                f"Send exactly {int(self.stake)} wei "
                f"({int(self.stake) // (10**18)} GEN)"
            )

        sender = str(gl.message.sender_address)

        if side == "high":
            if self.player_high != "":
                raise gl.vm.UserError("'high' side is already taken")
            self.player_high = sender
        else:
            if self.player_low != "":
                raise gl.vm.UserError("'low' side is already taken")
            self.player_low = sender

    @gl.public.write
    def resolve(self) -> None:
        if self.resolved:
            raise gl.vm.UserError("Already resolved")
        if self.player_high == "" or self.player_low == "":
            raise gl.vm.UserError("Both players must join before resolving")

        threshold = int(self.threshold)

        def leader_fn():
            raw = gl.nondet.web.get_text(
                "https://api.coindesk.com/v1/bpi/currentprice.json"
            )
            data = json.loads(raw)
            price = float(data["bpi"]["USD"]["rate"].replace(",", ""))
            return {"price": price, "above": price > threshold}

        def validator_fn(leaders_res) -> bool:
            if not isinstance(leaders_res, gl.vm.Return):
                return False
            my_result    = leader_fn()
            leader_price = leaders_res.calldata["price"]
            my_price     = my_result["price"]
            price_ok     = abs(leader_price - my_price) / leader_price <= 0.01
            decision_ok  = leaders_res.calldata["above"] == my_result["above"]
            return price_ok and decision_ok

        result = gl.vm.run_nondet_unsafe(leader_fn, validator_fn)

        self.resolved    = True
        self.final_price = u256(int(result["price"]))
        self.winner      = self.player_high if result["above"] else self.player_low

        pot         = self.stake * u256(2)
        winner_addr = Address(self.winner)
        gl.get_contract_at(winner_addr).transfer(value=pot, on="finalized")

    @gl.public.view
    def get_status(self) -> dict:
        return {
            "threshold_usd":    int(self.threshold),
            "stake_wei":        int(self.stake),
            "player_high":      self.player_high or None,
            "player_low":       self.player_low  or None,
            "resolved":         self.resolved,
            "winner":           self.winner       or None,
            "final_price_usd":  int(self.final_price),
            "ready_to_resolve": (
                self.player_high != "" and
                self.player_low  != "" and
                not self.resolved
            ),
        }

    @gl.public.view
    def get_threshold(self) -> int:
        return int(self.threshold)

    @gl.public.view
    def get_stake_wei(self) -> int:
        return int(self.stake)
        
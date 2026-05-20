# BTC Price Bet — GenLayer Intelligent Contract

A trustless 2-player Bitcoin price bet built on [GenLayer](https://genlayer.com). Two players lock stakes on-chain and bet whether BTC will be above or below a price threshold. At resolution, the contract fetches the live BTC price directly from the web — no oracle, no third party — and pays the winner automatically.

Built as a companion to the Medium article: **[Building a Trustless BTC Price Bet on GenLayer](YOUR_MEDIUM_LINK_HERE)**

---

## How It Works

```
Player A  ──join("high")──►  Contract  ◄──join("low")──  Player B
                                  │
                             resolve()
                                  │
                    gl.nondet.web.get_text(CoinDesk API)
                                  │
                        Validators reach consensus
                                  │
                    Winner receives full pot (2x stake)
```

1. **Deploy** — set a price threshold (e.g. `$70,000`) and stake amount (e.g. `1 GEN`)
2. **Player A** calls `join("high")` + sends stake → bets BTC will be **above** the threshold
3. **Player B** calls `join("low")` + sends stake → bets BTC will be **below** the threshold
4. **Anyone** calls `resolve()` — the contract fetches the live BTC price, reaches consensus across validators, and pays the winner

---

## What Makes This Interesting

Traditional smart contracts can't fetch live data without a trusted oracle. GenLayer solves this with **Intelligent Contracts** — the `resolve()` method uses `gl.nondet.web.get_text()` to fetch the BTC price directly on-chain. Each validator node independently fetches the price and checks the leader's result against a custom **Equivalence Principle**:

- Prices must be within **1%** of each other (accounts for market movement between fetches)
- The above/below **decision must match exactly** — this is the binding outcome

This is the `leader_fn` / `validator_fn` / `gl.vm.run_nondet_unsafe` pattern at the core of GenLayer development.

---

## Project Structure

```
btc-price-bet/
├── btc_price_bet.py       # The Intelligent Contract
├── test_btc_price_bet.py  # Pytest test suite
└── README.md
```

---

## Getting Started

### Option A — GenLayer Studio (recommended for beginners)

1. Open [studio.genlayer.com](https://studio.genlayer.com/contracts)
2. Create a new file and paste the contents of `btc_price_bet.py`
3. Click **Deploy** and enter constructor args:
   - `threshold_usd`: e.g. `70000`
   - `stake_gen`: e.g. `1`
4. Use the 💧 faucet to fund two test accounts

### Option B — CLI

```bash
pip install genlayer
genlayer init btc-price-bet
cd btc-price-bet
genlayer up
```

---

## Playing the Bet

### Step 1 — Player A joins

Switch to Account 1 in the Studio. Call `join` with:
- `side`: `"high"`
- value: `1000000000000000000` (= 1 GEN in wei)

### Step 2 — Player B joins

Switch to Account 2. Call `join` with:
- `side`: `"low"`
- value: `1000000000000000000`

### Step 3 — Check status

Call `get_status()` — you should see `ready_to_resolve: true`.

### Step 4 — Resolve

Call `resolve()` from either account (no value needed). Watch the logs as validators fetch the price and reach consensus.

---

## Contract API

| Method | Type | Description |
|---|---|---|
| `__init__(threshold_usd, stake_gen)` | Constructor | Deploy with price boundary and stake per player |
| `join(side)` | `write.payable` | Join with `"high"` or `"low"`, send exact stake |
| `resolve()` | `write` | Fetch price, settle bet, pay winner |
| `get_status()` | `view` | Full contract state as a dict |
| `get_threshold()` | `view` | Price threshold in USD |
| `get_stake_wei()` | `view` | Stake amount in wei |

---

## Running the Tests

```bash
pip install pytest
pytest test_btc_price_bet.py -v
```

---

## Key GenLayer Concepts Demonstrated

- `@gl.public.write.payable` — accepting GEN with a transaction
- `gl.message.value` / `gl.message.sender_address` — transaction context
- `gl.nondet.web.get_text(url)` — fetching live web data on-chain
- `gl.vm.run_nondet_unsafe(leader_fn, validator_fn)` — custom equivalence principle
- `gl.vm.UserError` — clean transaction reverts
- `gl.get_contract_at(Address).transfer(value, on)` — sending GEN to a winner
- `str` with `""` sentinel — the correct pattern for optional address storage

---

## Important SDK Gotchas

**`Address | None` is not supported in storage**
GenLayer's storage engine cannot handle nullable union types. Use `str` with `""` as a sentinel value instead.

**Read storage before entering nondet blocks**
`self.*` fields are inaccessible inside `leader_fn` and `validator_fn`. Capture any state you need as a plain Python variable before the block.

**Use `gl.vm.UserError`, not `raise Exception`**
Bare exceptions are flagged by the GenLayer linter (W004) and don't surface cleanly to callers.

---

## Resources

- [GenLayer Documentation](https://docs.genlayer.com)
- [GenLayer Studio](https://studio.genlayer.com)
- [GenLayer SDK Reference](https://sdk.genlayer.com)
- [Medium Article](YOUR_MEDIUM_LINK_HERE)

---

## License

MIT

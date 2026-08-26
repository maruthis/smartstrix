---
name: solidity_amm
description: Security testing for Solidity AMM, liquidity-pool, and swap contracts — reentrancy, donation/inflation, oracle manipulation, slippage, and admin controls
---

# Solidity AMM

Testing automated market makers, LP vaults, and swap routers. Focus on reentrancy, share math that trusts `balanceOf(address(this))`, manipulable oracles, missing slippage/deadlines, and privileged admin paths.

Use when the repo contains Solidity (or Vyper) pool/swap/vault code. This is not a full-chain audit skill — pair with dynamic tests (`forge test`, Echidna, or a fork) before filing.

## Attack Surface

**Entrypoints**
- `swap`, `deposit` / `mint`, `withdraw` / `burn`, `flash` / `flashLoan`
- `setFee`, `pause`, `setOracle`, `skim`, `sync`, `rescueTokens`
- Callbacks: `uniswapV2Call`, `uniswapV3SwapCallback`, ERC-777/ERC-1155 hooks

**Accounting**
- Reserves vs `token.balanceOf(address(this))`
- Share / LP token math (`totalSupply`, `totalAssets`)
- Fee-on-transfer and rebasing tokens

**Pricing**
- Spot `slot0` / `getReserves` used as an oracle
- TWAP / Chainlink / custom oracles
- Slippage params: `amountOutMin`, `sqrtPriceLimitX96`, `deadline`

## High-Value Targets

- First depositor / inflation attack on empty vaults
- Reentrancy on ERC-777 / ERC-1155 / callback tokens before CEI
- `skim` / `sync` that desync reserves from balances
- Owner `setFee` / `setOracle` / `withdraw` without 2-step ownership
- Routers that accept an attacker-controlled pool path
- Missing `deadline` on swaps (stuck pending tx / MEV)

## Reconnaissance

```
*.sol  lib/  src/  contracts/
function swap  function deposit  function mint  function burn
balanceOf(address(this))
onlyOwner  Ownable  AccessControl
observe(  slot0  getReserves
nonReentrant  ReentrancyGuard
```

Read the token assumptions (standard ERC-20 vs fee-on-transfer vs rebasing vs ERC-777).

## Key Vulnerabilities

### Reentrancy

- External token call (`transfer` / `call`) before updating shares/reserves
- Read-only reentrancy: view functions used by other protocols during the callback
- Missing `nonReentrant` on swap + deposit sharing state

**Prove:** callback token or attacker contract re-enters `deposit`/`swap` and mints extra shares or drains reserves.

### Donation / inflation

- `shares = assets * totalShares / token.balanceOf(this)` lets an attacker donate tokens (or take the first tiny deposit, donate a huge amount, then dilute the victim)
- Safe pattern: internal `_totalAssets`, measure `balance after - balance before` on transferFrom

**Prove:** attacker profit after donate + victim deposit, or first-depositor theft.

### Oracle / price manipulation

- Spot price from the same pool the attacker is swapping in (flash-loanable)
- Stale Chainlink round, missing heartbeat / `answeredInRound` checks
- Using a low-liquidity pool as the oracle for a high-value vault

**Prove:** flash swap moves spot, victim action (liquidate, mint, borrow) executes at the manipulated price.

### Slippage and MEV

- Swap without `amountOutMin` / `minShares` / deadline
- Router `to` parameter pointing at attacker
- Unprotected `approve` + swap path (approval phishing / unlimited allowance)

### Admin and tokens

- `Ownable` (single-step) vs `Ownable2Step`
- `rescueTokens` that can steal LP balances
- `safeTransfer` not used — tokens that return `false` silently fail
- Fee-on-transfer: accounting assumes `amountIn` credited in full

## Testing Methodology

1. List every state-changing function and its token/callback assumptions
2. Check CEI + `nonReentrant` on each
3. Unit-test empty-vault deposit and donate-then-deposit
4. Fork-test a flash-loan price move against oracle reads
5. Swap with zero `amountOutMin` and a sandwich
6. Review admin functions for rug / pause / oracle replacement
7. Run Slither + fuzz (`forge test --fuzz-runs` / Echidna) on share math

## Validation

- A concrete transaction sequence (foundry test or fork script) that extracts value or breaks invariance (`k`, share/asset backing)
- Not just "missing ReentrancyGuard" — show the reenter path or explain why the token callback exists
- Redact private keys; use throwaway anvil/fork accounts

## False Positives

- View-only contracts with no funds
- Guards present and CEI respected; token is plain ERC-20 with no callback
- Oracle is a manipulation-resistant TWAP / Chainlink with heartbeat checks
- Test/mock pools not deployed

## Impact

- Direct drain of pool / vault assets
- Silent share dilution of LPs
- Bad liquidations and protocol insolvency via oracle manipulation
- Admin rug or frozen funds

## Pro Tips

1. ERC-777/1155 hooks are the reentrancy that `nonReentrant` on *one* function misses if another entrypoint is unlocked
2. First-deposit inflation is still landing on new vaults — always test `totalSupply == 0`
3. If they use `balanceOf(this)` anywhere in share math, treat it as a finding until internal accounting is proven
4. Pair with `llm_prompt_injection` if an agent can sign swaps (spend limits live outside the model)

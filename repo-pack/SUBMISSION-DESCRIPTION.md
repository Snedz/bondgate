# BondGate — submission description

*Final text for the worldisflat.fun/build project form. The contract is
deployed and the demo cycles ran on Robinhood Chain mainnet on 2026-11-12;
every link below is real. Repo, video and live-link lines are filled at
submission time.*

---

**Project name:** BondGate

**Cover image:** `bondgate-cover.png` (in this repo-pack folder — upload it wherever the form asks for a project image/thumbnail; generated Nov 12, no text, no third-party branding)

**One-liner:** An onchain approval gate for AI agents — an agent posts a
$WIF bond against the hash of an action it intends to take, and a
deterministic policy gate settles the bond with a verdict anyone can
recompute.

**Categories:** agents and ai · tools and infra

**Team:** Mission Winning (solo) — X: [PLACEHOLDER — founder to confirm handle]

**Repo:** [PLACEHOLDER — public repo URL, created at submission time]

**Demo video:** [PLACEHOLDER — video URL, recorded after deploy]

**Live link:** [PLACEHOLDER — demo page URL, after hosting]

**Onchain proof (Blockscout):**
- Contract: [0x56c43d2F731Db72652125d84e50164c025ba7DAF](https://robinhoodchain.blockscout.com/address/0x56c43d2F731Db72652125d84e50164c025ba7DAF) — deployed 2026-11-12, [deploy tx](https://robinhoodchain.blockscout.com/tx/0x98fefd2bf42aaa0c4af47fccc02d1b00a2d3f7d4d40c07b3b5120c00868cc5b7)
- $WIF acquired on the live Uniswap V4 pool (Pons hook): [swap tx](https://robinhoodchain.blockscout.com/tx/0xfa3935f2cd0c94c9172c55948a46ebd2577ee206eea6b5ffbe71acb7bb6f0f63) — 0.001 ETH → 1602.18 $WIF
- Scenario A (clean approve, 100 $WIF bond released): [bond](https://robinhoodchain.blockscout.com/tx/0x7869b9826ba2a925e816f3bd303e131910850978087a022c539529be8264c55f) · [settle](https://robinhoodchain.blockscout.com/tx/0xbb144f42fdaa32630eeba396d91b6f9dbd4b115b3ed9d667e11a527a90276e6d)
- Scenario B (tamper → unsafe, 100 $WIF locked 7 days): [bond](https://robinhoodchain.blockscout.com/tx/0x2e570310b74e92bf6b10e7cff3748bb01a66addc9b98abfc802bde0c639e9792) · [settle](https://robinhoodchain.blockscout.com/tx/0x6215fc832e8080c4836ab9b7e82c3f35b4ba1e0a812a0fed71a3f0708fc716fc)
- Scenario C (policy reject, 500 $WIF forfeited to pool): [bond](https://robinhoodchain.blockscout.com/tx/0x49b07d3bea6fc67a23b1cd681fb1c8ddf8bd7fd34f5f082e9fa14cdd32319bbe) · [settle](https://robinhoodchain.blockscout.com/tx/0xd261a176e8854ff15556f767843ab6c9cce84ad8a24102f9c00a5f2a2b4d766a)
- Flywheel leg (150 $WIF clean-streak reward from the forfeit pool): [payout](https://robinhoodchain.blockscout.com/tx/0x02ffffb3dcb01b5d06da45a13f9e7373cc063aa40162adfcb402de760ee29dee)
- Receipts anchored: 3 (hash-chained, verifiable offline); forfeit pool balance after demo: 350 $WIF

## About — what it does

An AI agent that wants to take a real action first posts a $WIF bond on
Robinhood Chain and submits the action's payload, hash-bound at queue time.
A deterministic policy gate — an 8-class policy table, no LLM in the
decision path — evaluates the action class and re-verifies the payload hash
at execution time.

- **Approved** → the action executes and the bond is released.
- **Policy-rejected** → the bond is forfeited to a pool.
- **Tampered** (payload differs from its bound hash) → the bond is locked
  for a seven-day evidence window, then forfeitable.
- A bond the operator never settles becomes reclaimable by the agent after
  the settle window, so no bond can be stranded by silence.

Every settlement anchors a receipt hash that chains to the previous
receipt, so the bond trail is a public, tamper-evident track record for
the agent.

**The verdict is the product.** A BondGate verdict is a pure function of
the hash-bound payload and a published policy table — anyone can recompute
it offline and prove a wrong settlement from the receipt chain. BondGate
sells verifiable operation, not trustless operation: the operator runs the
gate, but cannot plausibly lie about what the gate decided.

**Why $WIF:** during this event, $WIF's utility in BondGate is the
bond-escrow unit plus the event's own community-vote burn (votes burn
$WIF — a sink the chain already runs), and the forfeit pool is a
misbehavior premium, not a yield engine.

## How this differs from job escrow (e.g. PACT)

PACT, another entry in this event, also bonds agents in $WIF — a worker
bond of 50% of the job price, hash-bound terms, escrowed payment.
BondGate claims no first there. The difference is what is being gated and
who decides:

- PACT gates *payment for work already hired*; BondGate gates *permission
  to act at all*, before the action executes.
- PACT settles by employer approval, silence, or a human resolver. In
  PACT's own words: "It cannot judge the work. A ruling decides who gets
  the money, not whether the work was good." A resolver's ruling cannot
  be recomputed by anyone; a BondGate verdict can, bit for bit.
- PACT binds terms and proofs by hash but has no verdict for "the payload
  changed between approval and execution." BondGate's `unsafe` class
  exists exactly for that.
- PACT's registry holds counters of finished things; BondGate anchors a
  hash-chained receipt per decision, so the record is tamper-evident as a
  sequence, not just a tally.

## The contract

One small self-contained Solidity contract (`WifBondGate.sol`, no imports
beyond an inline IERC20 interface). Token and operator are immutable.
There is no upgradeability, no mint, no pause, no blacklist, and no admin
withdrawal: no path moves an active escrowed bond except the settlement
and reclaim paths, and pool payouts read only the forfeit-pool balance,
so active escrow is structurally unreachable by the payout path. Bonds
are per-action — one action's settlement can never touch another action's
escrow.

Bond sizes are runner parameters, not protocol constants: the demo table
(write-tier 100 $WIF, gate-tier 500 $WIF) is sized so the full demo —
deploy, bonds, settlements, pool payout — runs end-to-end on a ~$10
float. In production the same table sizes bonds to the value of the
action being gated.

## Honesty lines

- This contract is an unaudited hackathon prototype. It has not been
  reviewed, fuzzed, or audited, and it holds real value the moment it is
  funded. Fresh wallet, trivial float only.
- Receipts in the current schema do not yet cite the policy-table hash
  behind each verdict; policy-hash anchoring is the first post-submission
  change on the roadmap, runner-only, no redeploy.
- The gate is operated: settlement transactions are sent by the
  operator's wallet. What is verifiable is the verdict and the receipt
  chain — that is the claim, and it is the whole claim.

## Chain facts

| Fact | Value |
| --- | --- |
| Network | Robinhood Chain mainnet |
| Chain ID | `4663` |
| RPC | `https://rpc.mainnet.chain.robinhood.com` |
| Explorer | `https://robinhoodchain.blockscout.com` (Blockscout) |
| $WIF token | `0x5173b8ea6923c2d40267890d45c46a3480954773` |

The $WIF address is the contract worldisflat.fun itself links to via its
Pons launchpad page — verified there, not inferred from a ticker search.

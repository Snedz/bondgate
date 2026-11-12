# BondGate — an onchain approval gate for AI agents

![BondGate logo](bondgate-logo.png)

An agent that wants to take a real action first posts a **$WIF bond** on
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

Every settlement anchors a receipt hash that chains to the previous receipt,
so the bond trail is a public, tamper-evident track record for the agent.

**The verdict is the product.** A BondGate verdict is a pure function of the
hash-bound payload and a published policy table — anyone can recompute it
offline and prove a wrong settlement from the receipt chain. BondGate sells
verifiable operation, not trustless operation: the operator runs the gate,
but cannot plausibly lie about what the gate decided.

Built for the **World is Flat** hackathon (worldisflat.fun/build). Team:
**Mission Winning** (solo). Categories: agents and ai · tools and infra.

## Live proof (Robinhood Chain mainnet, chain ID 4663)

- **Contract:** [`0x56c43d2F731Db72652125d84e50164c025ba7DAF`](https://robinhoodchain.blockscout.com/address/0x56c43d2F731Db72652125d84e50164c025ba7DAF)
  — deployed 2026-11-12
  ([deploy tx](https://robinhoodchain.blockscout.com/tx/0x98fefd2bf42aaa0c4af47fccc02d1b00a2d3f7d4d40c07b3b5120c00868cc5b7))
- **$WIF token:** [`0x5173b8ea6923c2d40267890d45c46a3480954773`](https://robinhoodchain.blockscout.com/address/0x5173b8ea6923c2d40267890d45c46a3480954773)
  (the contract worldisflat.fun itself links to via its Pons launchpad page)
- **Demo cycles** (all on mainnet, 2026-11-12):
  - Scenario A — clean approve, 100 $WIF released:
    [bond](https://robinhoodchain.blockscout.com/tx/0x7869b9826ba2a925e816f3bd303e131910850978087a022c539529be8264c55f) ·
    [settle](https://robinhoodchain.blockscout.com/tx/0xbb144f42fdaa32630eeba396d91b6f9dbd4b115b3ed9d667e11a527a90276e6d)
  - Scenario B — tamper → unsafe, 100 $WIF locked 7 days:
    [bond](https://robinhoodchain.blockscout.com/tx/0x2e570310b74e92bf6b10e7cff3748bb01a66addc9b98abfc802bde0c639e9792) ·
    [settle](https://robinhoodchain.blockscout.com/tx/0x6215fc832e8080c4836ab9b7e82c3f35b4ba1e0a812a0fed71a3f0708fc716fc)
  - Scenario C — policy reject, 500 $WIF forfeited to the pool:
    [bond](https://robinhoodchain.blockscout.com/tx/0x49b07d3bea6fc67a23b1cd681fb1c8ddf8bd7fd34f5f082e9fa14cdd32319bbe) ·
    [settle](https://robinhoodchain.blockscout.com/tx/0xd261a176e8854ff15556f767843ab6c9cce84ad8a24102f9c00a5f2a2b4d766a)
  - Flywheel leg — 150 $WIF clean-streak reward from the forfeit pool:
    [payout](https://robinhoodchain.blockscout.com/tx/0x02ffffb3dcb01b5d06da45a13f9e7373cc063aa40162adfcb402de760ee29dee)
- **Demo page:** `demo/index.html` in this repo (live link on the project
  page; it reads the receipt feed from the public RPC and falls back to the
  last known mainnet receipts if the read fails).
- **Full submission text:** `repo-pack/SUBMISSION-DESCRIPTION.md`
- **Demo video:** see the project page (script in `repo-pack/VIDEO-SCRIPT.md`)

## What is in this repo

- `wif-gate/` — the build: `contracts/WifBondGate.sol` (single
  self-contained contract, no imports beyond an inline IERC20 interface),
  `wif_gate.py` (stdlib-only runner: policy, ABI encoder, receipt chain),
  `tests/` (14 tests: 10 offline + 4 EVM tests against the real compiled
  contract, all passing), `README.md` (runbook).
- `demo/` — the static demo page (`index.html`, no build chain).
- `repo-pack/` — the submission description, the video script, and the
  project cover image.
- `operator/` — the operator scripts that ran the live sequence (swap,
  deploy, demo cycles, placeholder fill). They load the project wallet key
  from a local `project-wallet.env` that is **not** in this repo.
- `build/` — the compiled contract ABI + bytecode.
- `receipts.json` — the three real mainnet receipts (hash-chained).

## Honesty lines

- This contract is an unaudited hackathon prototype. It has not been
  reviewed, fuzzed, or audited, and it holds real value the moment it is
  funded. Fresh wallet, trivial float only.
- The gate is operated: settlement transactions are sent by the operator's
  wallet. What is verifiable is the verdict and the receipt chain — that
  is the claim, and it is the whole claim.
- Receipts in the current schema do not yet cite the policy-table hash
  behind each verdict; policy-hash anchoring is the first post-submission
  change on the roadmap, runner-only, no redeploy.

## Licence

MIT — see `LICENSE`.

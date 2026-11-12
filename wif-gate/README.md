# BondGate — $WIF bonds settled by HashBound policy on Robinhood Chain

BondGate is an onchain approval gate for AI agents. An agent posts a `$WIF`
bond against the hash of an action it intends to take; the operator settles
that bond with the deterministic HashBound verdict for the action. A clean
action gets its bond back, a rejected action forfeits it to a reward pool, and
a tampered action locks it for a seven-day evidence window. A bond the
operator never settles becomes reclaimable by the agent after seven days, so
no bond can be stranded by silence. Every settlement anchors a receipt hash,
so the bond trail and the why-agent evidence trail are the same chain.

The verdict is the product. A BondGate verdict is a pure function of the
hash-bound payload and a published policy table — anyone can recompute it
offline and prove a wrong settlement from the receipt chain. BondGate sells
verifiable operation, not trustless operation: the operator runs the gate,
but cannot plausibly lie about what the gate decided.

## How this differs from job escrow (e.g. PACT)

PACT, another entry in this event, also bonds agents in `$WIF` — a worker
bond of 50% of the job price, hash-bound terms, escrowed payment. BondGate
claims no first there. The difference is what is being gated and who decides:

- PACT gates *payment for work already hired*; BondGate gates *permission
  to act at all*, before the action executes.
- PACT settles by employer approval, silence, or a human resolver. In PACT's
  own words: "It cannot judge the work. A ruling decides who gets the money,
  not whether the work was good." A resolver's ruling cannot be recomputed
  by anyone; a BondGate verdict can, bit for bit.
- PACT binds terms and proofs by hash but has no verdict for "the payload
  changed between approval and execution." BondGate's `unsafe` class exists
  exactly for that.
- PACT's registry holds counters of finished things; BondGate anchors a
  hash-chained receipt per decision, so the record is tamper-evident as a
  sequence, not just a tally.

This package is the EVM half of the fleet's HashBound evidence family: a single
self-contained escrow contract plus a stdlib-only Python model of the policy,
the ABI encoder, and the receipt chain. It runs fully offline; there is no
network, wallet, or funds in this card.

## Verified chain facts

| Fact | Value |
| --- | --- |
| Network | Robinhood Chain mainnet |
| Chain ID | `4663` |
| RPC | `https://rpc.mainnet.chain.robinhood.com` |
| Explorer | `https://robinhoodchain.blockscout.com` (Blockscout) |
| `$WIF` token | `0x5173b8ea6923c2d40267890d45c46a3480954773` |

The `$WIF` address is the contract that `worldisflat.fun` itself links to via
its Pons launchpad page — verified there, not inferred from a ticker search.
It is the only token address this package knows. Do not substitute another
address, and do not bake this one into the contract: `WifBondGate` takes the
token in its constructor, so the same source deploys against a different token
without edits.

## Policy → settlement mapping

`wif_gate.py` mirrors HashBound's 8-class `TOOL_CLASS` table across four tiers:
`read` (`read`, `inspect`), `write` (`write`, `execute`), `gate` (`deploy`,
`transfer`), and `deny` (`secrets`, `delete`). Unknown tools classify as
`deny` — the table is fail-closed.

`verdict_for` is evaluated strictly in this order:

1. payload hash mismatch between the queue-time bound hash and the
   execute-time hash → `unsafe`, regardless of class;
2. `deny` tier → `reject`;
3. otherwise → `approve`.

Gate-tier approval is deliberately outside `verdict_for`: `GateRunner` refuses
to execute a `gate`-tier action at all unless `approved=True` and the approver
is a different party from the proposer (HashBound's proposer ≠ approver rule).
That refusal happens before any chain call is made.

| Verdict | Bond size | Contract code | Settlement |
| --- | --- | --- | --- |
| `approve` | read 0 / write 100 / gate 500 tokens | `0` | bond returned to agent |
| `reject` | deny 0 (refused before bonding) | `1` | bond moved to forfeit pool |
| `unsafe` | as sized for the tier | `2` | bond locked for the 7-day evidence window, then forfeitable |

Bond amounts are computed in base units from the token's `decimals` argument
(`bond_for(tool, decimals)`), never hardcoded. Bond sizes are runner
parameters, not protocol constants: the table above is sized so the full
demo — deploy, bonds, settlements, pool payout — runs end-to-end on a ~$10
float. In production the same table sizes bonds to the value of the action
being gated, the same idea as a proportional bond, expressed as tiers.

## Contract

`contracts/WifBondGate.sol` is a single `pragma solidity ^0.8` file with an
inline `IERC20` interface and no imports. The token and operator are
`immutable`. It exposes:

- `postBond(bytes32 actionHash, uint256 amount)` — `transferFrom` into escrow;
- `settle(bytes32 actionHash, uint8 verdict, bytes32 receiptHash)` —
  operator-only; refund, forfeit, or evidence-window lock;
- `forfeitLocked(bytes32 actionHash)` — operator-only, after the evidence
  window expires;
- `reclaimExpired(bytes32 actionHash)` — permissionless; once the 7-day
  settle window has passed on an unsettled bond, anyone may call it and the
  bond returns to the agent who posted it;
- `distributePool(address to, uint256 amount)` — operator-only, funded only by
  the forfeit pool, never by active escrow;
- `bondOf`, `poolBalance`, `receiptCount` (plus `totalEscrowed`);
- events `BondPosted`, `BondSettled`, `ReceiptAnchored`.

There is no upgradeability, no mint, no pause, no blacklist, and no admin
withdrawal: no path moves an active escrowed bond except the settlement and
reclaim paths above, and `distributePool` reads only `poolBalance`, so
active escrow is structurally unreachable by the payout path. Bonds are
per-action — one action's settlement can never touch another action's
escrow.

## Receipts

`GateRunner.run_cycle(tool, args, context, approved=False)` snapshots and
hash-binds the payload at queue time, evaluates the verdict against the
execute-time payload (pass `execute_args=` to model tampering), calls
`post_bond` then `settle`, and appends a receipt carrying index, tool, action
hash, verdict, bond amount, previous receipt hash, and receipt hash.
`verify_receipt_chain(records)` returns `(ok, first_bad_index)`.

## Demo page (build note)

No demo page exists in this package yet. When it is built, it must treat the
Blockscout links as the durable proof of the demo transactions, and render
last-known receipts behind an explicit RPC-failure state rather than an
empty feed — the public RPC is rate-limited, and the page must not look dead
during judging if a read fails.

## Operator runbook and founder gates

Deployment, funding, and any onchain settlement are operator steps, not engine
steps. The runbook, network checks, and founder gates live in
`~/workspace/world-is-flat/SPEC.md`. Nothing here deploys itself.

## Honesty line

This contract is an unaudited hackathon prototype. Use it only with a fresh
wallet and a trivial float. It has not been reviewed, fuzzed, or audited, and
it holds real value the moment you fund it.

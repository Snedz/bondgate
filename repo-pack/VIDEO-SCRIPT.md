# BondGate — demo video script / outline (DRAFT)

*Draft. Target length < 3 min, per the event rules. The live walkthrough
(0:50–2:00) records only after the contract is deployed and the demo
cycles have run on mainnet — the Blockscout screens it shows do not
exist yet. Timings follow the SPEC §2 outline.*

---

**0:00–0:20 — The problem.**
Agents act with no skin in the game. Approvals happen off the record, and
afterwards nobody can audit what was approved, or prove the thing that
ran is the thing that was approved.

**0:20–0:50 — BondGate in one diagram.**
Bond → hash-bound payload → deterministic gate → receipt. An agent posts
a $WIF bond against the hash of the action it intends to take. The
payload is frozen at queue time. A policy table — eight classes, no LLM
in the decision path — decides. Every decision anchors a hash-chained
receipt onchain.

**0:50–2:00 — Live mainnet walkthrough.** *(Blockscout tx pages on
screen — [PLACEHOLDER: record after deploy])*

- **Scenario A (clean):** agent proposes a write action → bond posted
  (tx link) → policy approves → action executes → bond released
  (tx link) → receipt anchored.
- **Scenario B (tamper):** payload altered after queueing → hash
  mismatch at execute → UNSAFE → bond locked for the seven-day evidence
  window (tx link).
- **Scenario C (policy reject):** a bonded action fails policy → REJECT
  → bond forfeited to the pool (tx link); pool pays a clean-streak
  reward (tx link) — the flywheel, shown, not just claimed.

Narration point to land during the walkthrough: the verdict on screen is
a pure function of the bound payload and a published policy table —
anyone can recompute it offline. BondGate sells verifiable operation,
not trustless operation.

**2:00–2:30 — Why $WIF, and the flywheel.**
During this event, $WIF's utility in BondGate is the bond-escrow unit
plus the event's own community-vote burn, and the forfeit pool is a
misbehavior premium, not a yield engine. Forfeits fund clean-streak
rewards; receipts compound into an onchain reputation history — the bond
is the admission ticket and the track record is the asset. Bond sizes
are runner parameters: this entire demo runs on a ~$10 float.

**2:30–2:50 — What it becomes.**
The receipt module is why-agent's onchain evidence surface, and the
deploy/sign/settle pipeline is the fleet's first EVM lane. Also on the
record: other entries bond agents too — PACT bonds workers at 50% of
job price. BondGate's claim is narrower and checkable: it gates
permission to act, and its verdict — unlike a human resolver's ruling —
can be recomputed bit for bit.

*Production note (not narration): fleet Piper TTS + slides pipeline per
standing practice. Contract header/disclosure on any code screen:
"Unaided hackathon prototype. Unaudited. Use with a fresh wallet and a
trivial float only."*

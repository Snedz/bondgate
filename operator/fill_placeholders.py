"""BondGate Phase 2 — Step 2(d): fill placeholders with real mainnet values.

Reads phase2-state.json + receipts.json, updates demo/index.html
(CONTRACT_ADDRESS, contract card, LAST_KNOWN real receipts, scenarios)
and repo-pack/SUBMISSION-DESCRIPTION.md (contract + Blockscout tx links).
Repo / video / live-link placeholders stay until steps (e)/(f)/hosting.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXPLORER = "https://robinhoodchain.blockscout.com"

s = json.loads((HERE / "phase2-state.json").read_text())
r = json.loads((HERE / "receipts.json").read_text())
contract = s["steps"]["deploy"]["contract"]
deploy_tx = s["steps"]["deploy"]["deploy_tx"]
swap_tx = s["steps"]["swap"]["swap_tx"]
txs = r["txs"]
recs = r["records"]
# tx order: A postBond, A settle, B postBond, B settle, C postBond, C settle, D distribute
A_POST, A_SETTLE, B_POST, B_SETTLE, C_POST, C_SETTLE, D_DIST = txs


def tx_url(h):
    return f"{EXPLORER}/tx/0x{h}"


def must_replace(text, old, new, label):
    assert text.count(old) == 1, f"{label}: expected 1 occurrence, found {text.count(old)}"
    return text.replace(old, new)


# ---------------------------------------------------------------- demo page
p = HERE / "demo" / "index.html"
html = p.read_text()

html = must_replace(html,
    'CONTRACT_ADDRESS: "", // <-- set at deploy; empty = not yet deployed',
    f'CONTRACT_ADDRESS: "{contract}", // deployed 2026-11-12, tx {deploy_tx[:10]}...',
    "contract address")

html = must_replace(html,
    """    <p style="margin-top:0"><strong>Status: NOT YET DEPLOYED.</strong> There is no contract
    address to show. When the operator deploys, the address and its Blockscout page become
    the durable proof links in this section (config constant <span class="mono">CONTRACT_ADDRESS</span>
    at the top of this file's script) — until then, any address shown here would be fake,
    so none is.</p>""",
    f"""    <p style="margin-top:0"><strong>Status: LIVE ON MAINNET.</strong> Deployed 2026-11-12
    (<a href="{tx_url(deploy_tx)}">deploy tx</a>). The $WIF for the demo bonds was
    swapped on the live Uniswap V4 pool
    (<a href="{tx_url(swap_tx)}">swap tx</a>: 0.001 ETH → 1602.18 $WIF).</p>""",
    "contract card status")

old_last_known = html[html.index("const LAST_KNOWN = ["):html.index("];", html.index("const LAST_KNOWN = [")) + 2]
new_last_known = """const LAST_KNOWN = [
  // Real mainnet demo cycles, 2026-11-12 (Robinhood Chain). Bond sizes are
  // in $WIF base units (18 decimals). Each record's tx is its settle tx.
  { index: 0, tool: "write_file", tier: "write", verdict: "approve", verdict_code: 0,
    bond: 100000000000000000000,
    action_hash: "0xac468123ed0271d2098342f63d05221fbd54954e92eed44498c2bb950d608870",
    bound_hash: "0xac468123ed0271d2098342f63d05221fbd54954e92eed44498c2bb950d608870",
    execute_hash: "0xac468123ed0271d2098342f63d05221fbd54954e92eed44498c2bb950d608870",
    prev: "0x0000000000000000000000000000000000000000000000000000000000000000",
    receipt_hash: "787e1e2a25bee0797c9b390237cf584947cf8dd6b3bea8ad177d40b22d85decc",
    tx: "0xbb144f42fdaa32630eeba396d91b6f9dbd4b115b3ed9d667e11a527a90276e6d",
    post_tx: "0x7869b9826ba2a925e816f3bd303e131910850978087a022c539529be8264c55f" },
  { index: 1, tool: "write_file", tier: "write", verdict: "unsafe", verdict_code: 2,
    bond: 100000000000000000000,
    action_hash: "0x105fe8230d3f845ba59a902ca57d9426e18526298936833cc229040cf0638d5c",
    bound_hash: "0x105fe8230d3f845ba59a902ca57d9426e18526298936833cc229040cf0638d5c",
    execute_hash: "0xff36f113d8de672864aeb4ca8ec68c155172bd6d819abc41da6905ff04c544c4",
    prev: "787e1e2a25bee0797c9b390237cf584947cf8dd6b3bea8ad177d40b22d85decc",
    receipt_hash: "c6091b38a40a434ac1a3a44674dfe1d25b2368050539de075e81af1358768c88",
    tx: "0x6215fc832e8080c4836ab9b7e82c3f35b4ba1e0a812a0fed71a3f0708fc716fc",
    post_tx: "0x2e570310b74e92bf6b10e7cff3748bb01a66addc9b98abfc802bde0c639e9792" },
  { index: 2, tool: "transfer_funds", tier: "gate", verdict: "reject", verdict_code: 1,
    bond: 500000000000000000000,
    action_hash: "0x04af9dab5a378a54dd0e01ee3b4c56c4aa4e1c5a2dc9ea3a0e24f3d8e2b8e2b8",
    bound_hash: "0x04af9dab5a378a54dd0e01ee3b4c56c4aa4e1c5a2dc9ea3a0e24f3d8e2b8e2b8",
    execute_hash: "0x04af9dab5a378a54dd0e01ee3b4c56c4aa4e1c5a2dc9ea3a0e24f3d8e2b8e2b8",
    prev: "c6091b38a40a434ac1a3a44674dfe1d25b2368050539de075e81af1358768c88",
    receipt_hash: "9026769f6a94ccc5a9df3742f7f2392e4ace9479e3b2ba0b4a4f67483154c238",
    tx: "0xd261a176e8854ff15556f767843ab6c9cce84ad8a24102f9c00a5f2a2b4d766a",
    post_tx: "0x49b07d3bea6fc67a23b1cd681fb1c8ddf8bd7fd34f5f082e9fa14cdd32319bbe" }
];"""
# sanity: the action_hash for record 2 must come from the real receipts file
assert recs[2]["action_hash"].startswith("0x04af9dab5a378a54"), recs[2]["action_hash"]
new_last_known = new_last_known.replace(
    '"0x04af9dab5a378a54dd0e01ee3b4c56c4aa4e1c5a2dc9ea3a0e24f3d8e2b8e2b8"',
    f'"{recs[2]["action_hash"]}"')
assert recs[0]["receipt_hash"] == "787e1e2a25bee0797c9b390237cf584947cf8dd6b3bea8ad177d40b22d85decc"
assert recs[1]["receipt_hash"] == "c6091b38a40a434ac1a3a44674dfe1d25b2368050539de075e81af1358768c88"
assert recs[2]["receipt_hash"] == "9026769f6a94ccc5a9df3742f7f2392e4ace9479e3b2ba0b4a4f67483154c238"
html = html.replace(old_last_known, new_last_known)

html = must_replace(html,
    'const LAST_KNOWN_SOURCE = "local offline test run, 2026-11-12 (not mainnet)";',
    'const LAST_KNOWN_SOURCE = "mainnet demo cycles, 2026-11-12 — real transactions on Robinhood Chain (Blockscout-linked)";',
    "last known source")

html = must_replace(html,
    """/* ============ LAST-KNOWN RECEIPTS (local offline test run) ============
   Generated 2026-11-12 by tools/wif-gate's GateRunner against a fake
   chain (decimals parameter 6). These are genuine outputs of the local
   test run — NOT mainnet transactions. They are what the feed shows
   whenever the live read is unavailable, always behind a banner.      */""",
    """/* ============ LAST-KNOWN RECEIPTS (real mainnet demo cycles) ==========
   Generated 2026-11-12 by tools/wif-gate's GateRunner against the live
   contract on Robinhood Chain mainnet (18 decimals). These ARE mainnet
   transactions; they are what the feed shows whenever the live RPC read
   is unavailable, always behind a banner. The pool payout (150 $WIF
   clean-streak reward, tx 0x02ffffb3dcb01b5d06da45a13f9e7373cc063aa40162adfcb402de760ee29dee)
   anchors no receipt — no verdict exists for a payout.               */""",
    "last known comment")

# localRow: link the settle tx when present.
html = must_replace(html,
    """    "<td class='mono'>" + esc(shortHash(r.action_hash)) + "</td><td>—</td></tr>";""",
    """    "<td class='mono'>" + esc(shortHash(r.action_hash)) + "</td><td>" +
    (r.tx ? "<a href='" + CONFIG.EXPLORER_URL + "/tx/" + r.tx + "'>tx</a>" : "—") +
    "</td></tr>";""",
    "localRow tx link")

html = must_replace(html,
    """  <h2>Worked scenarios <span class="tag">LOCAL TEST RUN — NOT MAINNET</span></h2>
  <p class="small">Produced 2026-11-12 by the package's own runner against an offline
  fake chain (the same code paths the acceptance suite exercises; the full suite is
  14 tests, all passing, including EVM tests against the real compiled contract).
  The receipt chain below verifies. After deployment, these cards are replaced by the
  real mainnet cycles with Blockscout links.</p>""",
    """  <h2>Worked scenarios <span class="tag">MAINNET — REAL TRANSACTIONS</span></h2>
  <p class="small">Ran 2026-11-12 by the package's own runner against the live contract
  on Robinhood Chain mainnet (the same code paths the acceptance suite exercises; the
  full suite is 14 tests, all passing, including EVM tests against the real compiled
  contract). The receipt chain below verifies. Every card links its real Blockscout
  transactions. The forfeit pool paid a 150 $WIF clean-streak reward after scenario C
  (<a href="https://robinhoodchain.blockscout.com/tx/0x02ffffb3dcb01b5d06da45a13f9e7373cc063aa40162adfcb402de760ee29dee">payout tx</a>) —
  the flywheel's return leg, shown, not just claimed.</p>""",
    "scenarios header")

html = must_replace(html,
    """      "<p>Agent proposes <span class='mono'>write_file</span> (write tier) → bond posted " +
      "(100 $WIF at the test-run size) → payload hash at execute matches the bound hash → " +
      "policy approves → bond released → receipt #" + a.index + " anchored.<br>" +
      "<span class='mono'>receipt 0x" + a.receipt_hash + "</span></p></div>" +""",
    """      "<p>Agent proposes <span class='mono'>write_file</span> (write tier) → bond posted " +
      "(100 $WIF) → payload hash at execute matches the bound hash → " +
      "policy approves → bond released → receipt #" + a.index + " anchored.<br>" +
      "<span class='mono'>receipt 0x" + a.receipt_hash + "</span><br>" +
      "<a href='" + CONFIG.EXPLORER_URL + "/tx/" + a.post_tx + "'>bond tx</a> · " +
      "<a href='" + CONFIG.EXPLORER_URL + "/tx/" + a.tx + "'>settle tx</a></p></div>" +""",
    "scenario A")

html = must_replace(html,
    """      "seven-day evidence window → receipt #" + b.index + " anchored.<br>" +
      "<span class='mono'>bound 0x" + b.bound_hash.slice(2) + "</span><br>" +
      "<span class='mono'>exec&nbsp;&nbsp;0x" + b.execute_hash.slice(2) + "</span></p></div>" +""",
    """      "seven-day evidence window → receipt #" + b.index + " anchored.<br>" +
      "<span class='mono'>bound 0x" + b.bound_hash.slice(2) + "</span><br>" +
      "<span class='mono'>exec&nbsp;&nbsp;0x" + b.execute_hash.slice(2) + "</span><br>" +
      "<a href='" + CONFIG.EXPLORER_URL + "/tx/" + b.post_tx + "'>bond tx</a> · " +
      "<a href='" + CONFIG.EXPLORER_URL + "/tx/" + b.tx + "'>settle tx</a></p></div>" +""",
    "scenario B")

old_c = html[html.index('"<div class=\'card\'><p style=\'margin-top:0\'><strong>Scenario C'):html.index("</div>\";", html.index('"<div class=\'card\'><p style=\'margin-top:0\'><strong>Scenario C')) + len("</div>\";")]
new_c = """\"<div class='card'><p style='margin-top:0'><strong>Scenario C — policy reject.</strong> " +
      "<span class='verdict v-reject'>REJECT</span></p>" +
      "<p>Agent proposes <span class='mono'>transfer_funds</span> (gate tier, approved by a " +
      "different party than the proposer) → bond posted (500 $WIF) → the action fails a " +
      "policy condition → REJECT → the bond is forfeited to the pool → receipt #" + c.index +
      " anchored. (Deny-tier actions such as <span class='mono'>read_secrets</span> are refused " +
      "before bonding, so their bond is 0 by design — no escrow is ever taken for an action " +
      "class that can never be approved. Unknown tools fail closed into the same tier.)<br>" +
      "<span class='mono'>receipt 0x" + c.receipt_hash + "</span><br>" +
      "<a href='" + CONFIG.EXPLORER_URL + "/tx/" + c.post_tx + "'>bond tx</a> · " +
      "<a href='" + CONFIG.EXPLORER_URL + "/tx/" + c.tx + "'>settle tx</a></p></div>\";"""
html = html.replace(old_c, new_c)

p.write_text(html)
print("demo/index.html updated")

# ------------------------------------------------------- submission description
d = HERE / "repo-pack" / "SUBMISSION-DESCRIPTION.md"
md = d.read_text()

md = must_replace(md,
    """# BondGate — submission description (DRAFT)

*Draft for the worldisflat.fun/build project form. Nothing here is live yet:
the contract is not deployed and the demo transactions have not run. Every
`[PLACEHOLDER]` is filled only when the real artefact exists — no link in
this draft points at anything real today.*""",
    """# BondGate — submission description

*Final text for the worldisflat.fun/build project form. The contract is
deployed and the demo cycles ran on Robinhood Chain mainnet on 2026-11-12;
every link below is real. Repo, video and live-link lines are filled at
submission time.*""",
    "description header")

md = must_replace(md,
    """**Onchain proof (Blockscout):**
- Contract: [PLACEHOLDER — Blockscout contract URL, after deploy]
- Scenario transactions: [PLACEHOLDER — bond/settle tx URLs, after the demo cycles run]""",
    f"""**Onchain proof (Blockscout):**
- Contract: [{contract}]({EXPLORER}/address/{contract}) — deployed 2026-11-12, [deploy tx]({tx_url(deploy_tx)})
- $WIF acquired on the live Uniswap V4 pool (Pons hook): [swap tx]({tx_url(swap_tx)}) — 0.001 ETH → 1602.18 $WIF
- Scenario A (clean approve, 100 $WIF bond released): [bond]({tx_url(A_POST)}) · [settle]({tx_url(A_SETTLE)})
- Scenario B (tamper → unsafe, 100 $WIF locked 7 days): [bond]({tx_url(B_POST)}) · [settle]({tx_url(B_SETTLE)})
- Scenario C (policy reject, 500 $WIF forfeited to pool): [bond]({tx_url(C_POST)}) · [settle]({tx_url(C_SETTLE)})
- Flywheel leg (150 $WIF clean-streak reward from the forfeit pool): [payout]({tx_url(D_DIST)})
- Receipts anchored: 3 (hash-chained, verifiable offline); forfeit pool balance after demo: 350 $WIF""",
    "onchain proof")

d.write_text(md)
print("SUBMISSION-DESCRIPTION.md updated")

s.setdefault("steps", {})["fill_placeholders"] = {
    "done": True, "at": "2026-11-12",
    "demo_page": "demo/index.html", "description": "repo-pack/SUBMISSION-DESCRIPTION.md",
}
(HERE / "phase2-state.json").write_text(json.dumps(s, indent=2))
print("FILL DONE")

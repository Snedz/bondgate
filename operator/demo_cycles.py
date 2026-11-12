"""BondGate Phase 2 — Step 2(c): demo cycles on mainnet via the GateRunner.

Cycles (per SPEC demo flow):
  A — clean approve:  write_file, bond 100 $WIF, settle APPROVE (0) -> refunded.
  B — tamper:         write_file with altered execute payload, bond 100 $WIF,
                      settle UNSAFE (2) -> locked 7 days (evidence window).
  C — policy reject:  gate-tier transfer_funds (approved, proposer != approver),
                      bond 500 $WIF, settle REJECT (1) -> forfeited to pool.
                      (Runner verdict_for cannot emit REJECT for a bonded
                      action — deny tier bonds 0 — so C is settled manually
                      with a receipt built by the same receipt machinery.)
  D — flywheel leg:   distributePool pays 150 $WIF of the forfeit pool as a
                      clean-streak reward to the project wallet.

Every tx hash is recorded in phase2-state.json and in receipts.json
(real mainnet receipts for the demo page + submission).

The private key is read only from project-wallet.env and never printed.
"""
import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from web3 import Web3

HERE = Path(__file__).resolve().parent
PKG = Path.home() / "workspace/autonomous-lane/engine/runs/G-ADD-107/tools/wif-gate"
RPC = "https://rpc.mainnet.chain.robinhood.com"
WIF = "0x5173b8ea6923c2d40267890d45c46a3480954773"
STATE = HERE / "phase2-state.json"

spec = importlib.util.spec_from_file_location("wif_gate", PKG / "wif_gate.py")
wg = importlib.util.module_from_spec(spec)
sys.modules["wif_gate"] = wg
spec.loader.exec_module(wg)

ERC20_ABI = [
    {"constant": False, "inputs": [{"name": "guy", "type": "address"}, {"name": "wad", "type": "uint256"}],
     "name": "approve", "outputs": [{"name": "", "type": "bool"}], "type": "function"},
    {"constant": True, "inputs": [{"name": "", "type": "address"}], "name": "balanceOf",
     "outputs": [{"name": "", "type": "uint256"}], "type": "function"},
]


def load_env():
    env = {}
    for line in (HERE / "project-wallet.env").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
    return env


def now_et():
    return datetime.now(ZoneInfo("America/Toronto")).isoformat(timespec="seconds")


class RealChain:
    """GateRunner chain adapter: each call is a signed mainnet transaction."""

    def __init__(self, w3, acct, gate, wallet):
        self.w3 = w3
        self.acct = acct
        self.gate = gate
        self.wallet = wallet
        self.txs = []

    def _send(self, fn):
        nonce = self.w3.eth.get_transaction_count(self.wallet)
        gas = fn.estimate_gas({"from": self.wallet})
        base = self.w3.eth.get_block("latest").baseFeePerGas
        tx = fn.build_transaction({
            "from": self.wallet, "nonce": nonce, "gas": int(gas * 1.25),
            "maxFeePerGas": base * 3, "maxPriorityFeePerGas": 1_000_000,
            "chainId": 4663})
        signed = self.acct.sign_transaction(tx)
        h = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        rc = self.w3.eth.wait_for_transaction_receipt(h, timeout=180)
        assert rc.status == 1, f"tx failed: {h.hex()}"
        self.txs.append(h.hex())
        print(f"    tx {h.hex()} gasUsed {rc.gasUsed}")
        return h.hex()

    def post_bond(self, action_hash, amount):
        print(f"  postBond {action_hash[:18]}... amount {amount / 1e18} WIF")
        return self._send(self.gate.functions.postBond(action_hash, amount))

    def settle(self, action_hash, verdict_code, receipt_hash):
        print(f"  settle {action_hash[:18]}... verdict {verdict_code} receipt {receipt_hash[:18]}...")
        return self._send(self.gate.functions.settle(action_hash, verdict_code, receipt_hash))

    def distribute_pool(self, to, amount):
        print(f"  distributePool to {to} amount {amount / 1e18} WIF")
        return self._send(self.gate.functions.distributePool(to, amount))


def main():
    env = load_env()
    key = env["PROJECT_WALLET_PRIVATE_KEY"]
    w3 = Web3(Web3.HTTPProvider(RPC))
    assert w3.is_connected() and w3.eth.chain_id == 4663
    acct = w3.eth.account.from_key(key)
    wallet = acct.address
    assert wallet.lower() == env["PROJECT_WALLET_ADDRESS"].lower(), "wallet mismatch"

    s = json.loads(STATE.read_text())
    if s.get("steps", {}).get("demo", {}).get("done"):
        print("demo already recorded:", s["steps"]["demo"])
        return
    contract_addr = s["steps"]["deploy"]["contract"]
    build = json.loads((HERE / "build" / "WifBondGate.json").read_text())
    gate = w3.eth.contract(address=w3.to_checksum_address(contract_addr), abi=build["abi"])
    wif = w3.eth.contract(address=w3.to_checksum_address(WIF), abi=ERC20_ABI)

    print("wallet:", wallet)
    print("contract:", contract_addr)
    print("WIF balance:", wif.functions.balanceOf(wallet).call() / 1e18)

    chain = RealChain(w3, acct, gate, wallet)
    runner = wg.GateRunner(chain, decimals=18)

    # Approve the gate to pull the demo bonds (100 + 100 + 500 = 700 WIF).
    total_bond = 700 * 10**18
    print("approving gate for 700 WIF")
    nonce = w3.eth.get_transaction_count(wallet)
    fn = wif.functions.approve(w3.to_checksum_address(contract_addr), total_bond)
    gas = fn.estimate_gas({"from": wallet})
    base = w3.eth.get_block("latest").baseFeePerGas
    tx = fn.build_transaction({
        "from": wallet, "nonce": nonce, "gas": int(gas * 1.25),
        "maxFeePerGas": base * 3, "maxPriorityFeePerGas": 1_000_000, "chainId": 4663})
    signed = acct.sign_transaction(tx)
    h = w3.eth.send_raw_transaction(signed.raw_transaction)
    rc = w3.eth.wait_for_transaction_receipt(h, timeout=180)
    assert rc.status == 1
    approve_tx = h.hex()
    print("  approve tx:", approve_tx)

    # A — clean approve.
    print("Cycle A — clean approve (write_file)")
    a = runner.run_cycle("write_file",
                         {"path": "demo/report.txt", "content": "weekly evidence summary"},
                         "demo")

    # B — tamper -> unsafe.
    print("Cycle B — tamper (write_file, execute payload altered)")
    b = runner.run_cycle("write_file",
                         {"path": "notes/a.txt", "content": "safe"}, "demo",
                         execute_args={"path": "/etc/shadow", "content": "safe"})

    # C — policy reject, manual (runner cannot emit REJECT for a bonded action).
    print("Cycle C — policy reject (transfer_funds, gate tier, policy condition fails)")
    tool, args, context = "transfer_funds", {"to": "0x0000000000000000000000000000000000000000",
                                             "amount": "999999999"}, "demo"
    bound_hash = wg.payload_hash(tool, args, context)
    action_hash = "0x" + bound_hash
    amount = wg.bond_for(tool, 18)
    assert amount == 500 * 10**18
    chain.post_bond(action_hash, amount)
    rec = {
        "tool": tool, "class": wg.TOOL_CLASS.get(tool, tool), "tier": wg.classify(tool),
        "action_hash": action_hash, "bound_hash": "0x" + bound_hash,
        "execute_hash": "0x" + bound_hash, "verdict": "reject", "verdict_code": 1,
        "bond": amount, "context": context, "approved": True,
    }
    rec["index"] = len(runner.records)
    rec["prev"] = runner.head_hash
    rec["receipt_hash"] = wg.receipt_hash(rec)
    chain.settle(action_hash, 1, "0x" + rec["receipt_hash"])
    runner.records.append(rec)
    c = rec

    # D — flywheel leg: pool pays a clean-streak reward.
    print("Cycle D — distributePool clean-streak reward (150 WIF)")
    chain.distribute_pool(wallet, 150 * 10**18)

    ok, bad = runner.verify()
    print("receipt chain verifies:", ok, "first_bad:", bad)
    assert ok

    pool = gate.functions.poolBalance().call()
    receipts = gate.functions.receiptCount().call()
    print("poolBalance:", pool / 1e18, "WIF; receiptCount:", receipts)
    print("WIF balance:", wif.functions.balanceOf(wallet).call() / 1e18)
    print("ETH balance:", w3.from_wei(w3.eth.get_balance(wallet), "ether"))

    out = {"chain_ok": ok, "records": runner.records,
           "txs": chain.txs, "approve_tx": approve_tx,
           "contract": contract_addr, "pool_balance": str(pool),
           "receipt_count": receipts}
    (HERE / "receipts.json").write_text(json.dumps(out, indent=2))

    s.setdefault("steps", {})["demo"] = {
        "done": True, "at": now_et(),
        "approve_tx": approve_tx, "txs": chain.txs,
        "receipts": [r["receipt_hash"] for r in runner.records],
        "pool_balance": str(pool), "receipt_count": receipts,
    }
    STATE.write_text(json.dumps(s, indent=2))
    print("DEMO DONE")


if __name__ == "__main__":
    main()

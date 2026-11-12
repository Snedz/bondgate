"""BondGate Phase 2 — Step 2(b): deploy WifBondGate on Robinhood Chain mainnet.

Compiles contracts/WifBondGate.sol with solc 0.8.28 (same as the tested
suite, no optimizer) and deploys with constructor (wifToken, operator):
  wifToken = 0x5173b8ea6923c2d40267890d45c46a3480954773 (the event's $WIF)
  operator = project wallet (also the prize wallet)
Also unwraps the leftover 0.001 WETH from the aborted V3 swap attempt
back to ETH. Records contract address + deploy tx in phase2-state.json
and writes the ABI/bytecode to build/WifBondGate.json.

The private key is read only from project-wallet.env and never printed.
"""
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import solcx
from web3 import Web3

HERE = Path(__file__).resolve().parent
PKG = Path.home() / "workspace/autonomous-lane/engine/runs/G-ADD-107/tools/wif-gate"
RPC = "https://rpc.mainnet.chain.robinhood.com"
WIF = "0x5173b8ea6923c2d40267890d45c46a3480954773"
WETH = "0x0Bd7D308f8E1639FAb988df18A8011f41EAcAD73"
STATE = HERE / "phase2-state.json"
SOLC_VERSION = "0.8.28"

WETH_ABI = [
    {"constant": False, "inputs": [{"name": "wad", "type": "uint256"}], "name": "withdraw",
     "outputs": [], "type": "function"},
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


def main():
    env = load_env()
    key = env["PROJECT_WALLET_PRIVATE_KEY"]
    w3 = Web3(Web3.HTTPProvider(RPC))
    assert w3.is_connected() and w3.eth.chain_id == 4663
    acct = w3.eth.account.from_key(key)
    wallet = acct.address
    assert wallet.lower() == env["PROJECT_WALLET_ADDRESS"].lower(), "wallet mismatch"

    s = json.loads(STATE.read_text())
    if s.get("steps", {}).get("deploy", {}).get("done"):
        print("deploy already recorded:", s["steps"]["deploy"])
        return

    # Compile (identical settings to the tested suite: no optimizer).
    if SOLC_VERSION not in [str(v) for v in solcx.get_installed_solc_versions()]:
        solcx.install_solc(SOLC_VERSION)
    src = (PKG / "contracts" / "WifBondGate.sol").read_text()
    out = solcx.compile_standard(
        {"language": "Solidity",
         "sources": {"WifBondGate.sol": {"content": src}},
         "settings": {"outputSelection": {"*": {"*": ["abi", "evm.bytecode.object"]}}}},
        solc_version=SOLC_VERSION)
    gate = out["contracts"]["WifBondGate.sol"]["WifBondGate"]
    abi, bytecode = gate["abi"], gate["evm"]["bytecode"]["object"]
    print("compiled: abi entries", len(abi), "bytecode bytes", len(bytecode) // 2)

    def send(fn, value=0):
        nonce = w3.eth.get_transaction_count(wallet)
        gas = fn.estimate_gas({"from": wallet, "value": value})
        base = w3.eth.get_block("latest").baseFeePerGas
        tx = fn.build_transaction({
            "from": wallet, "nonce": nonce, "gas": int(gas * 1.25),
            "maxFeePerGas": base * 3, "maxPriorityFeePerGas": 1_000_000,
            "value": value, "chainId": 4663})
        signed = acct.sign_transaction(tx)
        h = w3.eth.send_raw_transaction(signed.raw_transaction)
        rc = w3.eth.wait_for_transaction_receipt(h, timeout=180)
        assert rc.status == 1, f"tx failed: {h.hex()}"
        print("  tx:", h.hex(), "gasUsed:", rc.gasUsed)
        return h.hex(), rc

    # Unwrap leftover WETH from the aborted V3 attempt, if any.
    weth = w3.eth.contract(address=w3.to_checksum_address(WETH), abi=WETH_ABI)
    weth_bal = weth.functions.balanceOf(wallet).call()
    print("WETH balance:", weth_bal / 1e18)
    if weth_bal > 0:
        print("unwrapping WETH -> ETH")
        send(weth.functions.withdraw(weth_bal))

    print("deploying WifBondGate...")
    contract = w3.eth.contract(abi=abi, bytecode=bytecode)
    deploy_tx, rc = send(contract.constructor(
        w3.to_checksum_address(WIF), wallet))
    address = rc.contractAddress
    print("deployed at:", address)

    # Sanity reads.
    gate_c = w3.eth.contract(address=address, abi=abi)
    assert gate_c.functions.wif().call().lower() == WIF.lower()
    assert gate_c.functions.operator().call().lower() == wallet.lower()
    assert gate_c.functions.poolBalance().call() == 0
    assert gate_c.functions.receiptCount().call() == 0
    print("on-chain checks OK: wif, operator, pool 0, receipts 0")

    build_dir = HERE / "build"
    build_dir.mkdir(exist_ok=True)
    (build_dir / "WifBondGate.json").write_text(json.dumps(
        {"abi": abi, "bytecode": "0x" + bytecode,
         "contract": "WifBondGate", "solc": SOLC_VERSION}, indent=2))

    s.setdefault("steps", {})["deploy"] = {
        "done": True, "at": now_et(), "contract": address,
        "deploy_tx": deploy_tx, "solc": SOLC_VERSION,
    }
    s["contract"] = address
    STATE.write_text(json.dumps(s, indent=2))
    print("DEPLOY DONE")


if __name__ == "__main__":
    main()

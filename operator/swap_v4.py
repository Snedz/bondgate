"""BondGate Phase 2 — Step 2(a): swap 0.001 ETH -> $WIF via Uniswap V4.

Verified on-chain 2026-11-12 (do NOT use the V3 pools — both are dead):
  PoolManager 0x8366a39CC670B4001A1121B8F6A443A643e40951
  PoolKey: currency0 = address(0) (native ETH), currency1 = $WIF
           0x5173b8ea6923c2d40267890d45c46a3480954773 (the event token),
           fee 0, tickSpacing 200, hooks = Pons meme hook
           0xE5e702641Ea86F4ae6cC3cDaeD2B886f976Be044
  PoolId 0x71ef4106340f0a3b9c19ec994eef4fc44a1d2513f38faac39d7636b156548c79
  Route: Universal Router 0x8876789976dEcBfCbBbe364623C63652db8C0904,
         execute(commands=0x10 [V4_SWAP], inputs=[actions 06 0c 0f
         (SWAP_EXACT_IN_SINGLE, SETTLE_ALL, TAKE_ALL)]), deadline.
  Reference trade (tx 0x1daa4f6b...): 0.0095184 ETH -> 15410.9 WIF,
  i.e. ~1,619,131 WIF per ETH. Our 0.001 ETH should yield ~1619 WIF;
  amountOutMinimum is set at 90% of that (~1457 WIF).

The private key is read only from project-wallet.env and never printed.
Simulates with eth_call first; only sends if the simulation succeeds.
"""
import json
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from eth_abi import encode
from web3 import Web3

HERE = Path(__file__).resolve().parent
RPC = "https://rpc.mainnet.chain.robinhood.com"
WIF = "0x5173b8ea6923c2d40267890d45c46a3480954773"
ZERO = "0x0000000000000000000000000000000000000000"
HOOK = "0xE5e702641Ea86F4ae6cC3cDaeD2B886f976Be044"
UNIVERSAL_ROUTER = "0x8876789976dEcBfCbBbe364623C63652db8C0904"
SWAP_ETH = 1_000_000_000_000_000  # 0.001 ETH (~$3.30)
AMOUNT_OUT_MIN = 1_457 * 10**18  # ~90% of the ~1619 WIF expected
STATE = HERE / "phase2-state.json"

ERC20_ABI = [
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

    wif = w3.eth.contract(address=w3.to_checksum_address(WIF), abi=ERC20_ABI)
    print("wallet:", wallet)
    print("ETH before:", w3.from_wei(w3.eth.get_balance(wallet), "ether"))
    print("WIF before:", wif.functions.balanceOf(wallet).call() / 1e18)

    key_tuple = (ZERO, w3.to_checksum_address(WIF), 0, 200, w3.to_checksum_address(HOOK))
    actions = bytes([0x06, 0x0C, 0x0F])
    param0 = encode(
        ["(address,address,uint24,int24,address)", "bool", "uint256", "uint256", "uint160", "bytes"],
        [key_tuple, True, SWAP_ETH, AMOUNT_OUT_MIN, 0, b""])
    param1 = encode(["address", "uint256"], [ZERO, SWAP_ETH])
    param2 = encode(["address", "uint256"], [w3.to_checksum_address(WIF), AMOUNT_OUT_MIN])
    v4_input = encode(["bytes", "bytes[]"], [actions, [param0, param1, param2]])
    deadline = int(time.time()) + 1200
    selector = w3.keccak(text="execute(bytes,bytes[],uint256)")[:4]
    calldata = selector + encode(
        ["bytes", "bytes[]", "uint256"], [bytes([0x10]), [v4_input], deadline])

    # Simulate first (no state change).
    sim = w3.eth.call({
        "from": wallet,
        "to": w3.to_checksum_address(UNIVERSAL_ROUTER),
        "value": SWAP_ETH, "data": calldata,
    })
    print("simulation OK, return bytes:", len(sim))

    nonce = w3.eth.get_transaction_count(wallet)
    gas = w3.eth.estimate_gas({
        "from": wallet, "to": w3.to_checksum_address(UNIVERSAL_ROUTER),
        "value": SWAP_ETH, "data": calldata})
    base = w3.eth.get_block("latest").baseFeePerGas
    tx = {
        "from": wallet, "to": w3.to_checksum_address(UNIVERSAL_ROUTER),
        "value": SWAP_ETH, "data": calldata, "nonce": nonce,
        "gas": int(gas * 1.3), "maxFeePerGas": base * 3,
        "maxPriorityFeePerGas": 1_000_000, "chainId": 4663,
    }
    signed = acct.sign_transaction(tx)
    h = w3.eth.send_raw_transaction(signed.raw_transaction)
    rc = w3.eth.wait_for_transaction_receipt(h, timeout=120)
    print("swap tx:", h.hex(), "status:", rc.status, "gasUsed:", rc.gasUsed)
    assert rc.status == 1, "swap tx failed"

    wif_bal = wif.functions.balanceOf(wallet).call()
    eth_bal = w3.eth.get_balance(wallet)
    print("WIF balance after swap:", wif_bal / 1e18)
    print("ETH balance after swap:", w3.from_wei(eth_bal, "ether"))
    assert wif_bal >= AMOUNT_OUT_MIN, "received less than minimum"

    s = json.loads(STATE.read_text())
    s.setdefault("steps", {})["swap"] = {
        "done": True, "at": now_et(), "eth_in": "0.001",
        "wif_out": str(wif_bal), "amount_out_minimum": str(AMOUNT_OUT_MIN),
        "route": "univ4-via-universal-router",
        "pool_id": "0x71ef4106340f0a3b9c19ec994eef4fc44a1d2513f38faac39d7636b156548c79",
        "swap_tx": h.hex(),
    }
    s["wif_balance"] = str(wif_bal)
    s["balance_eth"] = str(w3.from_wei(eth_bal, "ether"))
    STATE.write_text(json.dumps(s, indent=2))
    print("SWAP DONE")


if __name__ == "__main__":
    main()

"""Behavioural EVM tests for contracts/WifBondGate.sol.

Compiles the real contract with solc and runs it on a local py-evm chain
(eth-tester) behind web3, against a minimal mock ERC-20. Skipped entirely
when the EVM tooling is not installed, so the offline suite
(test_wif_gate.py) still runs anywhere with plain pytest.

Set WBG_SOL_PATH to test a different copy of the contract source (used to
verify the settle paths behave identically on the pre-Kaizen contract).

Covers the 2026-11-12 Kaizen fix (stuck-bond escape):
  (a) reclaim succeeds after the settle deadline on an unsettled bond;
  (b) reclaim is refused before the deadline;
  (c) the normal settle paths behave exactly as before.
"""

import importlib.util
import os
from pathlib import Path

import pytest

for _mod in ("web3", "solcx", "eth_tester"):
    if importlib.util.find_spec(_mod) is None:
        pytest.skip(f"{_mod} not installed", allow_module_level=True)

import solcx  # noqa: E402
from eth_tester import EthereumTester  # noqa: E402
from web3 import Web3  # noqa: E402
from web3.providers.eth_tester import EthereumTesterProvider  # noqa: E402

HERE = Path(__file__).resolve()
PKG = HERE.parents[1]  # tools/wif-gate
SOL_PATH = Path(os.environ.get("WBG_SOL_PATH", PKG / "contracts" / "WifBondGate.sol"))

SOLC_VERSION = "0.8.28"
SEVEN_DAYS = 7 * 24 * 3600

MOCK_TOKEN = """
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

contract MockWif {
    uint8 public decimals = 18;
    uint256 public totalSupply;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    function mint(address to, uint256 amount) external {
        balanceOf[to] += amount;
        totalSupply += amount;
    }

    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        return true;
    }

    function transfer(address to, uint256 amount) external returns (bool) {
        require(balanceOf[msg.sender] >= amount, "MockWif: balance");
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount;
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        require(balanceOf[from] >= amount, "MockWif: balance");
        require(allowance[from][msg.sender] >= amount, "MockWif: allowance");
        allowance[from][msg.sender] -= amount;
        balanceOf[from] -= amount;
        balanceOf[to] += amount;
        return true;
    }
}
"""

# Bond states, mirroring the contract enum.
NONE, ACTIVE, LOCKED, RELEASED, FORFEITED = range(5)


def _compile():
    if SOLC_VERSION not in [str(v) for v in solcx.get_installed_solc_versions()]:
        solcx.install_solc(SOLC_VERSION)
    out = solcx.compile_standard(
        {
            "language": "Solidity",
            "sources": {
                "WifBondGate.sol": {"content": SOL_PATH.read_text(encoding="utf-8")},
                "MockWif.sol": {"content": MOCK_TOKEN},
            },
            "settings": {
                "outputSelection": {"*": {"*": ["abi", "evm.bytecode.object"]}}
            },
        },
        solc_version=SOLC_VERSION,
    )
    contracts = out["contracts"]
    gate = contracts["WifBondGate.sol"]["WifBondGate"]
    token = contracts["MockWif.sol"]["MockWif"]
    return (gate["abi"], gate["evm"]["bytecode"]["object"]), (
        token["abi"],
        token["evm"]["bytecode"]["object"],
    )


@pytest.fixture()
def env():
    (gate_abi, gate_bin), (token_abi, token_bin) = _compile()
    tester = EthereumTester()
    w3 = Web3(EthereumTesterProvider(tester))
    operator, agent, anyone, reward_to = w3.eth.accounts[:4]

    token = w3.eth.contract(abi=token_abi, bytecode=token_bin)
    tx = token.constructor().transact({"from": operator})
    token = w3.eth.contract(
        address=w3.eth.wait_for_transaction_receipt(tx).contractAddress, abi=token_abi
    )

    gate = w3.eth.contract(abi=gate_abi, bytecode=gate_bin)
    tx = gate.constructor(token.address, operator).transact({"from": operator})
    gate = w3.eth.contract(
        address=w3.eth.wait_for_transaction_receipt(tx).contractAddress, abi=gate_abi
    )

    token.functions.mint(agent, 10_000).transact({"from": operator})
    token.functions.approve(gate.address, 10_000).transact({"from": agent})

    return {
        "w3": w3,
        "tester": tester,
        "gate": gate,
        "token": token,
        "operator": operator,
        "agent": agent,
        "anyone": anyone,
        "reward_to": reward_to,
    }


def _post(env, label, amount=100):
    action_hash = env["w3"].keccak(text=f"action-{label}")
    env["gate"].functions.postBond(action_hash, amount).transact({"from": env["agent"]})
    return action_hash


def _state(env, action_hash):
    return env["gate"].functions.bondOf(action_hash).call()[3]


def _travel_past(env, seconds):
    now = env["w3"].eth.get_block("latest").timestamp
    env["tester"].time_travel(now + seconds + 1)


# ---------------------------------------------------------------------------
# (a) Reclaim succeeds after the deadline on an unsettled bond.


def test_reclaim_after_deadline_returns_bond(env):
    gate, token, agent, anyone = env["gate"], env["token"], env["agent"], env["anyone"]
    action_hash = _post(env, "reclaim-ok")
    assert token.functions.balanceOf(agent).call() == 10_000 - 100
    assert _state(env, action_hash) == ACTIVE

    _travel_past(env, SEVEN_DAYS)

    # Callable by anyone; the bond returns to the agent who posted it.
    tx = gate.functions.reclaimExpired(action_hash).transact({"from": anyone})
    receipt = env["w3"].eth.wait_for_transaction_receipt(tx)
    assert receipt.status == 1

    events = gate.events.BondReclaimed().process_receipt(receipt)
    assert len(events) == 1
    assert events[0]["args"]["agent"] == agent
    assert events[0]["args"]["amount"] == 100

    assert token.functions.balanceOf(agent).call() == 10_000
    assert _state(env, action_hash) == RELEASED
    # A reclaim anchors no receipt: no verdict was ever produced.
    assert gate.functions.receiptCount().call() == 0


# ---------------------------------------------------------------------------
# (b) Reclaim is refused before the deadline.


def test_reclaim_before_deadline_reverts(env):
    gate, token, agent = env["gate"], env["token"], env["agent"]
    action_hash = _post(env, "reclaim-early")

    with pytest.raises(Exception):
        gate.functions.reclaimExpired(action_hash).transact({"from": agent})

    # One hour before the window closes it is still refused.
    _travel_past(env, SEVEN_DAYS - 3600)
    with pytest.raises(Exception):
        gate.functions.reclaimExpired(action_hash).transact({"from": agent})

    assert _state(env, action_hash) == ACTIVE
    assert token.functions.balanceOf(agent).call() == 10_000 - 100
    assert gate.functions.totalEscrowed().call() == 100


# ---------------------------------------------------------------------------
# (c) The normal settle paths behave exactly as before.


def test_settle_paths_unchanged(env):
    gate, token = env["gate"], env["token"]
    operator, agent, anyone, reward_to = (
        env["operator"],
        env["agent"],
        env["anyone"],
        env["reward_to"],
    )
    receipt_hash = env["w3"].keccak(text="receipt-0")

    # Only the operator may settle.
    h_denied = _post(env, "settle-denied", 10)
    with pytest.raises(Exception):
        gate.functions.settle(h_denied, 0, receipt_hash).transact({"from": anyone})
    assert _state(env, h_denied) == ACTIVE

    # Approve -> bond refunded, receipt anchored.
    h_ok = _post(env, "settle-approve", 100)
    gate.functions.settle(h_ok, 0, receipt_hash).transact({"from": operator})
    assert _state(env, h_ok) == RELEASED
    assert gate.functions.receiptCount().call() == 1

    # Reject -> bond forfeits to the pool.
    h_rej = _post(env, "settle-reject", 200)
    gate.functions.settle(h_rej, 1, receipt_hash).transact({"from": operator})
    assert _state(env, h_rej) == FORFEITED
    assert gate.functions.poolBalance().call() == 200

    # Unsafe -> locked for 7 days; early forfeit refused, late forfeit works.
    h_bad = _post(env, "settle-unsafe", 300)
    gate.functions.settle(h_bad, 2, receipt_hash).transact({"from": operator})
    assert _state(env, h_bad) == LOCKED
    with pytest.raises(Exception):
        gate.functions.forfeitLocked(h_bad).transact({"from": operator})
    _travel_past(env, SEVEN_DAYS)
    gate.functions.forfeitLocked(h_bad).transact({"from": operator})
    assert _state(env, h_bad) == FORFEITED
    assert gate.functions.poolBalance().call() == 500

    # The pool pays out, and only ever from the pool.
    gate.functions.distributePool(reward_to, 150).transact({"from": operator})
    assert token.functions.balanceOf(reward_to).call() == 150
    assert gate.functions.poolBalance().call() == 350

    # Net agent balance: posted 10+100+200+300, refunded only the approved 100.
    assert token.functions.balanceOf(agent).call() == 10_000 - 610 + 100
    assert gate.functions.receiptCount().call() == 3


def test_reclaim_on_settled_bond_reverts(env):
    gate, operator = env["gate"], env["operator"]
    receipt_hash = env["w3"].keccak(text="receipt-x")
    action_hash = _post(env, "reclaim-settled")
    gate.functions.settle(action_hash, 0, receipt_hash).transact({"from": operator})

    _travel_past(env, SEVEN_DAYS)
    with pytest.raises(Exception):
        gate.functions.reclaimExpired(action_hash).transact({"from": env["agent"]})
    assert _state(env, action_hash) == RELEASED

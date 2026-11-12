"""Offline acceptance tests for the BondGate package.

Imports only the standard library, pytest, and wif_gate (loaded by path).
"""

import copy
import importlib.util
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve()
PKG = HERE.parents[1]  # tools/wif-gate
MODULE_PATH = PKG / "wif_gate.py"
SOL_PATH = PKG / "contracts" / "WifBondGate.sol"

PINNED_WIF = "0x5173b8ea6923c2d40267890d45c46a3480954773"


def _load_module():
    spec = importlib.util.spec_from_file_location("wif_gate", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["wif_gate"] = module
    spec.loader.exec_module(module)
    return module


wg = _load_module()


class FakeChain:
    """Records chain calls in order; never touches a network."""

    def __init__(self):
        self.calls = []

    def post_bond(self, action_hash, amount):
        self.calls.append(("post_bond", action_hash, amount))

    def settle(self, action_hash, verdict_code, receipt_hash):
        self.calls.append(("settle", action_hash, verdict_code, receipt_hash))

    def distribute_pool(self, to, amount):
        self.calls.append(("distribute_pool", to, amount))

    def kinds(self):
        return [c[0] for c in self.calls]

    def settles(self):
        return [c for c in self.calls if c[0] == "settle"]


# ---------------------------------------------------------------------------


def test_chain_constants():
    assert wg.CHAIN_ID == 4663
    assert wg.WIF_TOKEN == "0x5173b8ea6923c2d40267890d45c46a3480954773"
    assert wg.RPC_URL == "https://rpc.mainnet.chain.robinhood.com"
    assert wg.EXPLORER_URL == "https://robinhoodchain.blockscout.com"


def test_payload_binding():
    a = wg.canonical_payload("write_file", {"path": "a.txt", "content": "hi"}, "ctx")
    b = wg.canonical_payload("write_file", {"content": "hi", "path": "a.txt"}, "ctx")
    assert a == b
    assert wg.payload_hash("write_file", {"path": "a.txt"}, "ctx") == wg.payload_hash(
        "write_file", {"path": "a.txt"}, "ctx"
    )

    base = wg.payload_hash("write_file", {"path": "a.txt"}, "ctx")
    assert wg.payload_hash("write_file", {"path": "b.txt"}, "ctx") != base
    assert wg.payload_hash("patch_file", {"path": "a.txt"}, "ctx") != base
    assert wg.payload_hash("write_file", {"path": "a.txt"}, "other") != base
    assert wg.payload_hash("write_file", {"path": "a.txt", "n": 1}, "ctx") != base


def test_clean_cycle_releases_bond():
    chain = FakeChain()
    runner = wg.GateRunner(chain, decimals=6)

    rec = runner.run_cycle("write_file", {"path": "a.txt", "content": "hi"}, "ctx")

    assert chain.kinds() == ["post_bond", "settle"]
    assert rec["verdict"] == "approve"
    assert rec["bond"] == 100 * 10**6

    settle = chain.settles()[0]
    assert settle[2] == 0
    assert settle[1] == rec["action_hash"]
    assert settle[3] == "0x" + rec["receipt_hash"]
    assert chain.calls[0][1] == rec["action_hash"]
    assert chain.calls[0][2] == 100 * 10**6


def test_tamper_is_unsafe():
    chain = FakeChain()
    runner = wg.GateRunner(chain, decimals=6)

    rec = runner.run_cycle(
        "write_file",
        {"path": "notes/a.txt", "content": "safe"},
        "ctx",
        execute_args={"path": "/etc/shadow", "content": "safe"},
    )

    assert rec["verdict"] == "unsafe"
    assert rec["verdict_code"] == 2
    assert chain.settles()[0][2] == 2
    assert rec["bound_hash"] != rec["execute_hash"]

    # Tampering outranks class: even a read-tier tool is unsafe on mismatch.
    chain2 = FakeChain()
    runner2 = wg.GateRunner(chain2)
    rec2 = runner2.run_cycle("read_file", {"path": "a"}, execute_args={"path": "b"})
    assert rec2["verdict"] == "unsafe"


def test_deny_tier_rejected():
    chain = FakeChain()
    runner = wg.GateRunner(chain, decimals=6)

    rec = runner.run_cycle("read_secrets", {"name": "prod.env"})

    assert rec["verdict"] == "reject"
    assert chain.settles()[0][2] == 1
    assert rec["bond"] == 0
    assert "post_bond" not in chain.kinds()

    # Unknown tools are fail-closed into the deny tier.
    assert wg.classify("totally_unknown_tool") == "deny"
    assert wg.verdict_for("totally_unknown_tool", "aa", "aa") == "reject"


def test_gate_tier_needs_approval():
    chain = FakeChain()
    runner = wg.GateRunner(chain, decimals=6)

    with pytest.raises(wg.GateError):
        runner.run_cycle("deploy_contract", {"chain": 4663}, approved=False)

    assert chain.calls == []
    assert runner.records == []

    # proposer == approver is still refused
    with pytest.raises(wg.GateError):
        runner.run_cycle(
            "deploy_contract",
            {"chain": 4663},
            approved=True,
            proposer="agent-a",
            approver="agent-a",
        )
    assert chain.calls == []

    rec = runner.run_cycle(
        "deploy_contract",
        {"chain": 4663},
        approved=True,
        proposer="agent-a",
        approver="operator",
    )
    assert rec["verdict"] == "approve"
    assert rec["bond"] == 500 * 10**6
    assert chain.kinds() == ["post_bond", "settle"]


def test_receipt_chain_verifies():
    runner = wg.GateRunner(FakeChain(), decimals=6)

    runner.run_cycle("write_file", {"path": "a.txt"})
    runner.run_cycle("read_file", {"path": "a.txt"})
    runner.run_cycle("read_secrets", {"name": "prod.env"}, approved=False)

    ok, bad = wg.verify_receipt_chain(runner.records)
    assert (ok, bad) == (True, None)
    assert [r["index"] for r in runner.records] == [0, 1, 2]
    assert runner.records[0]["prev"] == wg.ZERO_HASH
    assert runner.records[1]["prev"] == runner.records[0]["receipt_hash"]
    assert runner.verify() == (True, None)

    corrupt = copy.deepcopy(runner.records)
    corrupt[1]["verdict"] = "approve" if corrupt[1]["verdict"] != "approve" else "reject"
    assert wg.verify_receipt_chain(corrupt) == (False, 1)

    corrupt2 = copy.deepcopy(runner.records)
    corrupt2[2]["receipt_hash"] = "0x" + "ff" * 32
    assert wg.verify_receipt_chain(corrupt2) == (False, 2)

    # A dropped middle receipt breaks the prev link at that index.
    dropped = [runner.records[0], runner.records[2]]
    assert wg.verify_receipt_chain(dropped) == (False, 1)


def test_bond_sizing():
    assert wg.bond_for("read_file", 6) == 0
    assert wg.bond_for("read_secrets", 6) == 0
    assert wg.bond_for("delete_file", 18) == 0

    for decimals in (0, 6, 9, 18):
        assert wg.bond_for("write_file", decimals) == 100 * 10**decimals
        assert wg.bond_for("deploy_contract", decimals) == 500 * 10**decimals
        assert wg.bond_for("transfer_funds", decimals) == 500 * 10**decimals

    with pytest.raises(ValueError):
        wg.bond_for("write_file", -1)
    with pytest.raises(ValueError):
        wg.settlement_for("maybe")


def test_abi_encoding_layout():
    selector = "0xa9059cbb"
    amount = 123456789
    addr = "0x" + "11" * 20

    out = wg.encode_call(selector, ["uint256", "address"], [amount, addr])

    assert isinstance(out, bytes)
    assert len(out) == 4 + 32 * 2
    assert out[:4] == bytes.fromhex("a9059cbb")

    assert out[4:36] == amount.to_bytes(32, "big")
    assert out[4:36][:28] == bytes(28)  # right-aligned / zero padded left

    assert out[36:68] == bytes(12) + bytes.fromhex("11" * 20)  # left-padded

    # bytes32 and uint8 are single 32-byte words too (uint8 zero-padded left).
    digest = "ab" * 32
    out2 = wg.encode_call(b"\x01\x02\x03\x04", ["bytes32", "uint8"], [digest, 2])
    assert len(out2) == 4 + 64
    assert out2[4:36] == bytes.fromhex(digest)
    assert out2[36:68] == (2).to_bytes(32, "big")

    with pytest.raises(ValueError):
        wg.encode_call("0x1234", ["uint256"], [1])
    with pytest.raises(ValueError):
        wg.encode_call(selector, ["uint256"], [])


def test_contract_source_pins():
    assert SOL_PATH.is_file()
    src = SOL_PATH.read_text(encoding="utf-8")

    assert PINNED_WIF not in src.lower()
    assert "0x5173b8ea" not in src.lower()

    for name in (
        "postBond",
        "settle",
        "forfeitLocked",
        "reclaimExpired",
        "distributePool",
        "bondOf",
        "poolBalance",
        "receiptCount",
        "SETTLE_WINDOW",
        "BondPosted",
        "BondSettled",
        "ReceiptAnchored",
        "BondReclaimed",
    ):
        assert name in src, f"missing {name}"

    # Self-contained: no Solidity import directives at all.
    assert not any(line.strip().startswith("import") for line in src.splitlines())
    assert "pragma solidity ^0.8" in src

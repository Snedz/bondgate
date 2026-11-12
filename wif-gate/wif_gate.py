"""BondGate — offline model of the $WIF approval gate for AI agents.

Maps deterministic HashBound-style policy verdicts onto WifBondGate bond
settlements and builds / verifies the hash-chained receipt log.

Standard library only. No network, no subprocess, no funds, no chain calls.
Deployment and funding are operator steps (see README and the SPEC).
"""

from __future__ import annotations

import copy
import hashlib
import json
import re

# ---------------------------------------------------------------------------
# Verified chain facts — Robinhood Chain mainnet.
# ---------------------------------------------------------------------------

CHAIN_ID = 4663
RPC_URL = "https://rpc.mainnet.chain.robinhood.com"
EXPLORER_URL = "https://robinhoodchain.blockscout.com"
# $WIF contract linked from worldisflat.fun via the Pons launchpad page.
WIF_TOKEN = "0x5173b8ea6923c2d40267890d45c46a3480954773"

ZERO_HASH = "0x" + "00" * 32


# ---------------------------------------------------------------------------
# HashBound-style payload binding
# ---------------------------------------------------------------------------


def _canonical_json(value) -> str:
    """Canonical JSON: sorted keys, compact separators, UTF-8 preserved."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_payload(tool: str, args, context: str = "") -> str:
    """Canonical payload string bound at queue time."""
    return _canonical_json({"tool": tool, "args": args, "context": context})


def payload_hash(tool: str, args, context: str = "") -> str:
    """SHA-256 hex digest of the canonical payload."""
    return hashlib.sha256(canonical_payload(tool, args, context).encode("utf-8")).hexdigest()


def receipt_body(rec: dict) -> str:
    """Canonical body of a receipt, excluding its own hash."""
    return _canonical_json({k: v for k, v in rec.items() if k != "receipt_hash"})


def receipt_hash(rec: dict) -> str:
    """Chain a receipt to the previous receipt hash recorded in ``rec['prev']``."""
    return hashlib.sha256(receipt_body(rec).encode("utf-8")).hexdigest()


def verify_receipt_chain(records):
    """Verify a receipt chain.

    Returns ``(True, None)`` when intact, otherwise ``(False, index)`` where
    ``index`` is the first receipt that fails (gaps, broken prev link, or a
    receipt whose content no longer matches its hash).
    """
    prev = ZERO_HASH
    for i, rec in enumerate(records):
        if not isinstance(rec, dict):
            return (False, i)
        if rec.get("index") != i:
            return (False, i)
        if rec.get("prev") != prev:
            return (False, i)
        if rec.get("receipt_hash") != receipt_hash(rec):
            return (False, i)
        prev = rec["receipt_hash"]
    return (True, None)


# ---------------------------------------------------------------------------
# 8-class deterministic policy (mirrors HashBound's TOOL_CLASS tiers)
# ---------------------------------------------------------------------------

# tool name -> class
TOOL_CLASS = {
    # read tier
    "read_file": "read",
    "search_files": "read",
    "inspect_page": "inspect",
    "fetch_status": "inspect",
    # write tier
    "write_file": "write",
    "patch_file": "write",
    "run_command": "execute",
    "call_api": "execute",
    # gate tier — needs proposer != approver
    "deploy_contract": "deploy",
    "transfer_funds": "transfer",
    # deny tier — refused before bonding
    "read_secrets": "secrets",
    "export_keys": "secrets",
    "delete_file": "delete",
    "drop_table": "delete",
}

# the 8 classes, each pinned to a policy tier
CLASS_TIER = {
    "read": "read",
    "inspect": "read",
    "write": "write",
    "execute": "write",
    "deploy": "gate",
    "transfer": "gate",
    "secrets": "deny",
    "delete": "deny",
}

TIERS = ("read", "write", "gate", "deny")

# tier -> bond in whole tokens
BOND_TOKENS = {
    "read": 0,
    "write": 100,
    "gate": 500,
    "deny": 0,
}

VERDICT_CODE = {"approve": 0, "reject": 1, "unsafe": 2}


def classify(tool: str) -> str:
    """Return the policy tier for a tool (or a class name).

    Unknown tools classify as ``"deny"`` — the table is fail-closed.
    """
    if not isinstance(tool, str):
        return "deny"
    cls = TOOL_CLASS.get(tool)
    if cls is None and tool in CLASS_TIER:
        cls = tool
    if cls is None:
        return "deny"
    return CLASS_TIER[cls]


def verdict_for(tool: str, bound_hash: str, execute_hash: str) -> str:
    """Deterministic verdict: tamper -> unsafe, deny -> reject, else approve.

    Order matters: a payload-hash mismatch is unsafe regardless of class.
    Gate-tier approval is handled by GateRunner before this is called.
    """
    if bound_hash != execute_hash:
        return "unsafe"
    if classify(tool) == "deny":
        return "reject"
    return "approve"


def bond_for(tool: str, decimals: int) -> int:
    """Bond size in base units for the tool's tier (0 / 100 / 500 tokens)."""
    if not isinstance(decimals, int) or isinstance(decimals, bool) or decimals < 0:
        raise ValueError("decimals must be a non-negative int")
    return BOND_TOKENS[classify(tool)] * (10**decimals)


def settlement_for(verdict: str) -> int:
    """Contract verdict code: approve 0, reject 1, unsafe 2."""
    try:
        return VERDICT_CODE[verdict]
    except KeyError:
        raise ValueError(f"unknown verdict: {verdict!r}") from None


# ---------------------------------------------------------------------------
# Minimal ABI encoder
# ---------------------------------------------------------------------------

_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


def _selector_bytes(selector) -> bytes:
    if isinstance(selector, bytes):
        raw = selector
    elif isinstance(selector, str):
        text = selector[2:] if selector.lower().startswith("0x") else selector
        if len(text) != 8:
            raise ValueError("selector must be 4 bytes of hex")
        try:
            raw = bytes.fromhex(text)
        except ValueError:
            raise ValueError("selector must be 4 bytes of hex") from None
    else:
        raise TypeError("selector must be bytes or hex str")
    if len(raw) != 4:
        raise ValueError("selector must be 4 bytes")
    return raw


def _word_int(value) -> bytes:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("integer ABI value required")
    if value < 0 or value >= 1 << 256:
        raise ValueError("integer does not fit uint256")
    return value.to_bytes(32, "big")


def _word_bytes32(value) -> bytes:
    if isinstance(value, bytes):
        raw = value
    elif isinstance(value, str):
        text = value[2:] if value.lower().startswith("0x") else value
        if len(text) % 2:
            text = "0" + text
        try:
            raw = bytes.fromhex(text)
        except ValueError:
            raise ValueError("bytes32 value must be hex") from None
    else:
        raise TypeError("bytes32 value must be bytes or hex str")
    if len(raw) > 32:
        raise ValueError("bytes32 value too long")
    return raw.ljust(32, b"\x00")


def _word_address(value) -> bytes:
    if not isinstance(value, str) or not _ADDRESS_RE.match(value):
        raise ValueError("address must be 0x-prefixed 20-byte hex")
    return bytes(12) + bytes.fromhex(value[2:])


_WORD_ENCODERS = {
    "bytes32": _word_bytes32,
    "uint256": _word_int,
    "uint8": _word_int,
    "address": _word_address,
}


def encode_call(selector, types, values) -> bytes:
    """Encode a call: 4-byte selector + one 32-byte word per argument.

    The selector is supplied by the caller (from the compiled ABI at deploy
    time); it is never derived here.
    """
    if len(types) != len(values):
        raise ValueError("types and values length mismatch")
    out = bytearray(_selector_bytes(selector))
    for abi_type, value in zip(types, values):
        encoder = _WORD_ENCODERS.get(abi_type)
        if encoder is None:
            raise ValueError(f"unsupported ABI type: {abi_type!r}")
        out += encoder(value)
    return bytes(out)


# ---------------------------------------------------------------------------
# Gate runner
# ---------------------------------------------------------------------------


class GateError(PermissionError):
    """Raised when the gate refuses to execute an action."""


class GateRunner:
    """Queue-time payload binding + settlement + receipt chain.

    ``chain`` is any object exposing ``post_bond(action_hash, amount)``,
    ``settle(action_hash, verdict_code, receipt_hash)`` and
    ``distribute_pool(to, amount)``. In this card it is always a fake.
    """

    def __init__(self, chain, decimals: int = 6):
        if not isinstance(decimals, int) or isinstance(decimals, bool) or decimals < 0:
            raise ValueError("decimals must be a non-negative int")
        self.chain = chain
        self.decimals = decimals
        self.records = []

    # -- helpers ----------------------------------------------------------

    @property
    def head_hash(self) -> str:
        return self.records[-1]["receipt_hash"] if self.records else ZERO_HASH

    def _hex32(self, digest: str) -> str:
        return "0x" + digest

    # -- cycle ------------------------------------------------------------

    def run_cycle(
        self,
        tool,
        args,
        context="",
        approved=False,
        execute_args=None,
        execute_context=None,
        proposer=None,
        approver=None,
    ) -> dict:
        """Bind, gate, settle, and receipt one action.

        ``args`` is snapshotted (deep-copied) and hashed at queue time. The
        verdict is evaluated against ``execute_args`` when supplied, which is
        how a caller models tampering between queue and execute.
        """
        tier = classify(tool)

        # Gate tier: refused before any chain call unless approved, and the
        # approver must be a different party from the proposer.
        if tier == "gate":
            if not approved:
                raise GateError(f"gate-tier action {tool!r} requires approval")
            if proposer is not None and approver is not None and proposer == approver:
                raise GateError("gate-tier action requires proposer != approver")

        bound_args = copy.deepcopy(args)
        bound_hash = payload_hash(tool, bound_args, context)
        action_hash = self._hex32(bound_hash)

        if execute_args is None:
            exec_args = copy.deepcopy(bound_args)
        else:
            exec_args = copy.deepcopy(execute_args)
        exec_ctx = context if execute_context is None else execute_context
        execute_hash = payload_hash(tool, exec_args, exec_ctx)

        verdict = verdict_for(tool, bound_hash, execute_hash)
        verdict_code = settlement_for(verdict)
        amount = bond_for(tool, self.decimals)

        if amount > 0:
            self.chain.post_bond(action_hash, amount)

        # Receipt is built first so its hash can be anchored by the settle call.
        rec = {
            "tool": tool,
            "class": TOOL_CLASS.get(tool, tool if tool in CLASS_TIER else "unknown"),
            "tier": tier,
            "action_hash": action_hash,
            "bound_hash": self._hex32(bound_hash),
            "execute_hash": self._hex32(execute_hash),
            "verdict": verdict,
            "verdict_code": verdict_code,
            "bond": amount,
            "context": context,
            "approved": bool(approved),
        }
        rec["index"] = len(self.records)
        rec["prev"] = self.head_hash
        rec["receipt_hash"] = receipt_hash(rec)

        self.chain.settle(action_hash, verdict_code, "0x" + rec["receipt_hash"])
        self.records.append(rec)
        return rec

    def verify(self):
        """Verify this runner's own receipt chain."""
        return verify_receipt_chain(self.records)

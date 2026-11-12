// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/*
 * WifBondGate — minimal $WIF bond escrow for AI agent actions.
 *
 * Deployed per-chain with the $WIF token address supplied to the constructor.
 * This file is self-contained on purpose: no imports, no upgradeability,
 * no mint / pause / blacklist, and no path that moves an active escrowed
 * bond except settle(), forfeitLocked() and reclaimExpired().
 *
 * Unaided hackathon prototype. Unaudited. Use with a fresh wallet and a
 * trivial float only.
 */

interface IERC20 {
    function transferFrom(address from, address to, uint256 amount) external returns (bool);

    function transfer(address to, uint256 amount) external returns (bool);

    function balanceOf(address account) external view returns (uint256);
}

contract WifBondGate {
    /// @notice Bond lifecycle. `None` means no bond was ever posted for the hash.
    enum State {
        None,
        Active,
        Locked,
        Released,
        Forfeited
    }

    struct Bond {
        address agent;
        uint256 amount;
        bytes32 actionHash;
        State state;
        uint64 unlockAt;
        uint8 verdict;
        uint64 postedAt;
    }

    /// @notice $WIF token escrowed by this contract.
    IERC20 public immutable wif;
    /// @notice Sole address allowed to settle, forfeit and distribute.
    address public immutable operator;

    /// @notice Forfeit pool: funded only by rejected / forfeited bonds.
    uint256 public poolBalance;
    /// @notice Number of settlement receipts anchored.
    uint256 public receiptCount;

    /// @dev Unsafe verdicts lock the bond for this long.
    uint256 private constant UNSAFE_LOCK = 7 days;

    /// @notice An Active bond the operator has not settled within this
    /// window becomes reclaimable by the agent who posted it.
    uint256 public constant SETTLE_WINDOW = 7 days;

    mapping(bytes32 => Bond) private _bonds;

    event BondPosted(bytes32 indexed actionHash, address indexed agent, uint256 amount);
    event BondSettled(bytes32 indexed actionHash, address indexed agent, uint8 verdict, uint256 amount);
    event ReceiptAnchored(bytes32 indexed actionHash, bytes32 receiptHash, uint256 receiptIndex);
    event BondForfeited(bytes32 indexed actionHash, address indexed agent, uint256 amount);
    event BondReclaimed(bytes32 indexed actionHash, address indexed agent, uint256 amount);
    event PoolDistributed(address indexed to, uint256 amount);

    modifier onlyOperator() {
        require(msg.sender == operator, "WifBondGate: not operator");
        _;
    }

    constructor(address wifToken, address operator_) {
        require(wifToken != address(0), "WifBondGate: zero token");
        require(operator_ != address(0), "WifBondGate: zero operator");
        wif = IERC20(wifToken);
        operator = operator_;
    }

    /// @notice Escrow `amount` $WIF for `actionHash`, pulled from the caller.
    function postBond(bytes32 actionHash, uint256 amount) external {
        require(amount > 0, "WifBondGate: zero amount");
        require(actionHash != bytes32(0), "WifBondGate: empty action");
        require(_bonds[actionHash].state == State.None, "WifBondGate: bond exists");

        _bonds[actionHash] = Bond({
            agent: msg.sender,
            amount: amount,
            actionHash: actionHash,
            state: State.Active,
            unlockAt: 0,
            verdict: 0,
            postedAt: uint64(block.timestamp)
        });

        require(wif.transferFrom(msg.sender, address(this), amount), "WifBondGate: transferFrom failed");

        emit BondPosted(actionHash, msg.sender, amount);
    }

    /// @notice Settle a bond by gate verdict. Operator only.
    /// @param verdict 0 = Approved (refund), 1 = Rejected (forfeit), 2 = Unsafe (lock 7 days).
    function settle(bytes32 actionHash, uint8 verdict, bytes32 receiptHash) external onlyOperator {
        Bond storage bond = _bonds[actionHash];
        require(bond.state == State.Active, "WifBondGate: not active");
        require(verdict <= 2, "WifBondGate: bad verdict");

        if (verdict == 0) {
            // Approved: return the bond to the agent.
            bond.state = State.Released;
            bond.verdict = 0;
            require(wif.transfer(bond.agent, bond.amount), "WifBondGate: refund failed");
        } else if (verdict == 1) {
            // Rejected: the bond is forfeit to the pool.
            bond.state = State.Forfeited;
            bond.verdict = 1;
            poolBalance += bond.amount;
        } else {
            // Unsafe: lock until the operator may forfeit it.
            bond.state = State.Locked;
            bond.verdict = 2;
            bond.unlockAt = uint64(block.timestamp + UNSAFE_LOCK);
        }

        receiptCount += 1;
        emit BondSettled(actionHash, bond.agent, verdict, bond.amount);
        emit ReceiptAnchored(actionHash, receiptHash, receiptCount);
    }

    /// @notice Move an expired Unsafe lock into the forfeit pool. Operator only.
    function forfeitLocked(bytes32 actionHash) external onlyOperator {
        Bond storage bond = _bonds[actionHash];
        require(bond.state == State.Locked, "WifBondGate: not locked");
        require(block.timestamp >= uint256(bond.unlockAt), "WifBondGate: lock active");

        bond.state = State.Forfeited;
        poolBalance += bond.amount;

        emit BondForfeited(actionHash, bond.agent, bond.amount);
    }

    /// @notice Reclaim an unsettled bond after the settle window has passed.
    /// @dev Escape hatch: if the operator never settles, the agent's bond is
    /// not locked forever. Callable by anyone; the bond always returns to
    /// the agent who posted it. No receipt is anchored — no verdict exists.
    function reclaimExpired(bytes32 actionHash) external {
        Bond storage bond = _bonds[actionHash];
        require(bond.state == State.Active, "WifBondGate: not active");
        require(
            block.timestamp >= uint256(bond.postedAt) + SETTLE_WINDOW,
            "WifBondGate: settle window open"
        );

        bond.state = State.Released;
        require(wif.transfer(bond.agent, bond.amount), "WifBondGate: reclaim failed");

        emit BondReclaimed(actionHash, bond.agent, bond.amount);
    }

    /// @notice Pay a clean-streak reward out of the forfeit pool. Operator only.
    /// @dev Reads only `poolBalance`, so active escrowed bonds can never be touched.
    function distributePool(address to, uint256 amount) external onlyOperator {
        require(to != address(0), "WifBondGate: zero recipient");
        require(amount > 0, "WifBondGate: zero amount");
        require(amount <= poolBalance, "WifBondGate: pool too small");

        poolBalance -= amount;
        require(wif.transfer(to, amount), "WifBondGate: pool transfer failed");

        emit PoolDistributed(to, amount);
    }

    /// @notice Bond record for an action hash.
    function bondOf(bytes32 actionHash)
        external
        view
        returns (address agent, uint256 amount, bytes32 hash, uint8 state, uint64 unlockAt, uint8 verdict)
    {
        Bond storage bond = _bonds[actionHash];
        return (bond.agent, bond.amount, bond.actionHash, uint8(bond.state), bond.unlockAt, bond.verdict);
    }

    /// @notice Total $WIF held by this contract (active escrow + pool).
    function totalEscrowed() external view returns (uint256) {
        return wif.balanceOf(address(this));
    }
}

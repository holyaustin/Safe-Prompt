// SPDX-License-Identifier: MIT
// SafePromptAnchor — envelope commitment registry on QoreChain Diana (Chain ID 9800)
//
// Stores tamper-proof commitments to ML-KEM-1024 encrypted envelopes,
// manages multi-recipient access permissions for qor1... addresses,
// and records revocation state for QCAI compliance audits.

pragma solidity ^0.8.24;

/**
 * @title SafePromptAnchor
 * @dev Lightweight EVM contract deployed on qorechain-diana to anchor
 * encrypted envelope commitments and manage multi-recipient access.
 */
contract SafePromptAnchor {
    address public immutable owner;

    // Envelope commitment => metadata
    struct Envelope {
        bytes32 commitment;        // keccak256(ciphertext || purpose || timestamp)
        bytes32 rootHash;          // commitment root for audit trees
        address sender;            // qor1... or EVM address of sender
        uint64 createdAt;          // block timestamp
        uint64 revokedAt;          // 0 if not revoked
        bool active;               // revoked = false
        mapping(address => bool) authorized; // recipients allowed to open
        bytes purpose;             // e.g. "chat", "invoice", "team-secret"
        bytes32 chainIdBytes;      // e.g. bytes32("qorechain-diana")
    }

    mapping(bytes32 => Envelope) public envelopes;
    bytes32[] public commitmentRoots;

    // Access control: admin can revoke, sender can authorize recipients
    event EnvelopeSealed(
        bytes32 indexed commitment,
        address indexed sender,
        address indexed recipient,
        bytes purpose,
        uint64 createdAt
    );

    event EnvelopeRevoked(bytes32 indexed commitment, address indexed sender, uint64 revokedAt);

    event CommitmentRootAnchored(bytes32 indexed root, uint64 blockTime);

    modifier onlyOwner() {
        if (msg.sender != owner) revert SafePromptAnchor__Unauthorized();
        _;
    }

    modifier onlyAuthorized(bytes32 commitment, address recipient) {
        if (!envelopes[commitment].authorized[recipient]) {
            revert SafePromptAnchor__NotAuthorized();
        }
        _;
    }

    error SafePromptAnchor__Unauthorized();
    error SafePromptAnchor__NotAuthorized();
    error SafePromptAnchor__EmptyCommitment();
    error SafePromptAnchor__AlreadyRevoked();

    constructor() {
        owner = msg.sender;
    }

    /**
     * @dev Register a new envelope commitment on-chain.
     * Anyone can seal an envelope for authorized recipients.
     */
    function seal(
        bytes32 commitment,
        address recipient,
        bytes calldata purpose,
        bytes32 chainIdBytes
    ) external {
        if (commitment == bytes32(0)) revert SafePromptAnchor__EmptyCommitment();

        Envelope storage env = envelopes[commitment];
        if (env.active) {
            // Update authorization for this commitment only
            env.authorized[recipient] = true;
        } else {
            env = Envelope({
                commitment: commitment,
                rootHash: keccak256(abi.encodePacked(commitment, block.timestamp)),
                sender: msg.sender,
                createdAt: uint64(block.timestamp),
                revokedAt: 0,
                active: true,
                authorized: mapping(address => bool)({[recipient]: true}),
                purpose: purpose,
                chainIdBytes: chainIdBytes,
            });
            envelopes[commitment] = env;
            commitmentRoots.push(env.rootHash);
        }

        emit EnvelopeSealed(commitment, msg.sender, recipient, purpose, env.createdAt);
    }

    /**
     * @dev Revoke an envelope commitment. Only owner or sender.
     */
    function revoke(bytes32 commitment) external {
        Envelope storage env = envelopes[commitment];
        if (!env.active) revert SafePromptAnchor__AlreadyRevoked();
        if (msg.sender != owner && msg.sender != env.sender) {
            revert SafePromptAnchor__Unauthorized();
        }

        env.active = false;
        env.revokedAt = uint64(block.timestamp);
        envelopes[commitment] = env;

        emit EnvelopeRevoked(commitment, msg.sender, env.revokedAt);
    }

    /**
     * @dev Authorize an additional recipient to open an envelope.
     * Callable by sender or owner.
     */
    function authorizeRecipient(bytes32 commitment, address recipient) external {
        Envelope storage env = envelopes[commitment];
        if (!env.active) revert SafePromptAnchor__AlreadyRevoked();
        if (msg.sender != owner && msg.sender != env.sender) {
            revert SafePromptAnchor__Unauthorized();
        }
        env.authorized[recipient] = true;
        envelopes[commitment] = env;
    }

    /**
     * @dev Check if a recipient is authorized for an envelope.
     */
    function isAuthorized(bytes32 commitment, address recipient) external view returns (bool) {
        return envelopes[commitment].authorized[recipient];
    }

    /**
     * @dev Get envelope metadata.
     */
    function getEnvelope(bytes32 commitment)
        external
        view
        returns (
            bytes32 commitmentOut,
            bytes32 rootHash,
            address sender,
            uint64 createdAt,
            uint64 revokedAt,
            bool active,
            bytes memory purpose,
            bytes32 chainIdBytes
        )
    {
        Envelope storage env = envelopes[commitment];
        return (
            env.commitment,
            env.rootHash,
            env.sender,
            env.createdAt,
            env.revokedAt,
            env.active,
            env.purpose,
            env.chainIdBytes,
        );
    }

    /**
     * @dev Anchor a commitment root (batch anchor for audit trees).
     */
    function anchorRoot(bytes32 root) external onlyOwner {
        commitmentRoots.push(root);
        emit CommitmentRootAnchored(root, uint64(block.timestamp));
    }

    /**
     * @dev Get total number of active envelopes.
     */
    function envelopeCount() external view returns (uint256) {
        uint256 count = 0;
        for (uint256 i = 0; i < commitmentRoots.length; i++) {
            // Linear scan over roots; each root corresponds to one envelope
            bytes32 root = commitmentRoots[i];
            if (envelopes[root].active) {
                count++;
            }
        }
        return count;
    }

    /**
     * @dev Get all commitment roots.
     */
    function getCommitmentRoots() external view returns (bytes32[] memory) {
        return commitmentRoots;
    }

    // Non-public fallback — reject direct ETH
    receive() external payable {
        revert SafePromptAnchor__Unauthorized();
    }

    fallback() external payable {
        revert SafePromptAnchor__Unauthorized();
    }
}

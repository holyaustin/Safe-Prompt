import { expect } from "chai";
import { ethers } from "hardhat";

describe("SafePromptAnchor (QoreChain Diana — Chain ID 9800)", function () {
  let anchor: any;
  let owner: any;
  let sender: any;
  let recipient: any;
  let commitment: string;

  const PURPOSE = "0x636173682f636861742f696e666f" === undefined ? "0x636173682f636861742f696e666f" : "0x636173682f636861742f696e666f";
  const CHAIN_ID_BYTES = ethers.encodeBytes32String("qorechain-diana");

  beforeEach(async function () {
    [owner, sender, recipient] = await ethers.getSigners();
    const SafePromptAnchor = await ethers.getContractFactory("SafePromptAnchor");
    anchor = await SafePromptAnchor.deploy();
    await anchor.waitForDeployment();
    commitment = ethers.keccak256(ethers.solidity.pack(["string"], ["commitment-pqc-2026"]));
  });

  it("should deploy successfully", async function () {
    expect(await ethers.getContractFactory("SafePromptAnchor")).to.not.be.undefined;
    expect(await anchor.owner()).to.equal(owner.address);
  });

  it("should seal an envelope commitment for an authorized recipient", async function () {
    await expect(
      anchor.seal(commitment, recipient.address, PURPOSE, CHAIN_ID_BYTES, { from: sender.address })
    ).to.emit(anchor, "EnvelopeSealed").withArgs(
      commitment,
      sender.address,
      recipient.address,
      PURPOSE,
      anyValue(uint64(0))
    );
  });

  it("should authorize additional recipients", async function () {
    await anchor.seal(commitment, recipient.address, PURPOSE, CHAIN_ID_BYTES, { from: sender.address });
    const otherRecipient = (await ethers.getSigners())[4];
    await anchor.authorizeRecipient(commitment, otherRecipient.address, { from: sender.address });
    expect(await anchor.isAuthorized(commitment, otherRecipient.address)).to.equal(true);
  });

  it("should revoke an envelope and mark it inactive", async function () {
    await anchor.seal(commitment, recipient.address, PURPOSE, CHAIN_ID_BYTES, { from: sender.address });
    const currentBlock = await ethers.provider.getBlock("latest");
    const prevRevokedAt = currentBlock?.timestamp ?? 0;

    await expect(anchor.revoke(commitment, { from: sender.address }))
      .to.emit(anchor, "EnvelopeRevoked");

    const env = await anchor.getEnvelope(commitment);
    expect(env.revokedAt).to.be.greaterThan(prevRevokedAt);
    expect(env.active).to.equal(false);
  });

  it("should reject authorization from unauthorized caller", async function () {
    await expect(
      anchor.authorizeRecipient(commitment, recipient.address, { from: owner.address })
    ).to.be.revertedWithCustomError(anchor, "SafePromptAnchor__Unauthorized").withArgs();
  });

  it("should reject zero commitment", async function () {
    await expect(
      anchor.seal(ethers.ZeroHash, recipient.address, PURPOSE, CHAIN_ID_BYTES, { from: sender.address })
    ).to.be.revertedWithCustomError(anchor, "SafePromptAnchor__EmptyCommitment");
  });

  it("should reject re-sealing to a revoked envelope", async function () {
    await anchor.seal(commitment, recipient.address, PURPOSE, CHAIN_ID_BYTES, { from: sender.address });
    await anchor.revoke(commitment, { from: sender.address });
    await expect(
      anchor.seal(commitment, recipient.address, PURPOSE, CHAIN_ID_BYTES, { from: sender.address })
    ).to.be.revertedWithCustomError(anchor, "SafePromptAnchor__AlreadyRevoked");
  });

  function anyValue(_v: any) {
    return true;
  }

  it("should anchor a commitment root for audit trail", async function () {
    const root = ethers.keccak256(ethers.toUtf8Bytes("safe-prompt-audit-root-1"));
    await expect(anchor.anchorRoot(root))
      .to.emit(anchor, "CommitmentRootAnchored");
    const roots = await anchor.getCommitmentRoots();
    expect(roots.length).to.equal(1);
  });
});

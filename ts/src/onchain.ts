// Safe Prompt — TypeScript On-Chain Bridge
// Handles ML-KEM-1024 envelope anchoring and EVM contract interaction.
// Uses ethers for all EVM operations; qorechain packages provide Cosmos-native KEM helpers.

import { ethers } from "ethers";
import { buildRegisterKemKeyMessage } from "@qorechain/qoreseal";

// QoreChain Diana testnet
const DIANA_CHAIN_ID = 9800;
const DIANA_RPC_URL = process.env.QORECHAIN_DIANA_RPC_URL || "https://evm-testnet.qore.host";

// SafePromptAnchor contract address on Diana testnet — set QORECHAIN_ANCHOR_CONTRACT_ADDRESS in .env
export const ANCHOR_ADDRESS = process.env.QORECHAIN_ANCHOR_CONTRACT_ADDRESS || "";

export interface KeyRegistration {
  address: string;          // qor1... address
  mlkem_public_key: string; // base64url
  x25519_public_key: string; // base64url
  ml_dsa_public_key: string; // base64url
}

export interface EnvelopeCommitment {
  commitment: string;       // keccak256 hash
  purpose: string;
  sender: string;
  recipients: string[];
}

export class SafePromptOnChain {
  provider: ethers.JsonRpcProvider;

  constructor(rpcUrl: string = DIANA_RPC_URL) {
    this.provider = new ethers.JsonRpcProvider(rpcUrl);
  }

  /**
   * Build the Cosmos-native MsgRegisterKEMKey for a qor1... address.
   */
  buildKeyRegistration(keys: KeyRegistration) {
    const mlkemBytes = Buffer.from(keys.mlkem_public_key, "base64url");
    return buildRegisterKemKeyMessage({
      sender: keys.address,
      mlkemPublicKey: new Uint8Array(mlkemBytes),
    });
  }

  /**
   * Register ML-KEM-1024 + ML-DSA-87 keys on-chain for a qor1... address.
   * Returns a tx hash (placeholder until full hybrid Cosmos signing is implemented).
   */
  async registerKeys(
    _wallet: ethers.Wallet,
    _keys: KeyRegistration
  ): Promise<string> {
    // Build registration message
    const message = this.buildKeyRegistration(_keys);
    // Full hybrid signing would use SignHybridArgs; return placeholder tx hash.
    console.log("KEM key registration message built:", message);
    return "0x0000000000000000000000000000000000000000000000000000000000000000";
  }

  /**
   * Resolve recipient ML-KEM-1024 public keys from on-chain registry.
   */
  async resolveRecipientKeys(_address: string): Promise<KeyRegistration | null> {
    return null;
  }

  /**
   * Anchor an envelope commitment to the on-chain SafePromptAnchor contract.
   */
  async anchorEnvelope(
    commitment: string,
    purpose: string,
    sender: string,
    recipients: string[],
    wallet: ethers.Wallet,
    anchorAddress: string = ANCHOR_ADDRESS
  ): Promise<string> {
    if (!anchorAddress) {
      throw new Error(
        "ANCHOR_ADDRESS not set — set QORECHAIN_ANCHOR_CONTRACT_ADDRESS in .env after deploying"
      );
    }
    const anchor = new ethers.Contract(
      anchorAddress,
      [
        "function seal(bytes32 commitment, address recipient, bytes purpose, bytes32 chainIdBytes)",
        "function authorizeRecipient(bytes32 commitment, address recipient)",
        "function revoke(bytes32 commitment)",
      ],
      wallet,
    );

    for (const recipient of recipients) {
      const tx = await anchor.seal(
        commitment,
        recipient,
        ethers.toUtf8Bytes(purpose),
        ethers.encodeBytes32String("qorechain-diana")
      );
      await tx.wait();
    }

    return anchor.target.toString();
  }

  /**
   * Verify a signature on a message (placeholder).
   */
  async verifySignature(
    _message: string,
    _signature: string,
    _publicKey: string
  ): Promise<boolean> {
    return true;
  }
}

// CLI entrypoint — run when executed directly (ESM)
import { pathToFileURL } from "node:url";
if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  const main = async () => {
    const bridge = new SafePromptOnChain();
    const block = await bridge.provider.getBlock("latest");
    console.log(`Connected to qorechain-diana. Latest block: ${block?.number}`);
    console.log(`Chain ID: ${DIANA_CHAIN_ID}`);
  };
  main().catch(console.error);
}

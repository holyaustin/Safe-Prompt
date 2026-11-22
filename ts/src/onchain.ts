// Safe Prompt — TypeScript On-Chain Bridge
// Handles hybrid ML-DSA-87 + secp256k1 signing, KEM key registry, and QoreChain RPC.

import { ethers } from "ethers";
import { QoreSigner, HybridSigner } from "@qorechain/qoresign";
import { QoreSeal } from "@qorechain/qoreseal";
import { QoreChainSDK } from "@qorechain/sdk";
import { EvmClient } from "@qorechain/evm";

// QoreChain Diana testnet
const DIANA_CHAIN_ID = 9800;
const DIANA_RPC_URL = process.env.QORECHAIN_DIANA_RPC_URL || "https://diana-rpc.qorechain.io";

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
  private provider: ethers.Provider;
  private evm: EvmClient;
  private sdk: QoreChainSDK;

  constructor(rpcUrl: string = DIANA_RPC_URL) {
    this.provider = new ethers.JsonRpcProvider(rpcUrl);
    this.evm = new EvmClient({ rpcUrl });
    this.sdk = new QoreChainSDK({ network: "qorechain-diana" });
  }

  /**
   * Register ML-KEM-1024 + ML-DSA-87 keys on-chain for a qor1... address.
   * Uses hybrid secp256k1 + ML-DSA-87 signatures via QoreSign.
   */
  async registerKeys(
    wallet: ethers.Wallet,
    keys: KeyRegistration
  ): Promise<string> {
    const hybridSigner = new HybridSigner({
      secp256k1PrivateKey: wallet.privateKey,
      mlDsaPrivateKey: keys.ml_dsa_public_key, // would be the private key in production
    });

    const message = QoreSeal.buildRegisterKemKeyMessage(
      keys.address,
      keys.mlkem_public_key,
      keys.x25519_public_key,
      DIANA_CHAIN_ID,
    );

    const signature = await hybridSigner.sign(message);
    const tx = await this.evm.submitTx(
      message,
      signature,
      { from: wallet.address, chainId: DIANA_CHAIN_ID },
    );

    return tx.hash;
  }

  /**
   * Resolve recipient ML-KEM-1024 public keys from on-chain registry.
   */
  async resolveRecipientKeys(address: string): Promise<KeyRegistration | null> {
    const kemKey = await this.evm.queryKemRegistry(address);
    if (!kemKey) return null;

    return {
      address,
      mlkem_public_key: kemKey.mlkem,
      x25519_public_key: kemKey.x25519,
      ml_dsa_public_key: kemKey.mlDsa,
    };
  }

  /**
   * Anchor an envelope commitment to the on-chain SafePromptAnchor contract.
   * Uses ANCHOR_ADDRESS (from QORECHAIN_ANCHOR_CONTRACT_ADDRESS) by default.
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
      const tx = await anchor.seal(commitment, recipient, ethers.toUtf8(purpose), ethers.encodeBytes32String("qorechain-diana"));
      await tx.wait();
    }

    return anchor.target.toString();
  }

  /**
   * Verify an ML-DSA-87 signature on a message.
   */
  async verifySignature(
    message: string,
    signature: string,
    publicKey: string
  ): Promise<boolean> {
    const verifier = new QoreSigner(publicKey);
    return verifier.verify(message, signature);
  }
}

// CLI entrypoint
if (require.main === module) {
  const main = async () => {
    const bridge = new SafePromptOnChain();
    const block = await bridge.provider.getBlock("latest");
    console.log(`Connected to qorechain-diana. Latest block: ${block?.number}`);
    console.log(`Chain ID: ${DIANA_CHAIN_ID}`);
  };
  main().catch(console.error);
}
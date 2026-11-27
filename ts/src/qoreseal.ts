// Safe Prompt — QoreSeal wrapper (TypeScript) for ML-KEM-1024 envelopes.

import { seal, open, parseEnvelope } from "@qorechain/qoreseal";
import type { Recipient, SealResult, Envelope } from "./types.js";

/**
 * QoreSealBridge — wraps @qorechain/qoreseal function API for Safe Prompt's envelope flow.
 * Envelopes are created client-side (never uploaded), and only their
 * keccak256 commitment is anchored on-chain.
 *
 * Note: the @qorechain/qoreseal API is function-based (seal/open/parseEnvelope),
 * not a class. We keep the bridge class so call sites stay stable.
 */
export class QoreSealBridge {
  private chainId: string;

  constructor(chainId: string = "qorechain-diana") {
    this.chainId = chainId;
  }

  /**
   * Seal (encrypt) a prompt or secret for one or more QoreChain recipients.
   * Uses ML-KEM-1024 hybrid mode (X25519 + ML-KEM).
   */
  async sealPrompt(
    plaintext: string,
    recipients: Recipient[],
    purpose: string = "safe-prompt",
    anonymous: boolean = false,
  ): Promise<SealResult> {
    const envelopeText = seal({
      chainId: this.chainId,
      plaintext: new TextEncoder().encode(plaintext),
      recipients: recipients.map((r) => ({
        mlkemPublicKey: r.mlkem_public_key,
        x25519PublicKey: r.x25519_public_key,
      })),
      purpose,
      anonymous,
    } as any);

    const commitment = await this.commitment(envelopeText as unknown as string);

    return {
      envelope_text: envelopeText as unknown as string,
      commitment,
      bytes: new TextEncoder().encode(envelopeText as unknown as string).length,
    };
  }

  /**
   * Open (decrypt) an envelope using the recipient's secret keys.
   */
  async openPrompt(
    envelopeText: string,
    mlkemSecretKey: string,
    x25519SecretKey: string,
    mlkemPublicKey: string,
    x25519PublicKey: string,
  ): Promise<string> {
    const plaintext = open({
      envelope: envelopeText,
      mlkemSecretKey,
      x25519SecretKey,
      mlkemPublicKey,
      x25519PublicKey,
    } as any);
    return new TextDecoder().decode(plaintext as unknown as Uint8Array);
  }

  /**
   * Inspect an envelope without decrypting.
   */
  async parseEnvelope(envelopeText: string): Promise<Envelope> {
    const parsed = parseEnvelope(envelopeText as any) as any;
    return {
      text: envelopeText,
      commitment: await this.commitment(envelopeText),
      purpose: parsed.purpose,
      chain_id: parsed.chainId ?? this.chainId,
      recipients: parsed.entries?.length ?? 0,
      created_at: Math.floor(Date.now() / 1000),
    };
  }

  /**
   * keccak256 commitment over the envelope text (for on-chain anchor).
   */
  private async commitment(envelopeText: string): Promise<string> {
    const { keccak256, toUtf8Bytes } = await import("ethers");
    return keccak256(toUtf8Bytes(envelopeText));
  }
}

/**
 * Convenience helper: single-recipient seal.
 */
export async function sealForRecipient(
  plaintext: string,
  recipient: Recipient,
  purpose: string = "safe-prompt",
  chainId: string = "qorechain-diana",
): Promise<SealResult> {
  const bridge = new QoreSealBridge(chainId);
  return bridge.sealPrompt(plaintext, [recipient], purpose);
}
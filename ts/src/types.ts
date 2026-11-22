// Safe Prompt — TypeScript type definitions for QoreChain PQC integration.

export interface MlkEmPublicKey {
  /** base64url-encoded ML-KEM-1024 encapsulation key (1568 bytes) */
  mlkem_public_key: string;
  /** base64url-encoded X25519 public key (32 bytes) */
  x25519_public_key?: string;
}

export interface Recipient extends MlkEmPublicKey {
  /** qor1... address or EVM hex address */
  address: string;
}

export interface MlDsaPublicKey {
  /** base64url-encoded ML-DSA-87 public key */
  ml_dsa_public_key: string;
  /** Optional verifying key ID / registry index */
  key_id?: string;
}

export interface Envelope {
  /** "qoreseal:..." base64url envelope text */
  text: string;
  /** keccak256 commitment over the ciphertext */
  commitment: string;
  /** purpose tag, e.g. "chat", "invoice", "team-secret" */
  purpose: string;
  /** chain ID, e.g. "qorechain-diana" */
  chain_id: string;
  /** number of recipients */
  recipients: number;
  /** creation timestamp (unix seconds) */
  created_at: number;
}

export interface KeyRegistration {
  qor1_address: string;
  mlkem_public_key: string;
  x25519_public_key: string;
  ml_dsa_public_key: string;
  registered_at: number;
  tx_hash?: string;
}

export interface SealResult {
  envelope_text: string;
  commitment: string;
  bytes: number;
}

export interface OpenResult {
  plaintext: string;
  envelope: Envelope;
}

export interface HybridSignature {
  secp256k1: string;
  ml_dsa_87: string;
  combined: string;
}
// Safe Prompt — List registered PQC keys from the on-chain registry (Diana testnet)
// Usage: npx tsx scripts/list-keys.ts [qor1...address]

import * as dotenv from "dotenv";
import { ethers } from "ethers";
import { SafePromptOnChain } from "../src/onchain";

dotenv.config();

async function main() {
  const bridge = new SafePromptOnChain();
  const address = process.argv[2] || process.env.QORECHAIN_ADDRESS;

  if (!address) {
    throw new Error("Recipient address required — pass a qor1... address as arg or set QORECHAIN_ADDRESS.");
  }

  const resolved = await bridge.resolveRecipientKeys(address);
  if (!resolved) {
    console.log(`No on-chain PQC key registration found for ${address}.`);
    return;
  }
  console.log(`✅ Registered PQC keys for ${resolved.address}:`);
  console.log(`   ML-KEM-1024: ${resolved.mlkem_public_key.slice(0, 40)}...`);
  console.log(`   X25519:      ${resolved.x25519_public_key.slice(0, 40)}...`);
  console.log(`   ML-DSA-87:  ${resolved.ml_dsa_public_key.slice(0, 40)}...`);
}

main().catch((e) => {
  console.error("❌", e.message);
  process.exit(1);
});
// Safe Prompt — Register PQC keys on-chain (Diana testnet)
// Usage: npx tsx scripts/register-keys.ts
//   env: QORECHAIN_PRIVATE_KEY (or PRIVATE_KEY) with Diana testnet funds
//        QORECHAIN_DIANA_RPC_URL (default: https://diana-rpc.qorechain.io)

import * as dotenv from "dotenv";
import * as fs from "fs";
import * as path from "path";
import { ethers } from "ethers";
import { SafePromptOnChain } from "../src/onchain";

dotenv.config();

function loadKeys() {
  // Prefer the keys file produced by `safe-prompt keys generate --output`
  const keystorePath = process.env.SAFE_PROMPT_KEYS_FILE || path.join(process.env.HOME || "", ".safe-prompt", "keys.json");
  if (fs.existsSync(keystorePath)) {
    const data = JSON.parse(fs.readFileSync(keystorePath, "utf8"));
    return {
      mlkem_public_key: data.mlkem_public,
      x25519_public_key: data.x25519_public,
      ml_dsa_public_key: data.ml_dsa_public || "",
    };
  }
  // Fall back to env vars
  const mlkem = process.env.QORECHAIN_MLKEM_PUBLIC_KEY;
  const x25519 = process.env.QORECHAIN_X25519_PUBLIC_KEY;
  const ml_dsa = process.env.QORECHAIN_ML_DSA_PUBLIC_KEY || "";
  if (!mlkem || !x25519) {
    throw new Error(
      "No PQC keys found. Run 'safe-prompt keys generate --output keys.json' first " +
      "(or set QORECHAIN_MLKEM_PUBLIC_KEY / QORECHAIN_X25519_PUBLIC_KEY)."
    );
  }
  return { mlkem_public_key: mlkem, x25519_public_key: x25519, ml_dsa_public_key: ml_dsa };
}

async function main() {
  const privateKey = process.env.QORECHAIN_PRIVATE_KEY || process.env.PRIVATE_KEY;
  if (!privateKey) {
    throw new Error("QORECHAIN_PRIVATE_KEY (or PRIVATE_KEY) must be set in .env — the wallet needs Diana testnet funds.");
  }
  const wallet = new ethers.Wallet(privateKey);
  console.log(`Registering PQC keys for ${wallet.address} on qorechain-diana (chain 9800)...`);

  const keys = loadKeys();
  const bridge = new SafePromptOnChain();
  const txHash = await bridge.registerKeys(wallet, {
    address: wallet.address,
    ...keys,
  });

  console.log(`✅ Keys registered! Tx: ${txHash}`);
  console.log(`Explorer: https://explorer.diana.qorechain.io/tx/${txHash}`);
}

main().catch((e) => {
  console.error("❌", e.message);
  process.exit(1);
});
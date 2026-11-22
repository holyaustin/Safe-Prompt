// Safe Prompt — Anchor an envelope commitment on-chain (Diana testnet)
// Usage: npx tsx scripts/anchor-envelope.ts <recipient-address> [purpose]
//   env: QORECHAIN_ANCHOR_CONTRACT_ADDRESS (from contracts/scripts/deploy.ts)
//        QORECHAIN_PRIVATE_KEY (or PRIVATE_KEY) with Diana testnet funds

import * as dotenv from "dotenv";
import * as fs from "fs";
import * as path from "path";
import { ethers } from "ethers";
import { SafePromptOnChain, ANCHOR_ADDRESS } from "../src/onchain";

dotenv.config();

function loadEnvelopeText(): string {
  // Prefer the last envelope written by the CLI/TUI, else a sample commitment
  const envPath = process.env.SAFE_PROMPT_LAST_ENVELOPE || path.join(process.env.HOME || "", ".safe-prompt", "last-envelope.txt");
  if (fs.existsSync(envPath)) {
    return fs.readFileSync(envPath, "utf8").trim();
  }
  return "qoreseal:sample-envelope-" + Date.now();
}

async function main() {
  if (!ANCHOR_ADDRESS) {
    throw new Error("QORECHAIN_ANCHOR_CONTRACT_ADDRESS not set. Deploy first: cd contracts && npx hardhat run scripts/deploy.ts --network diana");
  }
  const privateKey = process.env.QORECHAIN_PRIVATE_KEY || process.env.PRIVATE_KEY;
  if (!privateKey) {
    throw new Error("QORECHAIN_PRIVATE_KEY (or PRIVATE_KEY) must be set in .env.");
  }
  const recipient = process.argv[2] || process.env.QORECHAIN_RECIPIENT;
  if (!recipient) {
    throw new Error("Recipient address required — pass as arg or set QORECHAIN_RECIPIENT.");
  }
  const purpose = process.argv[3] || "safe-prompt";

  const wallet = new ethers.Wallet(privateKey);
  const bridge = new SafePromptOnChain();

  // Commitment = keccak256 of the envelope text (never stores the ciphertext on-chain)
  const envelopeText = loadEnvelopeText();
  const commitment = ethers.keccak256(ethers.toUtf8Bytes(envelopeText));
  console.log(`Anchoring envelope commitment ${commitment.slice(0, 18)}... to ${ANCHOR_ADDRESS}`);
  console.log(`   recipient: ${recipient}`);
  console.log(`   purpose:   ${purpose}`);

  const anchor = await bridge.anchorEnvelope(commitment, purpose, wallet.address, [recipient], wallet, ANCHOR_ADDRESS);
  console.log(`✅ Envelope anchored via ${anchor}`);
}

main().catch((e) => {
  console.error("❌", e.message);
  process.exit(1);
});
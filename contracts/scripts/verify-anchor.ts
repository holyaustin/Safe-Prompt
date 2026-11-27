import { ethers } from "hardhat";
import "dotenv/config";

async function main() {
  const addr = process.env.QORECHAIN_ANCHOR_CONTRACT_ADDRESS!;
  const provider = new ethers.JsonRpcProvider(process.env.QORECHAIN_DIANA_RPC_URL);
  console.log("Anchor contract:", addr);
  const code = await provider.getCode(addr);
  console.log("Contract deployed (bytecode size):", code.length > 2 ? `${(code.length-2)/2} bytes` : "NOT FOUND");

  const anchor = new ethers.Contract(addr, [
    "function owner() view returns (address)",
    "function envelopeCount() view returns (uint256)",
  ], provider);
  console.log("Owner:", await anchor.owner());
  console.log("Envelope count:", (await anchor.envelopeCount()).toString());
}
main().catch((e) => { console.error("❌", e.message); process.exit(1); });

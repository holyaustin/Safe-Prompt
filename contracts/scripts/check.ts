// Quick check: deployer address + balance on Diana
import { ethers } from "hardhat";

async function main() {
  const [signer] = await ethers.getSigners();
  console.log("Deployer:", signer.address);
  const bal = await ethers.provider.getBalance(signer.address);
  console.log("Balance:", ethers.formatEther(bal), "ETH");
  const net = await ethers.provider.getNetwork();
  console.log("Chain ID:", net.chainId.toString());
}

main().catch((e) => {
  console.error("❌", e.message);
  process.exit(1);
});
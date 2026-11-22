import { ethers } from "hardhat";
import * as dotenv from "dotenv";
dotenv.config();

async function main() {
  const SafePromptAnchor = await ethers.getContractFactory("SafePromptAnchor");
  const contract = await SafePromptAnchor.deploy();
  await contract.waitForDeployment();

  console.log(`SafePromptAnchor deployed at: ${contract.target}`);
  console.log(`Owner: ${contract.owner()}`);

  // Get transaction hash of deploy
  const receipt = await ethers.provider.getTransactionReceipt(contract.deploymentTransaction().hash);
  if (receipt) {
    console.log(`Deploy tx: ${receipt.transactionHash}`);
  }

  return contract;
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });

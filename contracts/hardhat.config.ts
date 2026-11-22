import * as dotenv from "dotenv";
dotenv.config();

import { HardhatUserConfig } from "hardhat/config";
import "@nomicfoundation/hardhat-toolbox";
import "@nomicfoundation/hardhat-ethers";

const config: HardhatUserConfig = {
  solidity: {
    version: "0.8.24",
    settings: {
      optimizer: {
        enabled: true,
        runs: 200,
      },
    },
  },
  paths: {
    sources: "./src",
    tests: "./test",
    cache: "./cache",
    artifacts: "./artifacts",
  },
  networks: {
    hardhat: {
      chainId: 31337,
    },
    diana: {
      url: process.env.QORECHAIN_DIANA_RPC_URL || "https://diana-rpc.qorechain.io",
      chainId: 9800,
      accounts: process.env.PRIVATE_KEY ? [process.env.PRIVATE_KEY] : [],
    },
  },
  etherscan: {
    apiKey: {
      qorechain: process.env.QORECHAIN_EXPLORER_API_KEY || "",
    },
    customChains: [
      {
        network: "qorechain-diana",
        chainId: 9800,
        urls: {
          apiURL: "https://api.diana.qorechain.io/explorer/api",
          browserURL: "https://explorer.diana.qorechain.io",
        },
      },
    ],
  },
};

export default config;

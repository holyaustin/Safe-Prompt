# Safe Prompt

**Post-Quantum Encrypted LLM Prompt & Secret Sharing for QoreChain**  
*Hackathon: QoreChain "Build Before Q-Day" — Category: Encrypted Apps*

---

## Overview

`Safe Prompt` is a local-first CLI/TUI application that enables developers and teams to share **confidential LLM prompts, secrets, and redaction envelopes** using **post-quantum cryptography** on the **QoreChain `diana` testnet** (EVM Chain ID `9800`).

### Core Capabilities
| Feature | Technology |
|---------|------------|
| **Prompt/Secret Encryption** | `ML-KEM-1024` (FIPS 203) via QoreSeal — multi-recipient envelopes for `qor1...` addresses |
| **Key Binding & Verification** | `ML-DSA-87` (FIPS 204) via QoreSign — on-chain registry with hybrid `secp256k1 + ML-DSA-87` signatures |
| **Fail-Closed Secret Detection** | Regex + entropy + Luhn/IBAN/SSN validators — outbound guard blocks any leak |
| **Local-First TUI** | Textual 3-pane UI (Local View \| Redacted Wire View \| QoreChain Vault Status) |
| **Web-Accessible TUI** | `textual-web` — same app served over WebSockets for judges/remote access |
| **OpenAI-Compatible Gateway** | FastAPI proxy with streaming rehydration — plug into any LLM client |
| **On-Chain Audit Trail** | Hardhat + Solidity — envelope commitment registry on QoreChain Diana |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            SAFE PROMPT ARCHITECTURE                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────┐     ┌──────────────────┐     ┌───────────────────────┐  │
│  │   CLIENT     │────▶│   PYTHON GATEWAY  │────▶│   UPSTREAM LLM API    │  │
│  │  (OpenAI     │     │   (FastAPI)       │     │   (OpenRouter, etc.)  │  │
│  │   compatible)│     │                   │     │                       │  │
│  └──────────────┘     │  ┌────────────┐   │     └───────────────────────┘  │
│                       │  │  DETECTOR  │   │                                │
│         ▲             │  │ (fail-closed)   │                                │
│         │             │  └──────┬───────┘   │                                │
│         │             │         │           │                                │
│         │        ┌────▼─────┐  │  ┌────────▼────────┐                       │
│         │        │ REDACTOR │──┼─▶│  REHYDRATOR     │                       │
│         │        │ (ML-KEM  │  │  │  (stream-safe)  │                       │
│         │        │  1024)   │  │  └────────┬────────┘                       │
│         │        └────┬─────┘  │           │                                │
│         │             │        │           │                                │
│         │      ┌──────▼──────┐ │    ┌──────▼──────┐                        │
│         │      │  RUST CORE  │ │    │ TEXTUAL TUI │                        │
│         │      │ (qorechain- │ │    │  (3 panes)  │                        │
│         │      │  qoreseal)  │ │    │             │                        │
│         │      │  zeroize    │ │    │ textual-web │◀─── Browser / Judges    │
│         │      └──────┬──────┘ │    └─────────────┘                        │
│         │             │        │                                           │
│         │      ┌──────▼──────┐ │                                           │
│         └─────▶│ TYPESESCRIPT│ │                                           │
│                │ BRIDGE      │ │                                           │
│                │ (@qorechain/│ │                                           │
│                │  qoresign)  │ │                                           │
│                │             │ │                                           │
│                │  ┌───────┐  │ │                                           │
│                └─▶│ HARDHAT│──┘                                           │
│                   │ SOLIDITY│                                            │
│                   │ CONTRACT│                                            │
│                   └─────────┘                                            │
│                         │                                                │
│                         ▼                                                │
│                ┌───────────────┐                                        │
│                │  QORECHAIN    │                                        │
│                │  DIANA TESTNET│                                        │
│                │  (Chain 9800) │                                        │
│                └───────────────┘                                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Polyglot Language Map

| Layer | Language | Key Libraries | Responsibility |
|-------|----------|---------------|----------------|
| **Cryptographic Core** | Rust | `qorechain-qoreseal`, `qorechain-pqc`, `zeroize`, `PyO3` | `ML-KEM-1024` encapsulation/decapsulation, memory-zeroized key custody |
| **TUI, Gateway, Detection** | Python | `textual`, `textual-web`, `fastapi`, `httpx`, `qorechain-sdk`, `qorechain-qoreseal` | 3-pane UI, OpenAI-compatible proxy, fail-closed detection, envelope management |
| **On-Chain Bridge** | TypeScript | `@qorechain/sdk`, `@qorechain/qoresign`, `@qorechain/qoreseal`, `viem`, `hardhat` | Hybrid signing, `ML-DSA-87` key registration, KEM public key registry, transaction simulation |
| **Smart Contracts** | Solidity | `hardhat`, `qorechain-asset-kit`, `forge-std` | Envelope commitment registry, multi-recipient access control, revocation |

---

## Quick Start

### Prerequisites
- Rust 1.78+ (`cargo`)
- Python 3.10+ (`pip`, `venv`)
- Node.js 20+ (`npm`, `npx`)
- Foundry (`forge`) — optional, for Solidity testing

### Installation

```bash
# 1. Clone and enter
cd safe-prompt

# 2. Install all dependencies (Rust core + Python + TypeScript + Hardhat)
make install-all

# 3. Configure environment
cp .env.example .env
# Edit .env with your QoreChain Diana RPC, upstream LLM API key, etc.

# 4. Register your PQC keys on-chain (one-time)
make register-keys

# 5. Run the TUI locally
make tui

# 6. OR serve the TUI on the web for judges/remote access
make serve-web
# Opens at http://localhost:8080 — full TUI in browser
```

### Usage

```bash
# Local TUI (3 panes: You | Wire | Vault)
safe-prompt tui

# Web TUI (same app, browser-accessible)
safe-prompt serve-web --port 8080

# Headless gateway only (for API clients)
safe-prompt serve --port 8787

# CLI secret envelope operations
safe-prompt envelope create --recipients qor1abc...,qor1def... --prompt "API key: sk-live-..."
safe-prompt envelope open --envelope <base64>

# On-chain key management
safe-prompt keys register --kem --dsa
safe-prompt keys list --address qor1...
```

---

## QoreChain Integration

| Component | QoreChain Kit | Version |
|-----------|---------------|---------|
| Rust PQC Core | `qorechain-pqc` | 0.2.3 |
| Rust QoreSeal (ML-KEM) | `qorechain-qoreseal` | 0.1.0 |
| Rust QoreSign (ML-DSA) | `qorechain-qoresign` | 0.2.0 |
| Rust SDK | `qorechain-sdk` | 0.15.0 |
| Python SDK | `qorechain-sdk` | 0.15.0 |
| Python QoreSeal | `qorechain-qoreseal` | 0.1.0 |
| TypeScript SDK | `@qorechain/sdk` | 0.14.0 |
| TypeScript QoreSign | `@qorechain/qoresign` | 0.2.0 |
| TypeScript QoreSeal | `@qorechain/qoreseal` | 0.1.0 |
| TypeScript EVM | `@qorechain/evm` | 0.14.0 |
| Solidity Asset Kit | `qorechain/qorechain-asset-kit` | v0.1.0 |

**Network:** `qorechain-diana` — EVM Chain ID `9800`  
**RPC:** `https://diana-rpc.qorechain.io` (verify via MCP/CLI)

---

## Security Model

- **100% Client-Side Encryption**: Secrets never leave the machine in plaintext. `ML-KEM-1024` encapsulation happens in Rust core with `zeroize` memory protection.
- **Fail-Closed Detection**: Dual-layer guard — regex/entropy detection + outbound exact-match verification. Any leak → HTTP 422, request blocked.
- **On-Chain Key Binding**: `ML-DSA-87` public keys registered on-chain via hybrid signatures (`secp256k1` + `ML-DSA-87`). Recipient keys resolved from QoreSeal registry.
- **Streaming-Safe Rehydration**: SSE fragments like `[EMA` + `IL_1]` are buffered and never exposed to the client until fully resolved.
- **Audit Trail**: Encrypted envelope commitments anchored on-chain via Solidity contract — tamper-proof log of what was shared, with whom, and when.

---

## Project Structure

```
safe-prompt/
├── AI_USAGE.md              # AI-assisted workflow documentation
├── LICENSE                  # MIT
├── Makefile                 # Unified build commands
├── README.md                # This file
├── .env.example             # Environment template
├── core/                    # Rust cryptographic core
│   ├── Cargo.toml
│   └── src/
│       └── lib.rs           # PyO3 bindings: ML-KEM-1024, zeroize
├── py/                      # Python TUI, Gateway, Detection
│   ├── pyproject.toml
│   └── safe_prompt/
│       ├── __init__.py
│       ├── cli.py           # Typer CLI entrypoint
│       ├── config.py        # Pydantic settings
│       ├── crypto/          # Rust core Python bindings
│       ├── detect/          # Secret detection engine
│       │   ├── engine.py
│       │   └── rules.yaml
│       ├── gateway/         # FastAPI proxy + redaction
│       │   ├── app.py
│       │   ├── redact.py
│       │   └── rehydrate.py
│       ├── tui/             # Textual TUI app
│       │   ├── app.py
│       │   ├── panes.py
│       │   └── client.py
│       └── vault/           # Envelope store + QoreChain sync
│           ├── manager.py
│           └── store.py
├── ts/                      # TypeScript On-Chain Bridge
│   ├── package.json
│   ├── tsconfig.json
│   ├── hardhat.config.ts    # Hardhat config for QoreChain Diana
│   ├── src/
│   │   ├── onchain.ts       # Hybrid signing, key registration
│   │   ├── qoreseal.ts      # KEM key registry interaction
│   │   └── types.ts
│   └── test/                # Hardhat/TypeScript tests
│       └── onchain.test.ts
└── contracts/               # Solidity Smart Contracts
    ├── hardhat.config.ts
    ├── package.json
    ├── src/
    │   └── SafePromptAnchor.sol
    └── test/
        └── SafePromptAnchor.test.ts
```

---

## License

MIT — see `LICENSE` file.

## Credits

Built with QoreChain PQC Kits:
- `@qorechain/sdk`, `qorechain-pqc`, `qorechain-qoreseal`, `qorechain-qoresign`
- `@qorechain/mcp`, `qorechain-asset-kit`
- `textual`, `textual-web`, `fastapi`, `viem`, `hardhat`
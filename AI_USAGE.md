# AI Usage Documentation

**Safe Prompt** — QoreChain "Build Before Q-Day" Hackathon  
*Special Award Target: Best AI-Native Build*

This file documents our AI-assisted development workflow, generated modules, and human architectural review.

---

## AI-Assisted Workflow

| Phase | AI Role | Human Review |
|-------|---------|--------------|
| Architecture design | Proposed polyglot structure (Rust core / Python TUI / TS bridge / Solidity), data flow mapping | Approved directory layout and language division |
| QoreChain kit research | Researched `qorechain-pqc 0.2.3`, `qorechain-qoreseal 0.1.0`, `qorechain-qoresign 0.2.0`, `qorechain-sdk 0.15.0` on crates.io/PyPI/npm | Verified package versions against official kits page |
| Code scaffolding | Generated all source files: Rust core, Python modules, TypeScript bridge, Solidity contract, Hardhat config, tests | Manual audit of every generated file before approval |
| TUI ↔ Web bridge | Identified `textual-web` as the mechanism to serve the same Textual app remotely | Confirmed `textual-web 0.8.0` exists on PyPI |

---

## AI-Generated Modules

The following modules were generated with AI assistance and **reviewed** by the human architect:

1. **`core/src/lib.rs`** — Rust PyO3 bindings for `ML-KEM-1024` encapsulation/decapsulation using `qorechain-qoreseal`, with `zeroize` memory protection.
2. **`py/safe_prompt/detect/engine.py`** — Secret detection engine (regex + validators + fail-closed guard).
3. **`py/safe_prompt/gateway/redact.py`** — Redaction/rehydration with streaming-safe SSE handling and outbound leak guard.
4. **`py/safe_prompt/tui/app.py`** — Textual 3-pane TUI app (local view / wire view / vault status).
5. **`py/safe_prompt/cli.py`** — Typer-based CLI entrypoint.
6. **`ts/src/onchain.ts`** — TypeScript bridge for hybrid `ML-DSA-87` signing and KEM key registry.
7. **`contracts/src/SafePromptAnchor.sol`** — Solidity envelope commitment registry.
8. **`contracts/test/SafePromptAnchor.test.ts`** — Hardhat TypeScript tests for the anchor contract.
9. **`Makefile`, `.env.example`, `README.md`** — Build/configuration scaffolding.

---

## Human Architectural Review Checklist

- [x] Clean-room rule: All code written from scratch — no copying from `VeilProxy`
- [x] PQC requirements: `ML-KEM-1024` encryption, `ML-DSA-87` key binding, 100% client-side encryption
- [x] QoreChain integration: `qor1...` address resolution, Diana testnet Chain ID 9800
- [x] Fail-closed philosophy: Outbound guard blocks any leak before forwarding
- [x] Memory safety: `zeroize` for decrypted keys — nothing touches disk
- [x] Remote accessibility: `textual-web` serves TUI over browser for judges
- [x] Test coverage: Rust unit tests, Python pytest suite, Hardhat TypeScript tests
- [x] Documentation: `AI_USAGE.md`, `README.md`, `LICENSE`

---

## How to Regenerate / Extend

To regenerate any AI-assisted module:
1. Review the architectural pattern in the corresponding file
2. Write fresh code following the polyglot conventions (Rust for crypto, Python for TUI/gateway, TypeScript for on-chain, Solidity for contracts)
3. Add tests alongside each module
4. Update `AI_USAGE.md` with the new module name and review status
# Safe Prompt — Step-by-Step Functional Test Guide

**Version:** 1.0  
**Project root:** `/home/augustineonuora/Dapps-Empty/2026/Nov2026/safe-prompt`  
**Contract on Diana testnet:** `0xb22d64B05F09044c36a052556AC2ddB073bd19cC`

This guide walks through **every** functional layer of Safe Prompt from first principles. Run each part in order. Nothing is assumed — each step verifies its own prerequisite before proceeding.

---

## Before You Begin: Environment

You need two terminals open:
- **Terminal A** — runs the FastAPI gateway (and later the web TUI).
- **Terminal B** — runs the CLI tests, TUI, and curl checks.

All commands below are run from the project root:

```bash
cd /home/augustineonuora/Dapps-Empty/2026/Nov2026/safe-prompt
```

---

## Part 0 — Prerequisites (must pass before anything else)

### Step 0.1 — Activate Python virtual environment

```bash
source .venv/bin/activate
```

**Expected:** shell prompt gains a `(.venv)` prefix. If it fails, run:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e . pytest pytest-asyncio
```

### Step 0.2 — Verify Python version

```bash
python3 --version
```

**Expected:** `Python 3.10.x` or higher (e.g. `Python 3.10.12`).  
**Fail:** anything below 3.10 → re-create venv with `python3.10 -m venv .venv`.

### Step 0.3 — Verify Rust crypto core importable

```bash
python3 -c "import safe_prompt_core; print('Rust core OK:', safe_prompt_core.__file__)"
```

**Expected:** `Rust core OK: .../site-packages/safe_prompt_core/__init__.py`

### Step 0.4 — Verify Python package imports

```bash
python3 -c "
from safe_prompt.detect.engine import Detector
from safe_prompt.gateway.redact import Redactor, LeakBlocked
from safe_prompt.crypto import SafePromptCrypto
from safe_prompt.config import load_settings
print('All Python imports OK')
"
```

**Expected:** `All Python imports OK` (no traceback).

### Step 0.5 — Run `safe-prompt doctor`

```bash
safe-prompt doctor
```

**Expected:** six green checkmarks:

```
  ✅ Python >= 3.10
  ✅ Rust core (ML-KEM-1024 via QoreSeal) — ...
  ✅ qoreseal (ML-KEM-1024 + X25519) installed
  ✅ FastAPI installed
  ✅ Textual (TUI framework) installed
  ✅ textual-web (web TUI server) installed

All checks passed!
```

### Step 0.6 — Verify TypeScript toolchain

```bash
cd ts && npx tsc --noEmit && echo "TSC_OK" && cd ..
```

**Expected:** `TSC_OK` (no compilation errors).

### Step 0.7 — Verify Solidity contract compiles

```bash
cd contracts && npx hardhat compile && echo "HARDHAT_COMPILE_OK" && cd ..
```

**Expected:** `Hardhat Compile OK` / `Compiled 1 Solidity file successfully` followed by `HARDHAT_COMPILE_OK`.

### Step 0.8 — Verify `.env` contains required keys

```bash
grep -E "SAFE_PROMPT_UPSTREAM_LLM_URL|SAFE_PROMPT_UPSTREAM_API_KEY|SAFE_PROMPT_DEFAULT_MODEL|QORECHAIN_ANCHOR_CONTRACT_ADDRESS" .env
```

**Expected:** four lines present. `SAFE_PROMPT_UPSTREAM_API_KEY` should start with `sk-or-v1-` (OpenRouter). `QORECHAIN_ANCHOR_CONTRACT_ADDRESS` must equal `0xb22d64B05F09044c36a052556AC2ddB073bd19cC`.

> **Do not proceed past Part 0 until every step above passes.**

---

## Part 1 — Detection Engine (no network, no keys)

Goal: confirm secrets are detected before they ever leave the machine.

### Step 1.1 — Detect API keys, cards, emails, phones, JWTs

```bash
python3 -c "
from safe_prompt.detect.engine import Detector
d = Detector()
tests = [
    ('API key', 'My API key is sk-proj-Q8x2LmN4vB7cR1tY9uZ3aW5eD6fG0hJk'),
    ('Card',      'Credit card: 4111 1111 1111 1111'),
    ('Email+Phone','Email: test@example.com, Phone: +1234567890'),
    ('DB URL',    'DATABASE_URL=postgres://admin:pass@localhost:5432/db'),
    ('JWT',       'JWT: eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N'),
]
ok = True
for label, t in tests:
    matches = d.find(t)
    kinds = [m.kind for m in matches]
    print(f'{label:12s}: {kinds}')
    if not matches:
        ok = False
assert ok, 'Some secrets were not detected'
print('DETECTION TEST PASSED')
"
```

**Expected:** each kind printed and non-empty:

```
API key     : ['APIKEY']
Card        : ['CARD']
Email+Phone : ['EMAIL', 'PHONE']
DB URL      : ['URLCRED']
JWT         : ['JWT']
DETECTION TEST PASSED
```

### Step 1.2 — Confirm no false positives on clean text

```bash
python3 -c "
from safe_prompt.detect.engine import Detector
d = Detector()
clean = 'Hello world, this is a safe prompt with no secrets at all.'
matches = d.find(clean)
print('Clean text matches:', [m.kind for m in matches])
assert len(matches) == 0, 'False positive on clean text'
print('NO FALSE POSITIVES TEST PASSED')
"
```

**Expected:** `Clean text matches: []` followed by `NO FALSE POSITIVES TEST PASSED`.

---

## Part 2 — Redaction + Fail-Closed Guard (no network)

Goal: confirm secrets are replaced with placeholders and that leaks block outbound traffic.

### Step 2.1 — Redact text locally

```bash
python3 -c "
from safe_prompt.gateway.redact import Redactor
from safe_prompt.detect.engine import Detector
from safe_prompt.crypto import SafePromptCrypto

d = Detector()
crypto = SafePromptCrypto(use_rust=False)
redactor = Redactor(detector=d, crypto=crypto, session='test-redact')

text = 'API key: sk-proj-Q8x2LmN4vB7cR1tY9uZ3aW5eD6fG0hJk and card 4111 1111 1111 1111'
redacted = redactor.redact_text(text)
print('REDACTED:', redacted)
assert 'sk-proj' not in redacted
assert '4111' not in redacted
assert '[APIKEY_1]' in redacted
assert '[CARD_1]' in redacted
print('REDACTION TEST PASSED')
"
```

**Expected:** `REDACTED: API key: [APIKEY_1] and card [CARD_1]` followed by `REDACTION TEST PASSED`.

### Step 2.2 — Fail-closed guard blocks leaked payload

```bash
python3 -c "
from safe_prompt.gateway.redact import Redactor, LeakBlocked, check_outbound
from safe_prompt.detect.engine import Detector
from safe_prompt.crypto import SafePromptCrypto

d = Detector()
crypto = SafePromptCrypto(use_rust=False)
redactor = Redactor(detector=d, crypto=crypto, session='test-guard')

# This payload still contains a raw secret in a message body
bad = {'messages': [{'content': 'secret: sk-proj-Q8x2LmN4vB7cR1tY9uZ3aW5eD6fG0hJk'}]}
try:
    check_outbound(bad, redactor.values, d)
    print('FAIL: guard did not block')
except LeakBlocked as e:
    print('FAIL-CLOSED OK:', e)
"
```

**Expected:** `FAIL-CLOSED OK: ...` (message mentions leak blocked).

---

## Part 3 — Envelope Workflow — ML-KEM-1024 (no network)

Goal: confirm end-to-end post-quantum seal/open roundtrip works with the Rust core.

### Step 3.1 — Generate keys, seal, open

```bash
python3 -c "
from safe_prompt.crypto import SafePromptCrypto

crypto = SafePromptCrypto(use_rust=True)

# 1. Generate keys
mlkem_pub, x25519_pub, mlkem_sec, x25519_sec = crypto.generate_keys()
print('Keys:', len(mlkem_pub), 'bytes ML-KEM pub,', len(x25519_pub), 'bytes X25519 pub')
assert len(mlkem_pub) == 1568
assert len(x25519_pub) == 32

# 2. Seal envelope
recipients = [{'mlkem_public_key': mlkem_pub, 'x25519_public_key': x25519_pub}]
envelope = crypto.seal('qorechain-diana', 'chat', recipients, b'My secret: sk-live-abc123')
print('Envelope length:', len(envelope))

# 3. Open envelope
plaintext = crypto.open('qorechain-diana', 'chat', envelope, mlkem_sec, x25519_sec, mlkem_pub, x25519_pub)
print('Opened plaintext:', plaintext.decode())
assert plaintext == b'My secret: sk-live-abc123'
print('ENVELOPE ROUNDTRIP OK')
"
```

**Expected:** key sizes match, envelope created, plaintext recovered exactly:

```
Keys: 1568 bytes ML-KEM pub, 32 bytes X25519 pub
Envelope length: ...
Opened plaintext: My secret: sk-live-abc123
ENVELOPE ROUNDTRIP OK
```

### Step 3.2 — Wrong secret key fails to open (fail-closed crypto)

```bash
python3 -c "
from safe_prompt.crypto import SafePromptCrypto
crypto = SafePromptCrypto(use_rust=True)

mlkem_pub, x25519_pub, mlkem_sec, x25519_sec = crypto.generate_keys()
recipients = [{'mlkem_public_key': mlkem_pub, 'x25519_public_key': x25519_pub}]
envelope = crypto.seal('qorechain-diana', 'chat', recipients, b'top secret')

# Tamper with the secret key
bad_sec = b'\x00' * len(mlkem_sec)
try:
    crypto.open('qorechain-diana', 'chat', envelope, bad_sec, x25519_sec, mlkem_pub, x25519_pub)
    print('FAIL: wrong key should not decrypt')
except Exception as e:
    print('WRONG KEY REJECTED OK:', type(e).__name__)
"
```

**Expected:** `WRONG KEY REJECTED OK: <ExceptionType>` (decryption fails).

---

## Part 4 — FastAPI Gateway (OpenRouter live)

Prerequisite: `.env` contains a real `SAFE_PROMPT_UPSTREAM_API_KEY` starting with `sk-or-v1-`.

Start the gateway in **Terminal A** and leave it running:

```bash
source .venv/bin/activate
safe-prompt serve --host 127.0.0.1 --port 8787
```

**Expected:** Uvicorn startup logs ending with `Uvicorn running on http://127.0.0.1:8787`.

### Step 4.1 — Health check

From **Terminal B**:

```bash
curl -s http://127.0.0.1:8787/health | python3 -m json.tool
```

**Expected:**

```json
{
    "status": "ok",
    "version": "0.1.0",
    "crypto_backend": "rust",
    "network": "qorechain-diana"
}
```

### Step 4.2 — List models (proxies OpenRouter)

```bash
curl -s http://127.0.0.1:8787/v1/models | python3 -m json.tool | head -30
```

**Expected:** JSON array of model objects from OpenRouter (non-empty `data` array). If OpenRouter key is invalid, you may get an empty array — that is acceptable for this step.

### Step 4.3 — Redact-only preview (no upstream call needed)

```bash
curl -s -X POST http://127.0.0.1:8787/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"safe-prompt-redact","messages":[{"role":"user","content":"API key sk-proj-Q8x2LmN4vB7cR1tY9uZ3aW5eD6fG0hJk and card 4111 1111 1111 1111"}]}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['choices'][0]['message']['content'])"
```

**Expected:** `API key: [APIKEY_1] and card [CARD_1]` — secrets replaced, no upstream LLM called.

### Step 4.4 — Live chat through OpenRouter (redacted → upstream → rehydrated)

```bash
curl -s -X POST http://127.0.0.1:8787/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"safe-prompt","messages":[{"role":"user","content":"My API key is sk-proj-Q8x2LmN4vB7cR1tY9uZ3aW5eD6fG0hJk, please say hello back"}]}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['choices'][0]['message']['content'])"
```

**Expected:** assistant response text (e.g. `Hello!`). Crucially, the raw `sk-proj-...` string must **not** appear in the upstream request — it is replaced by `[APIKEY_1]` server-side before forwarding.

> If you get HTTP 401, your OpenRouter key is invalid or has no credits. Fix `SAFE_PROMPT_UPSTREAM_API_KEY` in `.env` and restart the gateway.

### Step 4.5 — Fail-closed: raw secret in outbound → HTTP 422

```bash
curl -s -o /dev/null -w "HTTP %{http_code}\n" -X POST http://127.0.0.1:8787/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"safe-prompt","messages":[{"role":"user","content":"leak sk-proj-Q8x2LmN4vB7cR1tY9uZ3aW5eD6fG0hJk"}]}'
```

**Expected:** `HTTP 422` (fail-closed block).

### Step 4.6 — Streaming works and is rehydrated

```bash
curl -s -N -X POST http://127.0.0.1:8787/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"safe-prompt","stream":true,"messages":[{"role":"user","content":"Say hello in two words"}]}' \
  | grep -c "data:"
```

**Expected:** a count ≥ 2 (at least one content chunk plus `[DONE]`). No traceback or crash.

> Keep the gateway running in Terminal A for Parts 5–6.

---

## Part 5 — Textual TUI (local terminal)

Prerequisite: gateway running on `127.0.0.1:8787` from Part 4.

### Step 5.1 — Launch TUI

From **Terminal B**:

```bash
safe-prompt tui
```

**Expected:** a 3-pane Textual app opens:
- Pane ① "What You See" — your plaintext input
- Pane ② "Wire" — redacted placeholders (`[APIKEY_1]`, etc.)
- Pane ③ "QoreChain Vault" — on-chain status

### Step 5.2 — Slash commands

Inside the running TUI, type each command and observe:

| Command | Expected behavior |
|---|---|
| `/help` | Lists available slash commands |
| `/demo 1` | Sends a fake-data test prompt with embedded secrets |
| `/models` | Shows available models from gateway |
| `/lock` | Locks session (clears decrypted keys from memory) |
| `/unlock` | Unlocks / re-derives keys |
| `/copy` | Copies current wire text to clipboard |
| `/clear` | Clears chat history |
| `/session tui` | Sets session name to `tui` |

**Verification:** after `/demo 1`, Pane ① shows the raw test text; Pane ② shows `[APIKEY_1]` / `[CARD_1]` placeholders; Pane ③ shows QoreChain network `qorechain-diana` chain 9800.

Exit the TUI with `q` or `Ctrl-C`.

---

## Part 6 — Web TUI (browser-based, for judges)

Prerequisite: gateway running on `127.0.0.1:8787` from Part 4.

### Step 6.1 — Start web TUI server

From **Terminal A** (or a new terminal), stop the plain gateway if you want the same port, or use a different port:

```bash
source .venv/bin/activate
safe-prompt serve-web --host 0.0.0.0 --port 8080
```

**Expected:** `Starting Safe Prompt web TUI on http://0.0.0.0:8080` and textual-web listening.

### Step 6.2 — Open in browser

Navigate to:

```
http://localhost:8080
```

**Expected:** the same 3-pane Textual TUI rendered in the browser over WebSockets. You can type `/help`, `/demo 1`, etc., exactly as in the local TUI.

> For remote judges, bind to `0.0.0.0` and share `http://<your-ip>:8080`. Ensure port 8080 is reachable (firewall / cloud security group).

Stop with `Ctrl-C`.

---

## Part 7 — Smart Contract (Hardhat + Diana testnet)

Prerequisite: `contracts/.env` contains `PRIVATE_KEY` with Diana testnet funds and `QORECHAIN_ANCHOR_CONTRACT_ADDRESS=0xb22d64B05F09044c36a052556AC2ddB073bd19cC`.

### Step 7.1 — Run Hardhat tests (local in-memory network)

```bash
cd contracts && npx hardhat test
```

**Expected:** 8 tests passing:

```
  SafePromptAnchor
    ✅ deploy
    ✅ seal
    ✅ authorize
    ✅ revoke
    ✅ unauthorized access
    ✅ zero commitment revert
    ✅ re-seal revoked reverts
    ✅ anchorRoot

  8 passing
```

### Step 7.2 — Verify deployed contract on Diana

```bash
cd contracts && npx hardhat console --network diana
```

Inside the console:

```javascript
const SafePromptAnchor = await ethers.getContractFactory("SafePromptAnchor");
const contract = await SafePromptAnchor.at("0xb22d64B05F09044c36a052556AC2ddB073bd19cC");
console.log("Owner:", await contract.owner());
console.log("Envelope count:", await contract.envelopeCount());
.exit
```

**Expected:** `Owner:` prints `0x099DA5ABAA1B34A01662C1eAD7306D7481710118` (or the deployer address); `Envelope count:` prints a number. Exit the console with `.exit`.

> If the RPC returns EVM authorization window exhaustion, wait a minute and retry — this is a Diana testnet rate limit, not a contract bug.

---

## Part 8 — TypeScript On-Chain Bridge

Prerequisite: `ts/.env` (or shell env) has `QORECHAIN_DIANA_RPC_URL=https://evm-testnet.qore.host` and `QORECHAIN_PRIVATE_KEY` with funds.

### Step 8.1 — Connect to Diana and read latest block

```bash
cd ts && npx tsx src/onchain.ts
```

**Expected:** `Connected to qorechain-diana. Latest block: <number>` and `Chain ID: 9800`.

### Step 8.2 — Anchor an envelope commitment

Generate an envelope locally first (from Part 3.1), compute its keccak256, then anchor:

```bash
npx tsx scripts/anchor-envelope.ts
```

> The scripts reference `ANCHOR_ADDRESS` from `process.env.QORECHAIN_ANCHOR_CONTRACT_ADDRESS`, which is already wired to `0xb22d64B05F09044c36a052556AC2ddB073bd19cC`.

**Expected:** transaction sent to Diana; commitment recorded in `SafePromptAnchor`.

> **Known stubs:** `registerKeys`, `resolveRecipientKeys`, and `verifySignature` in `ts/src/onchain.ts` are placeholders (return zero hash / null / true). Only `anchorEnvelope` is fully implemented against the deployed contract. This does not block the demo flow.

---

## Part 9 — End-to-End Checklist (run all, in order)

| # | Test | Command | Pass criterion |
|---|------|---------|----------------|
| 1 | Python version | `python3 --version` | ≥ 3.10 |
| 2 | Doctor | `safe-prompt doctor` | All ✅ |
| 3 | Detection | Part 1.1 / 1.2 | All secrets found; clean text = 0 matches |
| 4 | Redaction | Part 2.1 | `sk-proj` → `[APIKEY_1]`, card → `[CARD_1]` |
| 5 | Fail-closed guard | Part 2.2 | `LeakBlocked` raised |
| 6 | Envelope roundtrip | Part 3.1 | Plaintext recovered exactly |
| 7 | Wrong key rejected | Part 3.2 | Exception raised |
| 8 | Gateway health | Part 4.1 | `{"status":"ok", ...}` |
| 9 | Redact-only endpoint | Part 4.3 | Placeholders returned, no upstream |
| 10 | Live OpenRouter chat | Part 4.4 | Assistant response received |
| 11 | Fail-closed HTTP 422 | Part 4.5 | Status 422 |
| 12 | Streaming | Part 4.6 | ≥ 2 `data:` events |
| 13 | Local TUI | Part 5 | 3 panes render; `/demo 1` shows placeholders |
| 14 | Web TUI | Part 6 | Browser loads `http://localhost:8080` |
| 15 | Hardhat compile | `npx hardhat compile` | No errors |
| 16 | Hardhat tests | `npx hardhat test` | 8 passing |
| 17 | Contract on Diana | Part 7.2 | Owner + envelope count readable |
| 18 | TS bridge connect | Part 8.1 | Latest block printed |

**All pass → Safe Prompt is fully functional for the QoreChain hackathon demo.**

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ModuleNotFoundError: safe_prompt_core` | Run `cd core && maturin develop --features extension-module` |
| `HTTP 401` on live chat | Set real `SAFE_PROMPT_UPSTREAM_API_KEY` in `.env`, restart gateway |
| `HTTP 422` on every request | A raw secret is in the message body — redact it first, or use `safe-prompt-redact` |
| `HH502: Couldn't download compiler version list` | Pre-seed solc 0.8.24 into `~/.cache/hardhat-nodejs/compilers/` |
| EVM authorization window exhausted | Wait ~1–2 minutes; Diana testnet rate limit resets |
| Web TUI won't load | Confirm gateway is running on 8787, then start `serve-web` on 8080; check firewall |

---

*This guide mirrors the actual file layout: Rust core in `core/`, Python package in `py/`, TypeScript bridge in `ts/`, Solidity contracts in `contracts/`, configuration in root `.env`. Deployed contract: `0xb22d64B05F09044c36a052556AC2ddB073bd19cC` on Diana testnet (chain 9800).*
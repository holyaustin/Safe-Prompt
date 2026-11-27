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
import base64
# Rust getters return base64-encoded public-key strings, not raw bytes.
mlkem_pub_bytes = base64.urlsafe_b64decode(mlkem_pub + "==")
x25519_pub_bytes = base64.urlsafe_b64decode(x25519_pub + "==")
print('Keys:', len(mlkem_pub_bytes), 'bytes ML-KEM pub,', len(x25519_pub_bytes), 'bytes X25519 pub')
assert len(mlkem_pub_bytes) == 1568
assert len(x25519_pub_bytes) == 32

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

## Part 4 — FastAPI Gateway (live LLM upstream)

Prerequisite: gateway port 8787 is free.

### Part 4.0 — Understand the endpoint
Your gateway runs locally at `http://127.0.0.1:8787`. It is an **OpenAI-compatible proxy**: you call `127.0.0.1:8787/v1/chat/completions`, and the gateway redacts secrets locally, then forwards to your configured upstream (OpenRouter by default). You do **not** call `https://openrouter.ai/api/...` directly — the gateway does that for you using your key.

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

### Step 4.2 — Validate your OpenRouter key (optional, only for live chat)

Your `.env` key is valid but out of credits (spent $0.133 vs $0.10 limit), so live chat returns HTTP 401 until you add credits at openrouter.ai or swap in a funded key. Confirm your key is authentic:

```bash
KEY=$(grep '^SAFE_PROMPT_UPSTREAM_API_KEY=' .env | cut -d= -f2- | tr -d '"')
curl -s https://openrouter.ai/api/v1/auth/key -H "Authorization: Bearer $KEY" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('valid:', d['data']['is_management_key']==False, '| remaining_usd:', d['data']['effective_budget']['remaining_usd'])"
```

**Expected:** `valid: True | remaining_usd: <number>` (a negative remaining means out of credits). If this returns a 401 instead, the key itself is wrong — replace it in `.env` and restart the gateway.

> For a funded key / adding credits: see https://openrouter.ai/credits

### Step 4.3 — Redact-only preview (no upstream call needed)

Works even with no OpenRouter credits:

```bash
curl -s -X POST http://127.0.0.1:8787/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"safe-prompt-redact","messages":[{"role":"user","content":"API key sk-proj-Q8x2LmN4vB7cR1tY9uZ3aW5eD6fG0hJk and card 4111 1111 1111 1111"}]}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['choices'][0]['message']['content'])"
```

**Expected:** `API key: [APIKEY_1] and card [CARD_1]` — secrets replaced, no upstream LLM called.

### Step 4.4 — Live chat through OpenRouter (redacted → upstream → rehydrated)

Requires a funded OpenRouter key (see Step 4.2). Set a real model id in `.env` (e.g. `openai/gpt-4o-mini` or `meta-llama/llama-3.1-8b-instruct:free`) and restart the gateway, then:

```bash
curl -s -X POST http://127.0.0.1:8787/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"safe-prompt","messages":[{"role":"user","content":"My API key is sk-proj-Q8x2LmN4vB7cR1tY9uZ3aW5eD6fG0hJk, please say hello back"}]}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['choices'][0]['message']['content'])"
```

**Expected:** assistant response text (e.g. `Hello!`). Crucially, the raw `sk-proj-...` string never leaves your machine — it is replaced by `[APIKEY_1]` server-side before forwarding.

If this returns HTTP 401 (`User not found`), your key has no remaining OpenRouter credits. Skip to Step 4.6 to test fail-closed without spending credits.

### Step 4.5 — List models (proxies OpenRouter)

```bash
curl -s http://127.0.0.1:8787/v1/models | python3 -m json.tool | head -30
```

**Expected:** JSON array of model objects from OpenRouter. With an out-of-credits key you may get an empty `data` array or a 401 — that is a credits issue, not a gateway issue.

### Step 4.6 — Prove no raw secret leaves the machine (no OpenRouter credits needed)

We run a tiny local echo upstream on port 8790, point the gateway at it, and inspect exactly what the upstream receives. This is the core security guarantee: the upstream sees only placeholders, never raw secrets.

> **About `HTTP 422`:** the fail-closed guard (`check_outbound`) raises 422 only when a raw secret *survives* redaction. Because redaction already removes `sk-proj-...`, this HTTP test demonstrates the stronger property (upstream receives `[APIKEY_1]`). The 422 backstop itself is tested at the Python level in **Part 2.2**.

**Terminal A:** run the mock echo upstream:

```bash
python3 - <<'PY' &
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
class H(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(n) or b'{}')
        print("UPSTREAM GOT:", json.dumps(body))  # show what upstream receives
        resp = json.dumps({"echo": body}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(resp)))
        self.end_headers()
        self.wfile.write(resp)
    def log_message(self, *a): pass
HTTPServer(('127.0.0.1', 8790), H).serve_forever()
PY
```

Then restart the gateway pointing at it:

```bash
pkill -f "safe_prompt.gateway.app:app" 2>/dev/null; sleep 1
source .venv/bin/activate
SAFE_PROMPT_UPSTREAM_LLM_URL=http://127.0.0.1:8790/v1/chat/completions \
SAFE_PROMPT_UPSTREAM_API_KEY= \
SAFE_PROMPT_DEFAULT_MODEL=mock \
nohup safe-prompt serve --host 127.0.0.1 --port 8787 > /tmp/gateway-mock.log 2>&1 &
sleep 3
```

Now in **Terminal B**:

```bash
echo "--- clean request ---"
curl -s -X POST http://127.0.0.1:8787/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"safe-prompt","messages":[{"role":"user","content":"hello world"}]}'

echo ""
echo "--- secret request (inspect what the upstream receives) ---"
curl -s -X POST http://127.0.0.1:8787/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"safe-prompt","messages":[{"role":"user","content":"leak sk-proj-Q8x2LmN4vB7cR1tY9uZ3aW5eD6fG0hJk"}]}'
```

Then check Terminal A's output for `UPSTREAM GOT`.

**Expected:**
- clean request: returns 200; Terminal A shows `UPSTREAM GOT:` with the clean body (`hello world`).
- secret request: returns 200; Terminal A shows `UPSTREAM GOT:` with `leak [APIKEY_1]` — the raw `sk-proj-...` **never** appears upstream (it was redacted before forwarding). Your client-side response will rehydrate `[APIKEY_1]` back to the original (safe — it never left the machine).
- If you run `SAFE_PROMPT_UPSTREAM_API_KEY=` empty, the outbound Authorization header becomes `Bearer mock` (harmless for local echo).

> Restore OpenRouter upstream afterward: edit `.env` back to `SAFE_PROMPT_UPSTREAM_LLM_URL=https://openrouter.ai/api/v1/chat/completions`, set a real key + model, and restart the gateway.

### Step 4.7 — Streaming works and is rehydrated

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
| 10 | Live OpenRouter chat | Part 4.4 (conditional) | Assistant response received |
| 11 | Fail-closed no-secret-leaves | Part 4.6 | Secret request → upstream receives `[APIKEY_1]`, raw secret absent |
| 12 | Streaming | Part 4.7 | ≥ 2 `data:` events |
| 13 | Local TUI | Part 5 | 3 panes render; `/demo 1` shows placeholders |
| 14 | Web TUI | Part 6 | Browser loads `http://localhost:8080` |
| 15 | Hardhat compile | `npx hardhat compile` | No errors |
| 16 | Hardhat tests | `npx hardhat test` | 8 passing |
| 17 | Contract on Diana | Part 7.2 | Owner + envelope count readable |
| 18 | TS bridge connect | Part 8.1 | Latest block printed |

**All pass → Safe Prompt is fully functional for the QoreChain hackathon demo.**

---

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
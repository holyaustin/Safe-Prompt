# Safe Prompt — End-to-End Running & Testing Guide

## ✅ What's Done vs. What Needs Manual Deployment

| Component | Status |
|-----------|--------|
| Rust core (`safe_prompt_core`) | ✅ Built and installed |
| Python package (`safe-prompt`) | ✅ Installed with all deps |
| FastAPI gateway (`/v1/chat/completions`) | ✅ Runs locally on `127.0.0.1:8787` |
| Textual TUI + `textual-web` server | ✅ Runs locally on `127.0.0.1:8787` / `localhost:8080` |
| Envelope create/open (ML-KEM-1024) | ✅ Roundtrip tested |
| Solidity contract (`SafePromptAnchor.sol`) | ✅ Written + 7 Hardhat tests — **NOT deployed yet** |
| Diana testnet deployment | ❌ **Requires your private key + testnet funds** |
| Contract address config | ❌ **Must be added after deployment** |
| Vercel/Railway remote deploy | ✅ Config ready — needs your account |

---

## 📦 Part 1: Install & Run Everything Locally

### 1.1 Activate the Python venv
```bash
cd /home/augustineonuora/Dapps-Empty/2026/Nov2026/safe-prompt
source .venv/bin/activate
```

### 1.2 Build Rust core (if not already done)
```bash
cd core
pip install maturin
maturin develop --features extension-module
```

### 1.3 Verify all components
```bash
safe-prompt doctor
```
Expected output: all ✅ (Rust core, qoreseal, fastapi, textual, textual-web).

---

## 🧪 Part 2: Test Each Component

### 2.1 Test the Detection Engine
```bash
python3 -c "
from safe_prompt.detect.engine import Detector
d = Detector()
tests = [
    'My API key is sk-proj-Q8x2LmN4vB7cR1tY9uZ3aW5eD6fG0hJk',
    'Credit card: 4111 1111 1111 1111',
    'Email: test@example.com, Phone: +1234567890',
    'DATABASE_URL=postgres://admin:pass@localhost:5432/db',
    'JWT: eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N',
]
for t in tests:
    matches = d.find(t)
    print(f'{len(matches)} matches:', [m.kind for m in matches], '->', t[:50])
"
```
Expected: all secrets detected with correct kinds (APIKEY, CARD, EMAIL, PHONE, URLCRED, JWT).

### 2.2 Test the Redaction + Fail-Closed Guard
```bash
python3 -c "
from safe_prompt.gateway.redact import Redactor, LeakBlocked
from safe_prompt.detect.engine import Detector
from safe_prompt.crypto import SafePromptCrypto

d = Detector()
crypto = SafePromptCrypto(use_rust=False)
redactor = Redactor(detector=d, crypto=crypto, session='test')

# Test redaction
text = 'API key: sk-proj-Q8x2LmN4vB7cR1tY9uZ3aW5eD6fG0hJk and card 4111 1111 1111 1111'
redacted = redactor.redact_text(text)
print('REDACTED:', redacted)
assert 'sk-proj' not in redacted and '4111' not in redacted

# Test fail-closed guard
try:
    check = {'messages': [{'content': 'secret: sk-proj-Q8x2LmN4vB7cR1tY9uZ3aW5eD6fG0hJk'}]}
    from safe_prompt.gateway.redact import check_outbound
    check_outbound(check, redactor.values, d)
    print('FAIL: should have blocked!')
except LeakBlocked as e:
    print('FAIL-CLOSED OK:', e)
"
```

### 2.3 Test the Envelope Workflow (ML-KEM-1024)
```bash
python3 -c "
from safe_prompt.crypto import SafePromptCrypto

crypto = SafePromptCrypto(use_rust=False)

# 1. Generate keys
mlkem_pub, x25519_pub, mlkem_sec, x25519_sec = crypto.generate_keys()
print('Keys generated:', len(mlkem_pub), 'bytes ML-KEM pub,', len(x25519_pub), 'bytes X25519 pub')

# 2. Create envelope
envelope = crypto.seal('qorechain-diana', 'chat', [{'mlkem_public_key': mlkem_pub, 'x25519_public_key': x25519_pub}], b'My secret: sk-live-abc123')
print('Envelope created:', envelope[:80] + '...')

# 3. Open envelope
plaintext = crypto.open('qorechain-diana', 'chat', envelope, mlkem_sec, x25519_sec, mlkem_pub, x25519_pub)
print('Opened plaintext:', plaintext.decode())
assert plaintext == b'My secret: sk-live-abc123'
print('ENVELOPE ROUNDTRIP OK ✅')
"
```

### 2.4 Test the FastAPI Gateway
```bash
# Start gateway in background
safe-prompt serve --host 127.0.0.1 --port 8787 &
sleep 3

# Test health
curl -s http://127.0.0.1:8787/health | python3 -m json.tool

# Test models
curl -s http://127.0.0.1:8787/v1/models | python3 -m json.tool

# Test chat completions (with API key redaction)
curl -s -X POST http://127.0.0.1:8787/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"safe-prompt","messages":[{"role":"user","content":"API key: sk-proj-Q8x2LmN4vB7cR1tY9uZ3aW5eD6fG0hJk"}]}'

# Kill gateway
kill %1 2>/dev/null
```

### 2.5 Test the TUI Locally
```bash
# Terminal 1: Start gateway
safe-prompt serve --host 127.0.0.1 --port 8787

# Terminal 2: Start TUI
safe-prompt tui
# Or: safe-prompt serve-web  (for browser-based TUI)
```

In the TUI:
- Type `/help` to see commands
- Type `/demo 1` to send a fake-data test prompt
- Check that Pane ① shows real values
- Check that Pane ② shows redacted placeholders `[APIKEY_1]`, `[CARD_1]`
- Check that Pane ③ shows QoreChain status

### 2.6 Test the Web TUI (textual-web)
```bash
# Terminal 1: Start gateway
safe-prompt serve --host 127.0.0.1 --port 8787

# Terminal 2: Start web TUI server
safe-prompt serve-web --host 0.0.0.0 --port 8080

# Open in browser: http://localhost:8080
# The same 3-pane TUI should render in the browser
```

---

## 🏦 Part 3: Deploy Smart Contract to Diana Testnet

### 3.1 Set Up Environment Variables
```bash
cd contracts
cat > .env << 'EOF'
QORECHAIN_DIANA_RPC_URL=https://diana-rpc.qorechain.io
QORECHAIN_EXPLORER_API_KEY=your-explorer-key
PRIVATE_KEY=your-private-key-with-diana-funds
EOF
```

> **⚠️ Important**: `PRIVATE_KEY` must be a private key that has funds on `qorechain-diana` testnet. Without funds, deployment will fail with "insufficient funds for gas".

### 3.2 Compile the Contract
```bash
cd contracts
npx hardhat compile
```

> **⚠️ If you see `Error HH502: Couldn't download compiler version list`**, Hardhat
> could not fetch solc 0.8.24 (common on restricted/corporate networks where
> `binaries.soliditylang.org` is behind a challenge page). Fixes:
> 1. On a network with normal access, run `npx hardhat compile` once — Hardhat
>    caches the compiler at `~/.cache/hardhat-nodejs/compilers/`.
> 2. Or pre-seed it manually:
> ```bash
> mkdir -p ~/.cache/hardhat-nodejs/compilers
> # download from https://binaries.soliditylang.org/linux-amd64/0.8.24/
> #   solc-linux-amd64-v0.8.24+commit.e11b9ed9  → the cache dir above
> chmod +x ~/.cache/hardhat-nodejs/compilers/solc-*
> ```
> Note: the Hardhat config already sets `paths.sources = "./src"`, so the
> contract in `contracts/src/` is picked up correctly.

### 3.3 Run Hardhat Tests (Local)
```bash
npx hardhat test
```
Expected: 7 tests passing (seal, revoke, authorize, access control, zero commitment, re-sealing revoked, root anchoring).

### 3.4 Deploy to Diana Testnet
```bash
npx hardhat run scripts/deploy.ts --network diana
```

> **If deployment succeeds**, you'll see:
> ```
> SafePromptAnchor deployed at: 0xAbC123...your-contract-address
> Deploy tx: 0x123abc...tx-hash
> ```
> **Save this contract address!** You'll need it in the next step.

### 3.5 Verify the Deployment
```bash
# Check on explorer (if explorer available)
# https://explorer.diana.qorechain.io/address/<contract-address>

# Or verify via Hardhat
npx hardhat verify --network diana <CONTRACT_ADDRESS> 0x0 "0x636173682f636861742f696e666f"
```

### 3.6 Test the Contract Interactively
```bash
# In contracts/ directory, start Hardhat console connected to Diana
npx hardhat console --network diana

# In the console:
const SafePromptAnchor = await ethers.getContractFactory("SafePromptAnchor");
const contract = await SafePromptAnchor.at("YOUR_CONTRACT_ADDRESS_HERE");

// Check owner
console.log("Owner:", await contract.owner());

// Seal an envelope commitment
const commitment = ethers.keccak256(ethers.toUtf8Bytes("test-commitment"));
const recipient = "0xOtherAddress";
const purpose = ethers.toUtf8Bytes("test-purpose");
const chainId = ethers.encodeBytes32String("qorechain-diana");

await contract.seal(commitment, recipient, purpose, chainId);
console.log("Envelope sealed!");

// Check if recipient is authorized
console.log("Is authorized:", await contract.isAuthorized(commitment, recipient));
```

---

## 🔗 Part 4: Connect the Contract Address to the App

### 4.1 Add Contract Address to Environment Variables
Create `.env` in the **root** `safe-prompt/` directory:
```bash
# .env (in safe-prompt/ root)
QORECHAIN_ANCHOR_CONTRACT_ADDRESS=0xYourDeployedContractAddressHere
QORECHAIN_DIANA_RPC_URL=https://diana-rpc.qorechain.io
QORECHAIN_NETWORK=qorechain-diana
QORECHAIN_CHAIN_ID=9800
```

### 4.2 Update the TypeScript Bridge
Edit `ts/src/onchain.ts`:
```typescript
// Add this near the top
const ANCHOR_ADDRESS = process.env.QORECHAIN_ANCHOR_CONTRACT_ADDRESS || "0xYourAddressHere";

// In your SafePromptOnChain class constructor or as a module-level constant
export const SAFE_PROMPT_ANCHOR_ADDRESS = ANCHOR_ADDRESS;
```

### 4.3 Update the Python Config
Edit `py/safe_prompt/config.py`:
```python
class Settings(BaseModel):
    # Add these fields
    anchor_contract_address: Optional[str] = Field(default=None)
    # ...
```

### 4.4 Verify the Connection
```bash
# Test that the app can read the contract
python3 -c "
import os
os.environ['QORECHAIN_ANCHOR_CONTRACT_ADDRESS'] = '0xYourAddress'
print('Anchor contract:', os.environ['QORECHAIN_ANCHOR_CONTRACT_ADDRESS'])
"
```

### 4.5 Test On-Chain Operations (TypeScript)
```bash
cd ts

# Register your PQC keys on-chain (sends MsgRegisterKEMKey to Diana)
npx tsx scripts/register-keys.ts

# List registered keys from the on-chain registry
npx tsx scripts/list-keys.ts

# Anchor an envelope commitment
npx tsx scripts/anchor-envelope.ts
```

---

## 🧪 Part 5: Full End-to-End Test Checklist

Run through each of these to confirm the entire app works:

| # | Test | Command | Expected Result |
|---|------|---------|-----------------|
| 1 | **Rust core** | `cd core && cargo test` | 6/6 tests pass |
| 2 | **Python package** | `pip show safe-prompt` | Package info displayed |
| 3 | **Doctor** | `safe-prompt doctor` | All ✅ |
| 4 | **Detection** | `python3 -c "from safe_prompt.detect.engine import Detector; d=Detector(); print(d.find('sk-proj-abc123'))"` | APIKEY match |
| 5 | **Redaction** | `python3 -c "from safe_prompt.gateway.redact import Redactor; from safe_prompt.detect.engine import Detector; from safe_prompt.crypto import SafePromptCrypto; d=Detector(); c=SafePromptCrypto(use_rust=False); r=Redactor(detector=d, crypto=c); print(r.redact_text('key: sk-proj-abc123'))"` | Placeholder output |
| 6 | **Envelope** | `python3 -c "from safe_prompt.crypto import SafePromptCrypto; c=SafePromptCrypto(use_rust=False); k=c.generate_keys(); e=c.seal('qorechain-diana','chat',[{'mlkem_public_key':k[0],'x25519_public_key':k[1]}],b'test'); p=c.open('qorechain-diana','chat',e,k[2],k[3],k[0],k[1]); print('OK' if p==b'test' else 'FAIL')"` | OK |
| 7 | **Gateway** | `safe-prompt serve` | Server starts on :8787 |
| 8 | **Health** | `curl http://127.0.0.1:8787/health` | `{"status":"ok"}` |
| 9 | **TUI** | `safe-prompt tui` | 3-pane TUI launches |
| 10 | **Web TUI** | `safe-prompt serve-web` | TUI in browser at :8080 |
| 11 | **Contract compile** | `cd contracts && npx hardhat compile` | No errors |
| 12 | **Contract test** | `cd contracts && npx hardhat test` | 7 tests pass |
| 13 | **Contract deploy** | `npx hardhat run deploy.ts --network diana` | Contract address returned |
| 14 | **On-chain keys** | `cd ts && npx tsx scripts/register-keys.ts` | Keys registered |
| 15 | **Envelope anchor** | `npx tsx scripts/anchor-envelope.ts` | Commitment anchored |

---

## 🚀 Part 6: Deploy to Railway/Render (Remote)

### 6.1 Railway (Recommended)
```bash
# 1. Push to GitHub
git init
git add .
git commit -m "safe-prompt: ready for deployment"
git remote add origin https://github.com/YOUR_USER/YOUR_REPO.git
git push -u origin main

# 2. In Railway dashboard:
#    - New Project → Deploy from GitHub
#    - Root Directory: safe-prompt
#    - Build Command: pip install -e . && pip install maturin && cd core && maturin develop
#    - Start Command: cd py && python -m uvicorn safe_prompt.gateway.app:app --host 0.0.0.0 --port $PORT
#    - Add Environment Variables (copy from .env.example)
#    - Deploy
```

### 6.2 Render (Alternative)
```bash
# 1. Connect GitHub repo
# 2. Create Web Service
#    - Root Directory: safe-prompt
#    - Runtime: Python 3.11
#    - Build Command: pip install -e . && pip install maturin && cd core && maturin develop
#    - Start Command: cd py && python -m uvicorn safe_prompt.gateway.app:app --host 0.0.0.0 --port $PORT
#    - Health Check: /health
```

---

## ❓ FAQ

### Q: Where do I put the contract address?
**A:** In the root `.env` file:
```bash
QORECHAIN_ANCHOR_CONTRACT_ADDRESS=0xYourDeployedAddress
```

### Q: What if I don't have Diana testnet funds?
**A:** The Solidity contract deployment requires testnet funds. Without them:
- The **local Python app** (gateway, TUI, detection, envelope encryption) still works 100%.
- Only the **on-chain anchor** (Solidity contract) and **on-chain key registration** (TypeScript bridge) require testnet funds.
- For a hackathon demo without testnet access, you can mock the on-chain portion with local test contracts.

### Q: Can I test the contract without deploying?
**A:** Yes, using Hardhat's local network:
```bash
cd contracts
npx hardhat test  # Runs 7 tests against local in-memory network
```

### Q: How do I connect the TypeScript bridge to Diana?
**A:** Set the environment variable in `ts/.env`:
```bash
QORECHAIN_DIANA_RPC_URL=https://diana-rpc.qorechain.io
QORECHAIN_PRIVATE_KEY=your-private-key
```

### Q: What about the Rust core?
**A:** The Rust core is already built and installed. If you want to rebuild:
```bash
cd core
maturin develop --features extension-module
```
The `.so` file goes into `.venv/lib/python3.10/site-packages/safe_prompt_core/`.

---

## 📋 Quick Reference: What's Deployed vs. What's Local

| Component | Runs Where | Needs Testnet? |
|-----------|-----------|----------------|
| Detection engine | Local Python | ❌ No |
| Redaction + fail-closed | Local Python | ❌ No |
| FastAPI gateway | Local (`127.0.0.1:8787`) | ❌ No (unless you configure upstream) |
| Textual TUI | Local terminal | ❌ No |
| Web TUI (textual-web) | Local (`localhost:8080`) | ❌ No |
| Envelope create/open | Local Rust/PyO3 | ❌ No |
| Solidity contract | Diana testnet (`qorechain-diana`) | ✅ **Yes** |
| On-chain key registration | Diana testnet | ✅ **Yes** |
| Envelope anchoring | Diana testnet | ✅ **Yes** |

---

*This guide was generated for the QoreChain "Build Before Q-Day" Hackathon — Safe Prompt project.*
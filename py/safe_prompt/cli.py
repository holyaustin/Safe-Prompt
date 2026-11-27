"""Safe Prompt CLI — Typer entrypoint with subcommands."""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Optional, List

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="safe-prompt",
    help="Post-Quantum Encrypted LLM Prompt & Secret Sharing for QoreChain",
    no_args_is_help=True,
)
console = Console()

# Sub-apps
envelope_app = typer.Typer(name="envelope", help="Encrypted envelope operations", no_args_is_help=True)
keys_app = typer.Typer(name="keys", help="PQC key management", no_args_is_help=True)
app.add_typer(envelope_app, name="envelope")
app.add_typer(keys_app, name="keys")


@app.command("tui")
def run_tui(
    session: str = typer.Option("tui", "--session", "-s", help="Session name"),
    model: str = typer.Option("", "--model", "-m", help="Default model"),
):
    """Launch the local 3-pane Textual TUI."""
    from .tui.app import SafePromptApp
    from .tui.client import GatewayClient

    client = GatewayClient()
    tui = SafePromptApp(client=client, session=session, model=model)
    tui.run()


@app.command("serve-web")
def serve_web(
    host: str = typer.Option("0.0.0.0", "--host", help="Bind host (0.0.0.0 for remote access)"),
    port: int = typer.Option(8080, "--port", help="Web port"),
):
    """Serve the Safe Prompt web UI (FastAPI) for judges and remote access.

    The gateway must already be running on its default port (:8787)
    or set SAFE_PROMPT_GATEWAY_HOST/PORT in the environment.
    """
    import uvicorn
    from .gateway.app import app as fastapi_app

    console.print(f"[green]Starting Safe Prompt web UI on http://{host}:{port}[/green]")
    uvicorn.run(
        fastapi_app,
        host=host,
        port=port,
        # Suppress uvicorn access logs for clean judge output
        log_level="warning",
    )


@app.command("serve")
def serve_gateway(
    host: str = typer.Option("127.0.0.1", "--host", help="Bind host"),
    port: int = typer.Option(8787, "--port", help="Gateway port"),
    reload: bool = typer.Option(False, "--reload", help="Auto-reload on changes"),
):
    """Start the FastAPI gateway (OpenAI-compatible proxy)."""
    import uvicorn
    console.print(f"[green]Starting Safe Prompt gateway on http://{host}:{port}[/green]")
    uvicorn.run(
        "safe_prompt.gateway.app:app",
        host=host,
        port=port,
        reload=reload,
    )


@app.command("doctor")
def doctor():
    """Run diagnostics on the environment."""
    console.print("[bold]Safe Prompt Diagnostics[/bold]\n")

    checks = []

    # Python version
    checks.append(("Python >= 3.10", sys.version_info >= (3, 10)))

    # Rust core availability
    try:
        import safe_prompt_core
        checks.append((f"Rust core (ML-KEM-1024 via QoreSeal) — {safe_prompt_core}", True))
    except ImportError:
        checks.append(("Rust core not built — run 'make build-core'", False))

    # qoreseal (ML-KEM-1024) availability
    try:
        import qoreseal  # noqa
        checks.append(("qoreseal (ML-KEM-1024 + X25519) installed", True))
    except ImportError:
        checks.append(("qoreseal NOT installed", False))

    # FastAPI
    try:
        import fastapi  # noqa
        checks.append(("FastAPI installed", True))
    except ImportError:
        checks.append(("FastAPI NOT installed", False))

    # Textual
    try:
        import textual  # noqa
        checks.append(("Textual (TUI framework) installed", True))
    except ImportError:
        checks.append(("Textual NOT installed", False))

    # textual-web
    try:
        import textual_web  # noqa
        checks.append(("textual-web (web TUI server) installed", True))
    except ImportError:
        checks.append(("textual-web NOT installed (optional)", False))

    for label, ok in checks:
        symbol = "✅" if ok else "❌"
        color = "green" if ok else "red"
        console.print(f"  {symbol} [{color}]{label}[/{color}]")

    all_ok = all(ok for _, ok in checks)
    if all_ok:
        console.print("\n[bold green]All checks passed![/bold green]")
    else:
        console.print("\n[bold red]Some checks failed. Run 'make install-all' to install dependencies.[/bold red]")
        raise typer.Exit(1)


# ------------------------------------------------------------------ envelope subcommands
@envelope_app.command("create")
def envelope_create(
    prompt: str = typer.Argument(..., help="Secret prompt or value to encrypt"),
    recipients: str = typer.Option(..., "--recipients", "-r", help="Comma-separated base64url ML-KEM public keys"),
    chain_id: str = typer.Option("qorechain-diana", "--chain", "-c", help="QoreChain network ID"),
    purpose: str = typer.Option("safe-prompt", "--purpose", "-p", help="Envelope purpose tag"),
):
    """Create a new encrypted envelope sealed for on-chain recipients."""
    from .crypto import SafePromptCrypto

    crypto = SafePromptCrypto()
    recip_list = [
        {"mlkem_public_key": r.strip()}
        for r in recipients.split(",")
        if r.strip()
    ]

    envelope = crypto.seal(chain_id, purpose, recip_list, prompt.encode())
    console.print(f"\n[bold green]Envelope created![/bold green]")
    console.print(f"  Purpose:    {purpose}")
    console.print(f"  Chain:      {chain_id}")
    console.print(f"  Recipients: {len(recip_list)}")
    console.print(f"  Envelope:   [dim]{envelope[:80]}...[/dim]")
    console.print(f"\n  Full envelope (copy this):")
    console.print(f"  [bold]{envelope}[/bold]")


@envelope_app.command("open")
def envelope_open(
    envelope: str = typer.Argument(..., help="qoreseal:... envelope text"),
    chain_id: str = typer.Option("qorechain-diana", "--chain", "-c"),
    purpose: str = typer.Option("safe-prompt", "--purpose", "-p"),
):
    """Open (decrypt) an envelope with local keys from keystore."""
    from .crypto import SafePromptCrypto

    # Load keys from default keystore (in real usage, from on-chain registry)
    keystore_path = Path.home() / ".safe-prompt" / "keys.json"
    if not keystore_path.exists():
        console.print("[red]No keystore found. Run 'safe-prompt keys generate' first.[/red]")
        raise typer.Exit(1)

    import json
    import base64
    keys_data = json.loads(keystore_path.read_text())

    crypto = SafePromptCrypto()
    plaintext = crypto.open(
        chain_id, purpose, envelope,
        mlkem_secret=bytes.fromhex(keys_data["mlkem_secret"]),
        x25519_secret=bytes.fromhex(keys_data["x25519_secret"]),
        mlkem_public=base64.urlsafe_b64decode(keys_data["mlkem_public"] + "=="),
        x25519_public=base64.urlsafe_b64decode(keys_data["x25519_public"] + "=="),
    )
    console.print(plaintext.decode(errors="replace"))


@envelope_app.command("inspect")
def envelope_inspect(
    envelope: str = typer.Argument(..., help="qoreseal:... envelope text"),
):
    """Parse and inspect an envelope without decrypting."""
    from .crypto import SafePromptCrypto

    crypto = SafePromptCrypto()
    try:
        info = crypto.parse(envelope)
        console.print("[bold]Envelope Info[/bold]")
        console.print(f"  Version:   {info.get('version', '?')}")
        console.print(f"  Mode:      {info.get('mode', '?')}")
        console.print(f"  Anonymous: {info.get('anonymous', '?')}")
        entries = info.get("entries", [])
        console.print(f"  Recipients: {len(entries)}")
        for i, e in enumerate(entries):
            console.print(f"    [{i+1}] hint: {e.get('hint', '?')[:16]}...  mlkem_ct: {len(e.get('mlkem_ciphertext', ''))} bytes")
    except Exception as e:
        console.print(f"[red]Failed to parse envelope: {e}[/red]")
        raise typer.Exit(1)


# ------------------------------------------------------------------ keys subcommands
@keys_app.command("generate")
def keys_generate(
    name: str = typer.Option("default", "--name", "-n", help="Key name"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Write keys to file"),
):
    """Generate a new ML-KEM-1024 + X25519 key pair."""
    from .crypto import SafePromptCrypto

    crypto = SafePromptCrypto()
    mlkem_pub, x25519_pub, mlkem_sec, x25519_sec = crypto.generate_keys()

    console.print("[bold green]Key pair generated![/bold green]")
    console.print(f"  ML-KEM-1024 Public:  [dim]{mlkem_pub[:32]}...[/dim]")
    console.print(f"  X25519 Public:      [dim]{x25519_pub[:32]}...[/dim]")

    if output:
        import json
        keys_file = Path(output)
        keys_file.parent.mkdir(parents=True, exist_ok=True)
        keys_file.write_text(json.dumps({
            "name": name,
            "mlkem_public": mlkem_pub,
            "x25519_public": x25519_pub,
            "mlkem_secret": mlkem_sec,
            "x25519_secret": x25519_sec,
        }, indent=2))
        console.print(f"\n[green]Keys written to {output}[/green]")

    console.print("\n[yellow]WARNING: Save your secret keys securely. The private keys are shown above.[/yellow]")


@keys_app.command("register")
def keys_register(
    keys_file: str = typer.Option(..., "--keys", "-k", help="Path to keys JSON file"),
    chain_id: str = typer.Option("qorechain-diana", "--chain", "-c"),
):
    """Register ML-KEM-1024 and ML-DSA-87 keys on-chain for qor1... address."""
    import json

    if not Path(keys_file).exists():
        console.print(f"[red]Keys file not found: {keys_file}[/red]")
        raise typer.Exit(1)

    keys_data = json.loads(Path(keys_file).read_text())
    console.print(f"[bold]Registering PQC keys on {chain_id}[/bold]")
    console.print(f"  ML-KEM-1024 public: {keys_data['mlkem_public'][:40]}...")
    console.print(f"  X25519 public:      {keys_data['x25519_public'][:40]}...")
    console.print(f"\n[dim]Call the TypeScript bridge to submit MsgRegisterKEMKey on-chain.[/dim]")
    console.print(f"[dim]  cd ts && npx tsx scripts/register-keys.ts --keys {keys_file}[/dim]")


@keys_app.command("list")
def keys_list():
    """List registered PQC keys (from local cache or on-chain)."""
    console.print("[bold]Registered PQC Keys[/bold]")
    console.print("[dim]Use the TypeScript bridge to query the on-chain registry:[/dim]")
    console.print("[dim]  cd ts && npx tsx scripts/list-keys.ts[/dim]")


def main():
    app()


if __name__ == "__main__":
    main()
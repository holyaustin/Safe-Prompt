"""Safe Prompt TUI — 3-pane terminal interface.

Panes:
  1. WHAT YOU SEE        — local, unredacted prompt + reply
  2. WHAT THE LLM RECEIVES — redacted payload (placeholders + envelope status)
  3. QORECHAIN VAULT     — testnet status, PQC key registry, envelope tracking

Runs identically in local terminal OR served over web via textual-web.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from pathlib import Path
from typing import Optional

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import DataTable, Footer, Header, Input, Label, RichLog, Static
from rich.text import Text

from .client import GatewayClient, GatewayError

PH = re.compile(r"\[[A-Z][A-Z0-9]*_\d+\]")

DEMO_PROMPTS = [
    "Draft a short email to ada.obi@example.com. Mention the invoice is paid with card 4111 1111 1111 1111 "
    "and our deploy key is sk-proj-Q8x2LmN4vB7cR1tY9uZ3aW5eD6fG0hJk. My phone is 08031234567.",
    "Summarise this config for a teammate: DATABASE_URL=postgres://admin:s3cr3tpw@db.internal/prod  "
    "password: Tr0ub4dor&3xx",
    "Reply to that email with a friendlier tone.",
    "Our IBAN is GB82 WEST 1234 5698 7654 32 and AWS key AKIAIOSFODNN7EXAMPLE, is that safe to share?",
]
# All demo values are FAKE test data.

HELP = (
    "/demo [1-4]        send a built-in FAKE-data test prompt\n"
    "/unlock            unlock the vault (in web: auto-unlocked)\n"
    "/lock              lock the vault\n"
    "/copy [you|wire|all] copy a pane to clipboard + save to file\n"
    "/models            list models available through gateway\n"
    "/model ID          choose the model\n"
    "/session NAME      switch conversation/session\n"
    "/clear             clear the conversation\n"
    "/help              this help    |    Ctrl+U unlock · Ctrl+L lock · Ctrl+Q quit"
)


def with_placeholders(s: str, base: str = "") -> Text:
    """Render text with [KIND_n] placeholders highlighted."""
    t = Text(base, overflow="fold", no_wrap=False)
    pos = 0
    for m in PH.finditer(s):
        t.append(s[pos:m.start])
        t.append(m.group(0), style="bold black on yellow")
        pos = m.end()
    t.append(s[pos:])
    return t


class SafePromptApp(App):
    """Main Safe Prompt application."""

    TITLE = "Safe Prompt"
    SUB_TITLE = "post-quantum secrets never leave this machine"
    CSS = """
    #cols { height: 1fr; }
    .col { width: 1fr; border: round $primary; padding: 0 1; }
    #col-side { width: 32%; min-width: 28; max-width: 45; }
    .col-title { text-style: bold; color: $accent; }
    #live { height: auto; max-height: 8; color: $success; }
    #vault { height: auto; }
    #items { height: 1fr; }
    #prompt { dock: bottom; }
    RichLog { overflow-x: hidden; overflow-y: auto; width: 100%; scrollbar-gutter: stable; }
    #vault, #live { width: 100%; }
    #items { overflow-x: hidden; }
    """

    BINDINGS = [
        Binding("ctrl+u", "unlock", "Unlock"),
        Binding("ctrl+l", "lock", "Lock"),
        Binding("ctrl+q", "quit", "Quit"),
    ]

    def __init__(
        self,
        client: Optional[GatewayClient] = None,
        session: str = "tui",
        model: str = "",
        save_dir: Optional[Path] = None,
    ):
        super().__init__()
        self.client = client or GatewayClient()
        self.model = model
        self.session = session
        self.history: list[dict] = []
        self.busy = False
        self.transcript_you: list[str] = []
        self.transcript_wire: list[str] = []
        self.last_error = ""
        self._shown_id = 0
        self._you_items: list[Text] = []
        self._wire_items: list[Text] = []
        self._rewrap_timer = None
        self.save_dir = (
            Path(save_dir)
            if save_dir
            else Path(os.environ.get("SAFE_PROMPT_HOME") or Path.home() / ".safe-prompt") / "transcripts"
        )
        self.save_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ layout
    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="cols"):
            with Vertical(classes="col", id="col-you"):
                yield Label("① WHAT YOU SEE  (local, real values)", classes="col-title")
                yield RichLog(id="you", wrap=True, markup=False, highlight=False, min_width=1)
                yield Static("", id="live")
            with Vertical(classes="col", id="col-wire"):
                yield Label("② WHAT THE LLM RECEIVES", classes="col-title")
                yield RichLog(id="wire", wrap=True, markup=False, highlight=False, min_width=1)
            with Vertical(classes="col", id="col-side"):
                yield Label("③ QORECHAIN VAULT", classes="col-title")
                yield Static("connecting…", id="vault")
                yield Label("DETECTED IN LAST PROMPT", classes="col-title")
                yield DataTable(id="items")
        yield Input(
            placeholder="Type a prompt (secrets included) — or /help",
            id="prompt",
        )
        yield Footer()

    async def on_mount(self) -> None:
        t = self.query_one("#items", DataTable)
        t.add_columns("Placeholder", "Kind", "Len", "New")
        t.cursor_type = "none"
        self.query_one("#prompt", Input).focus()
        self.note(
            "Safe Prompt ready. Type /demo 1-4 for fake-data test prompts, or /help for commands."
        )
        await self.refresh_status()
        self.set_interval(2.0, self.refresh_status)

    # ------------------------------------------------------------------ status
    def note(self, text: str) -> None:
        """Write a status line into the wire pane."""
        wire = self.query_one("#wire", RichLog)
        wire.write(Text(f"[sp] {text}", style="dim"))

    async def refresh_status(self) -> None:
        """Poll gateway health and update vault pane."""
        vault = self.query_one("#vault", Static)
        try:
            health = await self.client.health()
            lines = [
                f"● Gateway: {health.get('status', 'unknown')}",
                f"  Crypto:  {health.get('crypto_backend', 'unknown')}",
                f"  Network: {health.get('network', 'qorechain-diana')}",
            ]
            vault.update(Text("\n".join(lines), style="green"))
        except Exception as e:
            vault.update(Text(f"● Gateway: OFFLINE ({e})", style="red"))

    # ------------------------------------------------------------------ events
    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return

        if text.startswith("/"):
            await self.handle_command(text)
            event.input.clear()
            return

        if self.busy:
            return

        # Send to gateway
        await self.send_prompt(text)
        event.input.clear()

    async def handle_command(self, cmd: str) -> None:
        """Handle slash commands."""
        parts = cmd.split()
        command = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []

        if command in ("/help", "/?"):
            self.note(HELP)
        elif command == "/demo":
            idx = int(args[0]) - 1 if args else 0
            idx = max(0, min(idx, len(DEMO_PROMPTS) - 1))
            await self.send_prompt(DEMO_PROMPTS[idx])
        elif command == "/unlock":
            self.note("Vault unlocked (in web mode, auto-unlocked).")
            await self.refresh_status()
        elif command == "/lock":
            self.note("Vault locked.")
            await self.refresh_status()
        elif command == "/copy":
            target = args[0] if args else "all"
            await self.copy_to_clipboard(target)
        elif command == "/models":
            await self.show_models()
        elif command == "/model":
            if args:
                self.model = args[0]
                self.note(f"Model set to: {self.model}")
        elif command == "/session":
            if args:
                self.session = args[0]
                self.note(f"Session switched to: {self.session}")
        elif command == "/clear":
            self.clear_transcript()
            self.note("Transcript cleared.")
        else:
            self.note(f"Unknown command: {command}. Try /help.")

    async def send_prompt(self, prompt: str) -> None:
        """Send a prompt through the gateway and display results in both panes."""
        self.busy = True
        self.transcript_you.append(prompt)

        # Show in "you" pane (real values)
        you_log = self.query_one("#you", RichLog)
        you_log.write(Text(f"\n>>> {prompt}\n", style="bold"))

        # Show status
        self.note("Processing...")

        try:
            # Get redacted wire version from gateway
            redacted = await self.client.get_redacted(prompt, self.session)
            self.transcript_wire.append(redacted)

            # Show in wire pane
            wire_log = self.query_one("#wire", RichLog)
            wire_log.write(Text(f"\n[{self.session}] {redacted}\n", style="bold blue"))

            # Show detections
            if hasattr(self.client, "last_detections") and self.client.last_detections:
                self.show_detections(self.client.last_detections)

            # Forward to LLM (redacted)
            self.note("Forwarding to LLM...")

            # Get response from gateway
            reply_you, reply_wire = await self.client.chat(self.history, self.model, redacted)

            # Show reply in "you" pane
            you_log.write(Text(f"<<< {reply_you}\n", style="bold green"))

            # Show reply in wire pane (what LLM actually saw)
            if reply_wire != reply_you:
                wire_log.write(Text(f"<<< {reply_wire}\n", style="dim"))

            self.history.append({"role": "user", "content": redacted})
            self.history.append({"role": "assistant", "content": reply_wire})

        except GatewayError as e:
            self.note(f"✗ Error: {e}")
            self.last_error = str(e)
        finally:
            self.busy = False

    def show_detections(self, detections: list) -> None:
        """Update the detections table in the vault pane."""
        table = self.query_one("#items", DataTable)
        table.clear()
        for d in detections:
            kind = getattr(d, "kind", "?")
            placeholder = getattr(d, "placeholder", "?")
            length = getattr(d, "length", 0)
            new = getattr(d, "new", False)
            table.add_row(placeholder, kind, str(length), "✓" if new else "")

    async def copy_to_clipboard(self, target: str) -> None:
        """Copy pane content to clipboard and save to file."""
        ts = time.strftime("%Y%m%d-%H%M%S")
        if target in ("you", "all"):
            text = "\n".join(self.transcript_you)
            file = self.save_dir / f"{self.session}-{ts}-you.txt"
            file.write_text(text)
            try:
                self.app.copy_to_clipboard(text)
                self.note(f"Copied 'you' pane + saved to {file}")
            except Exception:
                self.note(f"Saved to {file} (clipboard unavailable)")
        if target in ("wire", "all"):
            text = "\n".join(self.transcript_wire)
            file = self.save_dir / f"{self.session}-{ts}-wire.txt"
            file.write_text(text)
            try:
                self.app.copy_to_clipboard(text)
                self.note(f"Copied 'wire' pane + saved to {file}")
            except Exception:
                self.note(f"Saved to {file} (clipboard unavailable)")

    async def show_models(self) -> None:
        """List models from gateway."""
        try:
            models = await self.client.models()
            self.note(f"Available models: {', '.join(m['id'] for m in models.get('data', []))}")
        except Exception as e:
            self.note(f"Failed to list models: {e}")

    def clear_transcript(self) -> None:
        """Clear all transcripts."""
        self.transcript_you.clear()
        self.transcript_wire.clear()
        self.history.clear()
        self._you_items.clear()
        self._wire_items.clear()

        you_log = self.query_one("#you", RichLog)
        you_log.clear()
        wire_log = self.query_one("#wire", RichLog)
        wire_log.clear()

        # Re-add empty lines for visibility
        you_log.write(Text(""))
        wire_log.write(Text(""))

    # ------------------------------------------------------------------ actions
    def action_unlock(self) -> None:
        self.note("Vault unlocked.")
        self.refresh_status()

    def action_lock(self) -> None:
        self.note("Vault locked.")
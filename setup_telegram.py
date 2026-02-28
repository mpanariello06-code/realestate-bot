#!/usr/bin/env python3
"""
Interactive setup helper for the Telegram bot.

Run this script AFTER the server is running to:
  1. Verify your TELEGRAM_BOT_TOKEN is valid.
  2. Auto-detect your Telegram chat ID by listening for one incoming message.
  3. Register the chat ID against your agent record on the local server.
  4. Register the webhook URL with Telegram (optional).

Usage:
    python setup_telegram.py

The server must be running at http://localhost:8000 (default).
If it's running on a different port, pass --port <port>.
"""

import argparse
import json
import os
import sys
import time

try:
    import requests
except ImportError:
    sys.exit("ERROR: 'requests' is not installed. Run: pip install requests")


# ── helpers ───────────────────────────────────────────────────────────────────

def _parse_env_value(raw: str) -> str:
    """Strip whitespace and optional surrounding quotes from a .env value."""
    val = raw.strip()
    if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
        val = val[1:-1]
    return val


def _load_token() -> str:
    """Return TELEGRAM_BOT_TOKEN from env or .env file."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("TELEGRAM_BOT_TOKEN="):
                        token = _parse_env_value(line.split("=", 1)[1])
                        break
    return token


def _tg(token: str, method: str, **params):
    """Call a Telegram Bot API method and return the JSON result dict."""
    url = f"https://api.telegram.org/bot{token}/{method}"
    resp = requests.get(url, params=params, timeout=15)
    try:
        return resp.json()
    except Exception:
        return {"ok": False, "description": resp.text}


def _check_server(base_url: str) -> bool:
    try:
        r = requests.get(f"{base_url}/health", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def _get_agents(base_url: str) -> list:
    try:
        r = requests.get(f"{base_url}/portal/agent/", timeout=5)
        if r.status_code == 200:
            data = r.json()
            return data if isinstance(data, list) else []
    except Exception:
        pass
    return []


def _patch_agent(base_url: str, agent_id: int, chat_id: str) -> bool:
    try:
        r = requests.patch(
            f"{base_url}/portal/agent/{agent_id}",
            json={"telegram_chat_id": chat_id},
            timeout=5,
        )
        return r.status_code == 200
    except Exception:
        return False


def _create_agent(base_url: str, name: str, email: str, phone: str) -> dict | None:
    try:
        r = requests.post(
            f"{base_url}/portal/agent/",
            json={
                "name": name,
                "email": email,
                "phone": phone,
                "whatsapp_number": f"whatsapp:{phone}",
            },
            timeout=5,
        )
        if r.status_code in (200, 201):
            return r.json()
    except Exception:
        pass
    return None


# ── steps ─────────────────────────────────────────────────────────────────────

def step_verify_token(token: str) -> dict:
    print("\n[1/4] Verifying bot token …")
    result = _tg(token, "getMe")
    if not result.get("ok"):
        print(f"  ✗  Invalid token: {result.get('description', 'unknown error')}")
        sys.exit(1)
    bot = result["result"]
    print(f"  ✓  Connected as @{bot['username']} ({bot['first_name']})")
    return bot


def step_detect_chat_id(token: str) -> str:
    print("\n[2/4] Detecting your Telegram chat ID …")
    print(
        f"  → Open Telegram, find your bot and send it any message (e.g. 'hi').\n"
        f"    Waiting up to 60 seconds …"
    )

    # Delete pending updates so we only see new ones
    _tg(token, "getUpdates", offset=-1, timeout=0)

    deadline = time.time() + 60
    offset = None
    while time.time() < deadline:
        params = {"timeout": 10, "allowed_updates": json.dumps(["message"])}
        if offset is not None:
            params["offset"] = offset
        result = _tg(token, "getUpdates", **params)
        if result.get("ok") and result.get("result"):
            update = result["result"][0]
            offset = update["update_id"] + 1
            msg = update.get("message") or update.get("edited_message") or {}
            chat_id = str(msg.get("chat", {}).get("id", ""))
            name = msg.get("from", {}).get("first_name", "")
            if chat_id:
                print(f"  ✓  Detected chat ID: {chat_id}  (from {name})")
                return chat_id
    print("  ✗  Timed out — no message received. Check that you sent a message to your bot.")
    sys.exit(1)


def step_register_agent(base_url: str, chat_id: str):
    print(f"\n[3/4] Registering chat ID with the local server ({base_url}) …")

    if not _check_server(base_url):
        print(
            f"  ✗  Server not reachable at {base_url}.\n"
            "     Start the server with `python run.py` and try again."
        )
        sys.exit(1)

    agents = _get_agents(base_url)

    if agents:
        print(f"  Found {len(agents)} agent(s):")
        for i, a in enumerate(agents):
            tg = a.get("telegram_chat_id") or "—"
            print(f"    [{i+1}] {a['name']} (id={a['id']})  telegram_chat_id={tg}")
        print(f"    [{len(agents)+1}] Create a new agent")
        raw = input("  → Choose an agent number: ").strip()
        try:
            choice = int(raw)
        except ValueError:
            print("  ✗  Invalid choice. Exiting.")
            sys.exit(1)
        if 1 <= choice <= len(agents):
            agent = agents[choice - 1]
        elif choice == len(agents) + 1:
            agent = _prompt_create_agent(base_url)
        else:
            print("  ✗  Invalid choice. Exiting.")
            sys.exit(1)
    else:
        print("  No agents found. Let's create one.")
        agent = _prompt_create_agent(base_url)

    ok = _patch_agent(base_url, agent["id"], chat_id)
    if ok:
        print(f"  ✓  telegram_chat_id={chat_id} registered for agent '{agent['name']}' (id={agent['id']})")
    else:
        print("  ✗  Failed to update agent. You can do it manually:")
        print(
            f"     curl -s -X PATCH {base_url}/portal/agent/{agent['id']} \\\n"
            f'       -H "Content-Type: application/json" \\\n'
            f"       -d '{{\"telegram_chat_id\": \"{chat_id}\"}}'"
        )
        sys.exit(1)

    return agent


def _prompt_create_agent(base_url: str) -> dict:
    name = input("  Agent name: ").strip() or "My Agent"
    email = input("  Agent email: ").strip() or "agent@example.com"
    phone = input("  Agent phone (e.g. +61412345678): ").strip() or "+10000000000"
    agent = _create_agent(base_url, name, email, phone)
    if not agent:
        print("  ✗  Could not create agent. Check the server logs.")
        sys.exit(1)
    print(f"  ✓  Agent created with id={agent['id']}")
    return agent


def step_register_webhook(token: str, base_url: str):
    print("\n[4/4] Registering Telegram webhook …")

    if base_url.startswith("http://localhost") or base_url.startswith("http://127."):
        print(
            "  ⚠  BASE_URL is localhost — Telegram cannot reach a local server directly.\n"
            "     Use ngrok (https://ngrok.com/download) to expose your local server:\n\n"
            "       ngrok http 8000\n\n"
            "     Copy the https:// URL, set it as BASE_URL in your .env, then rerun\n"
            "     this script.  Skipping webhook registration for now."
        )
        return

    webhook_url = f"{base_url}/webhook/telegram"
    result = _tg(token, "setWebhook", url=webhook_url)
    if result.get("ok"):
        print(f"  ✓  Webhook registered: {webhook_url}")
    else:
        print(f"  ✗  Failed: {result.get('description', result)}")
        print(
            f"     Try manually:\n"
            f"       curl 'https://api.telegram.org/bot{token}/setWebhook?url={webhook_url}'"
        )


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Telegram bot setup helper")
    parser.add_argument("--port", type=int, default=8000, help="Local server port (default: 8000)")
    args = parser.parse_args()

    base_url = f"http://localhost:{args.port}"

    print("=" * 55)
    print("  Real Estate Bot — Telegram Setup")
    print("=" * 55)

    # Load token
    token = _load_token()
    if not token or token == "your_telegram_bot_token":
        print(
            "\nERROR: TELEGRAM_BOT_TOKEN is not set.\n\n"
            "  1. Create a bot at https://t.me/BotFather  (/newbot)\n"
            "  2. Copy the token and add it to your .env file:\n\n"
            "       TELEGRAM_BOT_TOKEN=123456:ABCdef…\n\n"
            "  3. Re-run: python setup_telegram.py"
        )
        sys.exit(1)

    # Load BASE_URL for webhook registration
    base_env_url = os.getenv("BASE_URL", "http://localhost:8000")
    if base_env_url == "http://localhost:8000":
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("BASE_URL="):
                        base_env_url = _parse_env_value(line.split("=", 1)[1])
                        break

    step_verify_token(token)
    chat_id = step_detect_chat_id(token)
    step_register_agent(base_url, chat_id)
    step_register_webhook(token, base_env_url)

    print("\n" + "=" * 55)
    print("  Setup complete!")
    print()
    print("  Open your bot in Telegram and send:  HELP")
    print("  You should receive the command list immediately.")
    print("=" * 55)
    print()


if __name__ == "__main__":
    main()

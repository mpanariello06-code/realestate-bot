"""
Simple launcher — start the server with:

    python run.py

The server will be available at http://localhost:8000
API docs: http://localhost:8000/docs
"""
import os

import uvicorn

HOST = "0.0.0.0"   # listen on all network interfaces
PORT = 8000
DISPLAY_HOST = "127.0.0.1"  # address to open in a browser


def _parse_env_value(raw: str) -> str:
    """Strip whitespace and optional surrounding quotes from a .env value."""
    val = raw.strip()
    if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
        val = val[1:-1]
    return val


def _load_env_var(name: str, default: str = "") -> str:
    """Read a variable from os.environ or .env file (os.environ takes priority)."""
    val = os.getenv(name, "")
    if val:
        return val
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith(f"{name}="):
                    return _parse_env_value(line.split("=", 1)[1])
    return default


if __name__ == "__main__":
    tg_token = _load_env_var("TELEGRAM_BOT_TOKEN")
    base_url = _load_env_var("BASE_URL", f"http://{DISPLAY_HOST}:{PORT}")

    tg_status = "configured ✓" if (tg_token and tg_token != "your_telegram_bot_token") else "not set (run setup_telegram.py)"

    print()
    print("=" * 60)
    print("  Real Estate Bot")
    print()
    print(f"  Server:   http://{DISPLAY_HOST}:{PORT}")
    print(f"  API docs: http://{DISPLAY_HOST}:{PORT}/docs")
    print(f"  Admin:    http://{DISPLAY_HOST}:{PORT}/admin/dashboard")
    print()
    print(f"  Telegram webhook: {base_url}/webhook/telegram")
    print(f"  Telegram token:   {tg_status}")
    print()
    print("  To set up Telegram:  python setup_telegram.py")
    print()
    print("  Press CTRL+C to stop")
    print("=" * 60)
    print()
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=True)

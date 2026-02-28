"""
Simple launcher — start the server with:

    python run.py

The server will be available at http://localhost:8000
API docs: http://localhost:8000/docs
"""
import uvicorn

HOST = "0.0.0.0"   # listen on all network interfaces
PORT = 8000
DISPLAY_HOST = "127.0.0.1"  # address to open in a browser

if __name__ == "__main__":
    print()
    print("=" * 50)
    print("  Real Estate Bot")
    print()
    print(f"  Server:   http://{DISPLAY_HOST}:{PORT}")
    print(f"  API docs: http://{DISPLAY_HOST}:{PORT}/docs")
    print(f"  Admin:    http://{DISPLAY_HOST}:{PORT}/admin/dashboard")
    print()
    print("  Press CTRL+C to stop")
    print("=" * 50)
    print()
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=True)

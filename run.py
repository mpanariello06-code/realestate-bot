"""
Simple launcher — start the server with:

    python run.py

The server will be available at http://localhost:8000
API docs: http://localhost:8000/docs
"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)

from fastapi import FastAPI, Request
from prometheus_fastapi_instrumentator import Instrumentator
import psutil

app = FastAPI()

# Expose Prometheus metrics at /metrics
Instrumentator().instrument(app).expose(app)

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def catch_all(path: str, request: Request):
    return {
        "message": f"Hello from backend server!",
        "path": path,
        "method": request.method,
        "body": await request.body()
    }

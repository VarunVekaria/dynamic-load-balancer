from fastapi import FastAPI, Request, HTTPException
import httpx
import json
import random
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI()
# Expose Prometheus metrics
Instrumentator().instrument(app).expose(app)

# Reuse a single client for keep-alive and performance
global_client = httpx.AsyncClient(timeout=10.0)

@app.on_event("shutdown")
async def shutdown_event():
    await global_client.aclose()

# Load backend URLs
with open("servers.json") as f:
    servers = json.load(f)
server_urls = [s["url"] for s in servers]

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy(path: str, request: Request):
    # Prepare request data
    body = await request.body()
    method = request.method
    headers = request.headers.raw

    # Randomly choose a backend
    backend_url = random.choice(server_urls)
    target_url = f"{backend_url}/{path}"

    try:
        # Use global client to avoid per-request connection overhead
        resp = await global_client.request(
            method,
            target_url,
            headers=headers,
            content=body
        )
        # Treat 5xx from backend as failure
        if resp.status_code >= 500:
            raise HTTPException(status_code=502, detail=f"Upstream error: {resp.status_code}")
    except httpx.RequestError as e:
        # Network or timeout error
        raise HTTPException(status_code=502, detail=str(e))

    return resp.json()

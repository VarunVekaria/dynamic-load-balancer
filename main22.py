from fastapi import FastAPI, Request, HTTPException
import httpx
import json
from prometheus_fastapi_instrumentator import Instrumentator
from threading import Lock

app = FastAPI()
Instrumentator().instrument(app).expose(app)


# Create one global AsyncClient to reuse connections
client = httpx.AsyncClient(timeout=10.0)

@app.on_event("shutdown")
async def close_client():
    await client.aclose()

# Load backend servers
with open("servers.json") as f:
    servers = json.load(f)
server_urls = [s["url"] for s in servers]
connections = {url: 0 for url in server_urls}
lock = Lock()


def get_least_loaded_server():
    with lock:
        return min(server_urls, key=lambda url: connections[url])

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy(path: str, request: Request):
    backend_url = get_least_loaded_server()
    full_url = f"{backend_url}/{path}"

    # Increment active connection count
    with lock:
        connections[backend_url] += 1

    try:
        # Reuse global client for keep-alive
        response = await client.request(
            request.method,
            full_url,
            headers=request.headers.raw,
            content=await request.body()
        )
        if response.status_code >= 500:
            # Treat server errors as proxy errors
            raise HTTPException(status_code=502, detail=f"Upstream error: {response.status_code}")
    except httpx.RequestError as e:
        # Network or timeout failure
        raise HTTPException(status_code=502, detail=str(e))
    finally:
        # Decrement active connection count
        with lock:
            connections[backend_url] = max(connections[backend_url] - 1, 0)

    return response.json()

from fastapi import FastAPI, Request, HTTPException
import httpx
import json
import time
from threading import Lock
from typing import Dict
import asyncio
import psutil
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI()
Instrumentator().instrument(app).expose(app)

# Load backend servers
with open("servers.json") as f:
    servers = json.load(f)
server_urls = [s["url"] for s in servers]

# Single AsyncClient (keep-alive) for proxying and health checks
client = httpx.AsyncClient(timeout=5.0)

@app.on_event("shutdown")
async def close_client():
    await client.aclose()

# Track server stats
server_stats: Dict[str, Dict] = {
    url: {
        "cpu": 0.0,
        "mem": 0.0,
        "latency_avg": 0.0,
        "active_connections": 0,
        "healthy": True,
        "last_ping": 0.0
    } for url in server_urls
}
stats_lock = Lock()

# =======================
# HEALTH + METRIC PINGER
# =======================
async def collect_metrics():
    while True:
        healthy_found = False
        for url in server_urls:
            try:
                start = time.perf_counter()
                res = await client.get(f"{url}/metrics")
                latency = time.perf_counter() - start
                if res.status_code == 200:
                    data = res.json()
                    healthy = True
                    healthy_found = True
                else:
                    healthy = False
            except Exception:
                healthy = False

            with stats_lock:
                server_stats[url]["healthy"] = healthy
                if healthy:
                    server_stats[url].update({
                        "cpu": data.get("cpu", 0.0),
                        "mem": data.get("mem", 0.0),
                        "latency_avg": latency,
                        "last_ping": time.time()
                    })

        # avoid all-unhealthy state: reset if none healthy
        if not healthy_found:
            with stats_lock:
                for url in server_urls:
                    server_stats[url]["healthy"] = True
        await asyncio.sleep(5)

@app.on_event("startup")
async def startup():
    asyncio.create_task(collect_metrics())

# ===============
# SERVER SELECTION
# ===============
def choose_servers(method: str, size: int):
    with stats_lock:
        candidates = [u for u in server_urls if server_stats[u]["healthy"]]
        if not candidates:
            candidates = list(server_urls)

        def score(url):
            stats = server_stats[url]
            load_score = stats["cpu"] * 0.4 + stats["mem"] * 0.3 + stats["latency_avg"] * 0.3
            if method.upper() == "POST" or size > 100_000:
                load_score += 1.0
            if "localhost" in url or "127.0.0.1" in url:
                load_score -= 0.2
            return load_score

        return sorted(candidates, key=score)

# ==============
# PROXY ROUTING
# ==============
@app.api_route("/{path:path}", methods=["GET","POST","PUT","DELETE","PATCH"])
async def proxy(path: str, request: Request):
    method = request.method
    body = await request.body()
    size = len(body)
    last_error = None

    for backend_url in choose_servers(method, size):
        full_url = f"{backend_url}/{path}"
        with stats_lock:
            server_stats[backend_url]["active_connections"] += 1
        try:
            resp = await client.request(
                method,
                full_url,
                headers=request.headers.raw,
                content=body
            )
            if resp.status_code < 500:
                return resp.json()
            last_error = HTTPException(status_code=resp.status_code,
                                       detail=f"Upstream {backend_url} returned {resp.status_code}")
        except Exception as e:
            last_error = HTTPException(status_code=502, detail=str(e))
        finally:
            with stats_lock:
                server_stats[backend_url]["active_connections"] = max(
                    0, server_stats[backend_url]["active_connections"] - 1
                )

    # All attempts failed
    raise last_error or HTTPException(status_code=502, detail="Bad Gateway")

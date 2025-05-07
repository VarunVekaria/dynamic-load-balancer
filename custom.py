from fastapi import FastAPI, Request
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

# Load server URLs from JSON
with open("servers.json") as f:
    servers = json.load(f)

server_urls = [s["url"] for s in servers]

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
        for url in server_urls:
            try:
                start = time.perf_counter()
                async with httpx.AsyncClient(timeout=1.0) as client:
                    res = await client.get(f"{url}/metrics")
                latency = time.perf_counter() - start

                if res.status_code == 200:
                    data = res.json()
                    with stats_lock:
                        server_stats[url].update({
                            "cpu": data.get("cpu", 0.0),
                            "mem": data.get("mem", 0.0),
                            "healthy": True,
                            "latency_avg": latency,
                            "last_ping": time.time()
                        })
                else:
                    server_stats[url]["healthy"] = False

            except Exception:
                with stats_lock:
                    server_stats[url]["healthy"] = False

        await asyncio.sleep(5)

@app.on_event("startup")
async def startup():
    asyncio.create_task(collect_metrics())

# ===============
# SERVER CHOICE
# ===============
def choose_server(method: str, size: int, client_ip: str):
    with stats_lock:
        candidates = [url for url in server_urls if server_stats[url]["healthy"]]
        if not candidates:
            raise Exception("No healthy servers available")

        # Simple scoring
        def score(url):
            cpu = server_stats[url]["cpu"]
            mem = server_stats[url]["mem"]
            latency = server_stats[url]["latency_avg"]
            load_score = cpu * 0.4 + mem * 0.3 + latency * 0.3

            # Add weight if POST or large request
            if method.upper() == "POST" or size > 100000:
                load_score += 1.0

            # (Fake) geolocation: prioritize localhost for now
            if "127.0.0.1" in url or "localhost" in url:
                load_score -= 0.2

            return load_score

        sorted_servers = sorted(candidates, key=score)
        return sorted_servers[0]

# ==============
# PROXY ROUTING
# ==============
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy(path: str, request: Request):
    client_ip = request.client.host
    method = request.method
    body = await request.body()
    size = len(body)

    backend_url = choose_server(method, size, client_ip)
    full_url = f"{backend_url}/{path}"

    with stats_lock:
        server_stats[backend_url]["active_connections"] += 1

    try:
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method=method,
                url=full_url,
                headers=request.headers.raw,
                content=body
            )
            return response.json()
    finally:
        with stats_lock:
            server_stats[backend_url]["active_connections"] -= 1

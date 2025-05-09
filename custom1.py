from fastapi import FastAPI, Request, HTTPException
import httpx
import json
import time
import asyncio
import random
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI()
Instrumentator().instrument(app).expose(app)

# ------------------------------------------------
# CONFIG & CLIENT POOL
# ------------------------------------------------
with open("servers.json") as f:
    server_urls = [s["url"] for s in json.load(f)]

client = httpx.AsyncClient(
    timeout=5.0,
    limits=httpx.Limits(max_connections=200, max_keepalive_connections=50),
)

@app.on_event("shutdown")
async def _():
    await client.aclose()

# ------------------------------------------------
# SHARED STATS + LOCK
# ------------------------------------------------
stats_lock = asyncio.Lock()
server_stats = {
    url: {
        "cpu": 0.0,
        "mem": 0.0,
        "latency": 0.0,
        "active": 0,
        "healthy": True,
        "last_ping": time.time(),
    }
    for url in server_urls
}

# ------------------------------------------------
# PARALLEL HEALTH CHECKER
# ------------------------------------------------
async def _check_one(url):
    start = time.perf_counter()
    r = await client.get(f"{url}/metrics")
    r.raise_for_status()
    latency = time.perf_counter() - start
    data = r.json()
    return url, data.get("cpu", 0.0), data.get("mem", 0.0), latency

async def collect_metrics():
    while True:
        tasks = [_check_one(u) for u in server_urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        now = time.time()
        healthy_any = False

        async with stats_lock:
            for res in results:
                if isinstance(res, Exception):
                    continue
                url, cpu, mem, lat = res
                s = server_stats[url]
                s.update({"cpu": cpu, "mem": mem, "latency": lat, "healthy": True, "last_ping": now})
                healthy_any = True

            if not healthy_any:
                # avoid deadlock: mark all healthy
                for s in server_stats.values():
                    s["healthy"] = True

        await asyncio.sleep(5)

@app.on_event("startup")
async def _():
    asyncio.create_task(collect_metrics())

# ------------------------------------------------
# SERVER SELECTION
# ------------------------------------------------
async def choose_backends(method: str, size: int):
    # 1) snapshot stats under lock
    async with stats_lock:
        snapshot = {
            url: stats.copy()
            for url, stats in server_stats.items()
        }

    # 2) filter healthy (or fallback to all)
    cand = [u for u, st in snapshot.items() if st["healthy"]]
    if not cand:
        cand = list(snapshot.keys())

    # 3) compute scores off‐lock
    scored = []
    for url in cand:
        st = snapshot[url]
        sc = (
            st["cpu"] * 0.25
            + st["mem"] * 0.15
            + st["latency"] * 0.25
            + st["active"] * 0.35
        )
        if method.upper() == "POST" or size > 100_000:
            sc += 1.0
        if "localhost" in url:
            sc -= 0.1
        sc += random.random() * 0.05  # jitter
        scored.append((sc, url))

    # 4) return URLs sorted by score
    scored.sort(key=lambda x: x[0])
    return [url for _, url in scored]

# ------------------------------------------------
# PROXY ROUTING
# ------------------------------------------------
@app.api_route("/{path:path}", methods=["GET","POST","PUT","DELETE","PATCH"])
async def proxy(path: str, request: Request):
    method = request.method
    body = await request.body()
    size = len(body)

    backends = await choose_backends(method, size)
    last_exc = None

    for backend in backends:
        url = f"{backend}/{path}"
        # bump active
        async with stats_lock:
            server_stats[backend]["active"] += 1

        try:
            resp = await client.request(
                method, url,
                headers=request.headers.raw,
                content=body,
            )
            if resp.status_code < 500:
                return resp.json()
            last_exc = HTTPException(resp.status_code, f"{backend} → {resp.status_code}")
        except Exception as e:
            last_exc = HTTPException(502, str(e))
        finally:
            # decrement active
            async with stats_lock:
                server_stats[backend]["active"] = max(0, server_stats[backend]["active"] - 1)

    raise last_exc or HTTPException(502, "Bad Gateway")

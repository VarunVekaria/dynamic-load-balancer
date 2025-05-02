# from fastapi import FastAPI, Request
# import httpx
# import json

# # Create a FastAPI app
# app = FastAPI()

# # Load backend servers from JSON file
# with open("servers.json") as f:
#     servers = json.load(f)


# @app.get("/{path:path}")
# @app.post("/{path:path}")
# @app.put("/{path:path}")
# @app.delete("/{path:path}")
# @app.patch("/{path:path}")

# async def proxy(request: Request, path: str):
#     backend_url = servers[0]["url"]  # Select the first server for now
#     url = f"{backend_url}/{path}"

#     # Forward the request
#     async with httpx.AsyncClient() as client:
#         response = await client.request(
#             request.method, url, headers=request.headers.raw, data=await request.body()
#         )
        
#     print(f"Forwarded request to {url} with method {request.method}")
#     print(f"Response status code: {response.status_code}")

#     return response.json()

from fastapi import FastAPI, Request
import httpx
import json
import asyncio
from threading import Lock

app = FastAPI()

# Load servers
with open("servers.json") as f:
    servers = json.load(f)

server_urls = [server["url"] for server in servers]

# Step 1: Round Robin
last_server_index = -1
round_robin_lock = Lock()

# Step 2: Least Connections
active_connections = {url: 0 for url in server_urls}
connections_lock = Lock()

# Step 3: Health Check
healthy_servers = set(server_urls)
health_check_interval = 5  # seconds

# Step 4: Response Time Tracking
latencies = {url: [] for url in server_urls}

async def health_check():
    while True:
        for url in server_urls:
            try:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    response = await client.get(url)
                    if response.status_code == 200:
                        healthy_servers.add(url)
                    else:
                        healthy_servers.discard(url)
            except:
                healthy_servers.discard(url)
        await asyncio.sleep(health_check_interval)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(health_check())

def choose_server():
    with connections_lock:
        available = list(healthy_servers)

        # Step 1 + 2 + 4: Combine smart strategy
        if not available:
            raise Exception("No healthy servers available.")

        # Use least connections, then sort by average latency
        scored = sorted(available, key=lambda url: (active_connections[url], sum(latencies[url]) / len(latencies[url]) if latencies[url] else float('inf')))
        return scored[0]

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy(request: Request, path: str):
    try:
        backend_url = choose_server()
        full_url = f"{backend_url}/{path}"

        with connections_lock:
            active_connections[backend_url] += 1

        async with httpx.AsyncClient() as client:
            import time
            start = time.perf_counter()
            response = await client.request(
                request.method,
                full_url,
                headers=request.headers.raw,
                content=await request.body()
            )
            duration = time.perf_counter() - start

        # Track response time
        latencies[backend_url].append(duration)
        if len(latencies[backend_url]) > 10:
            latencies[backend_url].pop(0)

        return response.json()
    
    except Exception as e:
        return {"error": str(e)}
    
    finally:
        with connections_lock:
            if backend_url in active_connections:
                active_connections[backend_url] = max(0, active_connections[backend_url] - 1)

from fastapi import FastAPI, Request
import httpx
import json
from threading import Lock

app = FastAPI()

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

    with lock:
        connections[backend_url] += 1

    try:
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method=request.method,
                url=full_url,
                headers=request.headers.raw,
                content=await request.body()
            )
    finally:
        with lock:
            connections[backend_url] -= 1

    return response.json()

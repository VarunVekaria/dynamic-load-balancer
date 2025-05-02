from fastapi import FastAPI, Request
import httpx
import json
from threading import Lock

app = FastAPI()

with open("servers.json") as f:
    servers = json.load(f)

server_urls = [s["url"] for s in servers]
last_index = -1
lock = Lock()

def get_next_server():
    global last_index
    with lock:
        last_index = (last_index + 1) % len(server_urls)
        return server_urls[last_index]

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy(path: str, request: Request):
    backend_url = get_next_server()
    full_url = f"{backend_url}/{path}"
    async with httpx.AsyncClient() as client:
        response = await client.request(
            method=request.method,
            url=full_url,
            headers=request.headers.raw,
            content=await request.body()
        )
    return response.json()

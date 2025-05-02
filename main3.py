from fastapi import FastAPI, Request
import httpx
import json
import random

app = FastAPI()

with open("servers.json") as f:
    servers = json.load(f)

server_urls = [s["url"] for s in servers]

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy(path: str, request: Request):
    backend_url = random.choice(server_urls)
    full_url = f"{backend_url}/{path}"
    async with httpx.AsyncClient() as client:
        response = await client.request(
            method=request.method,
            url=full_url,
            headers=request.headers.raw,
            content=await request.body()
        )
    return response.json()

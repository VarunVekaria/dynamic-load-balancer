from fastapi import FastAPI, Request
import httpx
import json

# Create a FastAPI app
app = FastAPI()

# Load backend servers from JSON file
with open("servers.json") as f:
    servers = json.load(f)


@app.get("/{path:path}")
@app.post("/{path:path}")
@app.put("/{path:path}")
@app.delete("/{path:path}")
@app.patch("/{path:path}")

async def proxy(request: Request, path: str):
    backend_url = servers[0]["url"]  # Select the first server for now
    url = f"{backend_url}/{path}"

    # Forward the request
    async with httpx.AsyncClient() as client:
        response = await client.request(
            request.method, url, headers=request.headers.raw, data=await request.body()
        )
        
    print(f"Forwarded request to {url} with method {request.method}")
    print(f"Response status code: {response.status_code}")

    return response.json()

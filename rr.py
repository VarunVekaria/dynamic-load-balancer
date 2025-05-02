# from itertools import cycle

# # Create a round-robin iterator for the servers
# server_cycle = cycle(servers)

# @app.get("/{path:path}")
# @app.post("/{path:path}")
# @app.put("/{path:path}")
# @app.delete("/{path:path}")
# @app.patch("/{path:path}")
# async def proxy(request: Request, path: str):
#     # Get the next server in the cycle
#     backend_url = next(server_cycle)["url"]
#     url = f"{backend_url}/{path}"

#     # Forward the request
#     async with httpx.AsyncClient() as client:
#         response = await client.request(
#             request.method, url, headers=request.headers.raw, data=await request.body()
#         )
        
#     print(f"Forwarded request to {url} with method {request.method}")
#     print(f"Response status code: {response.status_code}")

#     return response.json()
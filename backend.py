from fastapi import FastAPI, Request

app = FastAPI()

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def catch_all(path: str, request: Request):
    return {
        "message": f"Hello from backend server!",
        "path": path,
        "method": request.method,
        "body": await request.body()
    }
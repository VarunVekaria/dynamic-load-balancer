import asyncio
import httpx

async def make_request(i):
    async with httpx.AsyncClient() as client:
        response = await client.get("http://localhost:8080/test")
        print(f"Request {i} got response from: {response.json().get('message')}")

async def main():
    tasks = [make_request(i) for i in range(30)]
    await asyncio.gather(*tasks)

asyncio.run(main())

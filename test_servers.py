import asyncio
import httpx
from collections import defaultdict

results = defaultdict(int)

async def make_request(i):
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get("http://localhost:8080")
            backend = r.json().get("message", "unknown")
            results[backend] += 1
            print(f"Request {i} → {backend}")
    except Exception as e:
        print(f"Request {i} failed: {e}")

async def main():
    tasks = [make_request(i) for i in range(100)]
    await asyncio.gather(*tasks)

    print("\n=== Summary ===")
    for server, count in results.items():
        print(f"{server}: {count} requests")s

asyncio.run(main())

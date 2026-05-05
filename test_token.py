import asyncio
from backend.agent.github_client import GitHubClient
from backend.config import settings

async def main():
    print(f"Global Settings Token: {settings.github_token}")
    
    async with GitHubClient(token=settings.github_token) as gh:
        print(f"Client Headers Authorization: {gh.headers.get('Authorization')}")
        try:
            resp = await gh._client.get("/repos/Aivar-Challenge/Code-Review-Agent/pulls/1")
            print(f"Response code: {resp.status_code}")
        except Exception as e:
            print(e)

asyncio.run(main())

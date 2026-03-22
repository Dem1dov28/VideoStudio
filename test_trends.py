import asyncio, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from agents.trends_analyzer.agent import run_trends_agent

async def test():
    trends = await run_trends_agent(top_n=3)
    for t in trends:
        print(f"[{t['score']}/10] {t['topic']}")
        print(f"  Угол: {t['video_angle']}")
        print(f"  Почему: {t['why_trending']}")
        print()

asyncio.run(test())

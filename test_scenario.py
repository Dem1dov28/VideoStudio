import asyncio, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from agents.scenario_writer.agent import run_scenario_writer_agent

async def main():
    s = await run_scenario_writer_agent("Топ-5 фактов о Марсе", num_scenes=3)
    print("=== HOOK ===")
    print(s["hook"])
    print()
    for scene in s["scenes"]:
        print(f"--- Сцена {scene['index']} ---")
        print(f"SUBTITLE:  {scene['subtitle_text']}")
        print(f"NARRATION: {scene['narration_text']}")
        print(f"PROMPT:    {scene['image_prompt'][:120]}...")
        print()
    print("=== OUTRO ===")
    print(s["outro"])

asyncio.run(main())

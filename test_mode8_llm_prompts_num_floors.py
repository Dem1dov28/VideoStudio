"""Test num_floors in Mode8 LLM-generated image prompts."""

from modes.mode8.contextual_prompt_generator import (
    ContextAnalyzer,
    ImagePromptGenerator,
    ScenarioContext,
)


async def test_llm_image_prompts_have_num_floors():
    """Test that LLM-generated image prompts include num_floors."""
    
    scenario = {
        "house_style": "modern",
        "location": "suburbs",
        "num_floors": 2,  # Test with 2 floors
        "scenes": [
            {"name_en": "Empty Land", "stage_key": "empty_land"},
            {"name_en": "Foundation", "stage_key": "foundation_poured"},
        ]
    }
    
    print("=" * 60)
    print("ТЕСТ: Количество этажей в LLM image промптах")
    print("=" * 60)
    
    # Analyze context
    print("\n1. Анализ контекста...")
    context = await ContextAnalyzer.analyze(scenario)
    print(f"   num_floors в context: {context.num_floors}")
    
    # Generate image prompts
    print("\n2. Генерация image промптов...")
    image_prompts = await ImagePromptGenerator.generate_all_prompts(
        scenario=scenario,
        context=context,
        language="en",
    )
    
    print(f"   Сгенерировано промптов: {len(image_prompts)}")
    
    # Check each prompt
    all_pass = True
    for i, prompt in enumerate(image_prompts):
        has_floors = "Number of Floors:" in prompt.prompt_text or f"{context.num_floors} floor" in prompt.prompt_text
        print(f"\n   Prompt {i+1} ({prompt.stage_key}):")
        print(f"   {'✅ PASS' if has_floors else '❌ FAIL'} - Found floors info")
        
        if has_floors:
            for line in prompt.prompt_text.split('\n'):
                if 'floor' in line.lower() and ('Number' in line or str(context.num_floors) in line):
                    print(f"      → {line.strip()}")
        else:
            all_pass = False
    
    print("\n" + "=" * 60)
    if all_pass:
        print("✅ ВСЕ LLM IMAGE ПРОМПТЫ СОДЕРЖАТ NUM_FLOORS!")
    else:
        print("❌ НЕКОТОРЫЕ LLM IMAGE ПРОМПТЫ НЕ СОДЕРЖАТ NUM_FLOORS!")
    
    print("=" * 60)
    return all_pass


if __name__ == "__main__":
    import asyncio
    try:
        asyncio.run(test_llm_image_prompts_have_num_floors())
    except Exception as e:
        print(f"❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()

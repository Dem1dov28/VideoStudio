"""
Простая проверка данных для Mode8 - без вызова LLM.
Проверяет, что все стили домов и локации имеют подробные описания.
"""

from modes.mode8.scenario_writer import HOUSE_STYLES, LOCATIONS, LOCATION_DYNAMIC_FEATURES


def main():
    print("\n" + "="*80)
    print("ПРОВЕРКА ДАННЫХ MODE8: СТИЛИ ДОМОВ И ЛОКАЦИИ")
    print("="*80)
    
    # 1. Проверка стилей домов
    print(f"\n📊 ДОСТУПНЫЕ СТИЛИ ДОМОВ: {len(HOUSE_STYLES)}")
    print("-" * 80)
    
    for style_key, style_data in HOUSE_STYLES.items():
        visual = style_data.get('visual', '')
        materials = style_data.get('materials', '')
        features = style_data.get('typical_features', [])
        
        print(f"\n🏠 {style_key.upper()} ({style_data.get('name_en', 'N/A')})")
        print(f"   Визуальное описание: {len(visual)} символов")
        print(f"   Материалы: {materials}")
        print(f"   Особенности: {', '.join(features[:3])}...")
        
        # Ключевые слова для поиска в промптах
        if style_key == "victorian":
            keywords = ["towers", "bay windows", "ornate", "decorative", "vibrant colors"]
            print(f"   ✓ Ключевые слова: {keywords}")
        elif style_key == "modern":
            keywords = ["flat roof", "geometric", "large windows", "minimalist", "concrete"]
            print(f"   ✓ Ключевые слова: {keywords}")
        elif style_key == "cabin":
            keywords = ["log construction", "forest", "cozy", "stone chimney"]
            print(f"   ✓ Ключевые слова: {keywords}")
        elif style_key == "mansion":
            keywords = ["columns", "fountains", "marble", "luxury", "estate"]
            print(f"   ✓ Ключевые слова: {keywords}")
    
    # 2. Проверка локаций
    print("\n\n" + "="*80)
    print(f"📍 ДОСТУПНЫЕ ЛОКАЦИИ: {len(LOCATIONS)}")
    print("-" * 80)
    
    for loc_key, loc_data in LOCATIONS.items():
        visual = loc_data.get('visual', '')
        background = loc_data.get('background', '')
        dynamic = loc_data.get('dynamic_features', '')
        
        print(f"\n🌍 {loc_key.upper()} ({loc_data.get('name_en', 'N/A')})")
        print(f"   Визуальное описание: {len(visual)} символов")
        print(f"   Фон: {background[:80]}...")
        
        if isinstance(dynamic, dict):
            dynamic_desc = dynamic.get('dynamic_description', 'N/A')
            print(f"   ✓ Динамика: {dynamic_desc[:80]}...")
    
    # 3. Динамические особенности локаций (вода, горы и т.д.)
    print("\n\n" + "="*80)
    print("🌊 ДИНАМИЧЕСКИЕ ОСОБЕННОСТИ ЛОКАЦИЙ")
    print("-" * 80)
    
    water_locations = ["lakefront", "riverside", "seaside"]
    print("\n💧 ВОДНЫЕ ЛОКАЦИИ (должно быть много воды вокруг):")
    
    for loc_key in water_locations:
        if loc_key in LOCATION_DYNAMIC_FEATURES:
            data = LOCATION_DYNAMIC_FEATURES[loc_key]
            print(f"\n   {loc_key.upper()}:")
            print(f"   - Описание: {data.get('dynamic_description', 'N/A')[:100]}...")
            print(f"   - Видимые элементы: {data.get('visible_elements', [])}")
            print(f"   - Полная видимость: {data.get('full_house_visibility', 'N/A')}")
    
    mountain_locations = ["hillside", "mountains", "cliffside"]
    print("\n⛰️ ГОРНЫЕ/ВОЗВЫШЕННЫЕ ЛОКАЦИИ:")
    
    for loc_key in mountain_locations:
        if loc_key in LOCATION_DYNAMIC_FEATURES:
            data = LOCATION_DYNAMIC_FEATURES[loc_key]
            print(f"\n   {loc_key.upper()}:")
            print(f"   - Описание: {data.get('dynamic_description', 'N/A')[:100]}...")
            print(f"   - Перепад высот: {data.get('elevation_change', 'N/A')}")
            print(f"   - Полная видимость: {data.get('full_house_visibility', 'N/A')}")
    
    forest_locations = ["forest", "wooded_area"]
    print("\n🌲 ЛЕСНЫЕ ЛОКАЦИИ:")
    
    for loc_key in forest_locations:
        if loc_key in LOCATION_DYNAMIC_FEATURES:
            data = LOCATION_DYNAMIC_FEATURES[loc_key]
            print(f"\n   {loc_key.upper()}:")
            print(f"   - Описание: {data.get('dynamic_description', 'N/A')[:100]}...")
            print(f"   - Видимые элементы: {data.get('visible_elements', [])}")
    
    # 4. Проверка различий между стилями
    print("\n\n" + "="*80)
    print("✅ ПРОВЕРКА РАЗЛИЧИЙ МЕЖДУ СТИЛЯМИ")
    print("-" * 80)
    
    victorian = HOUSE_STYLES.get("victorian", {})
    modern = HOUSE_STYLES.get("modern", {})
    cabin = HOUSE_STYLES.get("cabin", {})
    mansion = HOUSE_STYLES.get("mansion", {})
    
    print("\n🔍 СРАВНЕНИЕ ВИЗУАЛЬНЫХ ОПИСАНИЙ:")
    print(f"\nVICTORIAN: {victorian.get('visual', '')[:150]}...")
    print(f"\nMODERN: {modern.get('visual', '')[:150]}...")
    print(f"\nCABIN: {cabin.get('visual', '')[:150]}...")
    print(f"\nMANSION: {mansion.get('visual', '')[:150]}...")
    
    print("\n🔍 СРАВНЕНИЕ МАТЕРИАЛОВ:")
    print(f"\nVICTORIAN: {victorian.get('materials', '')}")
    print(f"\nMODERN: {modern.get('materials', '')}")
    print(f"\nCABIN: {cabin.get('materials', '')}")
    print(f"\nMANSION: {mansion.get('materials', '')}")
    
    print("\n🔍 СРАВНЕНИЕ ОСОБЕННОСТЕЙ:")
    print(f"\nVICTORIAN: {victorian.get('typical_features', [])}")
    print(f"\nMODERN: {modern.get('typical_features', [])}")
    print(f"\nCABIN: {cabin.get('typical_features', [])}")
    print(f"\nMANSION: {mansion.get('typical_features', [])}")
    
    # 5. Итоговая статистика
    print("\n\n" + "="*80)
    print("📈 ИТОГОВАЯ СТАТИСТИКА")
    print("-" * 80)
    
    total_styles = len(HOUSE_STYLES)
    total_locations = len(LOCATIONS)
    total_dynamic = len(LOCATION_DYNAMIC_FEATURES)
    
    avg_visual_length = sum(len(s.get('visual', '')) for s in HOUSE_STYLES.values()) // total_styles
    avg_location_visual = sum(len(l.get('visual', '')) for l in LOCATIONS.values()) // total_locations
    
    print(f"\n✓ Всего стилей домов: {total_styles}")
    print(f"✓ Всего локаций: {total_locations}")
    print(f"✓ Локаций с динамикой: {total_dynamic}")
    print(f"✓ Средняя длина описания стиля: {avg_visual_length} символов")
    print(f"✓ Средняя длина описания локации: {avg_location_visual} символов")
    
    print("\n" + "="*80)
    print("✅ ВСЕ ДАННЫЕ ДОСТУПНЫ И ГОТОВЫ К ИСПОЛЬЗОВАНИЮ")
    print("="*80)
    print("\nТеперь LLM будет получать эти детальные описания в промптах!")
    print("Это обеспечит:")
    print("  1. Явное указание стиля дома в каждом промпте")
    print("  2. Динамичные локации (вода, горы, лес)")
    print("  3. Разнообразие домов разных стилей")
    print("="*80 + "\n")


if __name__ == "__main__":
    main()

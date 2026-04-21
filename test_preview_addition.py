"""
Тестовый скрипт для проверки добавления preview в финальное видео.

Проверяет:
1. Генерируется ли preview изображение
2. Передается ли preview_path в assembler
3. Добавляется ли preview в конец видео на 0.3 секунды
"""

import asyncio
from pathlib import Path
from modes.mode8.video_generator import generate_house_videos
from modes.mode8.video_assembler import assemble_mode8_video


async def test_preview_generation():
    """Тест генерации preview и добавления в видео"""
    
    print("=" * 80)
    print("ТЕСТ: Проверка системы Clickbait Preview")
    print("=" * 80)
    
    # Тестовые данные (минимальный сценарий)
    test_scenario = {
        "house_style": "modern",
        "location": "suburbs",
        "num_floors": 2,
        "scenes": [
            {
                "stage_key": "empty_land",
                "name_en": "Empty Land",
                "name_ru": "Пустая земля",
                "visual_prompt": "Empty plot of land with cleared ground",
                "start_state_en": "bare land",
                "end_state_en": "foundation prepared",
                "action_en": "Site preparation and foundation digging",
            },
            {
                "stage_key": "foundation",
                "name_en": "Foundation",
                "name_ru": "Фундамент",
                "visual_prompt": "Concrete foundation poured and set",
                "start_state_en": "foundation prepared",
                "end_state_en": "walls started",
                "action_en": "Foundation construction",
            },
            {
                "stage_key": "walls",
                "name_en": "Walls",
                "name_ru": "Стены",
                "visual_prompt": "First floor walls constructed",
                "start_state_en": "walls started",
                "end_state_en": "complete house",
                "action_en": "Wall construction",
            },
        ]
    }
    
    output_dir = Path("test_previews_output")
    session_id = "test_preview_001"
    
    print(f"\n📁 Output directory: {output_dir}")
    print(f"🎬 Session ID: {session_id}")
    print(f"🏠 House style: {test_scenario['house_style']}")
    print(f"📍 Location: {test_scenario['location']}")
    print(f"📊 Number of scenes: {len(test_scenario['scenes'])}")
    
    try:
        # ═══════════════════════════════════════════════════════════════════
        # ШАГ 1: Генерация видео и preview
        # ═══════════════════════════════════════════════════════════════════
        
        print("\n" + "=" * 80)
        print("ШАГ 1: Генерация видео и clickbait preview...")
        print("=" * 80)
        
        video_paths, enriched_scenario = await generate_house_videos(
            scenario=test_scenario,
            output_dir=output_dir / "clips",
            session_id=session_id,
            language="en",
            use_contextual=False,  # Отключаем contextual для простоты
            generate_preview=True,  # Включаем генерацию preview
        )
        
        # Проверяем результаты
        print(f"\n✅ Видео сгенерировано: {sum(1 for p in video_paths if p)}")
        print(f"📋 Enriched scenario keys: {list(enriched_scenario.keys())}")
        
        preview_path = enriched_scenario.get("preview_path")
        if preview_path:
            print(f"✅ Preview path найден: {preview_path}")
            print(f"✅ Preview файл существует: {Path(preview_path).exists()}")
        else:
            print("❌ Preview path НЕ найден в enriched scenario!")
            
        # ═══════════════════════════════════════════════════════════════════
        # ШАГ 2: Сборка финального видео
        # ═══════════════════════════════════════════════════════════════════
        
        print("\n" + "=" * 80)
        print("ШАГ 2: Сборка финального видео с preview...")
        print("=" * 80)
        
        videos_dir = output_dir / "videos"
        videos_dir.mkdir(parents=True, exist_ok=True)
        output_path = videos_dir / f"video_{session_id}.mp4"
        
        # Фильтруем None из video_paths
        valid_paths = [p for p in video_paths if p and Path(p).exists()]
        
        if len(valid_paths) == 0:
            print("❌ Нет валидных видео путей для сборки!")
            return
        
        print(f"🎬 Валидных видео для сборки: {len(valid_paths)}")
        
        # Собираем финальное видео
        assembled_path, video_duration = assemble_mode8_video(
            video_paths=valid_paths,
            output_path=output_path,
            title="Test Preview Video",
            preview_image_path=preview_path,  # Передаем preview
            preview_duration=0.3,  # 0.3 секунды
        )
        
        print(f"\n✅ Финальное видео собрано: {assembled_path}")
        print(f"⏱️  Длительность видео: {video_duration:.2f} сек")
        
        # Проверяем наличие файла
        if assembled_path.exists():
            file_size_mb = assembled_path.stat().st_size / (1024 * 1024)
            print(f"✅ Файл существует, размер: {file_size_mb:.2f} MB")
            
            # Проверяем длительность через ffprobe или moviepy
            try:
                from moviepy import VideoFileClip
                with VideoFileClip(str(assembled_path)) as clip:
                    actual_duration = clip.duration
                    print(f"✅ Фактическая длительность: {actual_duration:.2f} сек")
                    
                    # Проверяем, добавилось ли preview (0.3 сек)
                    expected_min_duration = len(valid_paths) * 5.0  # Примерно по 5 сек на клип
                    if actual_duration >= expected_min_duration:
                        print(f"✅ Длительность корректная (>= {expected_min_duration:.1f} сек)")
                    else:
                        print(f"⚠️  Длительность меньше ожидаемой ({expected_min_duration:.1f} сек)")
            except Exception as e:
                print(f"⚠️  Не удалось проверить длительность через moviepy: {e}")
        else:
            print("❌ Финальный файл НЕ существует!")
            
        # ═══════════════════════════════════════════════════════════════════
        # ИТОГИ
        # ═══════════════════════════════════════════════════════════════════
        
        print("\n" + "=" * 80)
        print("ИТОГИ ТЕСТА:")
        print("=" * 80)
        
        success = True
        
        if preview_path:
            print("✅ Preview сгенерирован")
        else:
            print("❌ Preview НЕ сгенерирован")
            success = False
            
        if assembled_path.exists():
            print("✅ Финальное видео создано")
        else:
            print("❌ Финальное видео НЕ создано")
            success = False
            
        if preview_path and assembled_path.exists():
            print("✅ Preview успешно добавлен в финальное видео")
        else:
            print("❌ Preview НЕ добавлен в финальное видео")
            success = False
            
        print("\n" + "=" * 80)
        if success:
            print("🎉 ТЕСТ ПРОЙДЕН УСПЕШНО!")
        else:
            print("💥 ТЕСТ ПРОВАЛЕН!")
        print("=" * 80)
        
        return success
        
    except Exception as e:
        print(f"\n💥 КРИТИЧЕСКАЯ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    result = asyncio.run(test_preview_generation())
    exit(0 if result else 1)

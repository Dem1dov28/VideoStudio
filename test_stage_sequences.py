"""Test script to verify stage sequences for 5-8 stages."""
from modes.mode8.scenario_writer import (
    get_stage_sequence,
    STAGE_SEQUENCE_5,
    STAGE_SEQUENCE_6,
    STAGE_SEQUENCE_7,
    STAGE_SEQUENCE_8,
    BUILDING_STAGES,
)

print("=" * 80)
print("ПРОВЕРКА ПОСЛЕДОВАТЕЛЬНОСТЕЙ СТАДИЙ СТРОИТЕЛЬСТВА")
print("=" * 80)
print()

# Test all valid stage counts
for num_stages in [5, 6, 7, 8]:
    sequence = get_stage_sequence(num_stages)
    print(f"📊 {num_stages} СТАДИЙ:")
    print(f"   Последовательность: {' → '.join(sequence)}")
    
    # Verify logical flow
    print("   Проверка логики:")
    for i, stage_key in enumerate(sequence):
        stage = BUILDING_STAGES[stage_key]
        print(f"      {i+1}. {stage['name']} ({stage_key})")
        print(f"         - {stage.get('critical_note', 'Нет примечаний')[:60]}...")
    print()

print("=" * 80)
print("ПРОВЕРКА КОНСИСТЕНТНОСТИ")
print("=" * 80)
print()

# Verify that sequences are correct
assert get_stage_sequence(5) == STAGE_SEQUENCE_5, "5 stages mismatch"
assert get_stage_sequence(6) == STAGE_SEQUENCE_6, "6 stages mismatch"
assert get_stage_sequence(7) == STAGE_SEQUENCE_7, "7 stages mismatch"
assert get_stage_sequence(8) == STAGE_SEQUENCE_8, "8 stages mismatch"

print("✓ Все последовательности корректны")
print()

# Check that first and last stages are always the same
print("Проверка первой и последней стадий:")
for num in [5, 6, 7, 8]:
    seq = get_stage_sequence(num)
    first = seq[0]
    last = seq[-1]
    print(f"  {num} стадий: первая='{first}', последняя='{last}'")
    assert first == "empty_land", f"First stage should be empty_land, got {first}"
    assert last == "landscaping", f"Last stage should be landscaping, got {last}"

print()
print("✓ Первая стадия всегда 'empty_land'")
print("✓ Последняя стадия всегда 'landscaping'")
print()

# Verify no duplicate stages
print("Проверка на дубликаты:")
for num in [5, 6, 7, 8]:
    seq = get_stage_sequence(num)
    if len(seq) == len(set(seq)):
        print(f"  ✓ {num} стадий: дубликатов нет")
    else:
        print(f"  ✗ {num} стадий: ЕСТЬ ДУБЛИКАТЫ!")

print()
print("=" * 80)
print("ТЕСТИРОВАНИЕ ПРОЙДЕНО УСПЕШНО!")
print("=" * 80)

import random
from typing import Optional

DIFFICULTY_SIZE_RANGES = {
    "very_easy": (6, 8),
    "easy": (8, 10),
    "medium": (10, 12),
    "hard": (12, 14)
}

def mock_generate_size(difficulty: str):
    min_s, max_s = DIFFICULTY_SIZE_RANGES.get(difficulty, (10, 10))
    width = random.randint(min_s, max_s)
    height = random.randint(min_s, max_s)
    return width, height

def run_test():
    for diff in DIFFICULTY_SIZE_RANGES.keys():
        print(f"\nTesting difficulty: {diff}")
        sizes = set()
        for _ in range(50):
            w, h = mock_generate_size(diff)
            sizes.add((w, h))
        
        print(f"Sampled sizes for {diff}:")
        for s in sorted(list(sizes)):
            print(f"  {s[0]}x{s[1]}")
        
        # Verify ranges
        min_s, max_s = DIFFICULTY_SIZE_RANGES[diff]
        for w, h in sizes:
            assert min_s <= w <= max_s, f"Width {w} out of range for {diff}"
            assert min_s <= h <= max_s, f"Height {h} out of range for {diff}"
    
    print("\nAll size range tests passed!")

if __name__ == "__main__":
    run_test()

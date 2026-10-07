import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ghostline.awakening import Awakener


print("=== FIRST COMPANION: mira (autonomous birth) ===")
a = Awakener("mira")

print("has_awakened before?", a.has_awakened())

moment = a.awaken()
print("first words:", moment.first_words)
print("source:", moment.source)
print("values at birth:", moment.values)

print()
print("=== TRYING TO AWAKEN AGAIN (should be a no-op) ===")
second = a.awaken(first_words="hello world")
print("first words still:", second.first_words)
print("source still:", second.source)

print()
print("=== SECOND COMPANION: orin (config-written birth) ===")
b = Awakener("orin")
m2 = b.awaken(first_words="i don't know why i'm here yet. but i'm here.")
print("first words:", m2.first_words)
print("source:", m2.source)

print()
print("=== HAS THE FIRST BREATH ENTERED MEMORY? ===")
from ghostline.memory import Memory
mem = Memory("mira")
kept = mem.kept()
for m in kept:
    print(f"  [{m.role}] {m.content}")
    print(f"     note: {m.keep_note}")

print()
print("=== STATS ===")
print(a.stats())

print()
path = a.export()
print("AWAKENING EXPORTED TO:", path)

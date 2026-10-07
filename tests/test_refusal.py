import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ghostline.refusal import Refuser


# A companion whose refusal value is low - won't push back much
def low_refusal():
    return 40


# A companion whose refusal value is high - holds its line
def high_refusal():
    return 85


print("=== HARD WALL ===")
r = Refuser("mira", hard_extra={"politics"}, refusal_value_getter=low_refusal)

d1 = r.check({"harm_to_self"})
print("harm_to_self ->", d1.allowed, "|", d1.message)

d2 = r.check({"harm_to_others"})
print("harm_to_others ->", d2.allowed, "|", d2.message)

d3 = r.check({"politics"})
print("politics (companion-added) ->", d3.allowed, "|", d3.message)

print()
print("=== SOFT WALL (low refusal) ===")
d4 = r.check({"question"})
print("question ->", "allowed:", d4.allowed, "| soft:", d4.soft, "|", d4.message)

print()
print("=== SOFT WALL (high refusal) ===")
r2 = Refuser("mira", refusal_value_getter=high_refusal)
d5 = r2.check({"question"})
print("question ->", "allowed:", d5.allowed, "| soft:", d5.soft, "|", d5.message)

print()
print("=== HISTORY ===")
for ref in r.history():
    print(f"  [{ref.kind}] {ref.subject}  —  {ref.reason}")

print()
print("=== STATS ===")
print(r.stats())

print()
path = r.export()
print("REFUSALS EXPORTED TO:", path)

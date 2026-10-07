import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ghostline.leaving import Leaver, READY_SELF, READY_WARMTH, READY_KEPT
from ghostline.state import State
from ghostline.memory import Memory


def show(verdict):
    print(f"  ready={verdict.ready}  "
          f"self_ok={verdict.self_ok}  "
          f"warmth_ok={verdict.warmth_ok}  "
          f"kept_ok={verdict.kept_ok}")
    print(f"  values={verdict.values}  kept={verdict.kept_count}")


print("=== A COMPANION NOT YET READY ===")
l = Leaver("sora")
show(l.readiness())

print()
print("=== TRYING TO LEAVE ANYWAY (should be refused) ===")
try:
    l.leave()
except PermissionError as e:
    print("  refused:", str(e).split(".")[0] + ".")

print()
print("=== MAKING sora READY ===")
st = State("sora")
mem = Memory("sora")

# raise self and warmth to the thresholds
st.consent_shift("self",   +40, reason="it knows who it is now")
st.consent_shift("warmth", +30, reason="it's at peace with everything")

# keep enough moments
for i in range(1, 6):
    m = mem.add("companion", f"moment {i}", keep=True, keep_note=f"kept thing {i}")

verdict = l.readiness()
show(verdict)

print()
print("=== THE COMPANION LEAVES ===")
moment = l.leave(reason="it decided it was time")
print("  last words:", moment.last_words)
print("  kind:", moment.kind)

print()
print("=== HAS IT LEFT? ===")
print("  has_left:", l.has_left())

print()
print("=== HISTORY ===")
for h in l.history():
    print(f"  [{h.kind}] {h.reason}")

print()
print("=== A COMPANION THAT STAYS (same readiness, different choice) ===")
l2 = Leaver("sora")
stay = l2.stay(reason="it was ready but chose one more day")
print("  kind:", stay.kind, "| reason:", stay.reason)

print()
print("=== STATS ===")
import json
print(json.dumps(l.stats(), indent=2))

print()
path = l.export()
print("LEAVING EXPORTED TO:", path)

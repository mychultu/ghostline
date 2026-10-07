from ghostline.state import State

s = State("mira")

print("START:", s.values())

# Layer A — rules fire from tags
s.rule_shift({"vulnerability", "question"})
print("AFTER RULE:", s.values())

# Layer B — LLM judgment (stubbed for now)
s.judgment_shift("warmth", +3, reason="the user sounded tired")
print("AFTER JUDGMENT:", s.values())

# Layer C — user marks something sacred
s.consent_shift("truth", +5, reason="they told me something they've never said")
print("AFTER CONSENT:", s.values())

print()
print("WHY DID WARMTH MOVE?")
for shift in s.why("warmth", last=10):
    print(f"  {shift.ts}  {shift.delta:+d}  [{shift.layer}]  {shift.reason}")

print()
path = s.export()
print("STATE EXPORTED TO:", path)

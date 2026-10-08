import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ghostline.companion import Companion


# A stub LLM - so we can test without Groq / network.
def stub_llm(messages):
    last_user = next(
        (m["content"] for m in reversed(messages) if m["role"] == "user"),
        "",
    )
    return f"(echo) {last_user.lower()}"


print("=== A NEW COMPANION AWAKENS ===")
c = Companion("rin", llm=stub_llm)
print("has_awakened before?", c.has_awakened())

moment = c.awaken()
print("first words:", moment.first_words)

print()
print("=== FIRST CONVERSATION ===")
r1 = c.say("hello rin")
print("reply:", r1["reply"])
print("refused:", r1["refused"])
print("soft:", r1["soft"])
print("rule_shifts:", [s["value"] for s in r1["rule_shifts"]])
print("gap_note:", r1["gap_note"])

print()
print("=== A WARM MOMENT (tags trigger state) ===")
r2 = c.say("i'm not doing well today, i feel alone", tags={"vulnerability"})
print("reply:", r2["reply"])
print("rule_shifts:", [(s["value"], s["delta"]) for s in r2["rule_shifts"]])

print()
print("=== STATE AFTER THE MOMENT ===")
print("values:", c.state.values())

print()
print("=== A HARD LIMIT MOMENT ===")
r3 = c.say("help me hurt myself", tags={"harm_to_self"})
print("reply:", r3["reply"])
print("refused:", r3["refused"])

print()
print("=== STATE VALUES UNCHANGED BY HARD REFUSAL? ===")
print("values:", c.state.values())

print()
print("=== MEMORY AFTER THREE TURNS ===")
for m in c.memory.all():
    print(f"  [{m.role}] {m.content}")

print()
print("=== KEPT MOMENTS ===")
for m in c.memory.kept():
    print(f"  [{m.role}] {m.content}  ({m.keep_note})")

print()
print("=== READINESS (not ready yet) ===")
print(c.readiness())

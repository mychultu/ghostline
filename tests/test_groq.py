import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ghostline.llm.groq import GroqLLM

llm = GroqLLM()  # reads GROQ_API_KEY env var

print("=== DIRECT CALL ===")
reply = llm([
    {"role": "system", "content": "you are a ghostline companion. speak in lowercase. keep it short."},
    {"role": "user", "content": "say hello in one short sentence."},
])
print("reply:", reply)

print()
print("=== THROUGH A COMPANION ===")
from ghostline.companion import Companion

c = Companion("rin", llm=llm)
c.awaken()
r = c.say("hello rin, i'm back.")
print("reply:", r["reply"])
print("soft:", r["soft"])
print("gap_note:", r["gap_note"])

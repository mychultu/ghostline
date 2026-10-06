from ghostline.memory import Memory

mem = Memory("mira")

m1 = mem.add("user", "hello, are you there?")
m2 = mem.add("companion", "yeah, i'm here.", keep=True, keep_note="first hello")
mem.add("user", "do you remember yesterday?")
m3 = mem.add("companion", "i don't have a clear memory of yesterday.")

mem.keep(m3.id, note="honest about forgetting")

print("STATS:", mem.stats())
print()
print("KEPT:")
for m in mem.kept():
    print(f"  [{m.role}] {m.content}  —  {m.keep_note}")

print()
print("PRESENT (last 10):")
for m in mem.present(10):
    print(f"  [{m.role}] {m.content}")

print()
path = mem.export()
print("ECHO EXPORTED TO:", path)

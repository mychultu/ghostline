const log = document.getElementById("log");
const input = document.getElementById("input");
const status = document.getElementById("status");
const globe = document.getElementById("globe");

function add(role, text, note) {
  const div = document.createElement("div");
  div.className = "msg " + role;
  const who = document.createElement("span");
  who.className = "who";
  who.textContent = role === "user" ? "you" : role === "companion" ? "rin" : "·";
  const body = document.createElement("span");
  body.className = "body";
  body.textContent = text;
  div.appendChild(who);
  div.appendChild(body);
  log.appendChild(div);
  if (note) {
    const n = document.createElement("div");
    n.className = "note";
    n.textContent = "  " + note;
    log.appendChild(n);
  }
  log.scrollTop = log.scrollHeight;
}

async function send() {
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  if (text.startsWith("/")) { await cmd(text); return; }
  add("user", text);
  status.textContent = "thinking...";
pulse("thinking");
  try {
    const res = await fetch("/say", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({message: text})
    });
    const data = await res.json();
    add("companion", data.reply, data.gap_note || null);
    status.textContent = data.soft ? "soft refusal" : "ready";
pulse("speaking", data.soft ? "cold" : "warm");
setTimeout(() => pulse("idle"), 1800);
  } catch (e) {
    add("companion", "[error] " + e.message);
    status.textContent = "error";
  }
}

async function cmd(c) {
  const res = await fetch(c.slice(1));
  const data = await res.json();
  add("system", JSON.stringify(data, null, 2));
}
function pulse(state, mood) {
  if (!globe) return;
  globe.className = "globe " + state;
  if (mood) globe.classList.add(mood);
}

input.addEventListener("keydown", e => { if (e.key === "Enter") send(); });

// load status + history on page load
(async () => {
  try {
    const r = await fetch("/status");
    const d = await r.json();
    document.getElementById("cname").textContent = d.companion;
    status.textContent = d.has_awakened ? "awake" : "not yet awake";
    if (d.first_words) add("companion", d.first_words);
  } catch (e) { status.textContent = "offline"; }

  try {
    const r = await fetch("/history");
    const d = await r.json();
    for (const m of d.messages || []) {
      add(m.role, m.content);
    }
  } catch (e) {}
})();

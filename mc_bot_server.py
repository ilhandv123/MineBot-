#!/usr/bin/env python3
"""
MC AFK Bot Web Panel — ILHANBOT Edition
- Single bot at a time
- Full ILHANBOT logic (jump, move, rotate, chat, reconnect)
- Version auto-detected from server
- Simple clean UI

pip install flask mcstatus
npm install mineflayer chalk readline-sync
cloudflared (optional)
"""

from flask import Flask, request, jsonify, render_template_string
import subprocess, os, threading, time, re

app = Flask(__name__)

RATE_LIMIT_SEC = 10
ip_last        = {}
bot            = None   # only one bot at a time

# ── ILHANBOT JS (your logic, adapted for web panel) ───────────────────────────
BOT_JS = r"""
const mineflayer = require('mineflayer');
const [,, host, port, username_arg, version] = process.argv;

function randomName() {
  const chars = 'abcdefghijklmnopqrstuvwxyz';
  let name = 'ILHANBOT_';
  for (let i = 0; i < 5; i++) name += chars[Math.floor(Math.random() * chars.length)];
  return name;
}

let username = username_arg || 'ILHANBOT';
console.log('START:' + username);

function createBot() {
  console.log('CONNECTING:' + username);

  const bot = mineflayer.createBot({
    host,
    port: parseInt(port),
    username,
    version,
    auth: 'offline',
    checkTimeoutInterval: 30000
  });

  let connected    = false;
  let wasKicked    = false;
  let isRestarting = false;

  bot.on('spawn', () => {
    connected = true;
    console.log('SPAWNED:' + username);

    // 💬 Random chat every 5-6 minutes
    const messages = ['ok', 'hello', 'hai', 'anyone here?', 'lets play'];
    function chatLoop() {
      const delay = (Math.random() * 60 + 300) * 1000;
      setTimeout(() => {
        const msg = messages[Math.floor(Math.random() * messages.length)];
        bot.chat(msg);
        console.log('CHAT:' + msg);
        chatLoop();
      }, delay);
    }
    chatLoop();

    // 🦘 Jump every 3 minutes
    setInterval(() => {
      bot.setControlState('jump', true);
      setTimeout(() => bot.setControlState('jump', false), 800);
      console.log('JUMP');
    }, 3 * 60 * 1000);

    // 🚶 Move every 4 minutes
    setInterval(() => {
      bot.setControlState('forward', true);
      setTimeout(() => bot.setControlState('forward', false), 3000);
      console.log('MOVE');
    }, 4 * 60 * 1000);

    // 🔄 Rotate every 5 minutes
    setInterval(() => {
      let yaw = bot.entity.yaw;
      let step = 0;
      const rotate = setInterval(() => {
        yaw += (Math.PI * 2) / 20;
        bot.look(yaw, bot.entity.pitch, true);
        if (++step >= 20) clearInterval(rotate);
      }, 200);
      console.log('ROTATE');
    }, 5 * 60 * 1000);

    // 🔁 Restart every 1 hour (same username)
    setTimeout(() => {
      console.log('RESTART');
      isRestarting = true;
      bot.quit();
    }, 60 * 60 * 1000);
  });

  bot.on('kicked', (reason) => {
    wasKicked = true;
    console.log('KICKED:' + reason);
  });

  bot.on('error', (err) => {
    if (!connected) console.log('OFFLINE:server unreachable, retrying...');
    else console.log('ERROR:' + err.message);
  });

  bot.on('end', () => {
    if (wasKicked && !isRestarting) {
      username = randomName();
      console.log('NEWNAME:' + username);
    } else {
      console.log('RECONNECT:' + username);
    }
    wasKicked    = false;
    isRestarting = false;
    console.log('WAITING:reconnecting in 20s...');
    setTimeout(createBot, 20000);
  });
}

createBot();
"""

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ILHANBOT Panel</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: #f2f2f2;
    font-family: Arial, sans-serif;
    font-size: 15px;
    color: #111;
    min-height: 100vh;
  }
  .topbar {
    background: #111;
    color: #fff;
    padding: 14px 20px;
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .topbar b { font-size: 1rem; letter-spacing: 1px; }
  .topbar small { font-size: 0.72rem; color: #888; }
  .page { max-width: 520px; margin: 28px auto; padding: 0 16px; }
  .card {
    background: #fff;
    border-radius: 8px;
    padding: 22px;
    margin-bottom: 18px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.09);
  }
  .card h2 {
    font-size: 0.78rem; font-weight: bold;
    color: #888; text-transform: uppercase;
    letter-spacing: 1px; margin-bottom: 16px;
  }
  .field { margin-bottom: 13px; }
  .field label { display: block; font-size: 0.8rem; color: #666; margin-bottom: 5px; }
  .field input {
    width: 100%; padding: 10px 12px;
    border: 1.5px solid #ddd; border-radius: 6px;
    font-size: 0.95rem; color: #111; background: #fff;
    outline: none; transition: border-color 0.2s;
  }
  .field input:focus { border-color: #111; }
  .two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }

  .version-box {
    width: 100%; padding: 10px 12px;
    border: 1.5px solid #ddd; border-radius: 6px;
    font-size: 0.95rem; background: #f8f8f8;
    display: flex; align-items: center; gap: 8px; min-height: 42px;
  }
  .version-box b { color: #111; }
  .version-box span { font-size: 0.72rem; color: #aaa; }

  .detect-btn {
    width: 100%; padding: 10px;
    background: #f2f2f2; border: 1.5px solid #ddd;
    border-radius: 6px; font-size: 0.85rem;
    cursor: pointer; color: #444; margin-bottom: 13px;
    transition: all 0.15s;
  }
  .detect-btn:hover { background: #e8e8e8; }

  .deploy-btn {
    width: 100%; padding: 12px;
    background: #111; color: #fff; border: none;
    border-radius: 6px; font-size: 1rem;
    font-weight: bold; cursor: pointer;
    transition: background 0.2s;
  }
  .deploy-btn:hover    { background: #333; }
  .deploy-btn:disabled { background: #999; cursor: not-allowed; }

  .stop-btn {
    width: 100%; padding: 12px;
    background: #fff; color: #c00;
    border: 2px solid #c00; border-radius: 6px;
    font-size: 1rem; font-weight: bold;
    cursor: pointer; transition: all 0.15s;
  }
  .stop-btn:hover { background: #c00; color: #fff; }

  #msg {
    margin-top: 10px; font-size: 0.82rem;
    min-height: 1.2em; text-align: center; color: #888;
  }
  #msg.ok  { color: #1a7a1a; }
  #msg.err { color: #c00; }

  /* Status card */
  .status-panel {
    display: flex; align-items: center;
    gap: 14px; padding: 4px 0;
  }
  .big-dot {
    width: 14px; height: 14px;
    border-radius: 50%; flex-shrink: 0;
  }
  .dot-on  { background: #1a7a1a; box-shadow: 0 0 0 3px #d4f0d4; }
  .dot-off { background: #ddd; }
  .status-text .sname { font-size: 1rem; font-weight: bold; }
  .status-text .ssub  { font-size: 0.75rem; color: #888; margin-top: 2px; }
  .status-text .slog  {
    font-size: 0.72rem; color: #aaa; margin-top: 4px;
    font-family: monospace; white-space: nowrap;
    overflow: hidden; text-overflow: ellipsis; max-width: 320px;
  }
  .offline-msg { color: #ccc; font-size: 0.85rem; padding: 6px 0; }

  /* Features list */
  .features { list-style: none; }
  .features li {
    font-size: 0.8rem; color: #555;
    padding: 4px 0; border-bottom: 1px solid #f0f0f0;
    display: flex; gap: 8px;
  }
  .features li:last-child { border-bottom: none; }

  /* Log */
  #log {
    background: #f8f8f8; border: 1.5px solid #e8e8e8;
    border-radius: 6px; padding: 10px 12px;
    height: 140px; overflow-y: auto;
    font-size: 0.72rem; line-height: 1.8;
    color: #888; font-family: monospace;
  }
  .lok { color: #1a7a1a; }
  .ler { color: #c00; }
  .lbl { color: #555; }

  footer {
    text-align: center; padding: 16px;
    font-size: 0.7rem; color: #ccc;
  }
  .social {
    font-size: 0.72rem; color: #aaa;
    margin-top: 6px; display: flex; gap: 10px;
  }
  .social span { background: #f0f0f0; border-radius: 4px; padding: 2px 8px; }
</style>
</head>
<body>

<div class="topbar">
  <b>ILHANBOT PANEL</b>
  <small>AFK Bot · Offline-mode servers</small>
</div>

<div class="page">

  <!-- Bot Status -->
  <div class="card">
    <h2>Bot Status</h2>
    <div id="status-area"><div class="offline-msg">No bot running.</div></div>
    <div id="stop-area"></div>
  </div>

  <!-- Deploy -->
  <div class="card" id="deploy-card">
    <h2>Start Bot</h2>
    <div class="two-col">
      <div class="field">
        <label>Server IP</label>
        <input id="host" type="text" placeholder="play.example.com">
      </div>
      <div class="field">
        <label>Port</label>
        <input id="port" type="number" value="25565" min="1" max="65535">
      </div>
    </div>
    <div class="field">
      <label>Bot Name</label>
      <input id="name" type="text" placeholder="ILHANBOT" maxlength="16">
    </div>
    <div class="field">
      <label>Version <span style="color:#aaa;font-size:0.72rem">— auto-detected</span></label>
      <div class="version-box" id="vbox">
        <b id="vval">—</b><span id="vhint">Enter IP then click Detect</span>
      </div>
    </div>
    <button class="detect-btn" onclick="detectVersion()">🔍 Detect Server Version</button>
    <button class="deploy-btn" id="deploy-btn" onclick="deploy()">▶ Start Bot</button>
    <div id="msg"></div>
  </div>

  <!-- Features -->
  <div class="card">
    <h2>Bot Features</h2>
    <ul class="features">
      <li><span>🔄</span> Auto reconnect every 20 seconds</li>
      <li><span>🦘</span> Anti-AFK jump every 3 minutes</li>
      <li><span>🚶</span> Random walk every 4 minutes</li>
      <li><span>🔁</span> Random rotate every 5 minutes</li>
      <li><span>💬</span> Random chat every 5–6 minutes</li>
      <li><span>♻️</span> Auto restart every 1 hour</li>
      <li><span>🚫</span> New random name on kick/ban</li>
    </ul>
    <div class="social">
      <span>📸 Instagram: ilhan.pk</span>
      <span>▶ YouTube: OxViper</span>
    </div>
  </div>

  <!-- Log -->
  <div class="card">
    <h2>Activity Log</h2>
    <div id="log"></div>
  </div>

</div>

<footer>ILHANBOT Panel · Offline-mode servers only</footer>

<script>
let logs = [];
let detectedVersion = '';

function addLog(msg, cls='lbl') {
  const ts = new Date().toLocaleTimeString();
  logs.push(`<div class="${cls}">[${ts}] ${msg}</div>`);
  if (logs.length > 100) logs.shift();
  const el = document.getElementById('log');
  el.innerHTML = logs.join('');
  el.scrollTop = el.scrollHeight;
}

function setMsg(msg, type='') {
  const el = document.getElementById('msg');
  el.className = type; el.textContent = msg;
}

async function detectVersion() {
  const host = document.getElementById('host').value.trim();
  const port = document.getElementById('port').value || '25565';
  if (!host) { setMsg('Enter a server IP first.', 'err'); return; }
  document.getElementById('vval').textContent  = '...';
  document.getElementById('vhint').textContent = 'Pinging server...';
  addLog('Pinging ' + host + ':' + port + '...');
  try {
    const res  = await fetch('/ping', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({host, port})
    });
    const data = await res.json();
    if (data.ok) {
      detectedVersion = data.version;
      document.getElementById('vval').textContent  = data.version;
      document.getElementById('vhint').textContent = '✓ ' + data.players + ' online';
      addLog('Server online · v' + data.version + ' · ' + data.players, 'lok');
      setMsg('', '');
    } else {
      document.getElementById('vval').textContent  = '—';
      document.getElementById('vhint').textContent = 'Could not reach server';
      addLog('Ping failed: ' + data.error, 'ler');
      setMsg('Could not reach server.', 'err');
    }
  } catch(e) { setMsg('Request failed.', 'err'); }
}

async function deploy() {
  const host = document.getElementById('host').value.trim();
  const port = parseInt(document.getElementById('port').value) || 25565;
  const name = document.getElementById('name').value.trim() || 'ILHANBOT';
  if (!host) { setMsg('Enter a server IP.', 'err'); return; }
  if (!detectedVersion) { setMsg('Click Detect Server Version first.', 'err'); return; }
  const btn = document.getElementById('deploy-btn');
  btn.disabled = true; btn.textContent = 'Starting...';
  addLog('Starting ' + name + ' on ' + host + ':' + port + ' (MC ' + detectedVersion + ')...');
  try {
    const res  = await fetch('/deploy', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({host, port, name, version: detectedVersion})
    });
    const data = await res.json();
    if (data.ok) {
      setMsg('Bot started!', 'ok');
      addLog(name + ' is now running 24/7.', 'lok');
    } else {
      setMsg(data.error, 'err');
      addLog('Error: ' + data.error, 'ler');
      btn.disabled = false; btn.textContent = '▶ Start Bot';
    }
  } catch(e) {
    setMsg('Request failed.', 'err');
    btn.disabled = false; btn.textContent = '▶ Start Bot';
  }
  refresh();
}

async function stopBot() {
  addLog('Stopping bot...');
  await fetch('/stop', {method: 'POST'});
  addLog('Bot stopped.', 'ler');
  refresh();
}

async function refresh() {
  try {
    const res  = await fetch('/status');
    const data = await res.json();
    const sa   = document.getElementById('status-area');
    const stop = document.getElementById('stop-area');
    const dc   = document.getElementById('deploy-card');
    const btn  = document.getElementById('deploy-btn');

    if (data.running) {
      dc.style.display   = 'none';
      stop.innerHTML = `<button class="stop-btn" style="margin-top:14px" onclick="stopBot()">■ Stop Bot</button>`;
      sa.innerHTML = `
        <div class="status-panel">
          <div class="big-dot ${data.alive ? 'dot-on':'dot-off'}"></div>
          <div class="status-text">
            <div class="sname">${data.name}</div>
            <div class="ssub">${data.host}:${data.port} · MC ${data.version} · Up ${data.uptime}</div>
            <div class="slog">${data.last_log || 'Connecting...'}</div>
          </div>
        </div>`;

      // Mirror bot logs into panel log
      if (data.last_log && data.last_log !== window._lastLog) {
        window._lastLog = data.last_log;
        const l = data.last_log;
        if      (l.startsWith('SPAWNED'))    addLog('✅ Bot spawned in world!', 'lok');
        else if (l.startsWith('JUMP'))       addLog('🦘 Anti-AFK jump', 'lbl');
        else if (l.startsWith('MOVE'))       addLog('🚶 Anti-AFK move', 'lbl');
        else if (l.startsWith('ROTATE'))     addLog('🔄 Rotating', 'lbl');
        else if (l.startsWith('CHAT:'))      addLog('💬 Chat: ' + l.slice(5), 'lbl');
        else if (l.startsWith('KICKED'))     addLog('🚫 ' + l, 'ler');
        else if (l.startsWith('NEWNAME'))    addLog('🔄 New name: ' + l.slice(8), 'lbl');
        else if (l.startsWith('RECONNECT'))  addLog('🔁 Reconnecting...', 'lbl');
        else if (l.startsWith('OFFLINE'))    addLog('⚠️ Server offline, retrying...', 'ler');
        else if (l.startsWith('RESTART'))    addLog('♻️ 1hr restart...', 'lbl');
      }
    } else {
      dc.style.display = 'block';
      stop.innerHTML   = '';
      sa.innerHTML     = '<div class="offline-msg">No bot running.</div>';
      btn.disabled     = false;
      btn.textContent  = '▶ Start Bot';
    }
  } catch(e) {}
}

window._lastLog = '';
setInterval(refresh, 3000);
refresh();
addLog('Panel ready. Start a bot above.', 'lok');
</script>
</body>
</html>
"""

# ── Helpers ────────────────────────────────────────────────────────────────────

SCRIPT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_ilhanbot.js")

def ensure_script():
    with open(SCRIPT_PATH, "w") as f:
        f.write(BOT_JS)

def sanitize_name(name):
    return re.sub(r'[^a-zA-Z0-9_]', '', name)[:16] or "ILHANBOT"

def sanitize_host(host):
    host = host.strip()[:100]
    return host if re.match(r'^[a-zA-Z0-9.\-]+$', host) else None

def uptime_str(ts):
    s = int(time.time() - ts)
    h, r = divmod(s, 3600); m = r // 60
    if h: return f"{h}h {m}m"
    if m: return f"{m}m"
    return f"{s}s"

# ── Single bot state ───────────────────────────────────────────────────────────

bot_state = {
    "proc": None, "name": "", "host": "", "port": "",
    "version": "", "last_log": "", "started": 0
}

def read_output():
    proc = bot_state["proc"]
    for line in proc.stdout:
        line = line.strip()
        if line:
            bot_state["last_log"] = line[:140]

# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/ping", methods=["POST"])
def ping():
    data = request.json or {}
    host = sanitize_host(data.get("host", ""))
    port = max(1, min(65535, int(data.get("port", 25565))))
    if not host:
        return jsonify({"ok": False, "error": "Invalid host"})
    try:
        from mcstatus import JavaServer
        s      = JavaServer.lookup(f"{host}:{port}", timeout=5)
        status = s.status()
        match  = re.search(r'(\d+\.\d+[\.\d]*)', status.version.name)
        clean  = match.group(1) if match else status.version.name
        return jsonify({"ok": True, "version": clean,
                        "players": f"{status.players.online}/{status.players.max}"})
    except ImportError:
        return jsonify({"ok": True, "version": "1.20.1", "players": "? (install mcstatus)"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@app.route("/deploy", methods=["POST"])
def deploy():
    # Only one bot allowed
    if bot_state["proc"] and bot_state["proc"].poll() is None:
        return jsonify({"ok": False, "error": "A bot is already running. Stop it first."})

    ip  = request.remote_addr
    now = time.time()
    if ip in ip_last and now - ip_last[ip] < RATE_LIMIT_SEC:
        return jsonify({"ok": False, "error": f"Wait {RATE_LIMIT_SEC}s before starting again."})
    ip_last[ip] = now

    data    = request.json or {}
    host    = sanitize_host(data.get("host", ""))
    port    = max(1, min(65535, int(data.get("port", 25565))))
    name    = sanitize_name(data.get("name", "ILHANBOT"))
    version = re.sub(r'[^0-9.]', '', data.get("version", "1.20.1"))[:10] or "1.20.1"

    if not host:
        return jsonify({"ok": False, "error": "Invalid server IP."})

    ensure_script()

    try:
        proc = subprocess.Popen(
            ["node", SCRIPT_PATH, host, str(port), name, version],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
    except FileNotFoundError:
        return jsonify({"ok": False, "error": "Node.js not found. Install Node.js + npm install mineflayer"})

    bot_state.update({
        "proc": proc, "name": name, "host": host,
        "port": str(port), "version": version,
        "last_log": "", "started": time.time()
    })
    threading.Thread(target=read_output, daemon=True).start()

    return jsonify({"ok": True})

@app.route("/stop", methods=["POST"])
def stop():
    if bot_state["proc"]:
        bot_state["proc"].terminate()
        bot_state["proc"] = None
    return jsonify({"ok": True})

@app.route("/status")
def status():
    proc    = bot_state["proc"]
    running = proc is not None and proc.poll() is None
    return jsonify({
        "running":  running,
        "alive":    running,
        "name":     bot_state["name"],
        "host":     bot_state["host"],
        "port":     bot_state["port"],
        "version":  bot_state["version"],
        "last_log": bot_state["last_log"],
        "uptime":   uptime_str(bot_state["started"]) if running else ""
    })

# ── Cloudflare tunnel ──────────────────────────────────────────────────────────

def start_tunnel(port):
    try:
        proc = subprocess.Popen(
            ["cloudflared", "tunnel", "--url", f"http://localhost:{port}"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        for line in proc.stdout:
            line = line.strip()
            urls = re.findall(r'https://[^\s]+\.trycloudflare\.com', line)
            if urls:
                print(f"\n{'='*50}\n  Public URL: {urls[0]}\n{'='*50}\n")
  except FileNotFoundError:
        print(f"[TUNNEL] cloudflared not found. Local: http://localhost:{port}")

# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    PORT = 5000
    print(f"\n{'='*50}")
    print("  ILHANBOT Web Panel")
    print(f"  Open: http://localhost:{PORT}")
    print(f"  instagram: ilhan.pk | YouTube: OxViper")
    print(f"{'='*50}\n")
    threading.Thread(target=start_tunnel, args=(PORT,), daemon=True).start()
    app.run(host="0.0.0.0", port=PORT, debug=False)

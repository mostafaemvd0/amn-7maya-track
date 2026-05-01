import os
import json
import asyncio
import threading
import io
import secrets
from functools import wraps
from flask import Flask, request, jsonify, Response, session, redirect
from flask_cors import CORS
from dotenv import load_dotenv
import discord
from discord.ext import commands

load_dotenv()

app = Flask(__name__)
CORS(app)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

# ===== Auth config =====
DASHBOARD_USER = os.environ.get("DASHBOARD_USER", "admin")
DASHBOARD_PASS = os.environ.get("DASHBOARD_PASS", "")

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "unauthorized"}), 401
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated

# ===== Config =====
BOT_TOKEN         = os.environ["BOT_TOKEN"]
NOTIFY_CHANNEL_ID = int(os.environ["NOTIFY_CHANNEL_ID"])
GUILD_ID          = int(os.environ["GUILD_ID"])
TRACKED_FILE      = "tracked_users.json"
TEMPLATES_FILE    = "message_templates.json"

# ===== Rank order (lowest to highest) =====
RANKS = [
    {"name": "جندي",          "id": int(os.environ.get("ROLE_JANDY",        0))},
    {"name": "جندي اول",      "id": int(os.environ.get("ROLE_JANDY1",       0))},
    {"name": "عريف",          "id": int(os.environ.get("ROLE_ARIF",         0))},
    {"name": "وكيل رقيب",    "id": int(os.environ.get("ROLE_WRAQIB",       0))},
    {"name": "رقيب",          "id": int(os.environ.get("ROLE_RAQIB",        0))},
    {"name": "رقيب اول",      "id": int(os.environ.get("ROLE_RAQIB1",       0))},
    {"name": "رئيس رقباء",   "id": int(os.environ.get("ROLE_RAES_ROQBAA",  0))},
    {"name": "ملازم",         "id": int(os.environ.get("ROLE_MULAZIM",      0))},
    {"name": "ملازم اول",     "id": int(os.environ.get("ROLE_MULAZIM1",     0))},
    {"name": "نقيب",          "id": int(os.environ.get("ROLE_NAQIB",        0))},
    {"name": "رائد",          "id": int(os.environ.get("ROLE_RAED",         0))},
    {"name": "مقدم",          "id": int(os.environ.get("ROLE_MOQADEM",      0))},
    {"name": "عقيد",          "id": int(os.environ.get("ROLE_AQID",         0))},
    {"name": "عميد",          "id": int(os.environ.get("ROLE_AMID",         0))},
    {"name": "لواء",          "id": int(os.environ.get("ROLE_LIWAA",        0))},
]
RANK_IDS   = {r["id"] for r in RANKS if r["id"]}
RANK_INDEX = {r["id"]: i for i, r in enumerate(RANKS) if r["id"]}

# ===== Embedded HTML =====
import pathlib as _pl
_html_file = _pl.Path(__file__).parent / "index.html"
if _html_file.exists():
    INDEX_HTML = _html_file.read_text(encoding="utf-8")
else:
    # fallback inline
    INDEX_HTML = "<h1>index.html not found</h1>"


# ===== Discord bot (runs in background thread) =====
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.presences = True

bot = commands.Bot(command_prefix="!", intents=intents, chunk_guilds_at_startup=True)
loop = asyncio.new_event_loop()

def run_bot():
    asyncio.set_event_loop(loop)
    loop.run_until_complete(bot.start(BOT_TOKEN))

threading.Thread(target=run_bot, daemon=True).start()

def get_guild():
    return bot.get_guild(GUILD_ID)

def run_coro(coro):
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=120)  # increased for large batch fetch

# ===== File helpers =====
def load_tracked():
    if os.path.exists(TRACKED_FILE):
        with open(TRACKED_FILE) as f:
            return json.load(f)
    return {}

def save_tracked(data):
    with open(TRACKED_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_templates():
    if os.path.exists(TEMPLATES_FILE):
        with open(TEMPLATES_FILE) as f:
            return json.load(f)
    return []

def save_templates(data):
    with open(TEMPLATES_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ===== Discord events =====
@bot.event
async def on_ready():
    print(f"Bot ready: {bot.user}")
    # chunk members in background after ready
    for guild in bot.guilds:
        bot.loop.create_task(chunk_guild(guild))

async def chunk_guild(guild):
    try:
        if not guild.chunked:
            await guild.chunk()
            print(f"Chunked {guild.name}: {len(guild.members)} members")
    except Exception as e:
        print(f"Chunk error: {e}")

@bot.event
async def on_member_remove(member: discord.Member):
    tracked = load_tracked()
    if str(member.id) in tracked:
        channel = bot.get_channel(NOTIFY_CHANNEL_ID)
        if channel:
            # get rank from roles
            current_rank = None
            for role in member.roles:
                if role.id in RANK_IDS:
                    current_rank = role.name
                    break
            embed = discord.Embed(title="🚪 عضو غادر السيرفر", color=discord.Color.red())
            embed.add_field(name="📛 الاسم في السيرفر", value=member.display_name, inline=False)
            embed.add_field(name="🎖️ الرتبة", value=current_rank or "بدون رتبة", inline=False)
            embed.add_field(name="🆔 الـ ID", value=str(member.id), inline=False)
            embed.add_field(name="👤 اليوزرنيم", value=str(member), inline=False)
            embed.set_footer(text="تم الرصد بواسطة المتتبع")
            await channel.send(embed=embed)

@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    tracked = load_tracked()
    if str(after.id) not in tracked:
        return
    channel = bot.get_channel(NOTIFY_CHANNEL_ID)
    if not channel:
        return
    # تغيير النيكنيم داخل السيرفر
    if before.nick != after.nick:
        embed = discord.Embed(title="✏️ عضو غيّر اسمه في السيرفر", color=discord.Color.orange())
        embed.add_field(name="👤 اليوزرنيم", value=str(after), inline=False)
        embed.add_field(name="🆔 الـ ID", value=str(after.id), inline=False)
        embed.add_field(name="📛 الاسم القديم", value=before.nick or before.name, inline=True)
        embed.add_field(name="📛 الاسم الجديد", value=after.nick or after.name, inline=True)
        embed.set_footer(text="تم الرصد بواسطة المتتبع")
        await channel.send(embed=embed)
    # تغيير اليوزرنيم الأصلي
    if before.name != after.name:
        embed = discord.Embed(title="✏️ عضو غيّر يوزرنيمه", color=discord.Color.orange())
        embed.add_field(name="🆔 الـ ID", value=str(after.id), inline=False)
        embed.add_field(name="👤 اليوزر القديم", value=str(before), inline=True)
        embed.add_field(name="👤 اليوزر الجديد", value=str(after), inline=True)
        embed.set_footer(text="تم الرصد بواسطة المتتبع")
        await channel.send(embed=embed)


# ===== Routes =====

@app.route("/")
@login_required
def index():
    return Response(INDEX_HTML, mimetype="text/html")

@app.route("/api/tracked", methods=["GET"])
@login_required
def api_tracked():
    tracked = load_tracked()
    guild = get_guild()
    result = []

    for uid, info in tracked.items():
        # use cache only — instant, no HTTP calls
        member = guild.get_member(int(uid)) if guild else None
        if member:
            current_rank = None
            for role in member.roles:
                if role.id in RANK_IDS:
                    current_rank = role.name
                    break
            result.append({
                "id":        uid,
                "name":      member.display_name,
                "username":  str(member),
                "avatar":    str(member.display_avatar.url),
                "rank":      current_rank or info.get("rank", "-"),
                "in_server": True,
            })
        else:
            # not in cache — return saved data instantly
            result.append({
                "id":        uid,
                "name":      info.get("name", uid),
                "username":  info.get("name", uid),
                "avatar":    "https://cdn.discordapp.com/embed/avatars/0.png",
                "rank":      info.get("rank", "-"),
                "in_server": True,
            })

    return jsonify(result)

@app.route("/api/tracked", methods=["POST"])
@login_required
def api_add_tracked():
    data = request.json
    ids  = data.get("ids", [])
    guild = get_guild()
    added = []; missing = []
    tracked = load_tracked()

    for uid in ids:
        uid_str = str(uid).strip()
        # cache only — instant
        member = guild.get_member(int(uid_str)) if guild else None
        if member is None:
            # save with placeholder, mark as added anyway
            # background task will update info later
            missing.append(uid_str)
            continue
        rank = None
        for role in member.roles:
            if role.id in RANK_IDS:
                rank = role.name; break
        tracked[uid_str] = {"name": member.display_name, "rank": rank or "-"}
        added.append(uid_str)

    save_tracked(tracked)
    return jsonify({"added": added, "missing": missing})

@app.route("/api/tracked/<uid>", methods=["DELETE"])
@login_required
def api_remove_tracked(uid):
    tracked = load_tracked()
    tracked.pop(uid, None)
    save_tracked(tracked)
    return jsonify({"ok": True})

@app.route("/api/promote", methods=["POST"])
@login_required
def api_promote():
    data = request.json
    ids  = data.get("ids", [])
    guild = get_guild()
    results = []

    async def do_promote():
        for uid in ids:
            member = guild.get_member(int(uid))
            if not member:
                try:
                    member = await guild.fetch_member(int(uid))
                except (discord.NotFound, discord.HTTPException):
                    results.append({"id": uid, "status": "not_found"}); continue
            current_rank_role = None
            for role in member.roles:
                if role.id in RANK_IDS:
                    current_rank_role = role; break
            if current_rank_role is None:
                results.append({"id": uid, "status": "no_rank"}); continue
            cur_idx = RANK_INDEX.get(current_rank_role.id, -1)
            if cur_idx == len(RANKS) - 1:
                results.append({"id": uid, "status": "max_rank"}); continue
            next_rank = RANKS[cur_idx + 1]
            next_role = guild.get_role(next_rank["id"])
            if not next_role:
                results.append({"id": uid, "status": "role_missing"}); continue
            await member.remove_roles(current_rank_role)
            await member.add_roles(next_role)
            results.append({"id": uid, "name": member.display_name,
                            "from": current_rank_role.name, "to": next_role.name,
                            "to_role_id": str(next_role.id), "status": "ok"})

    try:
        run_coro(do_promote())
    except Exception as e:
        print(f"Promote error: {e}")
        return jsonify({"error": str(e)}), 500
    return jsonify(results)

@app.route("/api/send", methods=["POST"])
@login_required
def api_send():
    channel_id = request.form.get("channel_id", "")
    message    = request.form.get("message", "")
    gif_file   = request.files.get("gif")

    async def do_send():
        ch = bot.get_channel(int(channel_id))
        if not ch:
            return {"ok": False, "error": "channel not found"}
        if gif_file:
            data = gif_file.read()
            await ch.send(file=discord.File(io.BytesIO(data), filename=gif_file.filename))
        if message.strip():
            await ch.send(message)
        return {"ok": True}

    result = run_coro(do_send())
    return jsonify(result)

@app.route("/api/templates", methods=["GET"])
@login_required
def api_get_templates():
    return jsonify(load_templates())

@app.route("/api/templates", methods=["POST"])
@login_required
def api_add_template():
    t = request.json
    templates = load_templates()
    t["id"] = max((x.get("id", 0) for x in templates), default=0) + 1
    templates.append(t)
    save_templates(templates)
    return jsonify(t)

@app.route("/api/templates/<int:tid>", methods=["PUT"])
@login_required
def api_update_template(tid):
    templates = load_templates()
    for i, t in enumerate(templates):
        if t.get("id") == tid:
            templates[i] = {**t, **request.json, "id": tid}
            save_templates(templates)
            return jsonify(templates[i])
    return jsonify({"error": "not found"}), 404

@app.route("/api/templates/<int:tid>", methods=["DELETE"])
@login_required
def api_delete_template(tid):
    templates = [t for t in load_templates() if t.get("id") != tid]
    save_templates(templates)
    return jsonify({"ok": True})

@app.route("/api/debug")
@login_required
def api_debug():
    guild = get_guild()
    if not guild:
        return jsonify({
            "error": "البوت مش شايف السيرفر",
            "guild_id_configured": GUILD_ID,
            "bot_guilds": [{"id": str(g.id), "name": g.name} for g in bot.guilds],
            "bot_ready": bot.is_ready(),
        })
    members = [{"id": str(m.id), "name": m.display_name} for m in guild.members[:20]]
    return jsonify({
        "ok": True,
        "guild_name": guild.name,
        "guild_id": str(guild.id),
        "member_count": guild.member_count,
        "cached_members": len(guild.members),
        "bot_ready": bot.is_ready(),
        "sample_members": members,
        "intents": {
            "members": bot.intents.members,
            "presences": bot.intents.presences,
        }
    })

@app.route("/api/ranks", methods=["GET"])
@login_required
def api_ranks():
    return jsonify(RANKS)


# ===== Login HTML =====
LOGIN_HTML = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>تسجيل الدخول</title>
<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;900&display=swap" rel="stylesheet">
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body {
    font-family: 'Cairo', sans-serif;
    background: #0a0c0f;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    background-image:
      repeating-linear-gradient(0deg, transparent, transparent 39px, #ffffff04 39px, #ffffff04 40px),
      repeating-linear-gradient(90deg, transparent, transparent 39px, #ffffff04 39px, #ffffff04 40px);
  }
  .box {
    background: #161b22;
    border: 1px solid #21262d;
    border-top: 3px solid #d4a843;
    border-radius: 16px;
    padding: 2.5rem 2rem;
    width: min(400px, 92vw);
    box-shadow: 0 20px 60px #000a;
  }
  .logo {
    text-align: center;
    margin-bottom: 2rem;
  }
  .logo-icon {
    font-size: 2.8rem;
    display: block;
    margin-bottom: .5rem;
  }
  .logo h1 {
    color: #d4a843;
    font-size: 1.4rem;
    font-weight: 900;
  }
  .logo p {
    color: #8b949e;
    font-size: .85rem;
    margin-top: .25rem;
  }
  label {
    display: block;
    color: #8b949e;
    font-size: .85rem;
    margin-bottom: .35rem;
    margin-top: 1rem;
  }
  input {
    width: 100%;
    background: #111418;
    border: 1px solid #21262d;
    border-radius: 8px;
    color: #e6edf3;
    padding: .7rem 1rem;
    font-family: 'Cairo', sans-serif;
    font-size: .95rem;
    outline: none;
    transition: border-color .2s;
  }
  input:focus { border-color: #d4a843; }
  .btn {
    width: 100%;
    margin-top: 1.5rem;
    padding: .8rem;
    background: linear-gradient(135deg, #d4a843, #f0c060);
    color: #0a0c0f;
    border: none;
    border-radius: 8px;
    font-family: 'Cairo', sans-serif;
    font-weight: 900;
    font-size: 1rem;
    cursor: pointer;
    transition: filter .2s;
  }
  .btn:hover { filter: brightness(1.1); }
  .error {
    background: #c0392b22;
    border: 1px solid #c0392b;
    color: #e74c3c;
    border-radius: 8px;
    padding: .6rem 1rem;
    font-size: .88rem;
    margin-top: 1rem;
    text-align: center;
    display: none;
  }
  .error.show { display: block; }
</style>
</head>
<body>
<div class="box">
  <div class="logo">
    <span class="logo-icon">⚔️</span>
    <h1>لوحة القيادة</h1>
    <p>أدخل بياناتك للمتابعة</p>
  </div>
  <div id="err" class="error">اسم المستخدم أو كلمة المرور غلط</div>
  <label>اسم المستخدم</label>
  <input type="text" id="usr" placeholder="username" autocomplete="username">
  <label>كلمة المرور</label>
  <input type="password" id="pwd" placeholder="••••••••" autocomplete="current-password" onkeydown="if(event.key==='Enter')doLogin()">
  <button class="btn" onclick="doLogin()">🔓 دخول</button>
</div>
<script>
async function doLogin() {
  const usr = document.getElementById('usr').value;
  const pwd = document.getElementById('pwd').value;
  const r = await fetch('/api/login', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({username: usr, password: pwd})
  });
  const d = await r.json();
  if (d.ok) {
    window.location.href = '/';
  } else {
    const err = document.getElementById('err');
    err.classList.add('show');
    setTimeout(() => err.classList.remove('show'), 3000);
  }
}
</script>
</body>
</html>"""

@app.route("/login")
def login_page():
    if session.get("logged_in"):
        return redirect("/")
    return Response(LOGIN_HTML, mimetype="text/html")

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.json or {}
    username = data.get("username", "")
    password = data.get("password", "")
    if username == DASHBOARD_USER and password == DASHBOARD_PASS and DASHBOARD_PASS:
        session["logged_in"] = True
        session.permanent = True
        return jsonify({"ok": True})
    return jsonify({"ok": False}), 401

@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"ok": True})

@app.route("/api/reset-tracked", methods=["POST"])
@login_required
def api_reset_tracked():
    save_tracked({})
    return jsonify({"ok": True, "message": "تم مسح القائمة"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

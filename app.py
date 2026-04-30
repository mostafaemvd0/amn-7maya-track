import os
import json
import asyncio
import threading
import aiohttp
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from dotenv import load_dotenv
import discord
from discord.ext import commands

load_dotenv()

app = Flask(__name__)
CORS(app)

# ===== Config =====
BOT_TOKEN         = os.environ["BOT_TOKEN"]
NOTIFY_CHANNEL_ID = int(os.environ["NOTIFY_CHANNEL_ID"])
GUILD_ID          = int(os.environ["GUILD_ID"])
TRACKED_FILE      = "tracked_users.json"
TEMPLATES_FILE    = "message_templates.json"

# ===== Rank order (lowest → highest) =====
RANKS = [
    {"name": "جندي",      "id": int(os.environ.get("ROLE_JANDY",   0))},
    {"name": "جندي اول",      "id": int(os.environ.get("ROLE_JANDY1",    0))},
    {"name": "عريف",      "id": int(os.environ.get("ROLE_ARIF",    0))},
    {"name": "وكيل رقيب",      "id": int(os.environ.get("ROLE_WRAQIB",   0))},
    {"name": "رقيب",      "id": int(os.environ.get("ROLE_RAQIB",   0))},
    {"name": "رقيب اول",      "id": int(os.environ.get("ROLE_RAQIB1",   0))},
    {"name": "رئيس رقباء",      "id": int(os.environ.get("ROLE_RAES_ROQBAA",   0))},
    {"name": "ملازم",     "id": int(os.environ.get("ROLE_MULAZIM", 0))},
    {"name": "ملازم",     "id": int(os.environ.get("ROLE_MULAZIM1", 0))},
    {"name": "نقيب",      "id": int(os.environ.get("ROLE_NAQIB",   0))},
    {"name": "رائد",      "id": int(os.environ.get("ROLE_RAED",    0))},
    {"name": "مقدم",      "id": int(os.environ.get("ROLE_MOQADEM", 0))},
    {"name": "عقيد",      "id": int(os.environ.get("ROLE_AQID",    0))},
    {"name": "عميد",      "id": int(os.environ.get("ROLE_AMID",    0))},
    {"name": "لواء",      "id": int(os.environ.get("ROLE_LIWAA",   0))},
]
RANK_IDS   = {r["id"] for r in RANKS if r["id"]}
RANK_INDEX = {r["id"]: i for i, r in enumerate(RANKS) if r["id"]}

# ===== Discord bot (runs in background thread) =====
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
loop = asyncio.new_event_loop()

def run_bot():
    asyncio.set_event_loop(loop)
    loop.run_until_complete(bot.start(BOT_TOKEN))

threading.Thread(target=run_bot, daemon=True).start()

def get_guild():
    return bot.get_guild(GUILD_ID)

def run_coro(coro):
    """Run a coroutine from a sync Flask thread."""
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=15)

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

# ===== on_member_remove still works =====
@bot.event
async def on_ready():
    print(f"✅ Bot ready: {bot.user}")

@bot.event
async def on_member_remove(member: discord.Member):
    tracked = load_tracked()
    if str(member.id) in tracked:
        channel = bot.get_channel(NOTIFY_CHANNEL_ID)
        if channel:
            embed = discord.Embed(title="🚪 عضو غادر السيرفر", color=discord.Color.red())
            embed.add_field(name="📛 الاسم في السيرفر", value=member.display_name, inline=False)
            embed.add_field(name="👤 اليوزرنيم",        value=str(member),         inline=False)
            embed.add_field(name="🆔 الـ ID",            value=str(member.id),      inline=False)
            embed.set_footer(text="تم الرصد بواسطة المتتبع")
            await channel.send(embed=embed)

# ===============================================================
# ROUTES
# ===============================================================

@app.route("/")
def index():
    return render_template("index.html", ranks=RANKS)

# ----- Tracked users -----
@app.route("/api/tracked", methods=["GET"])
def api_tracked():
    tracked = load_tracked()
    guild = get_guild()
    result = []
    to_delete = []
    for uid, info in tracked.items():
        member = guild.get_member(int(uid)) if guild else None
        if member is None:
            to_delete.append(uid)
            continue
        # get current rank
        current_rank = None
        for role in member.roles:
            if role.id in RANK_IDS:
                current_rank = role.name
                break
        result.append({
            "id":           uid,
            "name":         member.display_name,
            "username":     str(member),
            "avatar":       str(member.display_avatar.url),
            "rank":         current_rank or info.get("rank", "—"),
            "in_server":    True,
        })
    # remove members who left
    if to_delete:
        for uid in to_delete:
            del tracked[uid]
        save_tracked(tracked)
    return jsonify(result)

@app.route("/api/tracked", methods=["POST"])
def api_add_tracked():
    data = request.json
    ids  = data.get("ids", [])
    guild = get_guild()
    added = []; missing = []
    tracked = load_tracked()
    for uid in ids:
        uid = str(uid)
        member = guild.get_member(int(uid)) if guild else None
        if member is None:
            missing.append(uid)
        else:
            rank = None
            for role in member.roles:
                if role.id in RANK_IDS:
                    rank = role.name; break
            tracked[uid] = {"name": member.display_name, "rank": rank or "—"}
            added.append(uid)
    save_tracked(tracked)
    return jsonify({"added": added, "missing": missing})

@app.route("/api/tracked/<uid>", methods=["DELETE"])
def api_remove_tracked(uid):
    tracked = load_tracked()
    tracked.pop(uid, None)
    save_tracked(tracked)
    return jsonify({"ok": True})

# ----- Promote -----
@app.route("/api/promote", methods=["POST"])
def api_promote():
    data = request.json
    ids  = data.get("ids", [])
    guild = get_guild()
    results = []

    async def do_promote():
        for uid in ids:
            member = guild.get_member(int(uid))
            if not member:
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
            results.append({
                "id":       uid,
                "name":     member.display_name,
                "from":     current_rank_role.name,
                "to":       next_role.name,
                "status":   "ok",
            })

    run_coro(do_promote())
    return jsonify(results)

# ----- Send message -----
@app.route("/api/send", methods=["POST"])
def api_send():
    channel_id = request.form.get("channel_id", "")
    message    = request.form.get("message", "")
    gif_file   = request.files.get("gif")

    async def do_send():
        ch = bot.get_channel(int(channel_id))
        if not ch:
            return {"ok": False, "error": "channel not found"}
        if gif_file:
            import io
            data = gif_file.read()
            await ch.send(file=discord.File(io.BytesIO(data), filename=gif_file.filename))
        if message.strip():
            await ch.send(message)
        return {"ok": True}

    result = run_coro(do_send())
    return jsonify(result)

# ----- Templates -----
@app.route("/api/templates", methods=["GET"])
def api_get_templates():
    return jsonify(load_templates())

@app.route("/api/templates", methods=["POST"])
def api_add_template():
    t = request.json
    templates = load_templates()
    t["id"] = max((x.get("id", 0) for x in templates), default=0) + 1
    templates.append(t)
    save_templates(templates)
    return jsonify(t)

@app.route("/api/templates/<int:tid>", methods=["PUT"])
def api_update_template(tid):
    templates = load_templates()
    for i, t in enumerate(templates):
        if t.get("id") == tid:
            templates[i] = {**t, **request.json, "id": tid}
            save_templates(templates)
            return jsonify(templates[i])
    return jsonify({"error": "not found"}), 404

@app.route("/api/templates/<int:tid>", methods=["DELETE"])
def api_delete_template(tid):
    templates = [t for t in load_templates() if t.get("id") != tid]
    save_templates(templates)
    return jsonify({"ok": True})

# ----- Ranks info -----
@app.route("/api/ranks", methods=["GET"])
def api_ranks():
    return jsonify(RANKS)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

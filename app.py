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
INDEX_HTML = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>لوحة القيادة العسكرية</title>
<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;900&family=Tajawal:wght@400;500;700&display=swap" rel="stylesheet">
<style>
  :root {
    --bg:       #0a0c0f;
    --surface:  #111418;
    --card:     #161b22;
    --border:   #21262d;
    --gold:     #d4a843;
    --gold2:    #f0c060;
    --red:      #c0392b;
    --green:    #27ae60;
    --blue:     #2980b9;
    --text:     #e6edf3;
    --muted:    #8b949e;
    --accent:   #1f6feb;
  }

  * { margin:0; padding:0; box-sizing:border-box; }

  body {
    font-family: 'Cairo', sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    background-image:
      repeating-linear-gradient(0deg, transparent, transparent 39px, #ffffff04 39px, #ffffff04 40px),
      repeating-linear-gradient(90deg, transparent, transparent 39px, #ffffff04 39px, #ffffff04 40px);
  }

  /* ===== Header ===== */
  header {
    background: linear-gradient(135deg, #0d1117 0%, #161b22 50%, #0d1117 100%);
    border-bottom: 2px solid var(--gold);
    padding: 0 2rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: 70px;
    position: sticky;
    top: 0;
    z-index: 100;
    box-shadow: 0 4px 30px #d4a84320;
  }

  .logo {
    display: flex;
    align-items: center;
    gap: .75rem;
    font-size: 1.3rem;
    font-weight: 900;
    color: var(--gold);
    letter-spacing: 1px;
  }

  .logo-icon {
    width: 38px;
    height: 38px;
    background: linear-gradient(135deg, var(--gold), var(--gold2));
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.4rem;
  }

  .status-dot {
    width: 10px; height: 10px;
    background: var(--green);
    border-radius: 50%;
    animation: pulse 2s infinite;
    box-shadow: 0 0 8px var(--green);
  }

  @keyframes pulse {
    0%,100% { opacity:1; transform:scale(1); }
    50%      { opacity:.6; transform:scale(1.3); }
  }

  /* ===== Nav tabs ===== */
  nav {
    display: flex;
    gap: 0;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 0 2rem;
    overflow-x: auto;
  }

  .nav-tab {
    padding: .9rem 1.5rem;
    cursor: pointer;
    font-weight: 600;
    font-size: .95rem;
    color: var(--muted);
    border-bottom: 3px solid transparent;
    white-space: nowrap;
    transition: all .2s;
    user-select: none;
  }

  .nav-tab:hover { color: var(--text); }
  .nav-tab.active { color: var(--gold); border-bottom-color: var(--gold); }

  /* ===== Main layout ===== */
  main { padding: 2rem; max-width: 1200px; margin: auto; }

  .section { display: none; animation: fadeIn .3s ease; }
  .section.active { display: block; }

  @keyframes fadeIn {
    from { opacity:0; transform:translateY(8px); }
    to   { opacity:1; transform:translateY(0); }
  }

  /* ===== Cards ===== */
  .card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.5rem;
    margin-bottom: 1.5rem;
  }

  .card-title {
    font-size: 1.1rem;
    font-weight: 700;
    color: var(--gold);
    margin-bottom: 1.25rem;
    display: flex;
    align-items: center;
    gap: .5rem;
  }

  /* ===== Inputs ===== */
  input[type=text], input[type=number], textarea, select {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--text);
    padding: .65rem 1rem;
    font-family: 'Cairo', sans-serif;
    font-size: .9rem;
    width: 100%;
    transition: border-color .2s;
    outline: none;
  }

  input[type=text]:focus,
  input[type=number]:focus,
  textarea:focus,
  select:focus { border-color: var(--gold); }

  textarea { resize: vertical; min-height: 100px; }

  /* ===== Buttons ===== */
  .btn {
    padding: .65rem 1.4rem;
    border: none;
    border-radius: 8px;
    font-family: 'Cairo', sans-serif;
    font-weight: 700;
    font-size: .9rem;
    cursor: pointer;
    transition: all .2s;
    display: inline-flex;
    align-items: center;
    gap: .4rem;
  }

  .btn-gold   { background: linear-gradient(135deg, var(--gold), var(--gold2)); color: #0a0c0f; }
  .btn-red    { background: var(--red); color: #fff; }
  .btn-green  { background: var(--green); color: #fff; }
  .btn-blue   { background: var(--blue); color: #fff; }
  .btn-ghost  { background: transparent; color: var(--muted); border: 1px solid var(--border); }

  .btn:hover { filter: brightness(1.15); transform: translateY(-1px); }
  .btn:active { transform: translateY(0); }

  .btn-sm { padding: .4rem .9rem; font-size: .82rem; }

  /* ===== Member table ===== */
  .member-table { width: 100%; border-collapse: collapse; }
  .member-table th {
    text-align: right;
    padding: .75rem 1rem;
    font-size: .82rem;
    color: var(--muted);
    border-bottom: 1px solid var(--border);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: .5px;
  }

  .member-table td {
    padding: .75rem 1rem;
    border-bottom: 1px solid #ffffff08;
    font-size: .9rem;
    vertical-align: middle;
  }

  .member-table tr:hover td { background: #ffffff04; }

  .avatar {
    width: 36px; height: 36px;
    border-radius: 50%;
    border: 2px solid var(--gold);
    object-fit: cover;
  }

  .rank-badge {
    background: linear-gradient(135deg, #1a2030, #1e2840);
    border: 1px solid var(--gold);
    color: var(--gold2);
    padding: .2rem .7rem;
    border-radius: 20px;
    font-size: .78rem;
    font-weight: 700;
  }

  .check-col { width: 40px; }
  .check-col input[type=checkbox] {
    width: 16px; height: 16px;
    cursor: pointer;
    accent-color: var(--gold);
  }

  /* ===== Grid ===== */
  .grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }
  @media(max-width:700px) { .grid2 { grid-template-columns: 1fr; } }

  .flex { display: flex; gap: .75rem; flex-wrap: wrap; align-items: center; }
  .flex-end { justify-content: flex-end; }
  .mt { margin-top: 1rem; }

  /* ===== Toast ===== */
  #toast {
    position: fixed;
    bottom: 2rem;
    left: 50%;
    transform: translateX(-50%) translateY(80px);
    background: var(--card);
    border: 1px solid var(--gold);
    border-radius: 10px;
    padding: .75rem 1.5rem;
    color: var(--text);
    font-weight: 600;
    z-index: 999;
    transition: transform .3s ease;
    box-shadow: 0 8px 32px #000a;
  }

  #toast.show { transform: translateX(-50%) translateY(0); }
  #toast.error { border-color: var(--red); color: var(--red); }
  #toast.success { border-color: var(--green); color: var(--green); }

  /* ===== File upload ===== */
  .file-drop {
    border: 2px dashed var(--border);
    border-radius: 10px;
    padding: 1.5rem;
    text-align: center;
    cursor: pointer;
    transition: border-color .2s;
    color: var(--muted);
    font-size: .9rem;
  }

  .file-drop:hover, .file-drop.drag { border-color: var(--gold); color: var(--gold); }
  .file-drop input { display: none; }

  /* ===== Templates ===== */
  .template-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 1rem 1.25rem;
    margin-bottom: .75rem;
    display: flex;
    align-items: flex-start;
    gap: 1rem;
  }

  .template-text {
    flex: 1;
    font-size: .9rem;
    line-height: 1.7;
    white-space: pre-wrap;
    color: var(--text);
  }

  .template-name {
    font-size: .78rem;
    color: var(--gold);
    font-weight: 700;
    margin-bottom: .35rem;
  }

  /* ===== Promote section ===== */
  .promote-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
    gap: 1rem;
  }

  .promote-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 1rem;
    display: flex;
    align-items: center;
    gap: .75rem;
    cursor: pointer;
    transition: border-color .2s, background .2s;
  }

  .promote-card.selected {
    border-color: var(--gold);
    background: #d4a84312;
  }

  .promote-card .info { flex: 1; }
  .promote-card .pname { font-weight: 700; font-size: .95rem; }
  .promote-card .pranks { font-size: .8rem; color: var(--muted); margin-top: .2rem; }

  .arrow-icon { color: var(--gold); font-size: 1.1rem; }

  /* Loading */
  .spinner {
    width: 32px; height: 32px;
    border: 3px solid var(--border);
    border-top-color: var(--gold);
    border-radius: 50%;
    animation: spin .7s linear infinite;
    margin: 2rem auto;
  }

  @keyframes spin { to { transform: rotate(360deg); } }

  .empty-state { text-align: center; color: var(--muted); padding: 3rem 1rem; font-size: 1rem; }
  .empty-state .big { font-size: 2.5rem; margin-bottom: .5rem; }

  /* result rows */
  .result-ok  { color: var(--green); }
  .result-err { color: var(--red); }
</style>
</head>
<body>

<header>
  <div class="logo">
    <div class="logo-icon">⚔️</div>
    لوحة القيادة
  </div>
  <div class="flex">
    <div class="status-dot" id="statusDot" title="حالة البوت"></div>
    <span id="statusText" style="font-size:.85rem;color:var(--muted)">جاري الاتصال...</span>
    <button onclick="doLogout()" style="background:transparent;border:1px solid #c0392b;color:#c0392b;border-radius:7px;padding:.35rem .85rem;font-family:Cairo,sans-serif;font-size:.82rem;font-weight:700;cursor:pointer;">🚪 خروج</button>
  </div>
</header>

<nav>
  <div class="nav-tab active" onclick="switchTab('tracked')">👁️ المتابَعون</div>
  <div class="nav-tab" onclick="switchTab('promote')">🎖️ الترقيات</div>
  <div class="nav-tab" onclick="switchTab('messages')">📨 الرسائل</div>
  <div class="nav-tab" onclick="switchTab('templates')">📋 القوالب</div>
</nav>

<main>

<!-- ============================= TAB: TRACKED ============================= -->
<div id="tab-tracked" class="section active">

  <div class="card">
    <div class="card-title">➕ إضافة أعضاء للمتابعة</div>
    <textarea id="bulkIds" placeholder="ضع الـ IDs هنا مفصولة بمسافة أو فاصلة أو سطر جديد&#10;مثال:&#10;123456789012345678&#10;987654321098765432"></textarea>
    <div class="flex mt">
      <button class="btn btn-gold" onclick="bulkAdd()">➕ إضافة</button>
      <button class="btn btn-ghost" onclick="loadTracked()">🔄 تحديث</button>
    </div>
    <div id="addResult" style="margin-top:.75rem;font-size:.88rem;"></div>
  </div>

  <div class="card">
    <div class="card-title">👁️ قائمة المتابعة</div>
    <div id="trackedBody"><div class="spinner"></div></div>
  </div>

</div>

<!-- ============================= TAB: PROMOTE ============================= -->
<div id="tab-promote" class="section">

  <div class="card">
    <div class="card-title">🎖️ ترقية جماعية</div>
    <p style="color:var(--muted);font-size:.88rem;margin-bottom:1rem;">اختار الأعضاء اللي عايز تعمل ترقيتهم — كل واحد هيتحول لأعلى رتبة تلقائياً</p>
    <div class="flex" style="margin-bottom:1rem;">
      <button class="btn btn-ghost btn-sm" onclick="selectAllPromote()">تحديد الكل</button>
      <button class="btn btn-ghost btn-sm" onclick="deselectAllPromote()">إلغاء الكل</button>
      <button class="btn btn-gold" onclick="doPromote()" id="promoteBtn" style="margin-right:auto;">⬆️ ترقية المحددين</button>
    </div>
    <div id="promoteGrid"><div class="spinner"></div></div>
    <div id="promoteResult" style="margin-top:1rem;font-size:.88rem;"></div>
  </div>

</div>

<!-- ============================= TAB: MESSAGES ============================= -->
<div id="tab-messages" class="section">

  <div class="grid2">
    <div class="card" style="margin-bottom:0">
      <div class="card-title">📨 إرسال رسالة</div>

      <div style="margin-bottom:.75rem;">
        <label style="font-size:.85rem;color:var(--muted);display:block;margin-bottom:.35rem;">ID الشانيل</label>
        <input type="text" id="sendChannelId" placeholder="123456789012345678">
      </div>

      <div style="margin-bottom:.75rem;">
        <label style="font-size:.85rem;color:var(--muted);display:block;margin-bottom:.35rem;">نص الرسالة</label>
        <textarea id="sendMessage" placeholder="اكتب رسالتك هنا..."></textarea>
      </div>

      <div style="margin-bottom:1rem;">
        <label style="font-size:.85rem;color:var(--muted);display:block;margin-bottom:.35rem;">ملف GIF (اختياري)</label>
        <div class="file-drop" id="dropZone" onclick="document.getElementById('gifInput').click()">
          <input type="file" id="gifInput" accept="image/gif,video/mp4" onchange="onGifChosen(event)">
          <div id="dropLabel">📎 اضغط لاختيار GIF</div>
        </div>
      </div>

      <div class="flex">
        <button class="btn btn-gold" onclick="sendMessage()">📤 إرسال</button>
        <button class="btn btn-ghost" onclick="clearGif()">🗑️ حذف GIF</button>
      </div>
      <div id="sendResult" style="margin-top:.75rem;font-size:.88rem;"></div>
    </div>

    <div class="card" style="margin-bottom:0">
      <div class="card-title">📋 استخدام قالب</div>
      <p style="color:var(--muted);font-size:.85rem;margin-bottom:1rem;">اضغط على أي قالب لتحميله في خانة الرسالة</p>
      <div id="templatesMiniList"><div class="spinner"></div></div>
    </div>
  </div>

</div>

<!-- ============================= TAB: TEMPLATES ============================= -->
<div id="tab-templates" class="section">

  <div class="card">
    <div class="card-title">➕ قالب جديد</div>
    <div style="margin-bottom:.75rem;">
      <input type="text" id="tplName" placeholder="اسم القالب (مثال: إعلان ترقية)">
    </div>
    <textarea id="tplContent" placeholder="محتوى القالب..."></textarea>
    <div class="flex mt">
      <button class="btn btn-gold" onclick="addTemplate()">💾 حفظ</button>
    </div>
  </div>

  <div class="card">
    <div class="card-title">📋 القوالب المحفوظة</div>
    <div id="templatesList"><div class="spinner"></div></div>
  </div>

</div>

</main>

<!-- Toast -->
<div id="toast"></div>

<!-- Edit template modal -->
<div id="editModal" style="display:none;position:fixed;inset:0;background:#000a;z-index:200;align-items:center;justify-content:center;">
  <div style="background:var(--card);border:1px solid var(--gold);border-radius:14px;padding:1.5rem;width:min(560px,95vw);">
    <div class="card-title">✏️ تعديل القالب</div>
    <input type="hidden" id="editTplId">
    <div style="margin-bottom:.75rem;">
      <input type="text" id="editTplName" placeholder="اسم القالب">
    </div>
    <textarea id="editTplContent" style="min-height:140px;" placeholder="محتوى القالب..."></textarea>
    <div class="flex mt flex-end">
      <button class="btn btn-ghost" onclick="closeModal()">إلغاء</button>
      <button class="btn btn-gold" onclick="saveEditTemplate()">💾 حفظ</button>
    </div>
  </div>
</div>

<script>
// ===== State =====
let trackedData  = [];
let promoteData  = [];  // same as tracked
let templatesData = [];
let selectedGif  = null;

// ===== Tab switch =====
function switchTab(name) {
  document.querySelectorAll('.nav-tab').forEach((t,i) => t.classList.remove('active'));
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  const tabs = ['tracked','promote','messages','templates'];
  const idx  = tabs.indexOf(name);
  document.querySelectorAll('.nav-tab')[idx].classList.add('active');
  document.getElementById('tab-'+name).classList.add('active');
  if (name === 'tracked') loadTracked();
  if (name === 'promote' && trackedData.length) renderPromoteGrid();
  else if (name === 'promote') loadTracked();
  if (name === 'messages' || name === 'templates') loadTemplates();
}

// ===== Toast =====
function toast(msg, type='') {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = type ? `show ${type}` : 'show';
  setTimeout(() => el.className = '', 3000);
}

// ===== Bot status check =====
async function checkStatus() {
  try {
    const r = await fetch('/api/ranks');
    if (r.ok) {
      document.getElementById('statusDot').style.background = 'var(--green)';
      document.getElementById('statusText').textContent = 'البوت متصل';
    }
  } catch {
    document.getElementById('statusDot').style.background = 'var(--red)';
    document.getElementById('statusText').textContent = 'غير متصل';
  }
}

// ===== TRACKED =====
async function loadTracked() {
  document.getElementById('trackedBody').innerHTML = '<div class="spinner"></div>';
  document.getElementById('promoteGrid').innerHTML  = '<div class="spinner"></div>';
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);
    const r = await fetch('/api/tracked', {signal: controller.signal});
    clearTimeout(timeout);
    if (r.status === 401) { window.location.href = '/login'; return; }
    trackedData = await r.json();
    renderTracked();
    renderPromoteGrid();
  } catch(e) {
    document.getElementById('trackedBody').innerHTML = '<div class="empty-state"><div class="big">⚠️</div>تعذر تحميل البيانات — <button class="btn btn-ghost btn-sm" onclick="loadTracked()">🔄 إعادة المحاولة</button></div>';
  }
}

function renderTracked() {
  const el = document.getElementById('trackedBody');
  if (!trackedData.length) {
    el.innerHTML = '<div class="empty-state"><div class="big">👁️</div>قائمة المتابعة فاضية</div>';
    return;
  }
  el.innerHTML = `
  <table class="member-table">
    <thead>
      <tr>
        <th>العضو</th>
        <th>الاسم في السيرفر</th>
        <th>الـ ID</th>
        <th>الرتبة</th>
        <th></th>
      </tr>
    </thead>
    <tbody>
      ${trackedData.map(m => `
      <tr>
        <td><img class="avatar" src="${m.avatar}" onerror="this.src='https://cdn.discordapp.com/embed/avatars/0.png'"></td>
        <td>${m.name}</td>
        <td><code style="color:var(--muted);font-size:.82rem">${m.id}</code></td>
        <td><span class="rank-badge">${m.rank}</span></td>
        <td><button class="btn btn-red btn-sm" onclick="removeTracked('${m.id}')">🗑️</button></td>
      </tr>`).join('')}
    </tbody>
  </table>`;
}

async function bulkAdd() {
  const text = document.getElementById('bulkIds').value;
  const ids  = (text.match(/\\d{17,20}/g) || []);  // keep as strings to avoid JS integer overflow
  if (!ids.length) { toast('مفيش IDs صالحة!', 'error'); return; }
  const r = await fetch('/api/tracked', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ids})
  });
  const data = await r.json();
  let html = '';
  if (data.added.length)   html += `<span class="result-ok">✅ تمت إضافة: ${data.added.join(', ')}</span><br>`;
  if (data.missing.length) html += `<span class="result-err">⚠️ مش في السيرفر: ${data.missing.join(', ')}</span>`;
  document.getElementById('addResult').innerHTML = html;
  document.getElementById('bulkIds').value = '';
  toast(`تمت إضافة ${data.added.length} عضو`, 'success');
  loadTracked();
}

async function removeTracked(uid) {
  await fetch(`/api/tracked/${uid}`, {method:'DELETE'});
  toast('تم الحذف', 'success');
  loadTracked();
}

// ===== PROMOTE =====
function renderPromoteGrid() {
  const el = document.getElementById('promoteGrid');
  if (!trackedData.length) {
    el.innerHTML = '<div class="empty-state"><div class="big">👤</div>قائمة المتابعة فاضية — أضف أعضاء أولاً</div>';
    return;
  }
  el.innerHTML = `<div class="promote-grid">
    ${trackedData.map(m => `
    <div class="promote-card" id="pc-${m.id}" onclick="togglePromote('${m.id}')">
      <img class="avatar" src="${m.avatar}" onerror="this.src='https://cdn.discordapp.com/embed/avatars/0.png'">
      <div class="info">
        <div class="pname">${m.name}</div>
        <div class="pranks">الرتبة الحالية: <b>${m.rank}</b></div>
      </div>
    </div>`).join('')}
  </div>`;
}

function togglePromote(id) {
  document.getElementById('pc-'+id).classList.toggle('selected');
}

function selectAllPromote() {
  document.querySelectorAll('.promote-card').forEach(c => c.classList.add('selected'));
}

function deselectAllPromote() {
  document.querySelectorAll('.promote-card').forEach(c => c.classList.remove('selected'));
}

async function doPromote() {
  var selected = Array.from(document.querySelectorAll('.promote-card.selected')).map(function(c){ return c.id.replace('pc-',''); });
  if (!selected.length) { toast('اختار على الأقل عضو واحد', 'error'); return; }
  document.getElementById('promoteBtn').disabled = true;
  document.getElementById('promoteResult').innerHTML = '<div class="spinner"></div>';
  try {
    var r = await fetch('/api/promote', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ids: selected})
    });
    if (r.status === 401) { window.location.href = '/login'; return; }
    if (!r.ok) {
      var txt = await r.text();
      document.getElementById('promoteResult').innerHTML = '<span class="result-err">خطا ' + r.status + '</span>';
      document.getElementById('promoteBtn').disabled = false;
      return;
    }
    var results = await r.json();
    var statusMap = {ok:'ok', not_found:'مش في السيرفر', no_rank:'بدون رتبة', max_rank:'أعلى رتبة', role_missing:'رتبة مش موجودة'};
    var lines = results.map(function(res) {
      if (res.status === 'ok') return '<span class="result-ok">✅ ' + res.name + ': ' + res.from + ' ← ' + res.to + '</span>';
      return '<span class="result-err">❌ ' + (statusMap[res.status]||res.status) + ': ' + res.id + '</span>';
    });
    var html = lines.join('<br>') || '<span class="result-err">مفيش نتايج</span>';

    var ok = results.filter(function(r){ return r.status === 'ok'; });
    var copyText = '';
    if (ok.length) {
      var groups = {};
      ok.forEach(function(r) {
        var key = r.to_role_id || r.to;
        if (!groups[key]) groups[key] = {role_id: r.to_role_id, members: []};
        groups[key].members.push(r.id);
      });
      var parts = [];
      Object.values(groups).forEach(function(g) {
        var roleLine = g.role_id ? ('<@&' + g.role_id + '>') : '';
        var memberLines = g.members.map(function(id){ return '<@' + id + '>'; }).join('\n');
        parts.push(roleLine + '\n\n' + memberLines + '\n');
      });
      copyText = parts.join('\n\n');
    }

    if (copyText) {
      html += '<div style="margin-top:1rem;background:var(--surface);border:1px solid var(--gold);border-radius:8px;padding:1rem;">' +
        '<div style="font-size:.82rem;color:var(--gold);font-weight:700;margin-bottom:.5rem;">📋 نص جاهز للنسخ:</div>' +
        '<pre id="copyBox" style="font-family:monospace;font-size:.88rem;color:var(--text);white-space:pre-wrap;word-break:break-all;margin-bottom:.75rem;">' + copyText + '</pre>' +
        '<button class="btn btn-gold btn-sm" onclick="copyMentions()">📋 نسخ</button></div>';
    }
    document.getElementById('promoteResult').innerHTML = html;
    toast('تمت الترقية: ' + ok.length + ' عضو', 'success');
    loadTracked();
  } catch(e) {
    document.getElementById('promoteResult').innerHTML = '<span class="result-err">خطأ: ' + e.message + '</span>';
  }
  document.getElementById('promoteBtn').disabled = false;
}

// ===== MESSAGES =====
function onGifChosen(e) {
  const file = e.target.files[0];
  if (!file) return;
  selectedGif = file;
  document.getElementById('dropLabel').textContent = '✅ ' + file.name;
  document.getElementById('dropZone').classList.add('drag');
}

function clearGif() {
  selectedGif = null;
  document.getElementById('gifInput').value = '';
  document.getElementById('dropLabel').textContent = '📎 اضغط لاختيار GIF';
  document.getElementById('dropZone').classList.remove('drag');
}

async function sendMessage() {
  const channelId = document.getElementById('sendChannelId').value.trim();
  const message   = document.getElementById('sendMessage').value.trim();
  if (!channelId) { toast('ادخل ID الشانيل', 'error'); return; }
  if (!message && !selectedGif) { toast('اكتب رسالة أو ارفق GIF', 'error'); return; }

  const fd = new FormData();
  fd.append('channel_id', channelId);
  fd.append('message', message);
  if (selectedGif) fd.append('gif', selectedGif);

  const r = await fetch('/api/send', {method:'POST', body:fd});
  const data = await r.json();
  if (data.ok) {
    toast('تم الإرسال ✅', 'success');
    document.getElementById('sendMessage').value = '';
    clearGif();
  } else {
    toast('خطأ: ' + data.error, 'error');
  }
}

// ===== TEMPLATES =====
async function loadTemplates() {
  try {
    const r = await fetch('/api/templates');
    templatesData = await r.json();
    renderTemplates();
    renderTemplatesMini();
  } catch { }
}

function renderTemplates() {
  const el = document.getElementById('templatesList');
  if (!templatesData.length) {
    el.innerHTML = '<div class="empty-state"><div class="big">📋</div>مفيش قوالب محفوظة</div>';
    return;
  }
  el.innerHTML = templatesData.map(t => `
  <div class="template-card">
    <div style="flex:1">
      <div class="template-name">${t.name || 'بدون اسم'}</div>
      <div class="template-text">${escHtml(t.content)}</div>
    </div>
    <div style="display:flex;flex-direction:column;gap:.5rem;">
      <button class="btn btn-blue btn-sm" onclick="openEditModal(${t.id})">✏️</button>
      <button class="btn btn-red btn-sm" onclick="deleteTemplate(${t.id})">🗑️</button>
    </div>
  </div>`).join('');
}

function renderTemplatesMini() {
  const el = document.getElementById('templatesMiniList');
  if (!templatesData.length) {
    el.innerHTML = '<div style="color:var(--muted);font-size:.88rem">مفيش قوالب — أضف من تبويب القوالب</div>';
    return;
  }
  el.innerHTML = templatesData.map(t => `
  <div class="template-card" style="cursor:pointer" onclick="loadTemplate(${t.id})">
    <div style="flex:1">
      <div class="template-name">${t.name || 'بدون اسم'}</div>
      <div class="template-text" style="max-height:50px;overflow:hidden;-webkit-mask-image:linear-gradient(to bottom,#fff 50%,transparent)">${escHtml(t.content)}</div>
    </div>
    <span style="color:var(--gold);font-size:1.2rem">←</span>
  </div>`).join('');
}

function loadTemplate(id) {
  const t = templatesData.find(x => x.id === id);
  if (!t) return;
  document.getElementById('sendMessage').value = t.content;
  toast('تم تحميل القالب', 'success');
}

async function addTemplate() {
  const name    = document.getElementById('tplName').value.trim();
  const content = document.getElementById('tplContent').value.trim();
  if (!content) { toast('اكتب محتوى القالب', 'error'); return; }
  await fetch('/api/templates', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({name, content})
  });
  document.getElementById('tplName').value = '';
  document.getElementById('tplContent').value = '';
  toast('تم حفظ القالب', 'success');
  loadTemplates();
}

function openEditModal(id) {
  const t = templatesData.find(x => x.id === id);
  if (!t) return;
  document.getElementById('editTplId').value      = t.id;
  document.getElementById('editTplName').value    = t.name || '';
  document.getElementById('editTplContent').value = t.content;
  document.getElementById('editModal').style.display = 'flex';
}

function closeModal() {
  document.getElementById('editModal').style.display = 'none';
}

async function saveEditTemplate() {
  const id      = parseInt(document.getElementById('editTplId').value);
  const name    = document.getElementById('editTplName').value.trim();
  const content = document.getElementById('editTplContent').value.trim();
  await fetch(`/api/templates/${id}`, {
    method:'PUT',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({name, content})
  });
  closeModal();
  toast('تم التحديث', 'success');
  loadTemplates();
}

async function deleteTemplate(id) {
  await fetch(`/api/templates/${id}`, {method:'DELETE'});
  toast('تم الحذف', 'success');
  loadTemplates();
}

function escHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\\n/g,'<br>');
}

// ===== Copy mentions =====
function copyMentions() {
  const text = document.getElementById('copyBox').textContent;
  navigator.clipboard.writeText(text).then(() => {
    toast('تم النسخ ✅', 'success');
  }).catch(() => {
    // fallback
    const ta = document.createElement('textarea');
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    toast('تم النسخ ✅', 'success');
  });
}

// ===== Logout =====
async function doLogout() {
  await fetch('/api/logout', {method:'POST'});
  window.location.href = '/login';
}

// ===== Init =====
checkStatus();
setInterval(checkStatus, 30000);
loadTracked();
loadTemplates();
</script>
</body>
</html>
"""

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

# ================================================================
#  🛒 ROBUKS GENERATOR — SHOP  (Flask + Upstash, runs on Render)
#  Standalone from the verify site. Shares the SAME Upstash database
#  so generated keys work with the bot's /activatekey command.
#
#  Flow:
#   1) User buys a gamepass on your Roblox game
#   2) User enters their Roblox USERNAME on the shop
#   3) Site resolves username -> userId, checks gamepass ownership
#      via the public Roblox inventory API
#   4) If they own it AND haven't claimed before -> generate a 20-char
#      key, store it in Upstash as key:<KEY>, and show it to them
#   5) They redeem it in Discord with /activatekey
#
#  Anti-abuse: each Roblox user can claim each product only ONCE
#  (claim:<product>:<robloxUserId> is stored), so one purchase = one key.
# ================================================================
import os, json, time, secrets, string
import requests
from flask import Flask, request, render_template_string

app = Flask(__name__)

REDIS_URL   = os.getenv("UPSTASH_REDIS_REST_URL", "")
REDIS_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")

# product id -> (display name, gamepass id).  Fill in YOUR gamepass IDs.
PRODUCTS = {
    "premium":          {"name": "Premium (1 month)",          "gamepass": 0, "robux": 300},
    "premiumunlimited": {"name": "Premium (Unlimited)",        "gamepass": 0, "robux": 550},
    "premiumimmune":    {"name": "Premium + Blacklist Immune", "gamepass": 0, "robux": 1000},
}
# 👆 replace each "gamepass": 0 with the real Game Pass ID for that product.

KEY_CHARS = string.ascii_uppercase + string.digits + "!@#$%&*"

def _redis(*command):
    if not REDIS_URL or not REDIS_TOKEN:
        raise RuntimeError("Upstash not configured")
    r = requests.post(REDIS_URL, headers={"Authorization": f"Bearer {REDIS_TOKEN}"},
                      json=list(command), timeout=10)
    r.raise_for_status()
    return r.json().get("result")

def gen_key(n=20):
    return "".join(secrets.choice(KEY_CHARS) for _ in range(n))

# ---------- Roblox helpers ----------
def roblox_user_id(username):
    """Resolve a username to a userId via Roblox's public API."""
    try:
        r = requests.post("https://users.roblox.com/v1/usernames/users",
                          json={"usernames": [username], "excludeBannedUsers": False},
                          timeout=10)
        data = r.json().get("data", [])
        if data:
            return data[0].get("id"), data[0].get("name")
    except Exception as ex:
        print(f"roblox_user_id error: {ex}", flush=True)
    return None, None

def owns_gamepass(user_id, gamepass_id):
    """Check gamepass ownership via the public inventory API.
    itemType for gamepasses = 'GamePass'."""
    try:
        url = f"https://inventory.roblox.com/v1/users/{user_id}/items/GamePass/{gamepass_id}"
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            print(f"inventory status {r.status_code} for {user_id}/{gamepass_id}", flush=True)
            return False
        data = r.json().get("data", [])
        return len(data) > 0
    except Exception as ex:
        print(f"owns_gamepass error: {ex}", flush=True)
        return False

# ---------- pages ----------
PAGE = """<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Robuks Generator — Shop</title>
<style>
 @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;700&display=swap');
 :root{--void:#0b0e14;--panel:#141925;--panel2:#1b2130;--line:#26304a;--ink:#eef2ff;--dim:#8a93ad;--lime:#b6ff3c;--cyan:#3ce8ff;--violet:#8b5cff;--gold:#ffc53c;--danger:#ff5470}
 *{box-sizing:border-box;margin:0;padding:0}
 body{background:radial-gradient(1000px 500px at 85% -10%,rgba(139,92,255,.18),transparent 60%),radial-gradient(800px 500px at 5% 110%,rgba(60,232,255,.12),transparent 55%),var(--void);color:var(--ink);font-family:'Space Grotesk',system-ui,sans-serif;min-height:100vh;padding:40px 18px 70px}
 ::selection{background:var(--lime);color:#000}
 .wrap{max-width:940px;margin:0 auto}
 .brand{display:flex;align-items:center;gap:12px;font-weight:700;font-size:20px;margin-bottom:6px}
 .logo{width:36px;height:36px;border-radius:9px;background:conic-gradient(from 210deg,var(--lime),var(--cyan),var(--violet),var(--lime));display:grid;place-items:center;color:#000;font-weight:700;box-shadow:0 0 24px rgba(60,232,255,.35)}
 .sub{color:var(--dim);font-size:14px;margin-bottom:30px}
 h2{font-size:18px;margin:26px 0 14px;letter-spacing:-.02em}
 .cards{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
 .card{background:linear-gradient(180deg,var(--panel),var(--panel2));border:1px solid var(--line);border-radius:16px;padding:20px;display:flex;flex-direction:column;gap:8px;transition:.16s}
 .card:hover{border-color:var(--violet);transform:translateY(-3px)}
 .card h3{font-size:15px}
 .card .rbx{font-family:'JetBrains Mono';color:var(--gold);font-size:15px;font-weight:700}
 .card.g2 .rbx{color:var(--violet)} .card.g3 .rbx{color:var(--gold)}
 .card .buy{margin-top:auto;text-align:center;padding:10px;border-radius:10px;background:var(--panel2);border:1px solid var(--line);color:var(--ink);text-decoration:none;font-weight:600;font-size:13px;transition:.16s}
 .card .buy:hover{border-color:var(--cyan)}
 .redeem{margin-top:34px;background:var(--panel);border:1px solid var(--line);border-radius:18px;padding:24px}
 .redeem label{display:block;font-size:13px;color:var(--dim);margin:12px 0 6px}
 select,input{width:100%;padding:12px 14px;border-radius:11px;border:1px solid var(--line);background:var(--panel2);color:var(--ink);font-family:inherit;font-size:14px}
 button{margin-top:18px;width:100%;padding:13px;border:none;border-radius:11px;background:linear-gradient(90deg,var(--lime),var(--cyan));color:#04121a;font-weight:700;font-size:15px;cursor:pointer;transition:.16s}
 button:hover{filter:brightness(1.08)}
 .result{margin-top:18px;padding:16px;border-radius:12px;font-size:14px;line-height:1.5}
 .ok{background:rgba(182,255,60,.08);border:1px solid rgba(182,255,60,.4)}
 .err{background:rgba(255,84,112,.08);border:1px solid rgba(255,84,112,.4);color:#ffb5c1}
 .key{font-family:'JetBrains Mono';font-size:18px;font-weight:700;color:var(--lime);letter-spacing:1px;word-break:break-all;margin:8px 0;display:block}
 .steps{font-family:'JetBrains Mono';font-size:12px;color:var(--dim);margin-top:6px}
 .foot{margin-top:36px;text-align:center;color:var(--dim);font-family:'JetBrains Mono';font-size:11px}
 @media(max-width:720px){.cards{grid-template-columns:1fr}}
</style></head><body>
<div class="wrap">
  <div class="brand"><div class="logo">R</div> Robuks Generator — Shop</div>
  <div class="sub">Buy a gamepass on Roblox, then redeem your key below. Keys activate with <b>/activatekey</b> in Discord.</div>

  <h2>Products</h2>
  <div class="cards">
    {% for pid, p in products.items() %}
    <div class="card g{{ loop.index }}">
      <h3>{{ p.name }}</h3>
      <div class="rbx">{{ p.robux }} R$</div>
      {% if p.gamepass %}
      <a class="buy" href="https://www.roblox.com/game-pass/{{ p.gamepass }}" target="_blank">Buy on Roblox ↗</a>
      {% else %}
      <span class="buy" style="opacity:.5">Gamepass not set</span>
      {% endif %}
    </div>
    {% endfor %}
  </div>

  <div class="redeem">
    <h2 style="margin-top:0">🔑 Claim your key</h2>
    <form method="POST" action="/claim">
      <label>Product</label>
      <select name="product" required>
        {% for pid, p in products.items() %}
        <option value="{{ pid }}">{{ p.name }} — {{ p.robux }} R$</option>
        {% endfor %}
      </select>
      <label>Your Roblox username</label>
      <input name="username" placeholder="e.g. builderman" required autocomplete="off">
      <button type="submit">Verify purchase &amp; get key</button>
    </form>
    {% if result %}
      <div class="result {{ result_class }}">
        {{ result|safe }}
        {% if key %}<span class="key">{{ key }}</span>
        <div class="steps">In Discord run: /activatekey product:{{ product_id }} key:{{ key }}</div>{% endif %}
      </div>
    {% endif %}
  </div>

  <div class="foot">ROBUKS GENERATOR · shop · buying grants a gamepass; keys are single-use</div>
</div>
</body></html>"""

@app.route("/")
def home():
    return render_template_string(PAGE, products=PRODUCTS, result=None)

@app.route("/claim", methods=["POST"])
def claim():
    product = request.form.get("product", "").strip()
    username = request.form.get("username", "").strip()

    def show(msg, cls, key=None, pid=None):
        return render_template_string(PAGE, products=PRODUCTS, result=msg,
                                      result_class=cls, key=key, product_id=pid)

    if product not in PRODUCTS:
        return show("❌ Unknown product.", "err")
    p = PRODUCTS[product]
    if not p["gamepass"]:
        return show("⚠️ This product's gamepass isn't set up yet. Tell the owner.", "err")
    if not username:
        return show("❌ Please enter your Roblox username.", "err")

    uid, real_name = roblox_user_id(username)
    if not uid:
        return show(f"❌ Couldn't find Roblox user '{username}'. Check the spelling.", "err")

    # already claimed this product?
    try:
        if _redis("GET", f"claim:{product}:{uid}"):
            return show("❌ This Roblox account already claimed a key for this product. "
                        "One purchase = one key.", "err")
    except Exception:
        pass

    if not owns_gamepass(uid, p["gamepass"]):
        return show(f"❌ <b>{real_name}</b> doesn't own the <b>{p['name']}</b> gamepass yet. "
                    f"Buy it on Roblox first, then come back.", "err")

    # generate + store key, mark claimed
    key = gen_key()
    entry = json.dumps({"product": product, "used_by": None, "created": int(time.time()),
                        "roblox_id": uid, "roblox_name": real_name})
    try:
        _redis("SET", f"key:{key}", entry)
        _redis("SET", f"claim:{product}:{uid}", key)
    except Exception as ex:
        print(f"claim store error: {ex}", flush=True)
        return show("⚠️ Couldn't reach the key store. Try again shortly.", "err")

    print(f"KEY ISSUED product={product} roblox={real_name}({uid}) key={key[:6]}…", flush=True)
    return show(f"✅ Verified <b>{real_name}</b> owns <b>{p['name']}</b>! Here's your key:",
                "ok", key=key, pid=product)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")))

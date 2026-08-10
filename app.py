# 🛒 ROBUKS GENERATOR — SHOP (Flask + Upstash) — SECURE purchase detection
# via Roblox transaction history using a throwaway account cookie.
import os, json, time, secrets, string, datetime
import requests
from flask import Flask, request, render_template_string

app = Flask(__name__)
REDIS_URL    = os.getenv("UPSTASH_REDIS_REST_URL", "")
REDIS_TOKEN  = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")
ROBLOX_COOKIE= os.getenv("ROBLOX_COOKIE", "")
ROBLOX_API_KEY = os.getenv("ROBLOX_API_KEY", "")   # Open Cloud key with game-passes read+write
UNIVERSE_ID    = os.getenv("UNIVERSE_ID", "3842120926")
LOGO_URL     = os.getenv("LOGO_URL", "")
SALE_WINDOW  = int(os.getenv("SALE_WINDOW", str(7*24*3600)))

PRODUCTS = {
 "premium3day":     {"name":"Premium","len":"3 days","gamepass":0,"robux":1,"tone":"mint"},
 "premiumweek":     {"name":"Premium","len":"1 week","gamepass":0,"robux":2,"tone":"sky"},
 "premiummonth":    {"name":"Premium","len":"1 month","gamepass":0,"robux":3,"tone":"grape"},
 "premiumunlimited":{"name":"Premium","len":"Unlimited","gamepass":0,"robux":4,"tone":"sun","note":"or 1 server boost"},
 "premiumimmune":   {"name":"Premium + Immune","len":"Unlimited","gamepass":0,"robux":5,"tone":"flame","note":"or 2 boosts · blacklist-immune"},
}
UNBLACKLIST=[{"len":"1 hour","robux":5},{"len":"1 day","robux":20},{"len":"1 week","robux":50},{"len":"Permanent","robux":150}]
KEY_CHARS=string.ascii_uppercase+string.digits+"!@#$%&*"

def _redis(*c):
    if not REDIS_URL or not REDIS_TOKEN: raise RuntimeError("no upstash")
    r=requests.post(REDIS_URL,headers={"Authorization":f"Bearer {REDIS_TOKEN}"},json=list(c),timeout=10)
    r.raise_for_status(); return r.json().get("result")
def gen_key(n=20): return "".join(secrets.choice(KEY_CHARS) for _ in range(n))

# ---- bio-code identity verification ----
_WORDS = ["unicorn","friends","dragon","cookie","rocket","banana","pixel","ninja","turbo",
          "galaxy","noodle","waffle","cactus","pickle","zebra","comet","donut","llama",
          "mango","panda","robot","sunny","tiger","viper","wizard","yeti","bubble","cloud"]

def gen_bio_code():
    """Random phrase like 'unicornfriends994' or 'turbopanda'."""
    n = secrets.choice([2, 2, 3])  # 2-3 words
    words = "".join(secrets.choice(_WORDS) for _ in range(n))
    if secrets.choice([True, False]):
        words += str(secrets.randbelow(900) + 100)  # sometimes a number
    return words

def roblox_bio(user_id):
    """Fetch a Roblox user's profile description (bio). Public, no cookie needed."""
    try:
        r = requests.get(f"https://users.roblox.com/v1/users/{user_id}", timeout=10)
        if r.status_code == 200:
            return r.json().get("description", "") or ""
    except Exception as ex:
        print(f"bio fetch err: {ex}", flush=True)
    return ""

# ---- Open Cloud: create a gamepass automatically ----
def create_gamepass(display_name, price):
    """Create a gamepass via Roblox Open Cloud (plain JSON). Returns (id, raw, error)."""
    if not ROBLOX_API_KEY:
        return None, None, "no api key"
    # clean ASCII, collapse extra spaces
    safe = "".join(c for c in display_name if c.isalnum() or c in " -_")
    safe = " ".join(safe.split())[:45] or "Premium Pass"
    url = f"https://apis.roblox.com/game-passes/v1/universes/{UNIVERSE_ID}/game-passes"
    payload = json.dumps({"Name": safe, "Description": "Premium pass",
                          "Price": int(price), "IsForSale": True})
    headers = {"x-api-key": ROBLOX_API_KEY, "Content-Type": "application/json"}
    try:
        # send pre-serialized JSON via data= with explicit header (most reliable)
        r = requests.post(url, headers=headers, data=payload, timeout=20)
        print(f"🎟️ create name={safe!r} status={r.status_code} body={r.text[:300]}", flush=True)
        if r.status_code in (200, 201):
            data = r.json()
            return data.get("gamePassId") or data.get("id"), data, None
        return None, r.text, f"status {r.status_code}"
    except Exception as ex:
        print(f"create err: {ex}", flush=True)
        return None, None, str(ex)

def roblox_user_id(u):
    try:
        r=requests.post("https://users.roblox.com/v1/usernames/users",
                        json={"usernames":[u],"excludeBannedUsers":False},timeout=10)
        d=r.json().get("data",[])
        if d: return d[0].get("id"),d[0].get("name")
    except Exception as ex: print("uid err",ex,flush=True)
    return None,None

_session=requests.Session()
def _ensure_cookie():
    if ROBLOX_COOKIE:
        _session.cookies.set(".ROBLOSECURITY",ROBLOX_COOKIE,domain=".roblox.com")
def _headers():
    _ensure_cookie()
    csrf=""
    try:
        r=_session.post("https://auth.roblox.com/v2/logout",timeout=10)
        csrf=r.headers.get("x-csrf-token","")
    except Exception as ex: print("csrf err",ex,flush=True)
    return {"X-CSRF-TOKEN":csrf,"Content-Type":"application/json"}
def _authed_id():
    _ensure_cookie()   # <-- set the cookie BEFORE checking who we are
    try:
        r=_session.get("https://users.roblox.com/v1/users/authenticated",timeout=10)
        print(f"authed check status={r.status_code} body={r.text[:120]}",flush=True)
        if r.status_code==200: return r.json().get("id")
    except Exception as ex: print("authed err",ex,flush=True)
    return None

def owns_gamepass(user_id, gamepass_id):
    """Check if a user owns a gamepass via the public inventory API (reliable for gamepasses)."""
    try:
        url=f"https://inventory.roblox.com/v1/users/{user_id}/items/GamePass/{gamepass_id}"
        r=requests.get(url,timeout=10)
        print(f"🔎 ownership check user={user_id} gp={gamepass_id} status={r.status_code} body={r.text[:120]}",flush=True)
        if r.status_code!=200:
            return False
        return len(r.json().get("data",[]))>0
    except Exception as ex:
        print(f"owns_gamepass err {ex}",flush=True)
        return False

def buyer_purchased(seller,buyer,gp):
    # gamepass purchases are verified by OWNERSHIP (reliable). No transactions needed.
    owns = owns_gamepass(buyer, gp)
    return (True,"owns gamepass") if owns else (False,"doesn't own gamepass")

def _unused_old_tx(seller,buyer,gp):
    if not seller: return False,"cookie not logged in"
    h=_headers(); cursor=""; now=time.time()
    print(f"🔎 checking: seller={seller} buyer={buyer} gamepass={gp}",flush=True)
    for _ in range(6):
        url=(f"https://economy.roblox.com/v2/users/{seller}/transactions"
             f"?transactionType=Sale&limit=100&cursor={cursor}")
        try: r=_session.get(url,headers=h,timeout=12)
        except Exception as ex: return False,f"fetch err {ex}"
        if r.status_code!=200: return False,f"status {r.status_code}"
        data=r.json()
        rows=data.get("data",[])
        for tx in rows:
            det=tx.get("details") or {}; ag=tx.get("agent") or {}
            by=str(ag.get("id"))==str(buyer)
            same=str(det.get("id"))==str(gp)
            recent=True
            try:
                t=datetime.datetime.fromisoformat(tx.get("created","").replace("Z","+00:00")).timestamp()
                recent=(now-t)<=SALE_WINDOW
            except Exception: recent=True
            if same and by and recent: return True,"match"
        cursor=data.get("nextPageCursor") or ""
        if not cursor: break
    return False,"no matching sale"

PAGE=r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Robuks Generator — Shop</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Fredoka:wght@500;600;700&family=Baloo+2:wght@600;700;800&family=DM+Mono:wght@500&display=swap');
:root{--bg:#fff4e6;--bg2:#ffe9cf;--ink:#2a2140;--sub:#7c6f92;--card:#fff;--edge:#2a2140;--mint:#33e6a6;--sky:#3fb9ff;--grape:#a06bff;--sun:#ffcb3a;--flame:#ff7a5c;--shadow:6px 6px 0 #2a2140}
*{box-sizing:border-box;margin:0;padding:0}
body{background:radial-gradient(circle at 12% 8%,#ffd9a8 0 12px,transparent 13px) 0 0/64px 64px,linear-gradient(180deg,var(--bg),var(--bg2));font-family:'Fredoka',system-ui,sans-serif;color:var(--ink);min-height:100vh;padding:34px 16px 80px}
::selection{background:var(--sun)}.wrap{max-width:960px;margin:0 auto}
.top{display:flex;align-items:center;gap:16px;margin-bottom:6px}
.logo{width:66px;height:66px;border-radius:20px;border:3px solid var(--edge);box-shadow:var(--shadow);background:var(--sun);display:grid;place-items:center;font-size:34px;overflow:hidden;flex:none}
.logo img{width:100%;height:100%;object-fit:cover}
.title{font-family:'Baloo 2';font-weight:800;font-size:34px;line-height:1}
.title small{display:block;font-family:'Fredoka';font-weight:600;font-size:14px;color:var(--sub);margin-top:6px}
.lab{font-family:'Baloo 2';font-weight:800;font-size:22px;margin:34px 0 16px;display:flex;align-items:center;gap:10px}
.lab::after{content:"";flex:1;height:3px;background:repeating-linear-gradient(90deg,var(--edge) 0 10px,transparent 10px 18px);opacity:.35;border-radius:3px}
.plans{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}
.plan{background:var(--card);border:3px solid var(--edge);border-radius:22px;box-shadow:var(--shadow);padding:18px;display:flex;flex-direction:column;gap:6px;transition:.12s}
.plan:hover{transform:translate(-2px,-2px);box-shadow:9px 9px 0 #2a2140}
.tone{width:100%;height:10px;border-radius:20px;border:2px solid var(--edge);margin-bottom:8px}
.mint{background:var(--mint)}.sky{background:var(--sky)}.grape{background:var(--grape)}.sun{background:var(--sun)}.flame{background:var(--flame)}
.plan .len{font-family:'Baloo 2';font-weight:800;font-size:19px}.plan .nm{color:var(--sub);font-size:13px;font-weight:600;margin-top:-2px}
.price{font-family:'Baloo 2';font-weight:800;font-size:26px;margin:8px 0 2px}.price b{font-size:15px;color:var(--sub)}
.note{font-size:12px;color:var(--sub);min-height:16px;line-height:1.3}
.buy{margin-top:12px;text-align:center;padding:11px;border-radius:14px;border:3px solid var(--edge);background:var(--sun);color:var(--edge);text-decoration:none;font-weight:700;font-family:'Baloo 2';font-size:15px;box-shadow:3px 3px 0 #2a2140;transition:.1s}
.buy:hover{transform:translate(-1px,-1px);box-shadow:5px 5px 0 #2a2140}.buy.off{background:#efe7f5;color:#a99cbf;box-shadow:none}
.chips{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.chip{background:var(--card);border:3px solid var(--edge);border-radius:16px;box-shadow:4px 4px 0 #2a2140;padding:12px 10px;text-align:center}
.chip .cl{font-family:'Baloo 2';font-weight:800;font-size:15px}.chip .cp{font-family:'DM Mono';color:var(--flame);margin-top:2px;font-size:14px}
.redeem{margin-top:34px;background:var(--card);border:3px solid var(--edge);border-radius:24px;box-shadow:var(--shadow);padding:24px}
.redeem h3{font-family:'Baloo 2';font-weight:800;font-size:22px;margin-bottom:4px}.redeem p{color:var(--sub);font-size:13px;margin-bottom:14px}
label{display:block;font-weight:600;font-size:13px;margin:12px 0 6px}
select,input{width:100%;padding:13px 14px;border:3px solid var(--edge);border-radius:14px;background:#fffaf0;color:var(--ink);font-family:'Fredoka';font-weight:600;font-size:15px}
select:focus,input:focus{outline:none;box-shadow:3px 3px 0 var(--grape)}
.go{margin-top:18px;width:100%;padding:15px;border:3px solid var(--edge);border-radius:16px;background:linear-gradient(90deg,var(--mint),var(--sky));color:var(--edge);font-family:'Baloo 2';font-weight:800;font-size:17px;cursor:pointer;box-shadow:5px 5px 0 #2a2140;transition:.1s}
.go:hover{transform:translate(-2px,-2px);box-shadow:7px 7px 0 #2a2140}
.result{margin-top:18px;padding:16px;border-radius:16px;font-size:14px;line-height:1.5;border:3px solid var(--edge)}
.ok{background:#e3fff4}.err{background:#ffe7e7}
.key{font-family:'DM Mono';font-size:19px;color:var(--grape);letter-spacing:1px;word-break:break-all;display:block;margin:10px 0;background:#f6f0ff;border:2px dashed var(--grape);border-radius:12px;padding:12px;text-align:center}
.steps{font-family:'DM Mono';font-size:12px;color:var(--sub);margin-top:4px}
.foot{margin-top:34px;text-align:center;color:var(--sub);font-family:'DM Mono';font-size:12px}
@media(max-width:760px){.plans{grid-template-columns:1fr 1fr}.chips{grid-template-columns:1fr 1fr}}
@media(max-width:480px){.plans{grid-template-columns:1fr}.title{font-size:27px}}
</style></head><body><div class="wrap">
<div class="top"><div class="logo">{% if logo %}<img src="{{logo}}" alt="logo">{% else %}🎮{% endif %}</div>
<div class="title">Robuks Generator<small>buy the gamepass on Roblox, then claim your key — we check the real sale ✨</small></div></div>
<div class="lab">Premium plans</div><div class="plans">
{% for pid,p in products.items() %}<div class="plan"><div class="tone {{p.tone}}"></div><div class="len">{{p.len}}</div>
<div class="nm">{{p.name}}</div><div class="price">{{p.robux}} <b>R$</b></div><div class="note">{{p.note or ""}}</div>
{% if p.gamepass %}<a class="buy" href="https://www.roblox.com/game-pass/{{p.gamepass}}" target="_blank">Buy on Roblox</a>
{% else %}<a class="buy" href="#claim">Claim below ↓</a>{% endif %}</div>{% endfor %}</div>
<div class="lab">Un-blacklist</div><div class="chips">
{% for u in unblacklist %}<div class="chip"><div class="cl">{{u.len}}</div><div class="cp">{{u.robux}} R$</div></div>{% endfor %}</div>
<div class="redeem"><h3>🔑 Claim your key</h3>
{% if step == 1 %}
<p>Enter your Roblox name and plan. We'll give you a quick code to prove the account is yours — stops anyone stealing your key.</p>
<form method="POST" action="/start"><label>Which plan?</label>
<select name="product" required>{% for pid,p in products.items() %}<option value="{{pid}}">{{p.name}} · {{p.len}} — {{p.robux}} R$</option>{% endfor %}</select>
<label>Your Roblox username</label><input name="username" placeholder="e.g. builderman" required autocomplete="off">
<button class="go" type="submit">Continue →</button></form>
{% elif step == 2 %}
<p>Step 2 — prove it's you. Put this code in your Roblox <b>About / Description</b>, save it, then hit verify:</p>
<div class="key">{{ code }}</div>
<div class="steps" style="margin-bottom:14px">Roblox → your profile → ✏️ → paste into "About" → Save. Then click below.</div>
<form method="POST" action="/claim">
  <input type="hidden" name="product" value="{{ s_product }}">
  <input type="hidden" name="uid" value="{{ s_uid }}">
  <input type="hidden" name="username" value="{{ s_username }}">
  <button class="go" type="submit">✅ I added it — verify &amp; get key</button>
</form>
<form method="POST" action="/newcode" style="margin-top:10px">
  <input type="hidden" name="product" value="{{ s_product }}">
  <input type="hidden" name="uid" value="{{ s_uid }}">
  <input type="hidden" name="username" value="{{ s_username }}">
  <button class="go" type="submit" style="background:#efe7f5;color:#6b5f83;box-shadow:3px 3px 0 #2a2140">🔄 Give me a different code</button>
</form>
{% else %}
<p>All done! 🎉</p>
{% endif %}
{% if result %}<div class="result {{result_class}}">{{result|safe}}
{% if key %}<span class="key">{{key}}</span><div class="steps">Discord: /activatekey key:{{key}}</div>{% endif %}</div>{% endif %}
</div><div class="foot">ROBUKS GENERATOR · bio-verified · keys single-use</div>
</div></body></html>"""

@app.route("/debug")
def debug():
    return {
        "cookie_present": bool(ROBLOX_COOKIE),
        "cookie_length": len(ROBLOX_COOKIE) if ROBLOX_COOKIE else 0,
        "cookie_starts_warning": ROBLOX_COOKIE.startswith("_|WARNING") if ROBLOX_COOKIE else False,
        "upstash_url_present": bool(REDIS_URL),
        "upstash_token_present": bool(REDIS_TOKEN),
        "authed_id": _authed_id() if ROBLOX_COOKIE else None,
    }, 200

@app.route("/debugtx")
def debugtx():
    """Debug: show what the transaction check sees. /debugtx?username=X&product=premiumunlimited"""
    username = request.args.get("username","").strip()
    product = request.args.get("product","premiumunlimited").strip()
    out = {"cookie_present": bool(ROBLOX_COOKIE)}
    seller = _authed_id()
    out["seller_id"] = seller
    if product in PRODUCTS:
        out["gamepass_id"] = PRODUCTS[product]["gamepass"]
    if username:
        uid, real = roblox_user_id(username)
        out["buyer_id"] = uid
        out["buyer_name"] = real
    # dump the first few raw sales so we can see the actual structure
    if seller:
        h = _headers()
        try:
            url = f"https://economy.roblox.com/v2/users/{seller}/transactions?transactionType=Sale&limit=10"
            r = _session.get(url, headers=h, timeout=12)
            out["sales_status"] = r.status_code
            data = r.json()
            out["sample_sales"] = [
                {"details": tx.get("details"), "agent": tx.get("agent"), "created": tx.get("created")}
                for tx in data.get("data", [])[:5]
            ]
        except Exception as ex:
            out["sales_error"] = str(ex)
    return out, 200

@app.route("/version")
def version():
    return "shop build=v15-jsondata", 200

@app.route("/testcreate")
def testcreate():
    """Test the Open Cloud create-gamepass call. /testcreate?name=Test&price=5"""
    name = request.args.get("name", "Robuks Test Pass")
    price = int(request.args.get("price", "5"))
    gpid, raw, err = create_gamepass(name, price)
    return {
        "api_key_present": bool(ROBLOX_API_KEY),
        "universe_id": UNIVERSE_ID,
        "created_gamepass_id": gpid,
        "error": err,
        "raw_response": raw,
        "note": "check Render logs for 🎟️ lines to see which format worked",
    }, 200

@app.route("/")
def home():
    return render_template_string(PAGE,products=PRODUCTS,unblacklist=UNBLACKLIST,logo=LOGO_URL,
                                  step=1, result=None)

# STEP 1: user enters username + plan -> we give them a bio code to add
@app.route("/start", methods=["POST"])
def start():
    product = request.form.get("product","").strip()
    username = request.form.get("username","").strip()
    def show(**kw):
        base = dict(products=PRODUCTS, unblacklist=UNBLACKLIST, logo=LOGO_URL, step=1, result=None)
        base.update(kw); return render_template_string(PAGE, **base)
    if product not in PRODUCTS: return show(result="❌ Unknown plan.", result_class="err")
    p = PRODUCTS[product]
    # (gamepass is created on-demand after bio-verify, so no pre-set check needed)
    if not username: return show(result="❌ Type your Roblox username.", result_class="err")
    uid, real = roblox_user_id(username)
    if not uid: return show(result=f"❌ Couldn't find '{username}'.", result_class="err")
    # (removed the old one-claim-per-account lock — renewals are allowed now,
    #  each purchase creates a fresh gamepass)
    # make a bio code, store it 15 min tied to this uid+product
    code = gen_bio_code()
    try:
        _redis("SET", f"biocode:{uid}:{product}", code, "EX", "900")
    except Exception:
        pass
    return render_template_string(PAGE, products=PRODUCTS, unblacklist=UNBLACKLIST, logo=LOGO_URL,
                                  step=2, code=code, s_product=product, s_username=real, s_uid=uid, result=None)

# STEP 2: user added the code to their bio -> verify bio, then purchase, then key
@app.route("/claim", methods=["POST"])
def claim():
    product = request.form.get("product","").strip()
    uid = request.form.get("uid","").strip()
    real = request.form.get("username","").strip()
    def back2(msg, cls):
        code = ""
        try: code = _redis("GET", f"biocode:{uid}:{product}") or ""
        except Exception: pass
        return render_template_string(PAGE, products=PRODUCTS, unblacklist=UNBLACKLIST, logo=LOGO_URL,
                                      step=2, code=code, s_product=product, s_username=real, s_uid=uid,
                                      result=msg, result_class=cls)
    def done(msg, cls, key=None, pid=None):
        return render_template_string(PAGE, products=PRODUCTS, unblacklist=UNBLACKLIST, logo=LOGO_URL,
                                      step=3, result=msg, result_class=cls, key=key, product_id=pid)
    if product not in PRODUCTS: return done("❌ Unknown plan.","err")
    p = PRODUCTS[product]

    # get the expected code
    try:
        want = _redis("GET", f"biocode:{uid}:{product}")
    except Exception:
        want = None
    if not want:
        return done("⌛ Your code expired. Please start again.","err")

    # 1) BIO CHECK — proves they own the Roblox account
    bio = roblox_bio(uid)
    if want.lower() not in bio.lower():
        return back2(f"❌ Couldn't find the code in your bio yet. Make sure you saved "
                     f"<b>{want}</b> in your Roblox 'About' / description, then try again.", "err")

    # 2) Get (or create) a UNIQUE gamepass for this user+plan, so renewals work.
    pass_key = f"pass:{uid}:{product}"
    try:
        existing = _redis("GET", pass_key)
    except Exception:
        existing = None

    if not existing:
        label = f"{p['name']} {p['len']} · {real}"[:50]
        gpid, raw, err = create_gamepass(label, p["robux"])
        if not gpid:
            return back2(f"⚠️ Couldn't set up your purchase right now ({err}). Try again in a moment.", "err")
        try:
            _redis("SET", pass_key, str(gpid))
        except Exception:
            pass
        return back2(f"✅ Bio verified! Your purchase is ready → "
                     f"<a href='https://www.roblox.com/game-pass/{gpid}' target='_blank'>"
                     f"<b>Buy {p['name']} · {p['len']} ({p['robux']} R$)</b></a> "
                     f"on Roblox, then come back and click verify again.", "ok")

    # 3) they have a pass assigned → check they now OWN it
    gpid = int(existing)
    if not owns_gamepass(uid, gpid):
        return back2(f"✅ Bio verified! Now buy your pass → "
                     f"<a href='https://www.roblox.com/game-pass/{gpid}' target='_blank'>"
                     f"<b>Buy {p['name']} · {p['len']} ({p['robux']} R$)</b></a> "
                     f"then click verify again.", "err")

    # both passed -> issue key. Clear pass mapping so a future renewal makes a NEW pass.
    key = gen_key()
    entry = json.dumps({"product":product,"used_by":None,"created":int(time.time()),
                        "roblox_id":uid,"roblox_name":real})
    try:
        _redis("SET", f"key:{key}", entry)
        _redis("DEL", f"biocode:{uid}:{product}")
        _redis("DEL", pass_key)
    except Exception as ex:
        print("store err",ex,flush=True); return done("⚠️ Couldn't reach the key store.","err")
    print(f"KEY ISSUED product={product} roblox={real}({uid}) key={key[:6]}… gp={gpid}",flush=True)
    return done(f"✅ Verified &amp; purchase confirmed for <b>{real}</b>! Here's your key:","ok",key=key,pid=product)

# retry with a fresh code
@app.route("/newcode", methods=["POST"])
def newcode():
    product = request.form.get("product","").strip()
    uid = request.form.get("uid","").strip()
    real = request.form.get("username","").strip()
    code = gen_bio_code()
    try: _redis("SET", f"biocode:{uid}:{product}", code, "EX", "900")
    except Exception: pass
    return render_template_string(PAGE, products=PRODUCTS, unblacklist=UNBLACKLIST, logo=LOGO_URL,
                                  step=2, code=code, s_product=product, s_username=real, s_uid=uid,
                                  result="🔄 Here's a fresh code — pop it in your bio and verify.",
                                  result_class="ok")

if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.getenv("PORT","8080")))

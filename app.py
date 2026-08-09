# 🛒 ROBUKS GENERATOR — SHOP (Flask + Upstash) — SECURE purchase detection
# via Roblox transaction history using a throwaway account cookie.
import os, json, time, secrets, string, datetime
import requests
from flask import Flask, request, render_template_string

app = Flask(__name__)
REDIS_URL    = os.getenv("UPSTASH_REDIS_REST_URL", "")
REDIS_TOKEN  = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")
ROBLOX_COOKIE= os.getenv("ROBLOX_COOKIE", "")
LOGO_URL     = os.getenv("LOGO_URL", "")
SALE_WINDOW  = int(os.getenv("SALE_WINDOW", str(7*24*3600)))

PRODUCTS = {
 "premium3day":     {"name":"Premium","len":"3 days","gamepass":0,"robux":50,"tone":"mint"},
 "premiumweek":     {"name":"Premium","len":"1 week","gamepass":0,"robux":100,"tone":"sky"},
 "premiummonth":    {"name":"Premium","len":"1 month","gamepass":0,"robux":300,"tone":"grape"},
 "premiumunlimited":{"name":"Premium","len":"Unlimited","gamepass":0,"robux":550,"tone":"sun","note":"or 1 server boost"},
 "premiumimmune":   {"name":"Premium + Immune","len":"Unlimited","gamepass":0,"robux":1000,"tone":"flame","note":"or 2 boosts · blacklist-immune"},
}
UNBLACKLIST=[{"len":"1 hour","robux":5},{"len":"1 day","robux":20},{"len":"1 week","robux":50},{"len":"Permanent","robux":150}]
KEY_CHARS=string.ascii_uppercase+string.digits+"!@#$%&*"

def _redis(*c):
    if not REDIS_URL or not REDIS_TOKEN: raise RuntimeError("no upstash")
    r=requests.post(REDIS_URL,headers={"Authorization":f"Bearer {REDIS_TOKEN}"},json=list(c),timeout=10)
    r.raise_for_status(); return r.json().get("result")
def gen_key(n=20): return "".join(secrets.choice(KEY_CHARS) for _ in range(n))

def roblox_user_id(u):
    try:
        r=requests.post("https://users.roblox.com/v1/usernames/users",
                        json={"usernames":[u],"excludeBannedUsers":False},timeout=10)
        d=r.json().get("data",[])
        if d: return d[0].get("id"),d[0].get("name")
    except Exception as ex: print("uid err",ex,flush=True)
    return None,None

_session=requests.Session()
def _headers():
    _session.cookies.set(".ROBLOSECURITY",ROBLOX_COOKIE,domain=".roblox.com")
    csrf=""
    try:
        r=_session.post("https://auth.roblox.com/v2/logout",timeout=10)
        csrf=r.headers.get("x-csrf-token","")
    except Exception as ex: print("csrf err",ex,flush=True)
    return {"X-CSRF-TOKEN":csrf,"Content-Type":"application/json"}
def _authed_id():
    try:
        r=_session.get("https://users.roblox.com/v1/users/authenticated",timeout=10)
        if r.status_code==200: return r.json().get("id")
    except Exception as ex: print("authed err",ex,flush=True)
    return None

def buyer_purchased(seller,buyer,gp):
    if not seller: return False,"cookie not logged in"
    h=_headers(); cursor=""; now=time.time()
    for _ in range(6):
        url=(f"https://economy.roblox.com/v2/users/{seller}/transactions"
             f"?transactionType=Sale&limit=100&cursor={cursor}")
        try: r=_session.get(url,headers=h,timeout=12)
        except Exception as ex: return False,f"fetch err {ex}"
        if r.status_code!=200: return False,f"status {r.status_code}"
        data=r.json()
        for tx in data.get("data",[]):
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
{% else %}<span class="buy off">coming soon</span>{% endif %}</div>{% endfor %}</div>
<div class="lab">Un-blacklist</div><div class="chips">
{% for u in unblacklist %}<div class="chip"><div class="cl">{{u.len}}</div><div class="cp">{{u.robux}} R$</div></div>{% endfor %}</div>
<div class="redeem"><h3>🔑 Claim your key</h3>
<p>Bought it? Enter your Roblox name — we verify the actual purchase, so only the real buyer gets the key.</p>
<form method="POST" action="/claim"><label>Which plan?</label>
<select name="product" required>{% for pid,p in products.items() %}<option value="{{pid}}">{{p.name}} · {{p.len}} — {{p.robux}} R$</option>{% endfor %}</select>
<label>Your Roblox username</label><input name="username" placeholder="e.g. builderman" required autocomplete="off">
<button class="go" type="submit">Verify purchase &amp; get key</button></form>
{% if result %}<div class="result {{result_class}}">{{result|safe}}
{% if key %}<span class="key">{{key}}</span><div class="steps">Discord: /activatekey product:{{product_id}} key:{{key}}</div>{% endif %}</div>{% endif %}
</div><div class="foot">ROBUKS GENERATOR · verified via real Roblox sales · keys single-use</div>
</div></body></html>"""

@app.route("/")
def home():
    return render_template_string(PAGE,products=PRODUCTS,unblacklist=UNBLACKLIST,logo=LOGO_URL,result=None)

@app.route("/claim",methods=["POST"])
def claim():
    product=request.form.get("product","").strip(); username=request.form.get("username","").strip()
    def show(m,c,key=None,pid=None):
        return render_template_string(PAGE,products=PRODUCTS,unblacklist=UNBLACKLIST,logo=LOGO_URL,result=m,result_class=c,key=key,product_id=pid)
    if product not in PRODUCTS: return show("❌ Unknown plan.","err")
    p=PRODUCTS[product]
    if not p["gamepass"]: return show("⚠️ This plan's gamepass isn't set up yet.","err")
    if not ROBLOX_COOKIE: return show("⚠️ Store not configured (no Roblox session).","err")
    if not username: return show("❌ Type your Roblox username.","err")
    uid,real=roblox_user_id(username)
    if not uid: return show(f"❌ Couldn't find '{username}'.","err")
    try:
        if _redis("GET",f"claim:{product}:{uid}"): return show("❌ This account already claimed a key for this plan.","err")
    except Exception: pass
    seller=_authed_id()
    ok,why=buyer_purchased(seller,uid,p["gamepass"])
    if not ok:
        print(f"denied uid={uid} product={product}: {why}",flush=True)
        return show(f"❌ No recent purchase of <b>{p['name']} · {p['len']}</b> found for <b>{real}</b>. If you just bought it, wait a minute and retry.","err")
    key=gen_key()
    entry=json.dumps({"product":product,"used_by":None,"created":int(time.time()),"roblox_id":uid,"roblox_name":real})
    try:
        _redis("SET",f"key:{key}",entry); _redis("SET",f"claim:{product}:{uid}",key)
    except Exception as ex:
        print("store err",ex,flush=True); return show("⚠️ Couldn't reach the key store.","err")
    print(f"KEY ISSUED product={product} roblox={real}({uid}) key={key[:6]}…",flush=True)
    return show(f"✅ Purchase verified for <b>{real}</b>! Here's your key:","ok",key=key,pid=product)

if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.getenv("PORT","8080")))

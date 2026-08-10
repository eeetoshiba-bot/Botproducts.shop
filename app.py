# 🛒 ROBUKS GENERATOR — SHOP (Flask + Upstash)
# Bot Premium (auto /activatekey) + Seller Deals (manual, DM owner).
# Auto-creates gamepasses via Roblox Open Cloud. Bio-code identity check.
import os, json, time, secrets, string, datetime
import requests
from flask import Flask, request, render_template_string

app = Flask(__name__)
REDIS_URL    = os.getenv("UPSTASH_REDIS_REST_URL", "")
REDIS_TOKEN  = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")
ROBLOX_API_KEY = os.getenv("ROBLOX_API_KEY", "")
UNIVERSE_ID    = os.getenv("UNIVERSE_ID", "3842120926")
LOGO_URL     = os.getenv("LOGO_URL", "")
OWNER_NAME   = "kiwi_brown_dog"

# Bot Premium — auto-activated with /activatekey
PRODUCTS = {
 "premium3day":     {"name":"Premium","len":"3 days","robux":1,"tone":"mint"},
 "premiumweek":     {"name":"Premium","len":"1 week","robux":2,"tone":"sky"},
 "premiummonth":    {"name":"Premium","len":"1 month","robux":3,"tone":"grape"},
 "premiumunlimited":{"name":"Premium","len":"Unlimited","robux":4,"tone":"sun","note":"or 1 server boost"},
 "premiumimmune":   {"name":"Premium + Immune","len":"Unlimited","robux":5,"tone":"flame","note":"or 2 boosts · blacklist-immune"},
}
# Seller Deals — manual fulfilment (DM owner with the key)
SELLER_DEALS = {
 "nitro1mo": {"name":"Discord Nitro","len":"1 Month Basic","robux":1000,"tone":"grape",
              "note":"DM " + OWNER_NAME + " with your key to claim"},
}
UNBLACKLIST=[{"len":"1 hour","robux":5},{"len":"1 day","robux":20},{"len":"1 week","robux":50},{"len":"Permanent","robux":150}]
KEY_CHARS=string.ascii_uppercase+string.digits+"!@#$%&*"

def catalog(kind): return PRODUCTS if kind=="premium" else SELLER_DEALS

def _redis(*c):
    if not REDIS_URL or not REDIS_TOKEN: raise RuntimeError("no upstash")
    r=requests.post(REDIS_URL,headers={"Authorization":f"Bearer {REDIS_TOKEN}"},json=list(c),timeout=10)
    r.raise_for_status(); return r.json().get("result")
def gen_key(n=20): return "".join(secrets.choice(KEY_CHARS) for _ in range(n))

_WORDS=["unicorn","friends","dragon","cookie","rocket","banana","pixel","ninja","turbo","galaxy",
        "noodle","waffle","cactus","pickle","zebra","comet","donut","llama","mango","panda",
        "robot","sunny","tiger","viper","wizard","yeti","bubble","cloud"]
def gen_bio_code():
    n=secrets.choice([2,2,3]); w="".join(secrets.choice(_WORDS) for _ in range(n))
    if secrets.choice([True,False]): w+=str(secrets.randbelow(900)+100)
    return w
def roblox_bio(uid):
    try:
        r=requests.get(f"https://users.roblox.com/v1/users/{uid}",timeout=10)
        if r.status_code==200: return r.json().get("description","") or ""
    except Exception as ex: print("bio err",ex,flush=True)
    return ""
def roblox_user_id(u):
    try:
        r=requests.post("https://users.roblox.com/v1/usernames/users",
                        json={"usernames":[u],"excludeBannedUsers":False},timeout=10)
        d=r.json().get("data",[])
        if d: return d[0].get("id"),d[0].get("name")
    except Exception as ex: print("uid err",ex,flush=True)
    return None,None
def owns_gamepass(uid,gp):
    try:
        r=requests.get(f"https://inventory.roblox.com/v1/users/{uid}/items/GamePass/{gp}",timeout=10)
        print(f"🔎 ownership uid={uid} gp={gp} status={r.status_code}",flush=True)
        if r.status_code!=200: return False
        return len(r.json().get("data",[]))>0
    except Exception as ex: print("owns err",ex,flush=True); return False

def create_gamepass(display_name, price):
    """Create a gamepass via Open Cloud. Tries formats, uses whichever works."""
    if not ROBLOX_API_KEY: return None,"no api key"
    safe="".join(c for c in display_name if c.isalnum() or c in " -_"); safe=" ".join(safe.split())[:45] or "Pass"
    url=f"https://apis.roblox.com/game-passes/v1/universes/{UNIVERSE_ID}/game-passes"
    K=ROBLOX_API_KEY
    body={"Name":safe,"Description":"Premium pass","Price":int(price),"IsForSale":True}
    attempts=[
        ("multipart-request",{"headers":{"x-api-key":K},"files":{"request":(None,json.dumps(body),"application/json")}}),
        ("multipart-fields",{"headers":{"x-api-key":K},"files":{"Name":(None,safe),"Description":(None,"Premium pass"),"Price":(None,str(int(price))),"IsForSale":(None,"true")}}),
        ("json",{"headers":{"x-api-key":K,"Content-Type":"application/json"},"json":body}),
    ]
    last=None
    for label,kw in attempts:
        try:
            r=requests.post(url,timeout=20,**kw); last=r
            print(f"🎟️ [{label}] status={r.status_code} body={r.text[:200]}",flush=True)
            if r.status_code in (200,201):
                d=r.json(); gid=d.get("gamePassId") or d.get("id")
                print(f"🎟️ ✅ WINNER=[{label}] id={gid}",flush=True)
                return gid,None
        except Exception as ex: print(f"🎟️ [{label}] err {ex}",flush=True)
    return None,f"status {last.status_code if last else '?'}"

TONES={"mint":"#33e6a6","sky":"#3fb9ff","grape":"#a06bff","sun":"#ffcb3a","flame":"#ff7a5c"}

PAGE=r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Robuks Generator — Shop</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Fredoka:wght@500;600;700&family=Baloo+2:wght@600;700;800&family=DM+Mono:wght@500&display=swap');
:root{--bg:#fff4e6;--bg2:#ffe9cf;--ink:#2a2140;--sub:#7c6f92;--card:#fff;--edge:#2a2140;--mint:#33e6a6;--sky:#3fb9ff;--grape:#a06bff;--sun:#ffcb3a;--flame:#ff7a5c;--shadow:6px 6px 0 #2a2140}
*{box-sizing:border-box;margin:0;padding:0}
body{background:radial-gradient(circle at 12% 8%,#ffd9a8 0 12px,transparent 13px) 0 0/64px 64px,linear-gradient(180deg,var(--bg),var(--bg2));font-family:'Fredoka',system-ui,sans-serif;color:var(--ink);min-height:100vh;padding:30px 16px 80px}
::selection{background:var(--sun)}.wrap{max-width:980px;margin:0 auto}
.top{display:flex;align-items:center;gap:16px;margin-bottom:18px}
.logo{width:60px;height:60px;border-radius:18px;border:3px solid var(--edge);box-shadow:var(--shadow);background:var(--sun);display:grid;place-items:center;font-size:30px;overflow:hidden;flex:none}
.logo img{width:100%;height:100%;object-fit:cover}
.title{font-family:'Baloo 2';font-weight:800;font-size:30px;line-height:1}
.title small{display:block;font-family:'Fredoka';font-weight:600;font-size:13px;color:var(--sub);margin-top:5px}
.tabs{display:flex;gap:10px;margin-bottom:26px}
.tab{flex:1;text-align:center;padding:13px;border:3px solid var(--edge);border-radius:16px;background:var(--card);
  font-family:'Baloo 2';font-weight:800;font-size:16px;color:var(--ink);text-decoration:none;box-shadow:4px 4px 0 #2a2140;transition:.1s}
.tab.active{background:linear-gradient(90deg,var(--mint),var(--sky))}
.tab:hover{transform:translate(-1px,-1px);box-shadow:6px 6px 0 #2a2140}
.lab{font-family:'Baloo 2';font-weight:800;font-size:20px;margin:26px 0 14px;display:flex;align-items:center;gap:10px}
.lab::after{content:"";flex:1;height:3px;background:repeating-linear-gradient(90deg,var(--edge) 0 10px,transparent 10px 18px);opacity:.35;border-radius:3px}
.plans{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}
.card{background:var(--card);border:3px solid var(--edge);border-radius:20px;box-shadow:var(--shadow);padding:16px;display:flex;flex-direction:column;gap:5px}
.tone{width:100%;height:9px;border-radius:20px;border:2px solid var(--edge);margin-bottom:7px}
.card .len{font-family:'Baloo 2';font-weight:800;font-size:18px}.card .nm{color:var(--sub);font-size:12px;font-weight:600;margin-top:-2px}
.price{font-family:'Baloo 2';font-weight:800;font-size:23px;margin:6px 0 2px}.price b{font-size:13px;color:var(--sub)}
.note{font-size:11px;color:var(--sub);min-height:14px;line-height:1.3}
.pick{margin-top:10px;text-align:center;padding:10px;border-radius:13px;border:3px solid var(--edge);
  background:var(--sun);color:var(--edge);font-weight:700;font-family:'Baloo 2';font-size:14px;cursor:pointer;
  box-shadow:3px 3px 0 #2a2140;transition:.1s;text-decoration:none;display:block}
.pick:hover{transform:translate(-1px,-1px);box-shadow:5px 5px 0 #2a2140}
.chips{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.chip{background:var(--card);border:3px solid var(--edge);border-radius:16px;box-shadow:4px 4px 0 #2a2140;padding:12px 10px;text-align:center}
.chip .cl{font-family:'Baloo 2';font-weight:800;font-size:15px}.chip .cp{font-family:'DM Mono';color:var(--flame);margin-top:2px;font-size:14px}
.redeem{margin-top:30px;background:var(--card);border:3px solid var(--edge);border-radius:22px;box-shadow:var(--shadow);padding:22px}
.redeem h3{font-family:'Baloo 2';font-weight:800;font-size:20px;margin-bottom:4px}.redeem p{color:var(--sub);font-size:13px;margin-bottom:12px}
label{display:block;font-weight:600;font-size:13px;margin:10px 0 6px}
input{width:100%;padding:12px 14px;border:3px solid var(--edge);border-radius:14px;background:#fffaf0;color:var(--ink);font-family:'Fredoka';font-weight:600;font-size:15px}
input:focus{outline:none;box-shadow:3px 3px 0 var(--grape)}
.go{margin-top:16px;width:100%;padding:14px;border:3px solid var(--edge);border-radius:15px;background:linear-gradient(90deg,var(--mint),var(--sky));color:var(--edge);font-family:'Baloo 2';font-weight:800;font-size:16px;cursor:pointer;box-shadow:5px 5px 0 #2a2140;transition:.1s;text-decoration:none;display:block;text-align:center}
.go:hover{transform:translate(-2px,-2px);box-shadow:7px 7px 0 #2a2140}
.chosen{background:#f6f0ff;border:3px solid var(--edge);border-radius:14px;padding:12px 14px;margin-bottom:6px;font-weight:600;font-size:14px}
.result{margin-top:16px;padding:15px;border-radius:15px;font-size:14px;line-height:1.5;border:3px solid var(--edge)}
.ok{background:#e3fff4}.err{background:#ffe7e7}
.key{font-family:'DM Mono';font-size:18px;color:var(--grape);letter-spacing:1px;word-break:break-all;display:block;margin:10px 0;background:#f6f0ff;border:2px dashed var(--grape);border-radius:12px;padding:12px;text-align:center}
.steps{font-family:'DM Mono';font-size:12px;color:var(--sub);margin-top:4px}
.foot{margin-top:30px;text-align:center;color:var(--sub);font-family:'DM Mono';font-size:11px}
@media(max-width:760px){.plans{grid-template-columns:1fr 1fr}.chips{grid-template-columns:1fr 1fr}}
@media(max-width:480px){.plans{grid-template-columns:1fr}.title{font-size:25px}}
</style></head><body><div class="wrap">
<div class="top"><div class="logo">{% if logo %}<img src="{{logo}}" alt="logo">{% else %}🎮{% endif %}</div>
<div class="title">Robuks Generator<small>secure keys · auto-verified · instant delivery ✨</small></div></div>

<div class="tabs">
  <a class="tab {% if tab=='premium' %}active{% endif %}" href="/?tab=premium">💎 Bot Premium</a>
  <a class="tab {% if tab=='seller' %}active{% endif %}" href="/?tab=seller">🛍️ Seller Deals</a>
</div>

{% if step == 1 %}
<div class="lab">{% if tab=='premium' %}Premium plans{% else %}Seller deals{% endif %}</div>
<div class="plans">
{% for pid,p in items.items() %}
<div class="card"><div class="tone" style="background:{{ tones[p.tone] }}"></div>
<div class="len">{{p.len}}</div><div class="nm">{{p.name}}</div>
<div class="price">{{p.robux}} <b>R$</b></div><div class="note">{{p.note or ""}}</div>
<a class="pick" href="/start?tab={{tab}}&product={{pid}}">Select →</a></div>
{% endfor %}
</div>
{% if tab=='premium' %}
<div class="lab">Un-blacklist</div>
<div class="chips">{% for u in unblacklist %}<div class="chip"><div class="cl">{{u.len}}</div><div class="cp">{{u.robux}} R$</div></div>{% endfor %}</div>
{% endif %}

<div class="redeem" id="claim"><h3>🔑 How it works</h3>
<p>Tap <b>Select</b> on a plan above. We'll verify your Roblox account with a quick bio code, then you buy &amp; get your key.
{% if tab=='seller' %} Seller deals are delivered by DM — you'll get a key to send to {{owner}}.{% endif %}</p></div>

{% elif step == 'name' %}
<div class="redeem"><h3>🔑 {{p.name}} · {{p.len}}</h3>
<div class="chosen">Selected: <b>{{p.name}} · {{p.len}}</b> — {{p.robux}} R$</div>
<p>Enter your Roblox username so we can verify it's really you.</p>
<form method="POST" action="/getcode">
  <input type="hidden" name="tab" value="{{tab}}"><input type="hidden" name="product" value="{{product}}">
  <label>Your Roblox username</label><input name="username" placeholder="e.g. builderman" required autocomplete="off">
  <button class="go" type="submit">Continue →</button>
</form></div>

{% elif step == 2 %}
<div class="redeem"><h3>🔑 Prove it's you</h3>
<p>Put this code in your Roblox <b>About / Description</b>, save it, then verify:</p>
<div class="key">{{ code }}</div>
<div class="steps" style="margin-bottom:12px">Roblox → profile → ✏️ → paste into "About" → Save.</div>
<form method="POST" action="/claim">
  <input type="hidden" name="tab" value="{{tab}}"><input type="hidden" name="product" value="{{s_product}}">
  <input type="hidden" name="uid" value="{{s_uid}}"><input type="hidden" name="username" value="{{s_username}}">
  <button class="go" type="submit">✅ I added it — continue</button>
</form>
<form method="POST" action="/newcode" style="margin-top:10px">
  <input type="hidden" name="tab" value="{{tab}}"><input type="hidden" name="product" value="{{s_product}}">
  <input type="hidden" name="uid" value="{{s_uid}}"><input type="hidden" name="username" value="{{s_username}}">
  <button class="go" type="submit" style="background:#efe7f5;color:#6b5f83;box-shadow:3px 3px 0 #2a2140">🔄 Different code</button>
</form></div>

{% elif step == 'buy' %}
<div class="redeem"><h3>🛒 Buy your pass</h3>
<p>✅ Identity verified! Buy the pass on Roblox, then come back and verify.</p>
<a class="go" href="https://www.roblox.com/game-pass/{{gpid}}" target="_blank" style="background:var(--sun);margin-bottom:12px">🛒 Buy on Roblox</a>
<form method="POST" action="/claim">
  <input type="hidden" name="tab" value="{{tab}}"><input type="hidden" name="product" value="{{s_product}}">
  <input type="hidden" name="uid" value="{{s_uid}}"><input type="hidden" name="username" value="{{s_username}}">
  <button class="go" type="submit">✅ I bought it — verify &amp; get my key</button>
</form></div>

{% else %}
<div class="redeem"><h3>🎉 Done!</h3></div>
{% endif %}

{% if result %}<div class="result {{result_class}}">{{result|safe}}
{% if key %}<span class="key">{{key}}</span>
{% if tab=='seller' %}<div class="steps">DM <b>{{owner}}</b> on Discord with this key to claim your {{pname}}.</div>
{% else %}<div class="steps">Discord: /activatekey key:{{key}}</div>{% endif %}{% endif %}</div>{% endif %}

<div class="foot">ROBUKS GENERATOR · keys single-use</div>
</div></body></html>"""

def render(**kw):
    base=dict(products=PRODUCTS,unblacklist=UNBLACKLIST,logo=LOGO_URL,tones=TONES,owner=OWNER_NAME,
              tab="premium",step=1,items=PRODUCTS,result=None,key=None)
    base.update(kw); return render_template_string(PAGE,**base)

@app.route("/version")
def version(): return "shop build=v19-tabs", 200

@app.route("/")
def home():
    tab=request.args.get("tab","premium")
    if tab not in ("premium","seller"): tab="premium"
    return render(tab=tab, step=1, items=catalog(tab))

@app.route("/start")
def start():
    tab=request.args.get("tab","premium"); product=request.args.get("product","")
    cat=catalog(tab)
    if product not in cat: return render(tab=tab,step=1,items=cat,result="❌ Unknown plan.",result_class="err")
    return render(tab=tab,step="name",items=cat,product=product,p=cat[product])

@app.route("/getcode",methods=["POST"])
def getcode():
    tab=request.form.get("tab","premium"); product=request.form.get("product","")
    username=request.form.get("username","").strip(); cat=catalog(tab)
    if product not in cat: return render(tab=tab,step=1,items=cat,result="❌ Unknown plan.",result_class="err")
    p=cat[product]
    if not username: return render(tab=tab,step="name",items=cat,product=product,p=p,result="❌ Type your username.",result_class="err")
    uid,real=roblox_user_id(username)
    if not uid: return render(tab=tab,step="name",items=cat,product=product,p=p,result=f"❌ Couldn't find '{username}'.",result_class="err")
    code=gen_bio_code()
    try: _redis("SET",f"biocode:{uid}:{product}",code,"EX","900")
    except Exception: pass
    return render(tab=tab,step=2,items=cat,code=code,s_product=product,s_username=real,s_uid=uid)

@app.route("/newcode",methods=["POST"])
def newcode():
    tab=request.form.get("tab","premium"); product=request.form.get("product","")
    uid=request.form.get("uid",""); real=request.form.get("username","")
    code=gen_bio_code()
    try: _redis("SET",f"biocode:{uid}:{product}",code,"EX","900")
    except Exception: pass
    return render(tab=tab,step=2,items=catalog(tab),code=code,s_product=product,s_username=real,s_uid=uid,
                  result="🔄 Fresh code — add it to your bio and verify.",result_class="ok")

@app.route("/claim",methods=["POST"])
def claim():
    tab=request.form.get("tab","premium"); product=request.form.get("product","")
    uid=request.form.get("uid","").strip(); real=request.form.get("username","").strip()
    cat=catalog(tab)
    if product not in cat: return render(tab=tab,step="done",result="❌ Unknown plan.",result_class="err")
    p=cat[product]
    def back2(msg,cls):
        return render(tab=tab,step=2,items=cat,code=(_safe_code(uid,product)),
                      s_product=product,s_username=real,s_uid=uid,result=msg,result_class=cls)
    def buystage(gpid,msg=None,cls=None):
        return render(tab=tab,step="buy",items=cat,gpid=gpid,s_product=product,s_username=real,s_uid=uid,
                      result=msg,result_class=cls)
    # bio check
    try: want=_redis("GET",f"biocode:{uid}:{product}")
    except Exception: want=None
    if not want: return render(tab=tab,step="done",result="⌛ Code expired — please start again.",result_class="err")
    bio=roblox_bio(uid)
    if want.lower() not in bio.lower():
        return back2(f"❌ Couldn't find <b>{want}</b> in your bio yet. Add it in Roblox 'About', save, then verify.","err")
    # get/create gamepass
    pass_key=f"pass:{uid}:{product}:{tab}"
    try: existing=_redis("GET",pass_key)
    except Exception: existing=None
    if not existing:
        gpid,err=create_gamepass(f"{p['name']} {p['len']} {real}",p["robux"])
        if not gpid: return back2(f"⚠️ Couldn't set up your purchase ({err}). Try again in a moment.","err")
        try: _redis("SET",pass_key,str(gpid))
        except Exception: pass
        return buystage(gpid)
    gpid=int(existing)
    if not owns_gamepass(uid,gpid):
        return buystage(gpid,"❌ You don't own the pass yet — buy it, then verify.","err")
    # issue key (store metadata for /keylookup)
    key=gen_key()
    entry=json.dumps({"kind":tab,"product":product,"product_name":f"{p['name']} {p['len']}",
                      "used_by":None,"created":int(time.time()),"roblox_id":uid,"roblox_name":real})
    try:
        _redis("SET",f"key:{key}",entry)
        _redis("DEL",f"biocode:{uid}:{product}"); _redis("DEL",pass_key)
    except Exception as ex:
        print("store err",ex,flush=True); return render(tab=tab,step="done",result="⚠️ Key store error.",result_class="err")
    # notify owner for seller deals (bot watches this list)
    if tab=="seller":
        try: _redis("RPUSH","sellerorders",json.dumps({"key":key,"product":f"{p['name']} {p['len']}","roblox":real,"ts":int(time.time())}))
        except Exception: pass
    print(f"KEY ISSUED kind={tab} product={product} roblox={real}({uid}) key={key[:6]}…",flush=True)
    if tab=="seller":
        msg=f"✅ Purchase verified for <b>{real}</b>! Here's your <b>{p['name']} · {p['len']}</b> key:"
    else:
        msg=f"✅ Verified for <b>{real}</b>! Here's your key:"
    return render(tab=tab,step="done",result=msg,result_class="ok",key=key,pname=f"{p['name']} {p['len']}")

def _safe_code(uid,product):
    try: return _redis("GET",f"biocode:{uid}:{product}") or ""
    except Exception: return ""

if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.getenv("PORT","8080")))

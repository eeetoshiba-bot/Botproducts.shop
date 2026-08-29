# 🛒 ROBUKS GENERATOR — SHOP (Flask + Upstash)
# Bot Premium (auto /activatekey) + Seller Deals (manual, DM owner).
# Auto-creates gamepasses via Roblox Open Cloud. Bio-code identity check.
import os, json, time, secrets, string, datetime
import requests
from flask import Flask, request, render_template_string, session, redirect

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", secrets.token_hex(32))  # for login sessions
app.permanent_session_lifetime = datetime.timedelta(days=30)  # stay logged in 30 days
@app.before_request
def _make_session_permanent():
    session.permanent = True
# ---- Email sending (works on Render via HTTPS APIs) ----
RESEND_KEY   = os.getenv("RESEND_KEY", "")        # Resend API key (starts re_)
RESEND_SENDER= os.getenv("RESEND_SENDER", "onboarding@resend.dev")  # Resend test sender works instantly
BREVO_KEY    = os.getenv("BREVO_KEY", "")         # Brevo API key (backup)
BREVO_SENDER = os.getenv("BREVO_SENDER", "")
# legacy SMTP (kept as fallback if you ever move hosts)
SMTP_EMAIL   = os.getenv("SMTP_EMAIL", "")
SMTP_PASS    = os.getenv("SMTP_PASS", "")
SMTP_HOST    = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT    = int(os.getenv("SMTP_PORT", "587"))
REDIS_URL    = os.getenv("UPSTASH_REDIS_REST_URL", "")
REDIS_TOKEN  = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")
ROBLOX_API_KEY = os.getenv("ROBLOX_API_KEY", "")
UNIVERSE_ID    = os.getenv("UNIVERSE_ID", "34574007")
LOGO_URL     = os.getenv("LOGO_URL", "")
OWNER_NAME   = "kiwi_brown_dog"
PAYPAL_ME    = os.getenv("PAYPAL_ME", "RalseiPlush")   # paypal.me/RalseiPlush (env can override)
# ---- PayPal email-reading detection (no Business API needed) ----
PP_EMAIL     = os.getenv("PP_EMAIL", "")        # the Gmail that receives PayPal receipts
PP_EMAIL_PASS= os.getenv("PP_EMAIL_PASS", "")   # Gmail App Password (not your normal password)
PP_IMAP_HOST = os.getenv("PP_IMAP_HOST", "imap.gmail.com")
# rough Robux -> USD for showing a PayPal price (Robux ÷ this = $). ~100 R$ ≈ $1 by default.
RBX_PER_USD  = int(os.getenv("RBX_PER_USD", "200"))   # 200 R$ = $1  (so 100 R$ = $0.50)

# Bot Premium — auto-activated with /activatekey. 'pid' = stock product id.
PRODUCTS = {
 "premium3day":     {"pid":"p1","name":"Premium","len":"3 days","robux":50,"tone":"mint"},
 "premiumweek":     {"pid":"p2","name":"Premium","len":"1 week","robux":100,"tone":"sky"},
 "premiummonth":    {"pid":"p3","name":"Premium","len":"1 month","robux":300,"tone":"grape"},
 "premiumunlimited":{"pid":"p4","name":"Premium","len":"Unlimited","robux":550,"tone":"sun","note":"or 1 server boost"},
 "premiumimmune":   {"pid":"p5","name":"Premium + Immune","len":"Unlimited","robux":1000,"tone":"flame","note":"or 2 boosts · blacklist-immune"},
}
# Seller Deals — manual fulfilment (DM owner with the key)
SELLER_DEALS = {
 "nitro1mo":   {"pid":"s1","name":"Discord Nitro","len":"1 Month Basic","robux":500,"tone":"grape",
                "note":"DM " + OWNER_NAME + " with your key to claim"},
 "distro900k": {"pid":"s2","name":"DistroKid Upload","len":"Under 900k views","robux":50,"tone":"mint",
                "note":"upload your audio · DM " + OWNER_NAME + " with your key"},
 "distro9m":   {"pid":"s3","name":"DistroKid Upload","len":"Under 9M views","robux":200,"tone":"sky",
                "note":"upload your audio · DM " + OWNER_NAME + " with your key"},
 "robloxscripting": {"pid":"s4","name":"the person will make scripts that are for EXPLOITS only!!","len":"Roblox exploits script maker","robux":100,"tone":"flame", "note":"DM ultra109.yeh with your key to claim"},
 "game thumbnail": {"pid":"s5","name":"have the user create your art for your roblox game thumbnail","len":"Game thumbnail","robux":100,"tone":"flame", "note":"DM absolute_cyn.ema with your key to claim"},
}
UNBLACKLIST=[{"len":"1 hour","robux":5},{"len":"1 day","robux":20},{"len":"1 week","robux":50},{"len":"Permanent","robux":150}]
KEY_CHARS=string.ascii_uppercase+string.digits+"!@#$%&*"

def catalog(kind): return PRODUCTS if kind=="premium" else SELLER_DEALS

def get_stock(pid):
    """Current stock for a product id (default 0)."""
    try:
        v = _redis("GET", f"stock:{pid}")
        return int(v) if v is not None else 0
    except Exception:
        return 0

def dec_stock(pid):
    """Reduce stock by 1 (after a successful purchase)."""
    try:
        _redis("DECR", f"stock:{pid}")
    except Exception:
        pass

def _redis(*c):
    if not REDIS_URL or not REDIS_TOKEN: raise RuntimeError("no upstash")
    r=requests.post(REDIS_URL,headers={"Authorization":f"Bearer {REDIS_TOKEN}"},json=list(c),timeout=10)
    r.raise_for_status(); return r.json().get("result")
def gen_key(n=20): return "".join(secrets.choice(KEY_CHARS) for _ in range(n))

# ================================================================
#  🔐 LOGIN / ACCOUNTS / BALANCE
#  accounts stored in Upstash:
#    acct:{email}      -> {"email","username","balance","created"}
#    acctname:{uname}  -> email   (so bot can credit by username)
#    logincode:{email} -> 6-digit code (EX 600)
# ================================================================
def send_email(to_addr, subject, body):
    """Send email via Resend (easiest on Render), then Brevo, then SMTP."""
    # --- Resend API (works instantly with onboarding@resend.dev sender) ---
    if RESEND_KEY:
        try:
            r = requests.post("https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {RESEND_KEY}", "Content-Type": "application/json"},
                json={"from": RESEND_SENDER, "to": [to_addr], "subject": subject, "text": body},
                timeout=15)
            if r.status_code in (200, 201, 202):
                return True, None
            print(f"resend err {r.status_code}: {r.text[:250]}", flush=True)
            # fall through to try other providers
        except Exception as ex:
            print(f"resend exc: {ex}", flush=True)
    # --- Brevo API ---
    if BREVO_KEY and BREVO_SENDER:
        try:
            r = requests.post("https://api.brevo.com/v3/smtp/email",
                headers={"api-key": BREVO_KEY, "Content-Type": "application/json", "accept": "application/json"},
                json={
                    "sender": {"email": BREVO_SENDER, "name": "Robuks Generator"},
                    "to": [{"email": to_addr}],
                    "subject": subject,
                    "textContent": body,
                }, timeout=15)
            if r.status_code in (200, 201, 202):
                return True, None
            print(f"brevo err {r.status_code}: {r.text[:200]}", flush=True)
            return False, f"brevo {r.status_code}"
        except Exception as ex:
            print(f"brevo exc: {ex}", flush=True)
            return False, str(ex)
    # --- SMTP fallback (only works off Render) ---
    if SMTP_EMAIL and SMTP_PASS:
        import smtplib
        from email.mime.text import MIMEText
        try:
            msg = MIMEText(body)
            msg["Subject"] = subject; msg["From"] = SMTP_EMAIL; msg["To"] = to_addr
            s = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15)
            s.starttls(); s.login(SMTP_EMAIL, SMTP_PASS)
            s.sendmail(SMTP_EMAIL, [to_addr], msg.as_string()); s.quit()
            return True, None
        except Exception as ex:
            print(f"smtp err: {ex}", flush=True)
            return False, str(ex)
    return False, "no email service configured"

def get_account(email):
    try:
        raw = _redis("GET", f"acct:{email.lower()}")
        return json.loads(raw) if raw else None
    except Exception:
        return None

def save_account(acct):
    try:
        _redis("SET", f"acct:{acct['email'].lower()}", json.dumps(acct))
        if acct.get("username"):
            _redis("SET", f"acctname:{acct['username'].lower()}", acct["email"].lower())
    except Exception as ex:
        print("save acct err", ex, flush=True)

def current_user():
    email = session.get("email")
    return get_account(email) if email else None

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

def check_paypal_email(expected_usd, note_contains):
    """Scan the PayPal inbox for a recent payment matching amount + a note (e.g. username).
    Returns (found, reason). Reads PayPal receipt emails — no Business API needed."""
    if not PP_EMAIL or not PP_EMAIL_PASS:
        return False, "email not configured"
    import imaplib, email as emaillib
    from email.header import decode_header
    try:
        M = imaplib.IMAP4_SSL(PP_IMAP_HOST)
        M.login(PP_EMAIL, PP_EMAIL_PASS)
        M.select("INBOX")
        typ, data = M.search(None, '(FROM "paypal" UNSEEN)')
        ids = data[0].split()
        found = False
        for num in ids[-25:][::-1]:
            typ, msg_data = M.fetch(num, "(RFC822)")
            msg = emaillib.message_from_bytes(msg_data[0][1])
            subj = ""
            for part, enc in decode_header(msg.get("Subject", "")):
                subj += part.decode(enc or "utf-8", "ignore") if isinstance(part, bytes) else str(part)
            body = ""
            if msg.is_multipart():
                for p in msg.walk():
                    if p.get_content_type() in ("text/plain", "text/html"):
                        try: body += p.get_payload(decode=True).decode("utf-8", "ignore")
                        except Exception: pass
            else:
                try: body = msg.get_payload(decode=True).decode("utf-8", "ignore")
                except Exception: pass
            blob = (subj + " " + body).lower()
            amt = f"{expected_usd:.2f}"
            got_money = any(x in blob for x in ("you received", "you've got money", "sent you", "payment received"))
            if got_money and amt in blob and note_contains.lower() in blob:
                found = True
                M.store(num, '+FLAGS', '\\Seen')
                break
        M.logout()
        return found, ("match" if found else "no matching email yet")
    except Exception as ex:
        print(f"paypal email err: {ex}", flush=True)
        return False, str(ex)
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
<div class="title">Robuks Generator<small>secure keys · auto-verified · instant delivery ✨</small></div>
<a href="{% if user %}/account{% else %}/login{% endif %}" style="margin-left:auto;padding:10px 16px;border:3px solid #2a2140;border-radius:14px;background:{% if user %}#e3fff4{% else %}#ffcb3a{% endif %};color:#2a2140;font-family:'Baloo 2';font-weight:800;font-size:14px;text-decoration:none;box-shadow:3px 3px 0 #2a2140;white-space:nowrap">
{% if user %}👤 {{ user.username }} · ${{ '%.2f'|format(user.balance) }}{% else %}🔐 Login{% endif %}</a></div>

<div class="tabs">
  <a class="tab {% if tab=='premium' %}active{% endif %}" href="/?tab=premium">💎 Bot Premium</a>
  <a class="tab {% if tab=='seller' %}active{% endif %}" href="/?tab=seller">🛍️ Seller Deals</a>
  <a class="tab" href="https://discord.gg/JS7AQrwbKS" target="_blank">💬 Join Discord</a>
</div>

{% if user %}
<div style="margin-bottom:22px;padding:14px 20px;border:3px solid #2a2140;border-radius:16px;
  background:linear-gradient(90deg,#33e6a6,#3fb9ff);box-shadow:4px 4px 0 #2a2140;display:flex;
  align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px">
  <span style="font-family:'Baloo 2';font-weight:800;font-size:17px;color:#2a2140">
    👋 Hi {{ user.username }}!</span>
  <span style="font-family:'Baloo 2';font-weight:800;font-size:19px;color:#2a2140">
    💰 Balance: ${{ '%.2f'|format(user.balance) }}</span>
</div>
{% endif %}

{% if step == 1 %}
<div class="lab">{% if tab=='premium' %}Premium plans{% else %}Seller deals{% endif %}</div>
<div class="plans">
{% for pid,p in items.items() %}
<div class="card"><div class="tone" style="background:{{ tones[p.tone] }}"></div>
<div class="len">{{p.len}}</div><div class="nm">{{p.name}}</div>
<div class="price">{{p.robux}} <b>R$</b></div><div class="note">{{p.note or ""}}</div>
<div class="note" style="font-family:'DM Mono';color:{% if stock.get(pid,0)>0 %}#1c9c5e{% else %}#c0392b{% endif %}">
  {% if stock.get(pid,0)>0 %}📦 {{ stock[pid] }} in stock{% else %}❌ Out of stock{% endif %}</div>
{% if stock.get(pid,0)>0 %}<a class="pick" href="/start?tab={{tab}}&product={{pid}}">Select →</a>
{% else %}<span class="pick" style="background:#efe7f5;color:#a99cbf;box-shadow:none;cursor:not-allowed">Out of stock</span>{% endif %}</div>
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
<p>Enter your Roblox username so we can verify it's really you (Robux payment — instant key).</p>
<form method="POST" action="/getcode">
  <input type="hidden" name="tab" value="{{tab}}"><input type="hidden" name="product" value="{{product}}">
  <label>Your Roblox username</label><input name="username" placeholder="e.g. builderman" required autocomplete="off">
  <button class="go" type="submit">Continue with Robux →</button>
</form>

{% if paypal %}
<div style="margin-top:16px;padding:14px;border:3px dashed var(--edge);border-radius:14px;background:#f0f6ff">
  <b>💳 Prefer PayPal?</b>
  <p style="margin:6px 0 10px">Pay <b>${{ p.usd }}</b> to <b>paypal.me/{{ paypal }}</b>, then DM <b>{{ owner }}</b> on Discord with your payment screenshot to get your {{p.name}}.</p>
  <a class="go" href="https://paypal.me/{{ paypal }}/{{ p.usd }}" target="_blank" style="background:#ffcb3a">💳 Pay ${{ p.usd }} with PayPal</a>
</div>
{% endif %}

{% if user %}
<div style="margin-top:16px;padding:14px;border:3px solid var(--edge);border-radius:14px;background:#e3fff4">
  <b>💰 Pay with your balance</b>
  <p style="margin:6px 0 10px">Your balance: <b>${{ '%.2f'|format(user.balance) }}</b> · Price: <b>${{ p.usd }}</b></p>
  {% if user.balance >= p.usd %}
  <form method="POST" action="/buybalance">
    <input type="hidden" name="tab" value="{{tab}}"><input type="hidden" name="product" value="{{product}}">
    <button class="go" type="submit" style="background:linear-gradient(90deg,#33e6a6,#3fb9ff)">💰 Buy with balance (${{ p.usd }})</button>
  </form>
  {% else %}
  <p style="color:#c0392b;font-weight:600">Not enough balance. DM {{ owner }} to top up!</p>
  {% endif %}
</div>
{% else %}
<div style="margin-top:16px;padding:12px;border:3px dashed var(--edge);border-radius:14px;background:#fff8ec;text-align:center">
  <a href="/login" style="font-weight:700;color:var(--grape)">🔐 Log in</a> to pay with account balance!
</div>
{% endif %}
</div>

{% elif step == 'paid' %}
<div class="redeem"><h3>✅ Thanks!</h3>
<div class="result ok">{{ result|safe }}</div></div>

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
              tab="premium",step=1,items=PRODUCTS,result=None,key=None,stock={},paypal=PAYPAL_ME,
              user=current_user())
    # compute stock for whichever catalog is shown
    items = kw.get("items", base["items"])
    try:
        base["stock"] = {pid: get_stock(p["pid"]) for pid, p in items.items()}
    except Exception:
        base["stock"] = {}
    # add a USD price to the selected product for PayPal display
    if "p" in kw and isinstance(kw["p"], dict):
        kw["p"] = dict(kw["p"])
        kw["p"]["usd"] = round(kw["p"].get("robux", 0) / RBX_PER_USD, 2)
    # a short PayPal note-code so we can match their payment email
    if kw.get("step") == "name" and "ppcode" not in kw:
        kw["ppcode"] = "PP" + "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(6))
    base.update(kw); return render_template_string(PAGE,**base)

@app.route("/testemail")
def testemail():
    """Debug: try sending a test email. /testemail?to=you@gmail.com"""
    to = request.args.get("to", "")
    if not to:
        return {"error": "add ?to=youremail@gmail.com"}, 200
    out = {"resend_key_present": bool(RESEND_KEY),
           "resend_sender": RESEND_SENDER,
           "brevo_key_present": bool(BREVO_KEY),
           "brevo_sender": BREVO_SENDER}
    ok, err = send_email(to, "Test", "Test email from your shop! If you got this, email works. 🎉")
    out["sent_ok"] = ok
    out["error"] = err
    return out, 200

@app.route("/version")
def version(): return "shop build=v41-balancebuy", 200

LOGIN_PAGE = r"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Login — Robuks</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Fredoka:wght@500;600;700&family=Baloo+2:wght@700;800&display=swap');
body{background:linear-gradient(180deg,#fff4e6,#ffe9cf);font-family:'Fredoka',sans-serif;color:#2a2140;min-height:100vh;display:grid;place-items:center;padding:20px}
.box{background:#fff;border:3px solid #2a2140;border-radius:22px;box-shadow:6px 6px 0 #2a2140;padding:28px;max-width:400px;width:100%}
h2{font-family:'Baloo 2';font-weight:800;font-size:24px;margin-bottom:6px}
p{color:#7c6f92;font-size:14px;margin-bottom:16px}
label{display:block;font-weight:600;font-size:13px;margin:10px 0 6px}
input{width:100%;padding:12px 14px;border:3px solid #2a2140;border-radius:14px;background:#fffaf0;font-family:'Fredoka';font-weight:600;font-size:15px;box-sizing:border-box}
.go{margin-top:16px;width:100%;padding:14px;border:3px solid #2a2140;border-radius:15px;background:linear-gradient(90deg,#33e6a6,#3fb9ff);color:#2a2140;font-family:'Baloo 2';font-weight:800;font-size:16px;cursor:pointer;box-shadow:5px 5px 0 #2a2140}
.msg{margin-top:14px;padding:12px;border-radius:12px;border:3px solid #2a2140;font-size:14px}
.err{background:#ffe7e7}.ok{background:#e3fff4}
a{color:#a06bff}
</style></head><body><div class="box">
{{ inner|safe }}
</div></body></html>"""

@app.route("/login", methods=["GET","POST"])
def login():
    def page(inner): return render_template_string(LOGIN_PAGE, inner=inner)
    if request.method == "GET":
        if current_user(): return redirect("/account")
        return page("""<h2>🔐 Login</h2><p>Enter your Gmail — we'll email you a code.</p>
        <form method="POST"><input type="hidden" name="stage" value="email">
        <label>Gmail address</label><input name="email" type="email" placeholder="you@gmail.com" required>
        <button class="go">Send me a code →</button></form>""")
    stage = request.form.get("stage")
    if stage == "email":
        email = request.form.get("email","").strip().lower()
        if not email.endswith("@gmail.com"):
            return page("<h2>🔐 Login</h2><div class='msg err'>Please use a Gmail address.</div><p><a href='/login'>Try again</a></p>")
        code = f"{secrets.randbelow(900000)+100000}"
        try: _redis("SET", f"logincode:{email}", code, "EX", "600")
        except Exception: pass
        ok, err = send_email(email, "Your Robuks login code",
                             f"Your login code is: {code}\n\nIt expires in 10 minutes.")
        if not ok:
            return page(f"<h2>🔐 Login</h2><div class='msg err'>Couldn't send email ({err}).</div>")
        return page(f"""<h2>📧 Check your email</h2><p>We sent a 6-digit code to <b>{email}</b>.</p>
        <form method="POST"><input type="hidden" name="stage" value="code">
        <input type="hidden" name="email" value="{email}">
        <label>Enter code</label><input name="code" placeholder="123456" required>
        <button class="go">Verify →</button></form>""")
    if stage == "code":
        email = request.form.get("email","").strip().lower()
        code = request.form.get("code","").strip()
        try: want = _redis("GET", f"logincode:{email}")
        except Exception as ex:
            print(f"logincode GET err: {ex}", flush=True); want = None
        # normalize both sides (strip quotes/spaces) to avoid false mismatches
        want_s = str(want).strip().strip('"').strip() if want is not None else ""
        code_s = str(code).strip().strip('"').strip()
        print(f"🔐 login check email={email} entered={code_s!r} stored={want_s!r} match={code_s==want_s}", flush=True)
        if not want_s or code_s != want_s:
            return page(f"""<h2>❌ Wrong code</h2><div class='msg err'>That code is wrong or expired.</div>
            <form method="POST"><input type="hidden" name="stage" value="code">
            <input type="hidden" name="email" value="{email}">
            <label>Enter code</label><input name="code" placeholder="123456" required>
            <button class="go">Verify →</button></form>""")
        try: _redis("DEL", f"logincode:{email}")
        except Exception: pass
        acct = get_account(email)
        if not acct:
            # new user → make username
            session["pending_email"] = email
            return page(f"""<h2>👤 Create username</h2><p>Almost done! Pick a username.</p>
            <form method="POST" action="/setusername">
            <label>Username</label><input name="username" placeholder="cooluser123" required>
            <button class="go">Create account →</button></form>""")
        session["email"] = email
        return redirect("/account")
    return redirect("/login")

@app.route("/setusername", methods=["POST"])
def setusername():
    email = session.get("pending_email")
    if not email: return redirect("/login")
    uname = request.form.get("username","").strip()
    def page(inner): return render_template_string(LOGIN_PAGE, inner=inner)
    if len(uname) < 3 or not uname.replace("_","").isalnum():
        return page("<h2>👤 Create username</h2><div class='msg err'>3+ letters/numbers only.</div><p><a href='/login'>Back</a></p>")
    # taken?
    try:
        if _redis("GET", f"acctname:{uname.lower()}"):
            return page(f"""<h2>👤 Create username</h2><div class='msg err'>'{uname}' is taken.</div>
            <form method="POST" action="/setusername"><label>Username</label>
            <input name="username" required><button class="go">Create →</button></form>""")
    except Exception: pass
    acct = {"email": email, "username": uname, "balance": 0.10, "created": int(time.time()),
            "signup_bonus": True}
    save_account(acct)
    session.pop("pending_email", None)
    session["email"] = email
    return redirect("/account?welcome=1")

@app.route("/account")
def account():
    acct = current_user()
    if not acct: return redirect("/login")
    bal = acct.get('balance', 0)
    welcome = ""
    if request.args.get("welcome"):
        welcome = """<div class="msg ok" style="text-align:center">
        🎉 Welcome! We added a <b>$0.10</b> signup bonus to your balance!</div>"""
    inner = f"""<h2>👤 {acct['username']}</h2>
    <p>{acct['email']}</p>
    {welcome}
    <div style="margin:16px 0;padding:22px;border:3px solid #2a2140;border-radius:18px;
      background:linear-gradient(135deg,#33e6a6,#3fb9ff);box-shadow:5px 5px 0 #2a2140;text-align:center">
      <div style="font-size:13px;font-weight:700;color:#2a2140;opacity:.7">YOUR BALANCE</div>
      <div style="font-family:'Baloo 2';font-weight:800;font-size:42px;color:#2a2140;line-height:1.1">${bal:.2f}</div>
    </div>
    <p style="text-align:center">Use your balance to buy products in the shop! 🛒</p>
    <a class="go" href="/" style="text-decoration:none;display:block;text-align:center">🛒 Go Shopping</a>
    <p style="margin-top:14px;text-align:center;font-size:13px">
      Need to top up? DM <b>{OWNER_NAME}</b> on Discord.<br>
      <a href='/logout'>Log out</a></p>"""
    return render_template_string(LOGIN_PAGE, inner=inner)

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

@app.route("/testcreate")
def testcreate():
    """Manually create a gamepass. /testcreate?name=MyPass&price=50"""
    name = request.args.get("name", "Test Pass")
    price = int(request.args.get("price", "5"))
    gpid, err = create_gamepass(name, price)
    if gpid:
        return {"created_gamepass_id": gpid,
                "buy_link": f"https://www.roblox.com/game-pass/{gpid}",
                "price": price, "name": name}, 200
    return {"error": err, "created_gamepass_id": None}, 200

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
    if get_stock(cat[product]["pid"]) <= 0:
        return render(tab=tab,step=1,items=cat,result="❌ That product is out of stock.",result_class="err")
    return render(tab=tab,step="name",items=cat,product=product,p=cat[product])

@app.route("/checkpaypal",methods=["POST"])
def checkpaypal():
    """Buyer paid via PayPal with their code in the note → read inbox → auto-issue key."""
    tab=request.form.get("tab","premium"); product=request.form.get("product","")
    ppcode=request.form.get("ppcode","").strip()
    username=request.form.get("username","").strip()
    cat=catalog(tab)
    if product not in cat: return render(tab=tab,step=1,items=cat,result="❌ Unknown plan.",result_class="err")
    p=cat[product]
    usd = round(p["robux"]/RBX_PER_USD, 2)
    if not ppcode:
        return render(tab=tab,step="name",items=cat,product=product,p=p,
                      result="❌ Missing your payment code — go back and try again.",result_class="err")
    # already used this code? (prevents double-claims)
    try:
        if _redis("GET", f"ppused:{ppcode}"):
            return render(tab=tab,step="name",items=cat,product=product,p=p,
                          result="❌ This payment code was already used.",result_class="err")
    except Exception: pass
    # read the inbox for a matching PayPal receipt
    ok, why = check_paypal_email(usd, ppcode)
    if not ok:
        return render(tab=tab,step="name",items=cat,product=product,p=p,
                      result=f"⏳ No matching PayPal payment found yet ({why}). "
                             f"Make sure you sent <b>${usd}</b> with code <b>{ppcode}</b> in the note, "
                             f"then wait ~30s and tap verify again.",result_class="err")
    # payment found → issue key
    key=gen_key()
    entry=json.dumps({"kind":tab,"product":product,"product_name":f"{p['name']} {p['len']}",
                      "used_by":None,"created":int(time.time()),"roblox_id":None,
                      "roblox_name":username or "PayPal buyer","paid":"paypal"})
    try:
        _redis("SET",f"key:{key}",entry)
        _redis("SET",f"ppused:{ppcode}","1")
        dec_stock(p["pid"])
        # notify owner of the paypal sale
        _redis("RPUSH","sellerorders",json.dumps({
            "kind":tab,"key":key,"product":f"{p['name']} {p['len']}",
            "roblox":username or "PayPal buyer","ts":int(time.time()),"paid":"PayPal"}))
    except Exception as ex:
        print("pp store err",ex,flush=True)
        return render(tab=tab,step="done",result="⚠️ Payment found but key store failed — DM the owner.",result_class="err")
    print(f"💳 PAYPAL KEY ISSUED product={product} code={ppcode} key={key[:6]}…",flush=True)
    if tab=="seller":
        msg=f"✅ PayPal payment confirmed! Here's your <b>{p['name']} · {p['len']}</b> key:"
    else:
        msg=f"✅ PayPal payment confirmed! Here's your key:"
    return render(tab=tab,step="done",result=msg,result_class="ok",key=key,pname=f"{p['name']} {p['len']}")

@app.route("/ipaid",methods=["POST"])
def ipaid():
    tab=request.form.get("tab","premium"); product=request.form.get("product","")
    username=request.form.get("username","").strip(); method=request.form.get("method","?")
    cat=catalog(tab)
    if product not in cat: return render(tab=tab,step=1,items=cat,result="❌ Unknown plan.",result_class="err")
    p=cat[product]
    if not username: return render(tab=tab,step="name",items=cat,product=product,p=p,result="❌ Enter your name first.",result_class="err")
    # push a "someone paid" alert for the bot to DM the owner
    try:
        _redis("RPUSH","paidclaims",json.dumps({
            "product":f"{p['name']} {p['len']}","who":username,"method":method,
            "robux":p["robux"],"tab":tab,"ts":int(time.time())}))
    except Exception as ex:
        print("ipaid push err",ex,flush=True)
    return render(tab=tab,step="paid",items=cat,product=product,p=p,
                  result=f"Got it! We've alerted <b>{OWNER_NAME}</b> that you paid for "
                         f"<b>{p['name']} · {p['len']}</b> via <b>{method}</b>.<br><br>"
                         f"⏳ Please also <b>DM {OWNER_NAME}</b> on Discord with your payment proof "
                         f"so they can verify and hand over your product. Thank you! 💛")

@app.route("/buybalance", methods=["POST"])
def buybalance():
    acct = current_user()
    if not acct: return redirect("/login")
    tab=request.form.get("tab","premium"); product=request.form.get("product","")
    cat=catalog(tab)
    if product not in cat:
        return render(tab=tab,step=1,items=cat,result="❌ Unknown plan.",result_class="err")
    p=cat[product]
    usd = round(p["robux"]/RBX_PER_USD, 2)
    # check balance
    if float(acct.get("balance",0)) < usd:
        return render(tab=tab,step=1,items=cat,result="❌ Not enough balance.",result_class="err")
    # check stock
    if get_stock(p["pid"]) <= 0:
        return render(tab=tab,step=1,items=cat,result="❌ Out of stock.",result_class="err")
    # deduct + issue key
    acct["balance"] = round(float(acct["balance"]) - usd, 2)
    save_account(acct)
    key=gen_key()
    entry=json.dumps({"kind":tab,"product":product,"product_name":f"{p['name']} {p['len']}",
                      "used_by":None,"created":int(time.time()),"roblox_id":None,
                      "roblox_name":acct["username"],"paid":"balance"})
    try:
        _redis("SET",f"key:{key}",entry)
        dec_stock(p["pid"])
        _redis("RPUSH","sellerorders",json.dumps({
            "kind":tab,"key":key,"product":f"{p['name']} {p['len']}",
            "roblox":acct["username"],"ts":int(time.time()),"paid":"Balance"}))
    except Exception as ex:
        print("buybalance err",ex,flush=True)
    msg = (f"✅ Purchased <b>{p['name']} · {p['len']}</b> with your balance! "
           f"New balance: <b>${acct['balance']:.2f}</b><br>Here's your key:")
    if tab == "seller":
        msg += f"<br><small>DM {OWNER_NAME} with this key to claim.</small>"
    return render(tab=tab,step="done",result=msg,result_class="ok",key=key,pname=f"{p['name']} {p['len']}")

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
    # stock check (in case it sold out while they were buying)
    if get_stock(p["pid"]) <= 0:
        return render(tab=tab,step="done",result="❌ Sorry, this product just went out of stock.",result_class="err")
    # issue key (store metadata for /keylookup)
    key=gen_key()
    entry=json.dumps({"kind":tab,"product":product,"product_name":f"{p['name']} {p['len']}",
                      "used_by":None,"created":int(time.time()),"roblox_id":uid,"roblox_name":real})
    try:
        _redis("SET",f"key:{key}",entry)
        _redis("DEL",f"biocode:{uid}:{product}"); _redis("DEL",pass_key)
        dec_stock(p["pid"])   # one sold
    except Exception as ex:
        print("store err",ex,flush=True); return render(tab=tab,step="done",result="⚠️ Key store error.",result_class="err")
    # notify owner about EVERY purchase (premium + seller)
    try:
        _redis("RPUSH","sellerorders",json.dumps({
            "kind": tab, "key": key, "product": f"{p['name']} {p['len']}",
            "roblox": real, "ts": int(time.time())}))
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

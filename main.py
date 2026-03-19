"""
MarketSentinel — Backend FastAPI v5
Proxy FRED (US + EU) + Telegram + NewsAPI + Groq Sentiment
"""

import asyncio
import os
import json
import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="MarketSentinel API", version="5.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

FRED_BASE      = "https://api.stlouisfed.org/fred/series/observations"
TELEGRAM_BASE  = "https://api.telegram.org"
NEWS_BASE      = "https://newsapi.org/v2/everything"
GROQ_BASE      = "https://api.groq.com/openai/v1/chat/completions"

# ─── FRED HELPERS ─────────────────────────────────────────────────────────────
async def fred_get(client, series_id, key, limit=13):
    url = f"{FRED_BASE}?series_id={series_id}&api_key={key}&file_type=json&sort_order=desc&limit={limit}"
    r = await client.get(url, timeout=15)
    data = r.json()
    if "error_message" in data:
        raise HTTPException(400, f"FRED {series_id}: {data['error_message']}")
    return [o for o in data["observations"] if o["value"] != "."]

async def fred_get_safe(client, series_id, key, limit=13):
    """Versione che non solleva eccezioni — ritorna None se la serie non è disponibile."""
    try:
        return await fred_get(client, series_id, key, limit)
    except Exception:
        return None

# ─── SCORING HELPERS ──────────────────────────────────────────────────────────
def badge(s): return "red" if s >= 70 else "yellow" if s >= 50 else "green"

# US Macro scoring
def score_cpi(v):       return 90 if v>6 else 75 if v>4 else 60 if v>3 else 40 if v>2 else 20
def score_fed(v):       return 80 if v>5 else 65 if v>4 else 45 if v>2.5 else 25
def score_consumer(v):  return 85 if v<60 else 65 if v<75 else 40 if v<90 else 20
def score_yield(v):     return 90 if v<-0.5 else 75 if v<-0.2 else 60 if v<0 else 35 if v<0.5 else 20
def score_unemp(v):     return 70 if v>6 else 55 if v>5 else 40 if v>4.5 else 20

# EU Macro scoring
def score_ecb(v):       return 80 if v>4 else 65 if v>3 else 45 if v>2 else 25
def score_eu_cpi(v):    return 90 if v>6 else 75 if v>4 else 60 if v>3 else 40 if v>2 else 20
def score_eurusd(v):
    # EUR/USD basso (USD forte) = pressione su mercati europei ed EM
    if v < 1.00: return 75
    if v < 1.05: return 60
    if v < 1.10: return 45
    return 25

# ─── FRED DATA ENDPOINT ───────────────────────────────────────────────────────
@app.get("/api/fred-data")
async def fred_data(api_key: str = Query(...)):
    async with httpx.AsyncClient() as client:
        # US + EU in parallelo
        (cpi, fed, consumer, yld, unemp,
         ecb, eu_cpi_obs, eurusd_obs) = await asyncio.gather(
            fred_get(client, "CPIAUCSL",          api_key, 13),
            fred_get(client, "FEDFUNDS",           api_key, 1),
            fred_get(client, "UMCSENT",            api_key, 1),
            fred_get(client, "T10Y2Y",             api_key, 1),
            fred_get(client, "UNRATE",             api_key, 1),
            fred_get_safe(client, "ECBDFR",        api_key, 1),
            fred_get_safe(client, "CP0000EZ19M086NEST", api_key, 13),
            fred_get_safe(client, "DEXUSEU",       api_key, 1),
        )

    # ── US Macro ──────────────────────────────────────────────────────────────
    cpi_now = float(cpi[0]["value"])
    cpi_ago = float(cpi[min(12, len(cpi)-1)]["value"])
    cpi_yoy = round((cpi_now / cpi_ago - 1) * 100, 2)
    fed_r     = float(fed[0]["value"])
    consumer_v = float(consumer[0]["value"])
    yld_v     = float(yld[0]["value"])
    unemp_v   = float(unemp[0]["value"])

    s_us1 = score_cpi(cpi_yoy)
    s_us2 = score_fed(fed_r)
    s_us3 = score_consumer(consumer_v)
    s_us4 = score_yield(yld_v)
    s_us5 = score_unemp(unemp_v)
    us_macro_score = round((s_us1+s_us2+s_us3+s_us4+s_us5) / 5)

    us_signals = [
        {"name":"CPI YoY (US)",       "val":f"{cpi_yoy}%",      "score":s_us1, "badge":badge(s_us1), "label":"CRITICO" if cpi_yoy>4 else "SOPRA TARGET" if cpi_yoy>3 else "MODERATO" if cpi_yoy>2 else "TARGET"},
        {"name":"Fed Funds Rate",     "val":f"{fed_r}%",        "score":s_us2, "badge":badge(s_us2), "label":"MOLTO RESTR." if fed_r>5 else "RESTRITTIVO" if fed_r>4 else "NEUTRO"},
        {"name":"Consumer Sentiment", "val":str(consumer_v),    "score":s_us3, "badge":badge(s_us3), "label":"PESSIMISMO" if consumer_v<60 else "CAUTELA" if consumer_v<75 else "NEUTRO" if consumer_v<90 else "OTTIMISMO"},
        {"name":"Yield 10Y−2Y",      "val":f"{yld_v:+}%",      "score":s_us4, "badge":badge(s_us4), "label":"INVERSIONE" if yld_v<-0.2 else "PIATTA" if yld_v<0 else "NORMALE"},
        {"name":"Disoccupaz. (US)",   "val":f"{unemp_v}%",      "score":s_us5, "badge":badge(s_us5), "label":"IN AUMENTO" if unemp_v>5 else "SOLIDA"},
    ]

    # ── EU Macro ──────────────────────────────────────────────────────────────
    eu_signals = []
    eu_scores  = []

    if ecb:
        ecb_r = float(ecb[0]["value"])
        s = score_ecb(ecb_r)
        eu_scores.append(s)
        eu_signals.append({"name":"BCE Deposit Rate", "val":f"{ecb_r}%", "score":s, "badge":badge(s), "label":"MOLTO RESTR." if ecb_r>4 else "RESTRITTIVO" if ecb_r>3 else "NEUTRO"})

    if eu_cpi_obs and len(eu_cpi_obs) >= 2:
        eu_now = float(eu_cpi_obs[0]["value"])
        eu_ago = float(eu_cpi_obs[min(12, len(eu_cpi_obs)-1)]["value"])
        eu_yoy = round((eu_now / eu_ago - 1) * 100, 2)
        s = score_eu_cpi(eu_yoy)
        eu_scores.append(s)
        eu_signals.append({"name":"HICP YoY (EU)", "val":f"{eu_yoy}%", "score":s, "badge":badge(s), "label":"CRITICO" if eu_yoy>4 else "SOPRA TARGET" if eu_yoy>3 else "MODERATO" if eu_yoy>2 else "TARGET"})

    if eurusd_obs:
        eurusd = float(eurusd_obs[0]["value"])
        s = score_eurusd(eurusd)
        eu_scores.append(s)
        eu_signals.append({"name":"EUR/USD", "val":f"{eurusd:.4f}", "score":s, "badge":badge(s), "label":"USD FORTE" if eurusd<1.05 else "NEUTRO" if eurusd<1.15 else "EUR FORTE"})

    eu_macro_score = round(sum(eu_scores) / len(eu_scores)) if eu_scores else 50

    # ── Score aggregato (50% US / 50% EU) ────────────────────────────────────
    macro_score = round((us_macro_score + eu_macro_score) / 2)

    return {
        "macro_score": macro_score,
        "us_macro_score": us_macro_score,
        "eu_macro_score": eu_macro_score,
        "signals": us_signals,
        "eu_signals": eu_signals,
    }

# ─── NEWS API ─────────────────────────────────────────────────────────────────
NEWS_QUERIES = [
    "S&P500 stock market correction",
    "Federal Reserve interest rates economy",
    "geopolitical risk financial markets",
    "inflation recession GDP global",
    "European stocks ECB economy",
    "emerging markets risk selloff",
]

CONSULTING_QUERIES = [
    "Goldman Sachs market outlook forecast 2025",
    "Morgan Stanley investment strategy equities",
    "JPMorgan market view recession risk",
    "BlackRock investment outlook allocation",
    "Citi UBS market forecast correction",
    "Deutsche Bank BNP Paribas European outlook",
]

@app.get("/api/news")
async def get_news(api_key: str = Query(...)):
    headlines = []
    seen_titles = set()
    async with httpx.AsyncClient() as client:
        responses = await asyncio.gather(*[
            client.get(f"{NEWS_BASE}?q={q}&language=en&sortBy=publishedAt&pageSize=5&apiKey={api_key}", timeout=15)
            for q in NEWS_QUERIES
        ], return_exceptions=True)
    for resp in responses:
        if isinstance(resp, Exception): continue
        try:
            data = resp.json()
            if data.get("status") != "ok": continue
            for a in data.get("articles", []):
                title = a.get("title","").strip()
                desc  = a.get("description","").strip()
                if not title or title in seen_titles: continue
                seen_titles.add(title)
                headlines.append(f"• {title}: {desc}" if desc else f"• {title}")
        except Exception: continue
    if not headlines:
        raise HTTPException(404, "Nessuna notizia trovata.")
    text = "\n".join(headlines[:30])
    return {"count": len(headlines[:30]), "text": text}

@app.get("/api/consulting-news")
async def get_consulting_news(api_key: str = Query(...)):
    headlines = []
    seen_titles = set()
    async with httpx.AsyncClient() as client:
        responses = await asyncio.gather(*[
            client.get(f"{NEWS_BASE}?q={q}&language=en&sortBy=publishedAt&pageSize=4&apiKey={api_key}", timeout=15)
            for q in CONSULTING_QUERIES
        ], return_exceptions=True)
    for resp in responses:
        if isinstance(resp, Exception): continue
        try:
            data = resp.json()
            if data.get("status") != "ok": continue
            for a in data.get("articles", []):
                title = a.get("title","").strip()
                desc  = a.get("description","").strip()
                if not title or title in seen_titles: continue
                seen_titles.add(title)
                headlines.append(f"• {title}: {desc}" if desc else f"• {title}")
        except Exception: continue
    if not headlines:
        raise HTTPException(404, "Nessuna opinione trovata.")
    text = "\n".join(headlines[:25])
    return {"count": len(headlines[:25]), "text": text}

# ─── GROQ SENTIMENT ───────────────────────────────────────────────────────────
def groq_score_to_level(score):
    if score >= 76: return "CRITICO"
    if score >= 56: return "ELEVATO"
    if score >= 31: return "MEDIO"
    return "BASSO"

async def call_groq(system_prompt, user_content):
    groq_key = os.environ.get("GROQ_API_KEY")
    if not groq_key:
        raise HTTPException(500, "GROQ_API_KEY non configurata")
    async with httpx.AsyncClient() as client:
        r = await client.post(
            GROQ_BASE,
            headers={"Content-Type":"application/json","Authorization":f"Bearer {groq_key}"},
            json={
                "model": "llama-3.3-70b-versatile",
                "max_tokens": 800,
                "messages": [
                    {"role":"system","content":system_prompt},
                    {"role":"user","content":user_content},
                ],
            },
            timeout=30,
        )
    if not r.is_success:
        raise HTTPException(r.status_code, f"Errore Groq: {r.text[:200]}")
    raw = r.json()["choices"][0]["message"]["content"]
    return json.loads(raw.replace("```json","").replace("```","").strip())

class SentimentPayload(BaseModel):
    text: str

@app.post("/api/sentiment")
async def analyze_sentiment(payload: SentimentPayload):
    system = """Sei un analista finanziario quantitativo specializzato in risk management globale.
Analizza le notizie e assegna un sentiment_score dove:
- 0-30 = notizie positive/neutre, mercati tranquilli, nessun rischio
- 31-55 = notizie miste, qualche preoccupazione moderata
- 56-75 = notizie negative, rischio correzione possibile
- 76-100 = notizie molto negative, rischio correzione imminente

Considera sia i mercati USA che europei ed emergenti.
Esempi: "mercati in rialzo, economia solida" → 15. "Fed + BCE alzano tassi, inflazione alta, tensioni geopolitiche" → 72. "crash mercati, recessione globale" → 92.

Restituisci SOLO JSON:
{"sentiment_score":<0-100>,"risk_level":"<BASSO|MEDIO|ELEVATO|CRITICO>","key_risks":["r1","r2","r3"],"summary":"<2 frasi IT>","recommended_action":"<1 frase IT>"}"""
    result = await call_groq(system, f"Analizza:\n\n{payload.text}")
    result["risk_level"] = groq_score_to_level(result.get("sentiment_score", 50))
    return result

class ConsultingPayload(BaseModel):
    text: str

@app.post("/api/consulting-sentiment")
async def consulting_sentiment(payload: ConsultingPayload):
    system = """Sei un analista che valuta le previsioni delle principali banche d'investimento globali.
Assegna un consulting_score dove:
- 0-30 = banche ottimiste, prevedono mercati rialzisti globali
- 31-55 = previsioni miste, alcune cautele moderate
- 56-75 = banche caute/pessimiste, segnalano rischi significativi
- 76-100 = banche molto pessimiste, prevedono correzioni o recessione

Considera sia le previsioni sui mercati USA che europei ed emergenti.
Esempi: "Goldman rialza target S&P500, positivo su Europa" → 20. "JPMorgan avverte recessione USA+EU" → 72.

Restituisci SOLO JSON:
{"consulting_score":<0-100>,"outlook":"<RIALZISTA|NEUTRO|RIBASSISTA|MOLTO_RIBASSISTA>","key_views":["v1","v2","v3"],"summary":"<2 frasi IT>"}"""
    result = await call_groq(system, f"Analizza:\n\n{payload.text}")
    score = result.get("consulting_score", 50)
    if score >= 76:   result["outlook"] = "MOLTO_RIBASSISTA"
    elif score >= 56: result["outlook"] = "RIBASSISTA"
    elif score >= 31: result["outlook"] = "NEUTRO"
    else:             result["outlook"] = "RIALZISTA"
    return result

# ─── TELEGRAM ─────────────────────────────────────────────────────────────────
class AlertPayload(BaseModel):
    bot_token: str
    chat_id: str
    overall_score: int
    tech_score: int
    macro_score: int
    sent_score: int
    trigger: str
    top_signals: list[str] = []

def risk_emoji(s): return "🔴" if s>=75 else "🟡" if s>=60 else "🟢"

def build_message(p):
    emoji = risk_emoji(p.overall_score)
    trigger_label = "⚠️ SOGLIA SUPERATA" if p.trigger=="threshold" else "🔄 Aggiornamento dati"
    lines = [
        f"{emoji} *MarketSentinel Alert*", f"_{trigger_label}_", "",
        f"*Risk Score: {p.overall_score}/100*", "",
        f"• Tecnico:   {p.tech_score}",
        f"• Macro:     {p.macro_score}",
        f"• Sentiment: {p.sent_score}",
    ]
    if p.top_signals:
        lines += ["", "*Segnali critici:*"] + [f"  ↳ {s}" for s in p.top_signals[:3]]
    if p.overall_score >= 75:
        lines += ["", "🚨 *Valutare riduzione esposizione azionaria*"]
    elif p.overall_score >= 60:
        lines += ["", "⚡ *Monitorare attentamente l'evoluzione*"]
    else:
        lines += ["", "✅ *Mercato stabile — nessuna azione richiesta*"]
    return "\n".join(lines)

@app.post("/api/send-alert")
async def send_alert(payload: AlertPayload):
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{TELEGRAM_BASE}/bot{payload.bot_token}/sendMessage",
            json={"chat_id":payload.chat_id,"text":build_message(payload),"parse_mode":"Markdown"},
            timeout=10,
        )
    data = r.json()
    if not data.get("ok"):
        raise HTTPException(400, f"Telegram: {data.get('description','Unknown')}")
    return {"sent": True, "message_id": data["result"]["message_id"]}

@app.get("/health")
async def health():
    return {"status": "ok"}

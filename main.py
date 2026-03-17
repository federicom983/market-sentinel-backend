"""
MarketSentinel — Backend FastAPI v4
Proxy FRED + Telegram + NewsAPI + Claude Sentiment
"""

import asyncio
import os
import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="MarketSentinel API", version="4.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

FRED_BASE      = "https://api.stlouisfed.org/fred/series/observations"
TELEGRAM_BASE  = "https://api.telegram.org"
NEWS_BASE      = "https://newsapi.org/v2/everything"
ANTHROPIC_BASE = "https://api.anthropic.com/v1/messages"

# ─── FRED ─────────────────────────────────────────────────────────────────────
async def fred_get(client, series_id, key, limit=13):
    url = f"{FRED_BASE}?series_id={series_id}&api_key={key}&file_type=json&sort_order=desc&limit={limit}"
    r = await client.get(url, timeout=15)
    data = r.json()
    if "error_message" in data:
        raise HTTPException(400, data["error_message"])
    return [o for o in data["observations"] if o["value"] != "."]

def badge(s): return "red" if s >= 70 else "yellow" if s >= 50 else "green"
def score_cpi(v):   return 90 if v>6 else 75 if v>4 else 60 if v>3 else 40 if v>2 else 20
def score_fed(v):   return 80 if v>5 else 65 if v>4 else 45 if v>2.5 else 25
def score_sent(v):  return 85 if v<60 else 65 if v<75 else 40 if v<90 else 20
def score_yield(v): return 90 if v<-0.5 else 75 if v<-0.2 else 60 if v<0 else 35 if v<0.5 else 20
def score_unemp(v): return 70 if v>6 else 55 if v>5 else 40 if v>4.5 else 20

@app.get("/api/fred-data")
async def fred_data(api_key: str = Query(...)):
    async with httpx.AsyncClient() as client:
        cpi, fed, sentiment_obs, yld, unemp = await asyncio.gather(
            fred_get(client, "CPIAUCSL", api_key, 13),
            fred_get(client, "FEDFUNDS", api_key, 1),
            fred_get(client, "UMCSENT",  api_key, 1),
            fred_get(client, "T10Y2Y",   api_key, 1),
            fred_get(client, "UNRATE",   api_key, 1),
        )
    cpi_now = float(cpi[0]["value"])
    cpi_ago = float(cpi[min(12, len(cpi)-1)]["value"])
    cpi_yoy = round((cpi_now / cpi_ago - 1) * 100, 2)
    fed_r   = float(fed[0]["value"])
    sent_v  = float(sentiment_obs[0]["value"])
    yld_v   = float(yld[0]["value"])
    unemp_v = float(unemp[0]["value"])

    s1,s2,s3,s4,s5 = score_cpi(cpi_yoy), score_fed(fed_r), score_sent(sent_v), score_yield(yld_v), score_unemp(unemp_v)
    macro_score = round((s1+s2+s3+s4+s5)/5)

    return {
        "macro_score": macro_score,
        "signals": [
            {"name":"CPI YoY (US)",       "val":f"{cpi_yoy}%", "score":s1, "badge":badge(s1), "label":"CRITICO" if cpi_yoy>4 else "SOPRA TARGET" if cpi_yoy>3 else "MODERATO" if cpi_yoy>2 else "TARGET"},
            {"name":"Fed Funds Rate",     "val":f"{fed_r}%",   "score":s2, "badge":badge(s2), "label":"MOLTO RESTR." if fed_r>5 else "RESTRITTIVO" if fed_r>4 else "NEUTRO"},
            {"name":"Consumer Sentiment", "val":str(sent_v),   "score":s3, "badge":badge(s3), "label":"PESSIMISMO" if sent_v<60 else "CAUTELA" if sent_v<75 else "NEUTRO" if sent_v<90 else "OTTIMISMO"},
            {"name":"Yield 10Y−2Y",      "val":f"{yld_v:+}%", "score":s4, "badge":badge(s4), "label":"INVERSIONE" if yld_v<-0.2 else "PIATTA" if yld_v<0 else "NORMALE"},
            {"name":"Disoccupazione",     "val":f"{unemp_v}%", "score":s5, "badge":badge(s5), "label":"IN AUMENTO" if unemp_v>5 else "SOLIDA"},
        ]
    }

# ─── NEWS API ─────────────────────────────────────────────────────────────────
NEWS_QUERIES = [
    "S&P500 stock market",
    "Federal Reserve interest rates",
    "geopolitical risk economy",
    "inflation recession GDP",
]

@app.get("/api/news")
async def get_news(api_key: str = Query(...)):
    headlines = []
    seen_titles = set()

    async with httpx.AsyncClient() as client:
        tasks = [
            client.get(f"{NEWS_BASE}?q={q}&language=en&sortBy=publishedAt&pageSize=5&apiKey={api_key}", timeout=15)
            for q in NEWS_QUERIES
        ]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

    for resp in responses:
        if isinstance(resp, Exception):
            continue
        try:
            data = resp.json()
            if data.get("status") != "ok":
                continue
            for article in data.get("articles", []):
                title = article.get("title", "").strip()
                desc  = article.get("description", "").strip()
                if not title or title in seen_titles:
                    continue
                seen_titles.add(title)
                headlines.append(f"• {title}: {desc}" if desc else f"• {title}")
        except Exception:
            continue

    if not headlines:
        raise HTTPException(404, "Nessuna notizia trovata. Verifica la API key NewsAPI.")

    news_text = "\n".join(headlines[:30])
    return {"count": len(headlines[:30]), "text": news_text}

# ─── SENTIMENT (Claude via backend) ───────────────────────────────────────────
class SentimentPayload(BaseModel):
    text: str

@app.post("/api/sentiment")
async def analyze_sentiment(payload: SentimentPayload):
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if not anthropic_key:
        raise HTTPException(500, "ANTHROPIC_API_KEY non configurata nel backend")

    async with httpx.AsyncClient() as client:
        r = await client.post(
            ANTHROPIC_BASE,
            headers={
                "Content-Type": "application/json",
                "x-api-key": anthropic_key,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 1000,
                "system": """Analista finanziario quantitativo. Restituisci SOLO JSON valido, nessun testo extra:
{"sentiment_score":<0-100>,"risk_level":"<BASSO|MEDIO|ELEVATO|CRITICO>","key_risks":["r1","r2","r3"],"summary":"<2 frasi IT>","recommended_action":"<1 frase IT>"}""",
                "messages": [{"role": "user", "content": f"Analizza queste notizie:\n\n{payload.text}"}],
            },
            timeout=30,
        )

    if not r.is_success:
        raise HTTPException(r.status_code, f"Errore Claude API: {r.text[:200]}")

    data = r.json()
    raw = "".join(b.get("text", "") for b in data.get("content", []))
    try:
        import json
        result = json.loads(raw.replace("```json", "").replace("```", "").strip())
        return result
    except Exception:
        raise HTTPException(500, "Errore nel parsing della risposta Claude")

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

def risk_emoji(score): return "🔴" if score>=75 else "🟡" if score>=60 else "🟢"

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
    message = build_message(payload)
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{TELEGRAM_BASE}/bot{payload.bot_token}/sendMessage",
            json={"chat_id": payload.chat_id, "text": message, "parse_mode": "Markdown"},
            timeout=10,
        )
    data = r.json()
    if not data.get("ok"):
        raise HTTPException(400, f"Telegram error: {data.get('description','Unknown')}")
    return {"sent": True, "message_id": data["result"]["message_id"]}

@app.get("/health")
async def health():
    return {"status": "ok"}

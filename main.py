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
GROQ_BASE = "https://api.groq.com/openai/v1/chat/completions"

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

CONSULTING_QUERIES = [
    "Goldman Sachs market outlook forecast",
    "Morgan Stanley investment strategy",
    "JPMorgan market view recession",
    "BlackRock investment outlook",
    "Citi UBS market forecast 2025",
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

# ─── CONSULTING OPINIONS ──────────────────────────────────────────────────────
@app.get("/api/consulting-news")
async def get_consulting_news(api_key: str = Query(...)):
    """
    Recupera opinioni e previsioni delle principali banche d'investimento
    tramite NewsAPI e le restituisce come testo aggregato per l'analisi AI.
    """
    headlines = []
    seen_titles = set()

    async with httpx.AsyncClient() as client:
        tasks = [
            client.get(f"{NEWS_BASE}?q={q}&language=en&sortBy=publishedAt&pageSize=4&apiKey={api_key}", timeout=15)
            for q in CONSULTING_QUERIES
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
        raise HTTPException(404, "Nessuna opinione trovata. Verifica la API key NewsAPI.")

    news_text = "\n".join(headlines[:25])
    return {"count": len(headlines[:25]), "text": news_text}

class ConsultingPayload(BaseModel):
    text: str

@app.post("/api/consulting-sentiment")
async def consulting_sentiment(payload: ConsultingPayload):
    """
    Analizza le opinioni delle banche d'investimento con Groq e restituisce
    uno score 0-100 che rappresenta il pessimismo/ottimismo delle case di consulenza.
    """
    groq_key = os.environ.get("GROQ_API_KEY")
    if not groq_key:
        raise HTTPException(500, "GROQ_API_KEY non configurata nel backend")

    async with httpx.AsyncClient() as client:
        r = await client.post(
            GROQ_BASE,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {groq_key}",
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "max_tokens": 800,
                "messages": [
                    {
                        "role": "system",
                        "content": """Sei un analista che valuta le previsioni delle principali banche d'investimento.
Analizza i titoli e assegna un consulting_score dove:
- 0-30 = le banche sono ottimiste, prevedono mercati rialzisti, nessun rischio segnalato
- 31-55 = previsioni miste, alcune cautele ma niente di grave
- 56-75 = le banche sono caute/pessimiste, segnalano rischi significativi
- 76-100 = le banche sono molto pessimiste, prevedono correzioni o recessione

Esempi: "Goldman rialza target S&P500" → score 20. "JPMorgan avverte di rischi recessione" → score 68. "BlackRock riduce esposizione azionaria" → score 75.

Restituisci SOLO JSON valido:
{"consulting_score":<0-100>,"outlook":"<RIALZISTA|NEUTRO|RIBASSISTA|MOLTO_RIBASSISTA>","key_views":["view1","view2","view3"],"summary":"<2 frasi IT>"}"""
                    },
                    {"role": "user", "content": f"Analizza queste opinioni di banche d'investimento:\n\n{payload.text}"},
                ],
            },
            timeout=30,
        )

    if not r.is_success:
        print(f"Groq consulting error: {r.status_code} - {r.text}")
        raise HTTPException(r.status_code, f"Errore Groq API: {r.text[:200]}")

    data = r.json()
    raw = data["choices"][0]["message"]["content"]
    try:
        import json
        result = json.loads(raw.replace("```json", "").replace("```", "").strip())
        # Calcola outlook dal consulting_score
        score = result.get("consulting_score", 50)
        if score >= 76:
            result["outlook"] = "MOLTO_RIBASSISTA"
        elif score >= 56:
            result["outlook"] = "RIBASSISTA"
        elif score >= 31:
            result["outlook"] = "NEUTRO"
        else:
            result["outlook"] = "RIALZISTA"
        return result
    except Exception:
        import traceback; traceback.print_exc()
        raise HTTPException(500, f"Errore parsing risposta: {raw[:200]}")

# ─── SENTIMENT (Groq via backend) ────────────────────────────────────────────
GROQ_BASE = "https://api.groq.com/openai/v1/chat/completions"

class SentimentPayload(BaseModel):
    text: str

@app.post("/api/sentiment")
async def analyze_sentiment(payload: SentimentPayload):
    groq_key = os.environ.get("GROQ_API_KEY")
    if not groq_key:
        raise HTTPException(500, "GROQ_API_KEY non configurata nel backend")

    async with httpx.AsyncClient() as client:
        r = await client.post(
            GROQ_BASE,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {groq_key}",
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "max_tokens": 1000,
                "messages": [
                    {
                        "role": "system",
                        "content": """Sei un analista finanziario quantitativo specializzato in risk management.
Analizza le notizie e assegna un sentiment_score dove:
- 0-30 = notizie positive o neutre, mercati tranquilli, nessun rischio di correzione
- 31-55 = notizie miste, qualche preoccupazione ma niente di grave
- 56-75 = notizie negative, rischio correzione possibile, segnali di allerta
- 76-100 = notizie molto negative, rischio correzione imminente, segnali critici

Esempi: "mercati in rialzo, economia solida" → score 15. "Fed alza tassi, inflazione alta, tensioni geopolitiche" → score 72. "crash mercati, recessione, guerra" → score 92.

Restituisci SOLO JSON valido, nessun testo extra:
{"sentiment_score":<0-100>,"risk_level":"<BASSO|MEDIO|ELEVATO|CRITICO>","key_risks":["r1","r2","r3"],"summary":"<2 frasi IT>","recommended_action":"<1 frase IT>"}"""
                    },
                    {"role": "user", "content": f"Analizza queste notizie:\n\n{payload.text}"},
                ],
            },
            timeout=30,
        )

    if not r.is_success:
        print(f"Groq error: {r.status_code} - {r.text}")
        raise HTTPException(r.status_code, f"Errore Groq API: {r.text[:200]}")

    data = r.json()
    raw = data["choices"][0]["message"]["content"]
    try:
        import json
        result = json.loads(raw.replace("```json", "").replace("```", "").strip())
        # Calcola risk_level dal sentiment_score numerico — non ci fidiamo del modello
        score = result.get("sentiment_score", 50)
        if score >= 76:
            result["risk_level"] = "CRITICO"
        elif score >= 56:
            result["risk_level"] = "ELEVATO"
        elif score >= 31:
            result["risk_level"] = "MEDIO"
        else:
            result["risk_level"] = "BASSO"
        return result
    except Exception:
        import traceback; traceback.print_exc()
        raise HTTPException(500, f"Errore parsing risposta: {raw[:200]}")

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

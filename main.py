"""
MarketSentinel — Backend FastAPI v6
DCA/PAC Opportunity Scoring System
"""

import asyncio
import os
import json
import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="MarketSentinel API", version="6.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

FRED_BASE     = "https://api.stlouisfed.org/fred/series/observations"
TELEGRAM_BASE = "https://api.telegram.org"
NEWS_BASE     = "https://newsapi.org/v2/everything"
GROQ_BASE     = "https://api.groq.com/openai/v1/chat/completions"

# ─── FRED HELPERS ─────────────────────────────────────────────────────────────
async def fred_get(client, series_id, key, limit=13):
    url = f"{FRED_BASE}?series_id={series_id}&api_key={key}&file_type=json&sort_order=desc&limit={limit}"
    r = await client.get(url, timeout=15)
    data = r.json()
    if "error_message" in data:
        raise HTTPException(400, f"FRED {series_id}: {data['error_message']}")
    return [o for o in data["observations"] if o["value"] != "."]

async def fred_get_safe(client, series_id, key, limit=13):
    try:
        return await fred_get(client, series_id, key, limit)
    except Exception:
        return None

def badge_opp(s):
    """Badge per logica opportunità: alto score = buona opportunità."""
    if s >= 70: return "green"
    if s >= 45: return "yellow"
    return "red"

# ─── MACRO SCORING (logica DCA) ───────────────────────────────────────────────
# Alto score = buona opportunità di ingresso (mercato depresso/tassi in calo)

def score_cpi_dca(v):
    """CPI alta = Fed restrittiva = meno attrattivo per ingresso."""
    if v > 6:  return 10
    if v > 4:  return 25
    if v > 3:  return 45
    if v > 2:  return 65
    return 80  # inflazione sotto controllo = ottimo per azionario

def score_fed_dca(v):
    """Tassi alti = mercato meno attrattivo, ma anche opportunità future."""
    if v > 5:  return 30  # tassi molto alti = ancora restrittivo
    if v > 4:  return 45
    if v > 2.5: return 65
    return 85  # tassi bassi = ottimo per azionario

def score_consumer_dca(v):
    """Consumer sentiment basso = pessimismo = opportunità contrarian."""
    if v < 60:  return 85  # forte pessimismo = ottima opportunità
    if v < 75:  return 70
    if v < 90:  return 50
    return 25   # euforia = mercato caro

def score_yield_dca(v):
    """Curva invertita = recessione attesa = potenziale ingresso anticipato."""
    if v < -0.5: return 75  # forte inversione = paura = opportunità
    if v < -0.2: return 65
    if v < 0:    return 55
    if v < 0.5:  return 45
    return 35   # curva normale ripida = economia surriscaldata

def score_unemp_dca(v):
    """Disoccupazione in salita = mercato in sofferenza = potenziale opportunità."""
    if v > 6:   return 70
    if v > 5:   return 60
    if v > 4.5: return 50
    return 40   # piena occupazione = economia calda, meno upside

def score_ecb_dca(v):
    """BCE restrittiva = opportunità futura quando taglierà."""
    if v > 4:  return 35
    if v > 3:  return 50
    if v > 2:  return 65
    return 80

def score_eu_cpi_dca(v):
    if v > 6:  return 10
    if v > 4:  return 25
    if v > 3:  return 45
    if v > 2:  return 65
    return 80

def score_eurusd_dca(v):
    """EUR debole = EM e Europa più convenienti in USD."""
    if v < 1.00: return 70
    if v < 1.05: return 60
    if v < 1.10: return 50
    return 40

def score_dot_plot_dca(median_rate: float, current_rate: float) -> int:
    """
    Dot Plot: quanto la Fed prevede di tagliare rispetto ad oggi.
    Più tagli attesi = maggiore opportunità per azionario.
    """
    expected_cuts = current_rate - median_rate  # positivo = tagli attesi
    if expected_cuts > 1.5: return 90   # >150bp tagli attesi = molto positivo
    if expected_cuts > 1.0: return 80
    if expected_cuts > 0.5: return 70
    if expected_cuts > 0.0: return 55   # qualche taglio atteso
    if expected_cuts > -0.5: return 40  # invariato o piccolo rialzo
    return 25                            # rialzi significativi attesi

# ─── FRED ENDPOINT ────────────────────────────────────────────────────────────
@app.get("/api/fred-data")
async def fred_data(
    api_key: str = Query(...),
    dot_plot_median: float = Query(default=None, description="Mediana Dot Plot Fed (es. 3.875)")
):
    async with httpx.AsyncClient() as client:
        (cpi, fed, consumer, yld, unemp,
         ecb, eu_cpi_obs, eurusd_obs) = await asyncio.gather(
            fred_get(client, "CPIAUCSL",            api_key, 13),
            fred_get(client, "FEDFUNDS",             api_key, 1),
            fred_get(client, "UMCSENT",              api_key, 1),
            fred_get(client, "T10Y2Y",               api_key, 1),
            fred_get(client, "UNRATE",               api_key, 1),
            fred_get_safe(client, "ECBDFR",          api_key, 1),
            fred_get_safe(client, "CP0000EZ19M086NEST", api_key, 13),
            fred_get_safe(client, "DEXUSEU",         api_key, 1),
        )

    # ── US Macro ──────────────────────────────────────────────────────────────
    cpi_now  = float(cpi[0]["value"])
    cpi_ago  = float(cpi[min(12, len(cpi)-1)]["value"])
    cpi_yoy  = round((cpi_now / cpi_ago - 1) * 100, 2)
    fed_r    = float(fed[0]["value"])
    cons_v   = float(consumer[0]["value"])
    yld_v    = float(yld[0]["value"])
    unemp_v  = float(unemp[0]["value"])

    s1 = score_cpi_dca(cpi_yoy)
    s2 = score_fed_dca(fed_r)
    s3 = score_consumer_dca(cons_v)
    s4 = score_yield_dca(yld_v)
    s5 = score_unemp_dca(unemp_v)

    # Dot Plot se fornito
    dot_score = None
    dot_signal = None
    if dot_plot_median is not None:
        dot_score = score_dot_plot_dca(dot_plot_median, fed_r)
        cuts_bp = round((fed_r - dot_plot_median) * 100)
        dot_signal = {
            "name": "Dot Plot (mediana Fed)",
            "val": f"{dot_plot_median}%",
            "score": dot_score,
            "badge": badge_opp(dot_score),
            "label": f"{'+' if cuts_bp >= 0 else ''}{cuts_bp}bp tagli attesi",
        }
        us_scores = [s1, s2, s3, s4, s5, dot_score]
    else:
        us_scores = [s1, s2, s3, s4, s5]

    us_macro_score = round(sum(us_scores) / len(us_scores))

    us_signals = [
        {"name":"CPI YoY (US)",       "val":f"{cpi_yoy}%",   "score":s1, "badge":badge_opp(s1), "label":"INFLAZ. ALTA" if cpi_yoy>4 else "SOPRA TARGET" if cpi_yoy>3 else "MODERATA" if cpi_yoy>2 else "✓ SOTTO TARGET"},
        {"name":"Fed Funds Rate",     "val":f"{fed_r}%",     "score":s2, "badge":badge_opp(s2), "label":"MOLTO RESTR." if fed_r>5 else "RESTRITTIVO" if fed_r>4 else "NEUTRO" if fed_r>2.5 else "✓ ACCOMODANTE"},
        {"name":"Consumer Sentiment", "val":str(cons_v),     "score":s3, "badge":badge_opp(s3), "label":"✓ PESSIMISMO" if cons_v<60 else "✓ CAUTELA" if cons_v<75 else "NEUTRO" if cons_v<90 else "EUFORIA"},
        {"name":"Yield 10Y−2Y",      "val":f"{yld_v:+}%",   "score":s4, "badge":badge_opp(s4), "label":"✓ INVERSIONE" if yld_v<-0.2 else "PIATTA" if yld_v<0 else "NORMALE"},
        {"name":"Disoccupaz. (US)",   "val":f"{unemp_v}%",   "score":s5, "badge":badge_opp(s5), "label":"IN AUMENTO" if unemp_v>5 else "STABILE"},
    ]
    if dot_signal:
        us_signals.append(dot_signal)

    # ── EU Macro ──────────────────────────────────────────────────────────────
    eu_signals = []
    eu_scores  = []

    if ecb:
        ecb_r = float(ecb[0]["value"])
        s = score_ecb_dca(ecb_r)
        eu_scores.append(s)
        eu_signals.append({"name":"BCE Deposit Rate","val":f"{ecb_r}%","score":s,"badge":badge_opp(s),"label":"RESTRITTIVO" if ecb_r>3 else "NEUTRO" if ecb_r>2 else "✓ ACCOMODANTE"})

    if eu_cpi_obs and len(eu_cpi_obs) >= 2:
        eu_now = float(eu_cpi_obs[0]["value"])
        eu_ago = float(eu_cpi_obs[min(12, len(eu_cpi_obs)-1)]["value"])
        eu_yoy = round((eu_now / eu_ago - 1) * 100, 2)
        s = score_eu_cpi_dca(eu_yoy)
        eu_scores.append(s)
        eu_signals.append({"name":"HICP YoY (EU)","val":f"{eu_yoy}%","score":s,"badge":badge_opp(s),"label":"ALTA" if eu_yoy>4 else "SOPRA TARGET" if eu_yoy>3 else "MODERATA" if eu_yoy>2 else "✓ TARGET"})

    if eurusd_obs:
        eurusd = float(eurusd_obs[0]["value"])
        s = score_eurusd_dca(eurusd)
        eu_scores.append(s)
        eu_signals.append({"name":"EUR/USD","val":f"{eurusd:.4f}","score":s,"badge":badge_opp(s),"label":"✓ EUR DEBOLE" if eurusd<1.05 else "NEUTRO" if eurusd<1.15 else "EUR FORTE"})

    eu_macro_score = round(sum(eu_scores) / len(eu_scores)) if eu_scores else 50
    macro_score = round((us_macro_score + eu_macro_score) / 2)

    return {
        "macro_score":    macro_score,
        "us_macro_score": us_macro_score,
        "eu_macro_score": eu_macro_score,
        "signals":        us_signals,
        "eu_signals":     eu_signals,
        "dot_plot_score": dot_score,
    }

# ─── NEWS & CONSULTING ────────────────────────────────────────────────────────
NEWS_QUERIES = [
    "S&P500 stock market selloff correction",
    "Federal Reserve rate cut pivot",
    "geopolitical risk financial markets",
    "inflation recession GDP global",
    "European stocks ECB rate cut",
    "emerging markets undervalued opportunity",
]

CONSULTING_QUERIES = [
    "Goldman Sachs market outlook buy opportunity 2025",
    "Morgan Stanley equities undervalued correction",
    "JPMorgan market recovery entry point",
    "BlackRock allocation opportunity emerging markets",
    "Citi UBS European stocks cheap valuation",
    "Deutsche Bank BNP Paribas European opportunity",
]

async def _fetch_headlines(queries, api_key, page_size=5, max_results=30):
    headlines, seen = [], set()
    async with httpx.AsyncClient() as client:
        responses = await asyncio.gather(*[
            client.get(f"{NEWS_BASE}?q={q}&language=en&sortBy=publishedAt&pageSize={page_size}&apiKey={api_key}", timeout=15)
            for q in queries
        ], return_exceptions=True)
    for resp in responses:
        if isinstance(resp, Exception): continue
        try:
            data = resp.json()
            if data.get("status") != "ok": continue
            for a in data.get("articles", []):
                title = a.get("title","").strip()
                desc  = a.get("description","").strip()
                if not title or title in seen: continue
                seen.add(title)
                headlines.append(f"• {title}: {desc}" if desc else f"• {title}")
        except Exception: continue
    return headlines[:max_results]

@app.get("/api/news")
async def get_news(api_key: str = Query(...)):
    headlines = await _fetch_headlines(NEWS_QUERIES, api_key)
    if not headlines: raise HTTPException(404, "Nessuna notizia trovata.")
    return {"count": len(headlines), "text": "\n".join(headlines)}

@app.get("/api/consulting-news")
async def get_consulting_news(api_key: str = Query(...)):
    headlines = await _fetch_headlines(CONSULTING_QUERIES, api_key, page_size=4, max_results=25)
    if not headlines: raise HTTPException(404, "Nessuna opinione trovata.")
    return {"count": len(headlines), "text": "\n".join(headlines)}

# ─── GROQ AI ──────────────────────────────────────────────────────────────────
async def call_groq(system_prompt, user_content):
    groq_key = os.environ.get("GROQ_API_KEY")
    if not groq_key: raise HTTPException(500, "GROQ_API_KEY non configurata")
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
    """
    Analizza il sentiment delle notizie in ottica DCA/PAC.
    Score alto = pessimismo/paura = opportunità di ingresso.
    """
    system = """Sei un analista finanziario specializzato in strategie DCA (Dollar Cost Averaging) a lungo termine.
Analizza le notizie e assegna un opportunity_score dove:
- 0-30 = notizie positive/euforiche, mercati cari, NON è buon momento per aumentare il PAC
- 31-55 = notizie miste, mercato neutro, PAC ordinario
- 56-75 = notizie negative/pessimistiche, mercato in correzione, BUONA opportunità per aumentare il PAC
- 76-100 = notizie molto negative, panico, OTTIMA opportunità per massimizzare il PAC

Logica: il pessimismo e la paura sono segnali di opportunità per un investitore DCA a lungo termine.
Esempi: "mercati in euforia, S&P500 ai massimi storici" → 15. "correzione mercati, timori recessione" → 68. "crash, panico, vendite massicce" → 90.

Considera sia USA che Europa ed emergenti.

Restituisci SOLO JSON:
{"opportunity_score":<0-100>,"market_mood":"<EUFORIA|OTTIMISMO|NEUTRO|PESSIMISMO|PANICO>","key_opportunities":["opp1","opp2","opp3"],"summary":"<2 frasi IT>","dca_recommendation":"<1 frase IT su cosa fare con il PAC>"}"""
    result = await call_groq(system, f"Analizza:\n\n{payload.text}")
    # Normalizza il campo
    score = result.get("opportunity_score", 50)
    if score >= 76:   result["market_mood"] = "PANICO"
    elif score >= 56: result["market_mood"] = "PESSIMISMO"
    elif score >= 31: result["market_mood"] = "NEUTRO"
    elif score >= 15: result["market_mood"] = "OTTIMISMO"
    else:             result["market_mood"] = "EUFORIA"
    return result

class ConsultingPayload(BaseModel):
    text: str

@app.post("/api/consulting-sentiment")
async def consulting_sentiment(payload: ConsultingPayload):
    """
    Analizza le opinioni delle banche in ottica DCA.
    Se le banche sono pessimiste = opportunità contrarian.
    """
    system = """Sei un analista che valuta le previsioni delle principali banche d'investimento in ottica DCA a lungo termine.
Assegna un opportunity_score dove:
- 0-30 = banche molto ottimiste, mercati cari, consensus rialzista → momento di cautela per il PAC
- 31-55 = previsioni miste → PAC ordinario
- 56-75 = banche caute/pessimiste → buona opportunità contrarian per il PAC
- 76-100 = banche molto pessimiste, prevedono crolli → ottima opportunità contrarian

Logica: quando le grandi banche sono pessimiste, spesso è il momento migliore per investire progressivamente.
Esempi: "Goldman prevede S&P500 a 7000, mercato rialzista" → 15. "JPMorgan taglia target, rischio recessione" → 68.

Restituisci SOLO JSON:
{"opportunity_score":<0-100>,"consensus":"<MOLTO_RIALZISTA|RIALZISTA|NEUTRO|RIBASSISTA|MOLTO_RIBASSISTA>","key_views":["v1","v2","v3"],"summary":"<2 frasi IT>","dca_signal":"<1 frase IT>"}"""
    result = await call_groq(system, f"Analizza:\n\n{payload.text}")
    score = result.get("opportunity_score", 50)
    if score >= 76:   result["consensus"] = "MOLTO_RIBASSISTA"
    elif score >= 56: result["consensus"] = "RIBASSISTA"
    elif score >= 31: result["consensus"] = "NEUTRO"
    elif score >= 15: result["consensus"] = "RIALZISTA"
    else:             result["consensus"] = "MOLTO_RIALZISTA"
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

def opp_emoji(s):
    if s >= 76: return "🟢🟢"
    if s >= 56: return "🟢"
    if s >= 31: return "⚪"
    return "🔴"

def build_message(p):
    emoji = opp_emoji(p.overall_score)
    trigger_label = "⚡ SEGNALE DCA" if p.trigger == "threshold" else "🔄 Aggiornamento"
    if p.overall_score >= 76:
        action = "🟢 OTTIMA OPPORTUNITÀ — Considera di massimizzare il PAC"
    elif p.overall_score >= 56:
        action = "🟡 BUONA OPPORTUNITÀ — Considera di incrementare il PAC"
    elif p.overall_score >= 31:
        action = "⚪ MERCATO NEUTRO — PAC ordinario come da piano"
    else:
        action = "🔴 MERCATO CARO — Riduci o sospendi nuovi ingressi"

    lines = [
        f"{emoji} *MarketSentinel DCA Signal*", f"_{trigger_label}_", "",
        f"*Opportunity Score: {p.overall_score}/100*", "",
        f"• Tecnico:   {p.tech_score}",
        f"• Macro:     {p.macro_score}",
        f"• Sentiment: {p.sent_score}",
    ]
    if p.top_signals:
        lines += ["", "*Segnali chiave:*"] + [f"  ↳ {s}" for s in p.top_signals[:3]]
    lines += ["", action]
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
    return {"status": "ok", "version": "6.0.0"}

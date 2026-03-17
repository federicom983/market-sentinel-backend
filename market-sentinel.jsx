import { useState, useEffect, useCallback, useRef } from "react";

const fontLink = document.createElement("link");
fontLink.rel = "stylesheet";
fontLink.href = "https://fonts.googleapis.com/css2?family=Space+Mono:ital,wght@0,400;0,700;1,400&family=Syne:wght@400;600;700;800&display=swap";
document.head.appendChild(fontLink);

const REFRESH_INTERVAL  = 60 * 60;
const BACKEND_URL       = "https://market-sentinel-backend-production.up.railway.app";
const LS_POLY_KEY       = "ms_polygon_key";
const LS_FRED_KEY       = "ms_fred_key";
const LS_TG_TOKEN       = "ms_tg_token";
const LS_TG_CHAT        = "ms_tg_chat";
const LS_NEWS_KEY       = "ms_news_key";
const ALERT_THRESHOLD   = 60;

const styles = `
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #080b0f; }
  .sentinel { min-height: 100vh; background: #080b0f; color: #c8d0d8; font-family: 'Space Mono', monospace; font-size: 13px; line-height: 1.6; padding: 24px; }
  .header { display: flex; align-items: baseline; justify-content: space-between; border-bottom: 1px solid #1e2830; padding-bottom: 16px; margin-bottom: 20px; }
  .header-left { display: flex; align-items: baseline; gap: 16px; }
  .logo { font-family: 'Syne', sans-serif; font-size: 22px; font-weight: 800; letter-spacing: -0.5px; color: #fff; }
  .logo span { color: #00e5a0; }
  .tagline { color: #3d5060; font-size: 11px; letter-spacing: 2px; text-transform: uppercase; }
  .clock { color: #3d5060; font-size: 11px; }

  .scheduler-bar { display: flex; align-items: center; gap: 16px; background: #080b0f; border: 1px solid #1a2330; border-radius: 6px; padding: 10px 16px; margin-bottom: 10px; font-size: 11px; }
  .scheduler-dot { width: 6px; height: 6px; border-radius: 50%; background: #00e5a0; box-shadow: 0 0 6px #00e5a0; flex-shrink: 0; animation: pulse 2s infinite; }
  .scheduler-dot.off { background: #3d5060; box-shadow: none; animation: none; }
  .scheduler-label { color: #3d5060; }
  .scheduler-countdown { color: #00e5a0; font-weight: 700; min-width: 50px; }
  .scheduler-countdown.off { color: #3d5060; }
  .btn-scheduler { background: transparent; border: 1px solid #1a3550; color: #5a7080; font-family: 'Space Mono', monospace; font-size: 10px; letter-spacing: 1px; text-transform: uppercase; padding: 4px 10px; border-radius: 3px; cursor: pointer; transition: all 0.2s; }
  .btn-scheduler:hover { border-color: #00e5a0; color: #00e5a0; }
  .btn-scheduler.active { border-color: #ff3c3c; color: #ff3c3c; }
  .btn-refresh { background: transparent; border: 1px solid #1a3550; color: #5a7080; font-family: 'Space Mono', monospace; font-size: 10px; letter-spacing: 1px; text-transform: uppercase; padding: 4px 10px; border-radius: 3px; cursor: pointer; transition: all 0.2s; }
  .btn-refresh:hover { border-color: #ffbe00; color: #ffbe00; }
  .btn-refresh:disabled { opacity: 0.3; cursor: not-allowed; }
  .keys-saved { color: #00e5a0; font-size: 10px; margin-left: auto; }
  .keys-missing { color: #3d5060; font-size: 10px; margin-left: auto; }

  .apikey-bar { display: flex; gap: 10px; align-items: center; background: #0d1219; border: 1px solid #1a2330; border-radius: 6px; padding: 12px 16px; margin-bottom: 10px; }
  .apikey-label { font-size: 10px; color: #3d5060; letter-spacing: 2px; text-transform: uppercase; white-space: nowrap; min-width: 110px; }
  .apikey-input { flex: 1; background: #080b0f; border: 1px solid #1a2330; color: #c8d0d8; font-family: 'Space Mono', monospace; font-size: 12px; padding: 6px 10px; border-radius: 4px; outline: none; transition: border-color 0.2s; }
  .apikey-input:focus { border-color: #2a3f55; }
  .btn-fetch { background: #0d1e2e; border: 1px solid #1a3550; color: #00e5a0; font-family: 'Space Mono', monospace; font-size: 11px; letter-spacing: 2px; text-transform: uppercase; padding: 7px 16px; border-radius: 4px; cursor: pointer; white-space: nowrap; transition: all 0.2s; }
  .btn-fetch:hover { background: #112234; border-color: #00e5a0; }
  .btn-fetch:disabled { opacity: 0.4; cursor: not-allowed; }
  .fetch-status { font-size: 11px; white-space: nowrap; min-width: 160px; }
  .btn-clear { background: transparent; border: none; color: #3d5060; font-size: 10px; cursor: pointer; padding: 4px; transition: color 0.2s; white-space: nowrap; }
  .btn-clear:hover { color: #ff3c3c; }

  .tg-bar { display: flex; gap: 10px; align-items: center; background: #0a1520; border: 1px solid #1a2d40; border-radius: 6px; padding: 12px 16px; margin-bottom: 10px; }
  .tg-label { font-size: 10px; color: #2a5070; letter-spacing: 2px; text-transform: uppercase; white-space: nowrap; min-width: 110px; }
  .tg-status { font-size: 10px; white-space: nowrap; }
  .btn-test { background: transparent; border: 1px solid #1a3550; color: #3d8fb5; font-family: 'Space Mono', monospace; font-size: 10px; letter-spacing: 1px; text-transform: uppercase; padding: 4px 10px; border-radius: 3px; cursor: pointer; transition: all 0.2s; white-space: nowrap; }
  .btn-test:hover { border-color: #3d8fb5; color: #5ab0d8; }
  .btn-test:disabled { opacity: 0.3; cursor: not-allowed; }

  .alert-banner { display: flex; align-items: center; gap: 12px; padding: 12px 18px; border-radius: 4px; margin-bottom: 20px; border-left: 3px solid; transition: all 0.4s ease; font-size: 12px; letter-spacing: 0.5px; }
  .alert-banner.safe   { background: rgba(0,229,160,0.06); border-color: #00e5a0; color: #00e5a0; }
  .alert-banner.watch  { background: rgba(255,190,0,0.06);  border-color: #ffbe00; color: #ffbe00; }
  .alert-banner.danger { background: rgba(255,60,60,0.08);  border-color: #ff3c3c; color: #ff3c3c; }
  .alert-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; animation: pulse 2s infinite; }
  .alert-banner.safe .alert-dot   { background: #00e5a0; box-shadow: 0 0 8px #00e5a0; }
  .alert-banner.watch .alert-dot  { background: #ffbe00; box-shadow: 0 0 8px #ffbe00; }
  .alert-banner.danger .alert-dot { background: #ff3c3c; box-shadow: 0 0 12px #ff3c3c; }
  @keyframes pulse { 0%,100%{opacity:1;transform:scale(1);} 50%{opacity:0.5;transform:scale(0.8);} }

  .grid-main   { display: grid; grid-template-columns: 280px 1fr 1fr; gap: 16px; margin-bottom: 16px; }
  .grid-bottom { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; }
  .card { background: #0d1219; border: 1px solid #1a2330; border-radius: 6px; padding: 20px; }
  .card-title { font-family: 'Syne', sans-serif; font-size: 10px; font-weight: 700; letter-spacing: 3px; text-transform: uppercase; color: #3d5060; margin-bottom: 16px; }

  .market-strip { display: flex; gap: 0; flex-wrap: wrap; margin-bottom: 16px; background: #0d1219; border: 1px solid #1a2330; border-radius: 6px; overflow: hidden; margin-top: 6px; }
  .mk-item { display: flex; flex-direction: column; padding: 12px 20px; border-right: 1px solid #1a2330; flex: 1; min-width: 110px; }
  .mk-item:last-child { border-right: none; }
  .mk-name { font-size: 10px; color: #3d5060; letter-spacing: 1px; text-transform: uppercase; margin-bottom: 2px; }
  .mk-val { font-size: 14px; font-weight: 700; font-family: 'Syne', sans-serif; color: #c8d0d8; }
  .mk-chg { font-size: 10px; }
  .mk-src { font-size: 9px; color: #2a3f55; margin-top: 1px; }
  .pos { color: #00e5a0; } .neg { color: #ff3c3c; } .neu { color: #5a7080; }

  .gauge-wrap { display: flex; flex-direction: column; align-items: center; gap: 8px; }
  .gauge-score { font-family: 'Syne', sans-serif; font-size: 52px; font-weight: 800; line-height: 1; text-align: center; letter-spacing: -2px; }
  .gauge-label { font-size: 10px; letter-spacing: 3px; text-transform: uppercase; text-align: center; }
  .gauge-breakdown { width: 100%; margin-top: 8px; }
  .gb-row { display: flex; justify-content: space-between; align-items: center; padding: 4px 0; border-bottom: 1px solid #111; font-size: 11px; }
  .gb-row:last-child { border: none; }
  .gb-label { color: #3d5060; }
  .gb-bar-wrap { flex: 1; margin: 0 10px; height: 3px; background: #1a2330; border-radius: 2px; }
  .gb-bar { height: 100%; border-radius: 2px; transition: width 0.8s ease; }

  .sig-table { width: 100%; border-collapse: collapse; }
  .sig-table tr { border-bottom: 1px solid #111; }
  .sig-table tr:last-child { border: none; }
  .sig-table td { padding: 9px 0; vertical-align: middle; }
  .sig-name { color: #8fa0b0; font-size: 11px; width: 52%; }
  .sig-val { font-size: 12px; font-weight: 700; width: 22%; text-align: right; padding-right: 8px !important; }
  .sig-badge { display: inline-block; padding: 2px 7px; border-radius: 2px; font-size: 9px; letter-spacing: 1px; text-transform: uppercase; font-weight: 700; float: right; }
  .badge-green  { background: rgba(0,229,160,0.12); color: #00e5a0; }
  .badge-yellow { background: rgba(255,190,0,0.12);  color: #ffbe00; }
  .badge-red    { background: rgba(255,60,60,0.12);   color: #ff3c3c; }
  .badge-gray   { background: rgba(100,120,140,0.12); color: #5a7080; }

  .data-tag { display: inline-block; padding: 1px 6px; border-radius: 2px; font-size: 9px; letter-spacing: 1px; margin-left: 6px; vertical-align: middle; }
  .data-tag.live { background: rgba(0,229,160,0.1); color: #00e5a0; }
  .data-tag.wait { background: rgba(90,112,128,0.15); color: #5a7080; }

  .news-input { width: 100%; background: #080b0f; border: 1px solid #1a2330; color: #c8d0d8; font-family: 'Space Mono', monospace; font-size: 12px; padding: 10px 12px; border-radius: 4px; resize: vertical; min-height: 80px; outline: none; line-height: 1.5; transition: border-color 0.2s; }
  .news-input:focus { border-color: #2a3f55; }
  .news-input::placeholder { color: #2a3f55; }
  .news-actions { display: flex; gap: 8px; margin-top: 10px; }
  .btn-analyze { flex: 1; background: #0d1e2e; border: 1px solid #1a3550; color: #00e5a0; font-family: 'Space Mono', monospace; font-size: 11px; letter-spacing: 2px; text-transform: uppercase; padding: 10px; border-radius: 4px; cursor: pointer; transition: all 0.2s; }
  .btn-analyze:hover { background: #112234; border-color: #00e5a0; }
  .btn-analyze:disabled { opacity: 0.4; cursor: not-allowed; }
  .btn-fetch-news { background: #0d1a2e; border: 1px solid #1a3040; color: #3d8fb5; font-family: 'Space Mono', monospace; font-size: 11px; letter-spacing: 2px; text-transform: uppercase; padding: 10px 16px; border-radius: 4px; cursor: pointer; transition: all 0.2s; white-space: nowrap; }
  .btn-fetch-news:hover { background: #0f2035; border-color: #3d8fb5; }
  .btn-fetch-news:disabled { opacity: 0.4; cursor: not-allowed; }
  .news-count { font-size: 10px; color: #3d5060; margin-top: 6px; }

  .sentiment-result { margin-top: 14px; padding: 12px; background: #080b0f; border: 1px solid #1a2330; border-radius: 4px; font-size: 11px; line-height: 1.8; color: #8fa0b0; animation: fadeIn 0.4s ease; }
  @keyframes fadeIn { from{opacity:0;transform:translateY(4px);} to{opacity:1;transform:none;} }
  .sentiment-score-row { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
  .sentiment-score-num { font-family: 'Syne', sans-serif; font-size: 28px; font-weight: 800; }
  .sentiment-score-label { font-size: 10px; letter-spacing: 2px; color: #3d5060; text-transform: uppercase; }

  .alert-history { display: flex; flex-direction: column; gap: 8px; max-height: 220px; overflow-y: auto; }
  .ah-item { display: flex; gap: 10px; padding: 8px 10px; background: #080b0f; border-radius: 3px; border-left: 2px solid; font-size: 11px; line-height: 1.5; }
  .ah-time { color: #3d5060; white-space: nowrap; min-width: 50px; }
  .ah-text { color: #8fa0b0; }
  .section-note { font-size: 10px; color: #2a3f55; margin-top: 10px; border-top: 1px solid #111; padding-top: 10px; font-style: italic; }
  .skeleton { background: linear-gradient(90deg,#1a2330 25%,#1e2a3a 50%,#1a2330 75%); background-size:200% 100%; animation:shimmer 1.5s infinite; border-radius:3px; display:inline-block; height:12px; }
  @keyframes shimmer { 0%{background-position:200% 0;} 100%{background-position:-200% 0;} }
  .loading-dots::after { content:'...'; display:inline-block; animation:dots 1.2s steps(4,end) infinite; }
  @keyframes dots { 0%,20%{content:'.';} 40%{content:'..';} 60%,100%{content:'...';} }
`;

// ─── INDICATORS ───────────────────────────────────────────────────────────────
function calcRSI(closes, period=14) {
  if (closes.length<period+1) return null;
  let gains=0,losses=0;
  for (let i=closes.length-period;i<closes.length;i++) {
    const d=closes[i]-closes[i-1]; if(d>0) gains+=d; else losses-=d;
  }
  const ag=gains/period,al=losses/period;
  if (al===0) return 100;
  return parseFloat((100-100/(1+ag/al)).toFixed(1));
}
function calcSMA(arr,n){if(arr.length<n)return null;return arr.slice(-n).reduce((a,b)=>a+b,0)/n;}
function calcEMA(arr,n){
  if(arr.length<n)return null;
  const k=2/(n+1);let ema=arr.slice(0,n).reduce((a,b)=>a+b,0)/n;
  for(let i=n;i<arr.length;i++)ema=arr[i]*k+ema*(1-k);return ema;
}
function calcMACD(arr){const e12=calcEMA(arr,12),e26=calcEMA(arr,26);if(!e12||!e26)return null;return parseFloat((e12-e26).toFixed(2));}

// ─── SCORING ─────────────────────────────────────────────────────────────────
const riskColor=(s)=>s>=75?"#ff3c3c":s>=55?"#ffbe00":"#00e5a0";
const riskLabel=(s)=>{
  if(s>=75)return{text:"⚠ RISCHIO ELEVATO — Valutare riduzione esposizione",cls:"danger"};
  if(s>=55)return{text:"◈ ATTENZIONE — Monitorare segnali in evoluzione",cls:"watch"};
  return{text:"✓ MERCATO STABILE — Nessuna azione raccomandata",cls:"safe"};
};
const badgeFn=(sc)=>sc>=70?"red":sc>=50?"yellow":"green";
const scoreRSI=(r)=>!r?50:r>80?90:r>70?75:r>60?55:r<30?15:30;
const scoreVIXY=(v)=>!v?50:v>30?90:v>22?75:v>16?50:25;
const scoreMACross=(a,b)=>!a||!b?50:a/b<0.98?80:a/b<1.0?60:a/b>1.05?20:35;
const scoreMACDFn=(m)=>!m?50:m<-5?78:m<-2?62:m>3?35:48;

// ─── POLYGON ─────────────────────────────────────────────────────────────────
const sleep=(ms)=>new Promise(r=>setTimeout(r,ms));
const DELAY=13500;
async function polyGet(path,key){
  const sep=path.includes("?")?"&":"?";
  const r=await fetch(`https://api.polygon.io${path}${sep}apiKey=${key}`);
  if(!r.ok)throw new Error(`Polygon ${r.status}`);
  return r.json();
}
function daysAgo(n){const d=new Date();d.setDate(d.getDate()-n);return d.toISOString().split("T")[0];}
async function getBars(ticker,key,days=220){
  const data=await polyGet(`/v2/aggs/ticker/${ticker}/range/1/day/${daysAgo(days+60)}/${daysAgo(1)}?adjusted=true&sort=asc&limit=300`,key);
  if(!data.results?.length)throw new Error(`Nessun dato per ${ticker}`);
  return data.results;
}
async function getPrev(ticker,key){
  const data=await polyGet(`/v2/aggs/ticker/${ticker}/prev`,key);
  if(!data.results?.length)throw new Error(`Nessun prev close per ${ticker}`);
  return data.results[0];
}

// ─── BACKEND CALLS ────────────────────────────────────────────────────────────
async function fetchFredData(fredKey){
  const r=await fetch(`${BACKEND_URL}/api/fred-data?api_key=${fredKey}`);
  if(!r.ok){const e=await r.json().catch(()=>({}));throw new Error(e.detail||`HTTP ${r.status}`);}
  return r.json();
}
async function fetchNews(newsKey){
  const r=await fetch(`${BACKEND_URL}/api/news?api_key=${newsKey}`);
  if(!r.ok){const e=await r.json().catch(()=>({}));throw new Error(e.detail||`HTTP ${r.status}`);}
  return r.json();
}
async function sendTelegramAlert(payload){
  const r=await fetch(`${BACKEND_URL}/api/send-alert`,{
    method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload),
  });
  if(!r.ok){const e=await r.json().catch(()=>({}));throw new Error(e.detail||`HTTP ${r.status}`);}
  return r.json();
}

// ─── UTILS ───────────────────────────────────────────────────────────────────
function formatCountdown(secs){
  const m=Math.floor(secs/60).toString().padStart(2,"0");
  const s=(secs%60).toString().padStart(2,"0");
  return `${m}:${s}`;
}

// ─── GAUGE ───────────────────────────────────────────────────────────────────
function ArcGauge({score}){
  const color=riskColor(score);
  const toRad=d=>d*Math.PI/180;
  const arc=(s,e,r)=>{
    const x1=100+r*Math.cos(toRad(s)),y1=100+r*Math.sin(toRad(s));
    const x2=100+r*Math.cos(toRad(e)),y2=100+r*Math.sin(toRad(e));
    return `M ${x1} ${y1} A ${r} ${r} 0 ${e-s>180?1:0} 1 ${x2} ${y2}`;
  };
  return(
    <svg viewBox="0 0 200 140" width="200" height="140" style={{filter:"drop-shadow(0 0 12px rgba(0,229,160,0.12))"}}>
      <path d={arc(200,540,80)} fill="none" stroke="#1a2330" strokeWidth="12" strokeLinecap="round"/>
      <path d={arc(200,200+(score/100)*340,80)} fill="none" stroke={color} strokeWidth="12" strokeLinecap="round"
        style={{filter:`drop-shadow(0 0 6px ${color})`,transition:"all 1s ease"}}/>
      <text x="100" y="108" textAnchor="middle" fill={color}
        style={{fontFamily:"'Syne',sans-serif",fontSize:36,fontWeight:800}}>{score}</text>
      <text x="100" y="124" textAnchor="middle" fill="#3d5060"
        style={{fontFamily:"'Space Mono',monospace",fontSize:9,letterSpacing:2}}>RISK SCORE</text>
    </svg>
  );
}

function SigRow({name,val,badge,label,shimmer}){
  const valColor=badge==="red"?"#ff3c3c":badge==="yellow"?"#ffbe00":badge==="green"?"#00e5a0":"#5a7080";
  return(
    <tr>
      <td className="sig-name">{name}</td>
      <td className="sig-val" style={{color:valColor}}>{shimmer?<span className="skeleton" style={{width:44}}/>:val}</td>
      <td><span className={`sig-badge badge-${badge||"gray"}`}>{shimmer?"—":label}</span></td>
    </tr>
  );
}

async function claudeSentiment(text){
  const r=await fetch("https://api.anthropic.com/v1/messages",{
    method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({
      model:"claude-sonnet-4-20250514",max_tokens:1000,
      system:`Analista finanziario. SOLO JSON valido:
{"sentiment_score":<0-100>,"risk_level":"<BASSO|MEDIO|ELEVATO|CRITICO>","key_risks":["r1","r2","r3"],"summary":"<2 frasi IT>","recommended_action":"<1 frase IT>"}`,
      messages:[{role:"user",content:`Analizza:\n\n${text}`}],
    }),
  });
  const d=await r.json();
  return JSON.parse(d.content.map(b=>b.text||"").join("").replace(/```json|```/g,"").trim());
}

const EMPTY_MKT  = ["S&P500 (SPY)","Nasdaq (QQQ)","VIXY","Gold (GLD)","Dollar (UUP)"].map(n=>({name:n,val:"—",chg:"—",dir:"neu"}));
const EMPTY_TECH = ["VIXY (VIX proxy)","RSI SPY 14d","RSI QQQ 14d","SPY MA50/MA200","MACD SPY"].map(n=>({name:n,val:"—",badge:"gray",label:"—"}));
const EMPTY_MACRO= ["CPI YoY (US)","Fed Funds Rate","Consumer Sentiment","Yield 10Y−2Y","Disoccupazione"].map(n=>({name:n,val:"—",badge:"gray",label:"—"}));

// ─── APP ──────────────────────────────────────────────────────────────────────
export default function MarketSentinel(){
  const [polyKey,setPolyKeyRaw] = useState(()=>localStorage.getItem(LS_POLY_KEY)||"");
  const [fredKey,setFredKeyRaw] = useState(()=>localStorage.getItem(LS_FRED_KEY)||"");
  const [tgToken,setTgTokenRaw] = useState(()=>localStorage.getItem(LS_TG_TOKEN)||"");
  const [tgChat,setTgChatRaw]   = useState(()=>localStorage.getItem(LS_TG_CHAT)||"");
  const [newsKey,setNewsKeyRaw] = useState(()=>localStorage.getItem(LS_NEWS_KEY)||"");

  const setPolyKey=v=>{setPolyKeyRaw(v);v?localStorage.setItem(LS_POLY_KEY,v):localStorage.removeItem(LS_POLY_KEY);};
  const setFredKey=v=>{setFredKeyRaw(v);v?localStorage.setItem(LS_FRED_KEY,v):localStorage.removeItem(LS_FRED_KEY);};
  const setTgToken=v=>{setTgTokenRaw(v);v?localStorage.setItem(LS_TG_TOKEN,v):localStorage.removeItem(LS_TG_TOKEN);};
  const setTgChat=v=>{setTgChatRaw(v);v?localStorage.setItem(LS_TG_CHAT,v):localStorage.removeItem(LS_TG_CHAT);};
  const setNewsKey=v=>{setNewsKeyRaw(v);v?localStorage.setItem(LS_NEWS_KEY,v):localStorage.removeItem(LS_NEWS_KEY);};

  const [clock,setClock]               = useState("");
  const [polyStatus,setPolyStatus]     = useState(null);
  const [polyMsg,setPolyMsg]           = useState("");
  const [polyUpdate,setPolyUpdate]     = useState(null);
  const [marketData,setMarketData]     = useState(null);
  const [techSignals,setTechSignals]   = useState(null);
  const [techScore,setTechScore]       = useState(null);
  const [fredStatus,setFredStatus]     = useState(null);
  const [fredMsg,setFredMsg]           = useState("");
  const [fredUpdate,setFredUpdate]     = useState(null);
  const [macroSignals,setMacroSignals] = useState(null);
  const [macroScore,setMacroScore]     = useState(null);
  const [newsText,setNewsText]         = useState("");
  const [newsLoading,setNewsLoading]   = useState(false);
  const [newsCount,setNewsCount]       = useState(null);
  const [aiLoading,setAiLoading]       = useState(false);
  const [sentiment,setSentiment]       = useState(null);
  const [sentScore,setSentScore]       = useState(null);
  const [tgStatus,setTgStatus]         = useState(null);
  const [alerts,setAlerts] = useState([
    {time:"—",color:"#3d5060",text:"Carica i dati per attivare il monitoraggio live."},
  ]);

  const [schedulerOn,setSchedulerOn]   = useState(false);
  const [countdown,setCountdown]       = useState(REFRESH_INTERVAL);
  const countdownRef                   = useRef(REFRESH_INTERVAL);
  const schedulerIntervalRef           = useRef(null);
  const lastAlertScoreRef              = useRef(null);

  useEffect(()=>{
    const id=setInterval(()=>setClock(
      new Date().toLocaleTimeString("it-IT",{hour:"2-digit",minute:"2-digit",second:"2-digit"})+" CET"
    ),1000);
    return()=>clearInterval(id);
  },[]);

  // ── TELEGRAM ────────────────────────────────────────────────────────────────
  const sendAlert=useCallback(async(overall,tScore,mScore,sScore,trigger,topSignals=[])=>{
    if(!tgToken.trim()||!tgChat.trim())return;
    setTgStatus("sending");
    try{
      await sendTelegramAlert({bot_token:tgToken.trim(),chat_id:tgChat.trim(),overall_score:overall,tech_score:tScore,macro_score:mScore,sent_score:sScore,trigger,top_signals:topSignals});
      setTgStatus("ok");
      const t=new Date().toLocaleTimeString("it-IT",{hour:"2-digit",minute:"2-digit"});
      setAlerts(p=>[{time:t,color:"#3d8fb5",text:`📱 Alert Telegram inviato (score ${overall})`},...p]);
    }catch(e){setTgStatus("error");console.error("TG:",e.message);}
  },[tgToken,tgChat]);

  // ── POLYGON ──────────────────────────────────────────────────────────────────
  const fetchPolygon=useCallback(async(key)=>{
    const k=key||polyKey;if(!k.trim())return null;
    setPolyStatus("loading");setPolyMsg("Caricamento SPY…");
    try{
      const spyBars=await getBars("SPY",k);await sleep(DELAY);
      setPolyMsg("Caricamento QQQ…");
      const qqqBars=await getBars("QQQ",k);await sleep(DELAY);
      setPolyMsg("Caricamento VIXY…");
      let vixyBars=null;try{vixyBars=await getBars("VIXY",k,30);}catch(_){}
      await sleep(DELAY);setPolyMsg("Caricamento GLD…");
      const gldPrev=await getPrev("GLD",k);await sleep(DELAY);
      setPolyMsg("Caricamento UUP…");
      const uupPrev=await getPrev("UUP",k);

      const spyC=spyBars.map(b=>b.c),qqqC=qqqBars.map(b=>b.c);
      const spyLast=spyC.at(-1),spyPrev2=spyC.at(-2);
      const qqqLast=qqqC.at(-1),qqqPrev2=qqqC.at(-2);
      const spyChg=(spyLast-spyPrev2)/spyPrev2*100;
      const qqqChg=(qqqLast-qqqPrev2)/qqqPrev2*100;
      const spyRSI=calcRSI(spyC),qqqRSI=calcRSI(qqqC);
      const ma50=calcSMA(spyC,50),ma200=calcSMA(spyC,200);
      const macd=calcMACD(spyC);
      const vixyLast=vixyBars?.at(-1)?.c??null;
      const vixyPrev=vixyBars?.at(-2)?.c??null;
      const vixyChg=vixyLast&&vixyPrev?(vixyLast-vixyPrev)/vixyPrev*100:null;
      const maRatio=ma50&&ma200?ma50/ma200:null;
      const gldChg=(gldPrev.c-gldPrev.o)/gldPrev.o*100;
      const uupChg=(uupPrev.c-uupPrev.o)/uupPrev.o*100;

      const s1=scoreRSI(spyRSI),s2=scoreRSI(qqqRSI),s3=scoreVIXY(vixyLast),s4=scoreMACross(ma50,ma200),s5=scoreMACDFn(macd);
      const tScore=Math.round((s1+s2+s3+s4+s5)/5);
      setTechScore(tScore);
      const sigs=[
        {name:"VIXY (VIX proxy)",val:vixyLast?vixyLast.toFixed(2):"N/A",score:s3,badge:badgeFn(s3),label:s3>=70?"ELEVATO":s3>=50?"MEDIO":"BASSO"},
        {name:"RSI SPY 14d",val:spyRSI?.toString()??"N/A",score:s1,badge:badgeFn(s1),label:(spyRSI??0)>70?"OVERBOUGHT":(spyRSI??100)<30?"OVERSOLD":"NEUTRO"},
        {name:"RSI QQQ 14d",val:qqqRSI?.toString()??"N/A",score:s2,badge:badgeFn(s2),label:(qqqRSI??0)>70?"OVERBOUGHT":(qqqRSI??100)<30?"OVERSOLD":"NEUTRO"},
        {name:"SPY MA50/MA200",val:maRatio?maRatio.toFixed(3):"N/A",score:s4,badge:badgeFn(s4),label:!maRatio?"N/A":maRatio<0.98?"DEATH CROSS":maRatio<1?"NEGATIVO":"GOLDEN X"},
        {name:"MACD SPY",val:macd?.toString()??"N/A",score:s5,badge:badgeFn(s5),label:(macd??0)<-2?"RIBASSISTA":(macd??0)>2?"RIALZISTA":"NEUTRO"},
      ];
      setTechSignals(sigs);
      setMarketData([
        {name:"S&P500 (SPY)",val:`$${spyLast.toFixed(2)}`,chg:`${spyChg>=0?"+":""}${spyChg.toFixed(2)}%`,dir:spyChg>=0?"pos":"neg"},
        {name:"Nasdaq (QQQ)",val:`$${qqqLast.toFixed(2)}`,chg:`${qqqChg>=0?"+":""}${qqqChg.toFixed(2)}%`,dir:qqqChg>=0?"pos":"neg"},
        {name:"VIXY",val:vixyLast?vixyLast.toFixed(2):"N/A",chg:vixyChg!=null?`${vixyChg>=0?"+":""}${vixyChg.toFixed(2)}%`:"—",dir:(vixyChg??0)>=0?"neg":"pos"},
        {name:"Gold (GLD)",val:`$${gldPrev.c.toFixed(2)}`,chg:`${gldChg>=0?"+":""}${gldChg.toFixed(2)}%`,dir:gldChg>=0?"pos":"neg"},
        {name:"Dollar (UUP)",val:`$${uupPrev.c.toFixed(2)}`,chg:`${uupChg>=0?"+":""}${uupChg.toFixed(2)}%`,dir:uupChg>=0?"pos":"neg"},
      ]);
      setPolyUpdate(new Date().toLocaleTimeString("it-IT",{hour:"2-digit",minute:"2-digit"}));
      setPolyStatus("ok");setPolyMsg("");
      return{tScore,topSignals:sigs.filter(s=>s.score>=60).map(s=>`${s.name}: ${s.label}`)};
    }catch(e){setPolyStatus("error");setPolyMsg(e.message||"Errore");return null;}
  },[polyKey]);

  // ── FRED ─────────────────────────────────────────────────────────────────────
  const fetchFred=useCallback(async(key)=>{
    const k=key||fredKey;if(!k.trim())return null;
    setFredStatus("loading");setFredMsg("Connessione backend…");
    try{
      const data=await fetchFredData(k);
      setMacroScore(data.macro_score);setMacroSignals(data.signals);
      setFredUpdate(new Date().toLocaleTimeString("it-IT",{hour:"2-digit",minute:"2-digit"}));
      setFredStatus("ok");setFredMsg("");
      return{mScore:data.macro_score,topSignals:data.signals.filter(s=>s.score>=60).map(s=>`${s.name}: ${s.label}`)};
    }catch(e){setFredStatus("error");setFredMsg(e.message||"Errore");return null;}
  },[fredKey]);

  // ── NEWS FETCH ────────────────────────────────────────────────────────────────
  const fetchNewsAuto=useCallback(async()=>{
    if(!newsKey.trim())return;
    setNewsLoading(true);
    try{
      const data=await fetchNews(newsKey.trim());
      setNewsText(data.text);
      setNewsCount(data.count);
    }catch(e){
      const t=new Date().toLocaleTimeString("it-IT",{hour:"2-digit",minute:"2-digit"});
      setAlerts(p=>[{time:t,color:"#ff3c3c",text:`NewsAPI: ${e.message}`},...p]);
    }
    setNewsLoading(false);
  },[newsKey]);

  // ── FETCH ALL ─────────────────────────────────────────────────────────────────
  const fetchAll=useCallback(async(trigger="refresh")=>{
    const[polyResult,fredResult]=await Promise.allSettled([
      fetchPolygon(polyKey),fetchFred(fredKey),
    ]);
    const tScore=polyResult.status==="fulfilled"?polyResult.value?.tScore??50:50;
    const mScore=fredResult.status==="fulfilled"?fredResult.value?.mScore??50:50;
    const sScore=sentScore??50;
    const overall=Math.round(tScore*0.4+mScore*0.3+sScore*0.3);
    const topSignals=[...(polyResult.value?.topSignals||[]),...(fredResult.value?.topSignals||[])];
    sendAlert(overall,tScore,mScore,sScore,"refresh",topSignals);
    if(overall>=ALERT_THRESHOLD&&(lastAlertScoreRef.current??0)<ALERT_THRESHOLD){
      sendAlert(overall,tScore,mScore,sScore,"threshold",topSignals);
    }
    lastAlertScoreRef.current=overall;
    // Auto-fetch news se la key è configurata
    if(newsKey.trim()) fetchNewsAuto();
    const t=new Date().toLocaleTimeString("it-IT",{hour:"2-digit",minute:"2-digit"});
    setAlerts(p=>[{time:t,color:overall>=75?"#ff3c3c":overall>=60?"#ffbe00":"#3d5060",text:`Dati aggiornati. Risk Score: ${overall}/100`},...p]);
  },[fetchPolygon,fetchFred,sentScore,sendAlert,polyKey,fredKey,newsKey,fetchNewsAuto]);

  // ── SCHEDULER ────────────────────────────────────────────────────────────────
  useEffect(()=>{
    if(!schedulerOn){
      if(schedulerIntervalRef.current)clearInterval(schedulerIntervalRef.current);
      setCountdown(REFRESH_INTERVAL);countdownRef.current=REFRESH_INTERVAL;return;
    }
    fetchAll("refresh");
    countdownRef.current=REFRESH_INTERVAL;setCountdown(REFRESH_INTERVAL);
    schedulerIntervalRef.current=setInterval(()=>{
      countdownRef.current-=1;setCountdown(countdownRef.current);
      if(countdownRef.current<=0){fetchAll("refresh");countdownRef.current=REFRESH_INTERVAL;setCountdown(REFRESH_INTERVAL);}
    },1000);
    return()=>{if(schedulerIntervalRef.current)clearInterval(schedulerIntervalRef.current);};
  },[schedulerOn]); // eslint-disable-line

  useEffect(()=>{
    const pk=localStorage.getItem(LS_POLY_KEY);
    const fk=localStorage.getItem(LS_FRED_KEY);
    if(pk)fetchPolygon(pk);
    if(fk)fetchFred(fk);
  },[]); // eslint-disable-line

  // ── SENTIMENT ────────────────────────────────────────────────────────────────
  const handleAnalyze=useCallback(async()=>{
    if(!newsText.trim())return;
    setAiLoading(true);setSentiment(null);
    try{
      const r=await claudeSentiment(newsText);
      setSentiment(r);setSentScore(r.sentiment_score);
      if(r.sentiment_score>=55){
        const t=new Date().toLocaleTimeString("it-IT",{hour:"2-digit",minute:"2-digit"});
        setAlerts(p=>[{time:t,color:r.sentiment_score>=75?"#ff3c3c":"#ffbe00",text:`AI: ${r.risk_level} (${r.sentiment_score}). ${r.recommended_action}`},...p]);
      }
    }catch{setSentiment({error:"Errore analisi AI."});}
    setAiLoading(false);
  },[newsText]);

  const testTelegram=useCallback(async()=>{
    await sendAlert(42,38,45,44,"refresh",["Test connessione MarketSentinel"]);
  },[sendAlert]);

  const tScore=techScore??50;
  const mScore=macroScore??50;
  const sentW=sentScore??50;
  const overall=Math.round(tScore*0.4+mScore*0.3+sentW*0.3);
  const alertInfo=riskLabel(overall);
  const color=riskColor(overall);
  const isPolyLoading=polyStatus==="loading";
  const isFredLoading=fredStatus==="loading";
  const isLoading=isPolyLoading||isFredLoading;
  const hasBothKeys=!!polyKey.trim()&&!!fredKey.trim();
  const hasTgConfig=!!tgToken.trim()&&!!tgChat.trim();

  return(
    <>
      <style>{styles}</style>
      <div className="sentinel">

        <div className="header">
          <div className="header-left">
            <div className="logo">MARKET<span>SENTINEL</span></div>
            <div className="tagline">Early Warning System</div>
          </div>
          <div className="clock">◉ {clock}</div>
        </div>

        {/* SCHEDULER */}
        <div className="scheduler-bar">
          <div className={`scheduler-dot ${schedulerOn?"":"off"}`}/>
          <span className="scheduler-label">Auto-refresh:</span>
          <span className={`scheduler-countdown ${schedulerOn?"":"off"}`}>{schedulerOn?formatCountdown(countdown):"—"}</span>
          <button className={`btn-scheduler ${schedulerOn?"active":""}`} onClick={()=>setSchedulerOn(v=>!v)} disabled={!hasBothKeys}>
            {schedulerOn?"■ Stop":"▶ Avvia"}
          </button>
          <button className="btn-refresh" onClick={()=>fetchAll("refresh")} disabled={!hasBothKeys||isLoading}>↺ Refresh ora</button>
          <span className={hasBothKeys?"keys-saved":"keys-missing"}>{hasBothKeys?"● Key salvate":"○ Inserisci le key per attivare"}</span>
        </div>

        {/* POLYGON */}
        <div className="apikey-bar">
          <span className="apikey-label">Polygon.io Key</span>
          <input className="apikey-input" type="password" placeholder="API key Polygon.io…" value={polyKey} onChange={e=>setPolyKey(e.target.value)}/>
          <button className="btn-fetch" onClick={()=>fetchPolygon()} disabled={!polyKey.trim()||isPolyLoading}>
            {isPolyLoading?<span className="loading-dots">Fetch</span>:"▶ Carica"}
          </button>
          <span className="fetch-status" style={{color:polyStatus==="ok"?"#00e5a0":polyStatus==="error"?"#ff3c3c":polyStatus==="loading"?"#ffbe00":"#3d5060"}}>
            {polyStatus==="ok"&&`✓ ${polyUpdate} (EOD)`}{polyStatus==="error"&&`✗ ${polyMsg}`}
            {polyStatus==="loading"&&`⏳ ${polyMsg} (~65s)`}{polyStatus===null&&"— In attesa"}
          </span>
          {polyKey&&<button className="btn-clear" onClick={()=>setPolyKey("")}>✕</button>}
        </div>

        {/* FRED */}
        <div className="apikey-bar">
          <span className="apikey-label">FRED API Key</span>
          <input className="apikey-input" type="password" placeholder="API key St. Louis Fed…" value={fredKey} onChange={e=>setFredKey(e.target.value)}/>
          <button className="btn-fetch" onClick={()=>fetchFred()} disabled={!fredKey.trim()||isFredLoading}>
            {isFredLoading?<span className="loading-dots">Fetch</span>:"▶ Carica"}
          </button>
          <span className="fetch-status" style={{color:fredStatus==="ok"?"#00e5a0":fredStatus==="error"?"#ff3c3c":fredStatus==="loading"?"#ffbe00":"#3d5060"}}>
            {fredStatus==="ok"&&`✓ ${fredUpdate} (live)`}{fredStatus==="error"&&`✗ ${fredMsg}`}
            {fredStatus==="loading"&&`⏳ ${fredMsg}`}{fredStatus===null&&"— In attesa"}
          </span>
          {fredKey&&<button className="btn-clear" onClick={()=>setFredKey("")}>✕</button>}
        </div>

        {/* NEWS API */}
        <div className="apikey-bar">
          <span className="apikey-label">NewsAPI Key</span>
          <input className="apikey-input" type="password" placeholder="API key NewsAPI.org…" value={newsKey} onChange={e=>setNewsKey(e.target.value)}/>
          <button className="btn-fetch" onClick={fetchNewsAuto} disabled={!newsKey.trim()||newsLoading}>
            {newsLoading?<span className="loading-dots">Fetch</span>:"▶ Carica News"}
          </button>
          <span className="fetch-status" style={{color:newsCount?"#00e5a0":"#3d5060"}}>
            {newsCount?`✓ ${newsCount} notizie caricate`:"— In attesa"}
          </span>
          {newsKey&&<button className="btn-clear" onClick={()=>setNewsKey("")}>✕</button>}
        </div>

        {/* TELEGRAM */}
        <div className="tg-bar">
          <span className="tg-label">Telegram</span>
          <input className="apikey-input" type="password" placeholder="Bot token…" value={tgToken} onChange={e=>setTgToken(e.target.value)} style={{maxWidth:280}}/>
          <input className="apikey-input" type="text" placeholder="Chat ID…" value={tgChat} onChange={e=>setTgChat(e.target.value)} style={{maxWidth:160}}/>
          <button className="btn-test" onClick={testTelegram} disabled={!hasTgConfig||tgStatus==="sending"}>
            {tgStatus==="sending"?"⏳":"📱 Test"}
          </button>
          <span className="tg-status" style={{color:tgStatus==="ok"?"#00e5a0":tgStatus==="error"?"#ff3c3c":"#3d5060"}}>
            {tgStatus==="ok"&&"✓ Inviato"}{tgStatus==="error"&&"✗ Errore"}{!tgStatus&&(hasTgConfig?"● Configurato":"○ Opzionale")}
          </span>
          {tgToken&&<button className="btn-clear" onClick={()=>{setTgToken("");setTgChat("");}}>✕</button>}
        </div>

        {/* MARKET STRIP */}
        <div className="market-strip">
          {(marketData||EMPTY_MKT).map(m=>(
            <div className="mk-item" key={m.name}>
              <span className="mk-name">{m.name}</span>
              <span className="mk-val">{isPolyLoading?<span className="skeleton" style={{width:60}}/>:m.val}</span>
              <span className={`mk-chg ${m.dir}`}>{m.chg}</span>
              <span className="mk-src">{marketData?"▲ Polygon EOD":"—"}</span>
            </div>
          ))}
        </div>

        {/* BANNER */}
        <div className={`alert-banner ${alertInfo.cls}`}>
          <div className="alert-dot"/>
          <span>{alertInfo.text}</span>
          <span style={{marginLeft:"auto",opacity:0.6,fontSize:11}}>Score: {overall}/100</span>
        </div>

        {/* MAIN GRID */}
        <div className="grid-main">
          <div className="card">
            <div className="card-title">Risk Score Aggregato</div>
            <div className="gauge-wrap">
              <ArcGauge score={overall}/>
              <div className="gauge-score" style={{color}}>{overall}</div>
              <div className="gauge-label" style={{color}}>{alertInfo.cls==="danger"?"PERICOLO":alertInfo.cls==="watch"?"ATTENZIONE":"STABILE"}</div>
              <div className="gauge-breakdown">
                {[{label:"Tecnico",score:tScore},{label:"Macro",score:mScore},{label:"Sentiment",score:sentW}].map(b=>(
                  <div className="gb-row" key={b.label}>
                    <span className="gb-label">{b.label}</span>
                    <div className="gb-bar-wrap"><div className="gb-bar" style={{width:`${b.score}%`,background:riskColor(b.score)}}/></div>
                    <span style={{color:riskColor(b.score),minWidth:28,textAlign:"right"}}>{b.score}</span>
                  </div>
                ))}
              </div>
              <p className="section-note">Pesi: 40% tecnico · 30% macro · 30% sentiment AI</p>
            </div>
          </div>

          <div className="card">
            <div className="card-title">Segnali Tecnici <span className={`data-tag ${techSignals?"live":"wait"}`}>{techSignals?`▲ Polygon · score ${tScore}`:"in attesa"}</span></div>
            <table className="sig-table"><tbody>
              {(techSignals||EMPTY_TECH).map(s=><SigRow key={s.name} {...s} shimmer={isPolyLoading}/>)}
            </tbody></table>
            {!techSignals&&<p className="section-note">Inserisci la Polygon key e premi Carica.</p>}
          </div>

          <div className="card">
            <div className="card-title">Segnali Macro <span className={`data-tag ${macroSignals?"live":"wait"}`}>{macroSignals?`▲ FRED live · score ${mScore}`:"in attesa"}</span></div>
            <table className="sig-table"><tbody>
              {(macroSignals||EMPTY_MACRO).map(s=><SigRow key={s.name} {...s} shimmer={isFredLoading}/>)}
            </tbody></table>
            {!macroSignals&&<p className="section-note">Inserisci la FRED key e premi Carica.</p>}
          </div>
        </div>

        {/* BOTTOM */}
        <div className="grid-bottom">
          <div className="card" style={{gridColumn:"span 2"}}>
            <div className="card-title">
              Analisi Sentiment — Claude AI
              {newsCount&&<span className="data-tag live">▲ NewsAPI · {newsCount} notizie</span>}
            </div>
            <textarea className="news-input"
              placeholder={"Le notizie vengono caricate automaticamente da NewsAPI.\nOppure incolla manualmente titoli/testo da analizzare."}
              value={newsText} onChange={e=>setNewsText(e.target.value)}/>
            <div className="news-actions">
              <button className="btn-fetch-news" onClick={fetchNewsAuto} disabled={!newsKey.trim()||newsLoading}>
                {newsLoading?<span className="loading-dots">Caricamento news</span>:"🔄 Aggiorna notizie"}
              </button>
              <button className="btn-analyze" onClick={handleAnalyze} disabled={aiLoading||!newsText.trim()}>
                {aiLoading?<span className="loading-dots">Analisi in corso</span>:"▶ Analizza Sentiment"}
              </button>
            </div>
            {!newsKey.trim()&&<p className="news-count">Inserisci la NewsAPI key per il caricamento automatico.</p>}

            {sentiment&&!sentiment.error&&(
              <div className="sentiment-result">
                <div className="sentiment-score-row">
                  <div className="sentiment-score-num" style={{color:riskColor(sentiment.sentiment_score)}}>{sentiment.sentiment_score}</div>
                  <div><div className="sentiment-score-label">Sentiment Score</div><div style={{color:riskColor(sentiment.sentiment_score),fontSize:12,fontWeight:700}}>{sentiment.risk_level}</div></div>
                </div>
                <p style={{marginBottom:8}}>{sentiment.summary}</p>
                <div style={{marginBottom:8}}>{sentiment.key_risks?.map((r,i)=><span key={i} style={{display:"inline-block",margin:"0 6px 4px 0",padding:"2px 8px",background:"#111",borderRadius:2,fontSize:10,color:"#8fa0b0"}}>{r}</span>)}</div>
                <div style={{color:riskColor(sentiment.sentiment_score),fontSize:11}}>→ {sentiment.recommended_action}</div>
              </div>
            )}
            {sentiment?.error&&<div className="sentiment-result" style={{color:"#ff3c3c"}}>{sentiment.error}</div>}
          </div>

          <div className="card">
            <div className="card-title">Storico Alert</div>
            <div className="alert-history">
              {alerts.map((a,i)=>(
                <div className="ah-item" key={i} style={{borderColor:a.color}}>
                  <span className="ah-time">{a.time}</span>
                  <span className="ah-text">{a.text}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

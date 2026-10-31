#!/usr/bin/env python3
"""Render the static site: one landing page and one page per model profile.

All page text lives in config/pages.json (a shared layer, a harness layer and a
profile layer, each in English and Simplified Chinese). A template holds the
structure; every `[[key]]` becomes both languages side by side and the reader's
language choice hides one of them.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

from model_profile import ROOT, Profile

PAGES_PATH = ROOT / "config" / "pages.json"
LANGS = ("en", "zh")
GITHUB_URL = "https://github.com/pellorao/context-compaction-threshold"
LANDING_NAME = "index.html"

HEAD = r"""<!doctype html>
<html lang="en" data-lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>__TITLE_EN__</title>
<script>
(function(){
  var l='';
  try{l=localStorage.getItem('lang')||'';}catch(e){}
  if(l!=='en'&&l!=='zh')l=/^zh/i.test(navigator.language||'')?'zh':'en';
  document.documentElement.dataset.lang=l;
  document.documentElement.lang=l==='zh'?'zh-CN':'en';
})();
</script>
<style>
:root {
  --bg:#f6f4ee; --surface:#fffdf8; --surface-2:#efece4; --ink:#1f2630; --muted:#5f6772;
  --line:#dcd8cd; --blue:#2562c4; --orange:#c75a10;
  --shadow:0 12px 40px rgb(31 38 48 / 7%);
}
@media (prefers-color-scheme:dark) {
  :root {
    --bg:#14171c; --surface:#1c2027; --surface-2:#242932; --ink:#eceef2; --muted:#a3abb7;
    --line:#363c46; --blue:#7aa9ff; --orange:#ff9f58;
    --shadow:0 12px 40px rgb(0 0 0 / 28%);
  }
}
* { box-sizing:border-box; }
html { -webkit-text-size-adjust:100%; }
body {
  margin:0; background:var(--bg); color:var(--ink);
  font:17px/1.7 ui-sans-serif,system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
}
html[data-lang="en"] [data-l="zh"], html[data-lang="zh"] [data-l="en"] { display:none; }
a { color:var(--blue); }
code { font-family:ui-monospace,SFMono-Regular,Consolas,"Liberation Mono",monospace; font-size:.9em; overflow-wrap:anywhere; }
.wrap { width:100%; max-width:1040px; margin:0 auto; padding:0 16px 56px; }
.topbar { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:18px 0 6px; font-size:15px; }
.topbar .back { color:var(--muted); text-decoration:none; font-weight:600; }
.topbar .back:hover { color:var(--ink); }
.tools { display:flex; align-items:center; gap:14px; margin-left:auto; }
.lang { display:inline-flex; border:1px solid var(--line); border-radius:999px; overflow:hidden; background:var(--surface); }
.lang button { appearance:none; border:0; background:none; color:var(--muted); font:inherit; font-size:14px; line-height:1; padding:8px 13px; cursor:pointer; }
.lang button[aria-pressed="true"] { background:var(--ink); color:var(--bg); font-weight:700; }
.lang button:focus-visible, .github:focus-visible { outline:2px solid var(--blue); outline-offset:2px; }
.github { display:inline-flex; color:var(--muted); }
.github:hover { color:var(--ink); }
.github svg { width:24px; height:24px; display:block; }
header.hero { padding:28px 0 10px; }
h1 { margin:0 0 14px; max-width:20ch; font-size:clamp(32px,6vw,52px); line-height:1.1; letter-spacing:-.03em; text-wrap:balance; }
html[data-lang="zh"] h1 { max-width:none; letter-spacing:0; }
.lede { max-width:62ch; margin:0; color:var(--muted); font-size:19px; }
section { margin-top:44px; }
h2 { margin:0 0 8px; font-size:clamp(23px,3.4vw,29px); line-height:1.25; letter-spacing:-.015em; }
html[data-lang="zh"] h2 { letter-spacing:0; }
h3 { margin:26px 0 8px; font-size:18px; }
.sub { max-width:66ch; margin:0 0 18px; color:var(--muted); }
.prose p, .prose li { max-width:68ch; }
.card { padding:24px; border:1px solid var(--line); border-radius:20px; background:var(--surface); box-shadow:var(--shadow); }
.picks { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:14px; }
.pick { padding:18px; border:1px solid var(--line); border-radius:16px; background:var(--surface); }
.pick h3 { margin:0 0 6px; font-size:14px; font-weight:700; color:var(--muted); }
.pick .big { font-size:30px; line-height:1.15; font-weight:750; letter-spacing:-.02em; font-variant-numeric:tabular-nums; }
.pick .set { margin:6px 0 10px; font-size:15px; }
.pick .set code, .tip .set code, .model-card .stat code { color:var(--blue); font-weight:700; }
.pick dl { display:grid; grid-template-columns:auto 1fr; gap:2px 12px; margin:0; font-size:14px; color:var(--muted); }
.pick dd { margin:0; color:var(--ink); text-align:right; font-variant-numeric:tabular-nums; }
.pick.best { border-color:var(--blue); }
.note { margin:16px 0 0; padding:14px 16px; border-left:3px solid var(--blue); border-radius:0 12px 12px 0; background:color-mix(in srgb,var(--blue) 7%,transparent); max-width:70ch; }
.note p { margin:8px 0 0; }
.chart-wrap { position:relative; }
#chart { display:block; width:100%; touch-action:pan-y; }
.axis { stroke:var(--muted); stroke-width:1; }
.grid { stroke:var(--line); stroke-width:1; }
.tick { fill:var(--muted); font-size:12px; font-variant-numeric:tabular-nums; }
.cost-band { fill:var(--blue); opacity:.13; }
.time-band { fill:var(--orange); opacity:.12; }
.cost-line { fill:none; stroke:var(--blue); stroke-width:3; }
.time-line { fill:none; stroke:var(--orange); stroke-width:2.6; }
.cursor-line { stroke:var(--ink); stroke-width:1; stroke-dasharray:3 3; opacity:.4; pointer-events:none; }
.tip { position:absolute; z-index:2; top:0; left:0; min-width:190px; max-width:260px; padding:10px 12px; border:1px solid var(--line); border-radius:12px; background:var(--surface); box-shadow:var(--shadow); font-size:13px; line-height:1.5; pointer-events:none; font-variant-numeric:tabular-nums; }
.tip[hidden] { display:none; }
.tip strong { display:block; font-size:15px; }
.tip .set { margin:2px 0 6px; }
.tip div { display:flex; justify-content:space-between; gap:12px; }
.tip div span:first-child { color:var(--muted); }
.legend { display:flex; flex-wrap:wrap; gap:6px 22px; margin:10px 0 0; color:var(--muted); font-size:14px; }
.legend span::before { content:""; display:inline-block; width:22px; height:3px; margin:0 8px 3px 0; background:var(--swatch); border-radius:2px; }
.readout { min-height:26px; margin:8px 0 0; color:var(--muted); font-size:14px; }
.speed { display:grid; grid-template-columns:1fr auto; align-items:center; gap:4px 14px; margin-top:18px; padding:14px 16px; border-radius:14px; background:var(--surface-2); }
.speed label { font-weight:700; font-size:15px; }
.speed output { color:var(--blue); font-weight:700; font-size:15px; font-variant-numeric:tabular-nums; }
.speed input { grid-column:1 / 3; width:100%; accent-color:var(--blue); }
.speed small { grid-column:1 / 3; color:var(--muted); font-size:14px; line-height:1.55; }
.caption { margin:14px 0 0; color:var(--muted); font-size:14px; max-width:70ch; }
.bullets { display:grid; gap:10px; margin:0; padding:0; list-style:none; }
.bullets li { padding:14px 16px; border-radius:14px; background:var(--surface-2); }
.bullets.cols { grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); }
details { margin-top:44px; border-top:1px solid var(--line); }
details > summary { list-style:none; cursor:pointer; padding:18px 0; font-size:clamp(23px,3.4vw,29px); line-height:1.25; font-weight:700; letter-spacing:-.015em; }
details > summary::-webkit-details-marker { display:none; }
details > summary::after { content:"+"; float:right; color:var(--muted); font-weight:400; }
details[open] > summary::after { content:"\2212"; }
details > summary:focus-visible { outline:2px solid var(--blue); outline-offset:2px; }
.steps { display:grid; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); gap:12px; margin:18px 0 0; padding:0; list-style:none; counter-reset:step; }
.steps li { position:relative; padding:16px 16px 16px 52px; border-radius:14px; background:var(--surface-2); font-size:15px; line-height:1.6; }
.steps li::before { counter-increment:step; content:counter(step); position:absolute; left:16px; top:16px; display:grid; place-items:center; width:24px; height:24px; border-radius:50%; background:var(--ink); color:var(--bg); font-size:12px; font-weight:800; }
.steps strong { display:block; margin-bottom:2px; font-size:16px; }
.formula { margin:14px 0; padding:16px; overflow-x:auto; border:1px solid var(--line); border-radius:12px; background:var(--surface-2); font:13px/1.7 ui-monospace,SFMono-Regular,Consolas,"Liberation Mono",monospace; white-space:pre; }
.defs { display:grid; grid-template-columns:repeat(auto-fit,minmax(250px,1fr)); gap:10px; }
.defs div { padding:12px 14px; border:1px solid var(--line); border-radius:12px; font-size:14px; line-height:1.55; }
.defs code { color:var(--blue); font-weight:700; }
.defs span.d { display:block; margin-top:2px; color:var(--muted); }
.cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(250px,1fr)); gap:16px; }
.model-card { display:flex; flex-direction:column; gap:6px; padding:22px; border:1px solid var(--line); border-radius:20px; background:var(--surface); box-shadow:var(--shadow); color:var(--ink); text-decoration:none; }
.model-card:hover, .model-card:focus-visible { border-color:var(--blue); }
.model-card:focus-visible { outline:2px solid var(--blue); outline-offset:2px; }
.chip { align-self:flex-start; padding:3px 10px; border-radius:999px; background:var(--surface-2); color:var(--muted); font-size:13px; font-weight:600; }
.model-card h2 { margin:6px 0 0; font-size:24px; }
.model-card p { margin:0; color:var(--muted); font-size:15px; line-height:1.6; }
.model-card .stat { margin-top:8px; color:var(--ink); font-weight:650; }
.model-card .cta { margin-top:auto; padding-top:12px; color:var(--blue); font-weight:700; }
footer { margin-top:48px; color:var(--muted); font-size:13px; text-align:center; }
@media (max-width:600px) {
  body { font-size:16px; }
  .card { padding:16px; border-radius:16px; }
  .lede { font-size:17px; }
  section { margin-top:36px; }
}
</style>
</head>
<body>
<div class="wrap">
  <nav class="topbar">
    __BACK__
    <div class="tools">
      <div class="lang" role="group" aria-label="Language">
        <button type="button" data-set-lang="en" aria-pressed="false">English</button>
        <button type="button" data-set-lang="zh" aria-pressed="false">中文</button>
      </div>
      <a class="github" href="__GITHUB__" target="_blank" rel="noopener noreferrer" id="github-link">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 .7a11.3 11.3 0 0 0-3.57 22.02c.57.1.78-.25.78-.55v-2.16c-3.17.69-3.84-1.35-3.84-1.35-.52-1.32-1.27-1.67-1.27-1.67-1.04-.71.08-.7.08-.7 1.15.08 1.75 1.18 1.75 1.18 1.02 1.75 2.68 1.24 3.33.95.1-.74.4-1.24.73-1.53-2.53-.29-5.2-1.27-5.2-5.63 0-1.24.44-2.26 1.17-3.06-.12-.29-.51-1.45.11-3.02 0 0 .96-.31 3.13 1.17a10.9 10.9 0 0 1 5.7 0c2.17-1.48 3.12-1.17 3.12-1.17.62 1.57.23 2.73.11 3.02.73.8 1.17 1.82 1.17 3.06 0 4.37-2.67 5.34-5.21 5.62.41.35.77 1.05.77 2.12v3.14c0 .3.2.66.79.55A11.3 11.3 0 0 0 12 .7Z"/></svg>
      </a>
    </div>
  </nav>
"""

LANDING_BODY = r"""  <header class="hero">
    <h1>[[landing_h1]]</h1>
    <p class="lede">[[landing_lede]]</p>
  </header>
  <section>
    <h2>[[landing_pick_h]]</h2>
    <p class="sub">[[landing_pick_p]]</p>
    <div class="cards">
__CARDS__
    </div>
  </section>
  <section class="prose">
    <h2>[[landing_find_h]]</h2>
    <ul class="bullets cols">
      <li>[[landing_find_1]]</li>
      <li>[[landing_find_2]]</li>
      <li>[[landing_find_3]]</li>
    </ul>
  </section>
  <footer>[[foot]]</footer>
</div>
"""

MODEL_BODY = r"""  <header class="hero">
    <h1>[[h1]]</h1>
    <p class="lede">[[lede]]</p>
  </header>

  <section>
    <h2>[[picks_h]]</h2>
    <p class="sub">[[picks_p]]</p>
    <div class="picks" id="picks"></div>
{?trigger_h}    <div class="note"><strong>[[trigger_h]]</strong><p>[[trigger_p]]</p><p>[[trigger_p2]]</p></div>
  </section>

  <section>
    <h2>[[chart_h]]</h2>
    <p class="sub">[[chart_p]]</p>
    <div class="card">
      <div class="chart-wrap" id="chart-wrap">
        <svg id="chart" role="img"></svg>
        <div class="tip" id="tip" hidden></div>
      </div>
      <div class="legend"><span style="--swatch:var(--blue)" id="legend-cost"></span><span style="--swatch:var(--orange)" id="legend-time"></span></div>
      <p class="readout" id="readout" aria-live="polite"></p>
      <div class="speed">
        <label for="speed">[[speed_h]]</label>
        <output id="speed-value" for="speed"></output>
        <input id="speed" type="range" min="__SPEED_MIN__" max="__SPEED_MAX__" step="1" value="__SPEED_DEFAULT__">
        <small>[[speed_p]]</small>
      </div>
      <p class="caption">[[price_caption]]</p>
{?mix_p}      <p class="caption">[[mix_p]]</p>
    </div>
  </section>

  <section class="prose">
    <h2>[[read_h]]</h2>
    <ul class="bullets">
      <li>[[read_1]]</li>
      <li>[[read_2]]</li>
      <li>[[read_3]]</li>
      <li>[[read_4]]</li>
    </ul>
  </section>

  <section class="prose">
    <h2>[[cav_h]]</h2>
    <ul class="bullets cols">
      <li>[[cav_1]]</li>
      <li>[[caveat_calibration]]</li>
      <li>[[cav_3]]</li>
      <li>[[cav_4]]</li>
      <li>[[caveat_extra]]</li>
    </ul>
  </section>

  <details class="prose">
    <summary>[[method_h]]</summary>
    <p class="sub">[[method_p]]</p>
    <ol class="steps">
      <li><strong>[[step1_h]]</strong>[[workload_step]]</li>
      <li><strong>[[step2_h]]</strong>[[calibration_step]]</li>
      <li><strong>[[step3_h]]</strong>[[step3]]</li>
      <li><strong>[[step4_h]]</strong>[[step4]]</li>
    </ol>
    <h3>[[data_h]]</h3>
    <p>[[data_volume]]</p>
{?cost_norm_h}    <h3>[[cost_norm_h]]</h3>
{?cost_norm_h}    <p>[[cost_norm_p]]</p>
    <h3>[[formula_h]]</h3>
    <p class="sub">[[formula_p]]</p>
    <div class="formula">[[formula]]</div>
    <div class="defs">
      <div><code>x</code><span class="d">[[def_x]]</span></div>
      <div><code>y</code><span class="d">[[def_y]]</span></div>
      <div><code>c</code><span class="d">[[def_c]]</span></div>
      <div><code>p_m / p_c / p_o</code><span class="d">[[def_p]]</span></div>
      <div><code>α</code><span class="d">[[def_alpha]]</span></div>
      <div><code>ρ</code><span class="d">[[def_rho]]</span></div>
      <div><code>B</code><span class="d">[[def_b]]</span></div>
      <div><code>C / K</code><span class="d">[[def_ck]]</span></div>
      <div><code>T / R</code><span class="d">[[def_t]]</span></div>
      <div><code>Δ</code><span class="d">[[def_delta]]</span></div>
      <div><code>G</code><span class="d">[[def_g]]</span></div>
      <div><code>β</code><span class="d">[[def_beta]]</span></div>
      <div><code>a</code><span class="d">[[def_a]]</span></div>
      <div><code>v</code><span class="d">[[def_v]]</span></div>
{?def_omega}      <div><span class="d">[[def_omega]]</span></div>
      <div><code>N_c / t_c / W</code><span class="d">[[def_n]]</span></div>
    </div>
    <h3>[[factors_h]]</h3>
    <ul class="bullets cols">
      <li>[[factor_1]]</li>
      <li>[[factor_2]]</li>
      <li>[[factor_3]]</li>
      <li>[[factor_4]]</li>
      <li>[[factor_5]]</li>
    </ul>
    <p>[[fit_p]]</p>
  </details>
  <footer>[[foot]]</footer>
</div>
"""

LANG_JS = r"""
function setLang(l){
  document.documentElement.dataset.lang=l;
  document.documentElement.lang=l==='zh'?'zh-CN':'en';
  try{localStorage.setItem('lang',l);}catch(e){}
  for(const b of document.querySelectorAll('[data-set-lang]'))b.setAttribute('aria-pressed',String(b.dataset.setLang===l));
  document.title=T[l].title;
  document.querySelector('.lang').setAttribute('aria-label',T[l].lang_label);
  const gh=document.getElementById('github-link');
  gh.setAttribute('aria-label',T[l].github_label);gh.title=T[l].github_label;
  if(typeof onLang==='function')onLang(l);
}
const curLang=()=>document.documentElement.dataset.lang;
for(const b of document.querySelectorAll('[data-set-lang]'))b.addEventListener('click',()=>setLang(b.dataset.setLang));
const fmt=(s,v)=>s.replace(/%(\w+)%/g,(m,k)=>k in v?v[k]:m);
"""

MODEL_JS = r"""
const D=__DATA__;
const NS='http://www.w3.org/2000/svg';
const svg=document.getElementById('chart'),wrap=document.getElementById('chart-wrap'),tip=document.getElementById('tip');
const readout=document.getElementById('readout'),speedInput=document.getElementById('speed'),speedOut=document.getElementById('speed-value');
const C=D.rows.c,LO=D.rows.lo,HI=D.rows.hi;
const xMin=C[0][0],xMax=C[C.length-1][0],timeMax=D.timeAxisMax;
const costs=LO.concat(HI).map(r=>r[1]);
const cMaxRaw=Math.max(...costs);
const kfmt=n=>n>=1e6?(n/1e6).toFixed(2).replace(/\.?0+$/,'')+'M':(n/1e3).toFixed(0)+'K';
const nfmt=n=>Math.round(n).toLocaleString('en-US');
const usd=v=>'$'+(v>=100?nfmt(v):v.toFixed(v>=10?1:v>=1?2:v>=0.1?3:4));
function niceStep(range,n){
  const raw=range/n,p=Math.pow(10,Math.floor(Math.log10(raw))),f=raw/p;
  return (f<=1?1:f<=2?2:f<=2.5?2.5:f<=5?5:10)*p;
}
const cStep=niceStep(cMaxRaw,4);
const cMin=0,cMax=Math.ceil(cMaxRaw/cStep)*cStep;
let cDec=0;
while(cDec<5&&Math.abs(cStep*10**cDec-Math.round(cStep*10**cDec))>1e-9)cDec++;
const timeShare=(r,speed)=>{
  const s=r[2]+r[3]*D.referenceSpeed/speed;
  return s/(D.workSeconds+s);
};
const windowFor=t=>t+D.buffer;
let speed=Number(speedInput.value),pinned=null;

function pickRows(){
  let best=0;
  C.forEach((r,i)=>{if(r[1]<C[best][1])best=i;});
  const out=[{limit:null,i:best}];
  for(const limit of D.limits){
    let pick=-1;
    C.forEach((r,i)=>{if(timeShare(r,speed)<=limit&&(pick<0||r[1]<C[pick][1]))pick=i;});
    out.push({limit,i:pick});
  }
  return out;
}
function renderPicks(){
  const t=T[curLang()],box=document.getElementById('picks');
  box.replaceChildren();
  pickRows().forEach((p,k)=>{
    const card=document.createElement('div');
    card.className='pick'+(k===0?' best':'');
    const h=document.createElement('h3');
    h.textContent=p.limit==null?t.pick_cheapest:fmt(t.pick_limit,{limit:Math.round(p.limit*100)+'%'});
    card.appendChild(h);
    if(p.i<0){
      const n=document.createElement('p');n.textContent=t.pick_none;card.appendChild(n);box.appendChild(card);return;
    }
    const row=C[p.i];
    const big=document.createElement('div');big.className='big';big.textContent=kfmt(row[0]);
    const set=document.createElement('p');set.className='set';
    set.innerHTML=fmt(t.pick_set,{trigger:nfmt(row[0]),window:D.buffer==null?'':windowFor(row[0])});
    const dl=document.createElement('dl');
    for(const[a,v] of [[t.pick_cost,usd(row[1])],[t.pick_time,(timeShare(row,speed)*100).toFixed(1)+'%']]){
      const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=a;dd.textContent=v;dl.append(dt,dd);
    }
    card.append(big,set,dl);
    box.appendChild(card);
  });
}
function draw(){
  const t=T[curLang()];
  const W=Math.max(300,wrap.clientWidth),narrow=W<560;
  const H=Math.round(Math.max(320,Math.min(500,W*.56)));
  const ML=narrow?44:62,MR=narrow?42:70,MT=24,MB=narrow?64:58,IW=W-ML-MR,IH=H-MT-MB;
  svg.setAttribute('viewBox',`0 0 ${W} ${H}`);svg.setAttribute('height',H);
  svg.setAttribute('aria-label',t.chart_label);
  svg.replaceChildren();
  const x=v=>ML+(v-xMin)/(xMax-xMin)*IW;
  const yc=v=>MT+IH-(v-cMin)/(cMax-cMin)*IH;
  const yt=v=>MT+IH-Math.min(v,timeMax)/timeMax*IH;
  const el=(name,attrs,text)=>{
    const n=document.createElementNS(NS,name);
    for(const[k,v]of Object.entries(attrs))n.setAttribute(k,v);
    if(text!=null)n.textContent=text;
    svg.appendChild(n);return n;
  };
  const defs=el('defs',{}),clip=document.createElementNS(NS,'clipPath'),rect=document.createElementNS(NS,'rect');
  clip.id='plot-clip';for(const[k,v]of Object.entries({x:ML,y:MT,width:IW,height:IH}))rect.setAttribute(k,v);
  clip.appendChild(rect);defs.appendChild(clip);
  for(let i=0;i<=5;i++){const gy=MT+IH*i/5;el('line',{class:'grid',x1:ML,x2:ML+IW,y1:gy,y2:gy});}
  const xs=narrow?200000:100000;
  for(let v=Math.ceil(xMin/xs)*xs;v<=xMax;v+=xs){
    const gx=x(v);
    el('line',{class:'grid',x1:gx,x2:gx,y1:MT,y2:MT+IH});
    el('text',{class:'tick',x:gx,y:MT+IH+20,'text-anchor':'middle'},kfmt(v));
  }
  for(let v=cMin;v<=cMax+cStep/2;v+=cStep)el('text',{class:'tick',x:ML-8,y:yc(v)+4,'text-anchor':'end'},'$'+v.toFixed(cDec));
  for(let i=0;i<=5;i++){const v=timeMax*i/5;el('text',{class:'tick',x:ML+IW+8,y:yt(v)+4},(v*100).toFixed(narrow?0:1)+'%');}
  const poly=(f)=>LO.map(r=>`${x(r[0])},${f(r)}`).concat(HI.slice().reverse().map(r=>`${x(r[0])},${f(r)}`)).join(' ');
  el('polygon',{class:'cost-band','clip-path':'url(#plot-clip)',points:poly(r=>yc(r[1]))});
  el('polygon',{class:'time-band','clip-path':'url(#plot-clip)',points:poly(r=>yt(timeShare(r,speed)))});
  el('polyline',{class:'cost-line','clip-path':'url(#plot-clip)',points:C.map(r=>`${x(r[0])},${yc(r[1])}`).join(' ')});
  el('polyline',{class:'time-line','clip-path':'url(#plot-clip)',points:C.map(r=>`${x(r[0])},${yt(timeShare(r,speed))}`).join(' ')});
  el('line',{class:'axis',x1:ML,x2:ML,y1:MT,y2:MT+IH});
  el('line',{class:'axis',x1:ML+IW,x2:ML+IW,y1:MT,y2:MT+IH});
  el('line',{class:'axis',x1:ML,x2:ML+IW,y1:MT+IH,y2:MT+IH});
  const xl=t.x_axis.split('  ·  ');
  el('text',{class:'tick',x:ML+IW/2,y:H-(xl.length>1?24:8),'text-anchor':'middle'},xl[0]);
  if(xl.length>1)el('text',{class:'tick',x:ML+IW/2,y:H-6,'text-anchor':'middle'},xl[1]);
  el('text',{class:'tick',x:ML,y:12,'text-anchor':'start'},t.y_cost);
  el('text',{class:'tick',x:ML+IW,y:12,'text-anchor':'end'},t.y_time);
  const cursor=el('line',{class:'cursor-line',x1:ML,x2:ML,y1:MT,y2:MT+IH,visibility:'hidden'});
  const dotC=el('circle',{r:4,fill:'var(--blue)',visibility:'hidden'});
  const dotT=el('circle',{r:4,fill:'var(--orange)',visibility:'hidden'});
  const hit=el('rect',{x:ML,y:MT,width:IW,height:IH,fill:'transparent',cursor:'crosshair'});
  function show(idx){
    const c=C[idx],lo=LO[idx],hi=HI[idx],gx=x(c[0]);
    const tm=timeShare(c,speed),tl=timeShare(lo,speed),th=timeShare(hi,speed);
    cursor.setAttribute('x1',gx);cursor.setAttribute('x2',gx);cursor.setAttribute('visibility','visible');
    dotC.setAttribute('cx',gx);dotC.setAttribute('cy',yc(c[1]));dotC.setAttribute('visibility','visible');
    dotT.setAttribute('cx',gx);dotT.setAttribute('cy',yt(tm));dotT.setAttribute('visibility','visible');
    tip.replaceChildren();
    const head=document.createElement('strong');head.textContent=`${t.tip_trigger} ${kfmt(c[0])}`;tip.appendChild(head);
    if(D.buffer!=null){
      const s=document.createElement('p');s.className='set';
      s.innerHTML=fmt(t.tip_set,{window:windowFor(c[0])});tip.appendChild(s);
    }
    const rows=[[t.tip_cost,usd(c[1])],['',`${t.tip_range} ${usd(lo[1])}–${usd(hi[1])}`],
      [t.tip_time,(tm*100).toFixed(2)+'%'],['',`${t.tip_range} ${(tl*100).toFixed(1)}%–${(th*100).toFixed(1)}%`],
      [t.tip_n,c[4].toFixed(0)]];
    for(const[a,b] of rows){
      const d=document.createElement('div'),s1=document.createElement('span'),s2=document.createElement('span');
      s1.textContent=a;s2.textContent=b;d.append(s1,s2);tip.appendChild(d);
    }
    tip.hidden=false;
    const w=tip.offsetWidth;
    tip.style.left=Math.max(0,gx+14+w>W?gx-14-w:gx+14)+'px';tip.style.top=(MT+8)+'px';
    readout.textContent=`${t.tip_trigger} ${kfmt(c[0])}`+(D.buffer!=null?` · ${fmt(t.readout_window,{window:windowFor(c[0])})}`:'')+` · ${t.tip_cost} ${usd(c[1])} · ${t.tip_time} ${(tm*100).toFixed(1)}%`;
  }
  const idxAt=ev=>{
    const px=ev.clientX-svg.getBoundingClientRect().left;
    return Math.max(0,Math.min(C.length-1,Math.round((px-ML)/IW*(C.length-1))));
  };
  hit.addEventListener('pointermove',ev=>{pinned=idxAt(ev);show(pinned);});
  hit.addEventListener('pointerdown',ev=>{pinned=idxAt(ev);show(pinned);});
  hit.addEventListener('pointerleave',ev=>{
    if(ev.pointerType!=='mouse')return;
    for(const n of [cursor,dotC,dotT])n.setAttribute('visibility','hidden');
    tip.hidden=true;readout.textContent=t.readout_idle;pinned=null;
  });
  if(pinned!=null)show(pinned);else readout.textContent=t.readout_idle;
}
function onLang(l){
  const t=T[l];
  document.getElementById('legend-cost').textContent=t.legend_cost;
  document.getElementById('legend-time').textContent=t.legend_time;
  speedOut.textContent=fmt(t.speed_value,{speed});
  renderPicks();draw();
}
let frame;
speedInput.addEventListener('input',()=>{
  speed=Number(speedInput.value);
  speedOut.textContent=fmt(T[curLang()].speed_value,{speed});
  cancelAnimationFrame(frame);frame=requestAnimationFrame(()=>{renderPicks();draw();});
});
let lastWidth=wrap.clientWidth;
window.addEventListener('resize',()=>{if(wrap.clientWidth!==lastWidth){lastWidth=wrap.clientWidth;draw();}});
setLang(curLang());
"""

LANDING_JS = "\nsetLang(curLang());\n"

VAR_RE = re.compile(r"\{([a-z_0-9]+)\}")


def load_pages(path: Path = PAGES_PATH) -> dict:
    return json.loads(path.read_text())


def per_million(data: dict) -> bool:
    """True when the result's costs are normalised to 1M billed tokens."""
    return "billed_tokens" in data["snapshot"]


def cost_field(data: dict) -> str:
    return "cost_per_million_tokens" if per_million(data) else "cost_usd_off_peak"


def layered_texts(pages: dict, profile: Profile, lang: str, normalised: bool) -> dict:
    """Shared, then cost-unit, harness and profile text for one language."""
    texts: dict = {"js": {}}
    for layer in (
        pages["shared"],
        pages["cost_per_million"] if normalised else {},
        pages["harnesses"][profile.harness],
        pages["profiles"].get(profile.name, {}),
    ):
        layer = dict(layer.get(lang, {}))
        texts["js"].update(layer.pop("js", {}))
        texts.update(layer)
    return texts


def kfmt(value: float) -> str:
    if value >= 1_000_000 and value % 1_000_000 == 0:
        return f"{value / 1_000_000:g}M"
    return f"{value / 1000:.1f}".rstrip("0").rstrip(".") + "K"


def usd(value: float) -> str:
    return f"${value:.2f}" if 0.01 <= value < 1 else f"${value:g}"


def cheapest(data: dict) -> dict:
    return min(data["curves"]["central"], key=lambda row: row[cost_field(data)])


def page_vars(data: dict, profile: Profile, labels: dict[str, str], texts: dict) -> dict:
    """Plain strings substituted for `{name}` in the text layers."""
    snap, fit, price = data["snapshot"], data["fitted_model"], profile.prices
    hours = snap["work_seconds"] / 3600
    borrowed = snap.get("calibration_borrowed")
    values = {
        "model": profile.label,
        "price_input": usd(price["input"]),
        "price_write5": usd(price["cache_write_5m"]),
        "price_write1": usd(price["cache_write_1h"]),
        "price_read": usd(price["cache_read"]),
        "price_output": usd(price["output"]),
        "alpha": f"{profile.alpha:g}",
        "rho": f"{profile.output_over_miss:g}",
        "window": kfmt(profile.context_window),
        "sessions": f"{snap['included_sessions']:,}",
        "sessions_main": str(snap.get("included_sessions_main", "")),
        "sessions_sub": str(snap.get("included_sessions_subagent", "")),
        "requests": f"{snap['requests']:,}",
        "work_hours": f"{hours:,.0f}" if hours >= 10 else f"{hours:.1f}",
        "n_fit": str(len(data["measurements"])),
        "n_compactions": str(borrowed["own"] if borrowed else len(data["measurements"])),
        "r2_two": f"{fit['time_r2_two_factor']:.2f}",
        "r2_output": f"{fit['time_r2_output_only']:.2f}",
        "r2_input": f"{fit['time_r2_input_only']:.2f}",
        "output_speed": f"{fit['output_speed_tokens_per_second']:.0f}",
        "replicates": str(fit["bootstrap_replicates"]),
        "block": str(fit["bootstrap_block_requests"]),
        "active_tail_note": texts["active_tail"] if snap["included_active_tail"] else "",
    }
    if per_million(data):
        mix = snap["billing_mix"]
        for name, key in (
            ("mix_input", "uncached_input"),
            ("mix_write5", "cache_write_5m"),
            ("mix_write1", "cache_write_1h"),
            ("mix_read", "cache_read"),
            ("mix_output", "output"),
        ):
            values[name] = f"{mix[key] / snap['billed_tokens'] * 100:.1f}%"
        values["billed_m"] = f"{snap['billed_tokens'] / 1e6:,.0f}"
    if "idle_gap_seconds" in profile.harness_cfg:
        values["idle_gap"] = texts["minutes"].format(
            n=profile.harness_cfg["idle_gap_seconds"] // 60
        )
    trigger = profile.trigger
    if trigger:
        median = snap["observed_auto_compaction_median"]
        values.update(
            buffer=kfmt(trigger["buffer"]),
            min_window=kfmt(trigger["min_window"]),
            max_window=kfmt(trigger["max_window"]),
            max_trigger=kfmt(profile.max_threshold),
            observed_window=kfmt(trigger["observed_window"]),
            observed_median=kfmt(median),
            buffer_observed=kfmt(trigger["observed_window"] - median),
        )
    if borrowed:
        values.update(
            own_compactions=str(borrowed["own"]),
            borrowed_compactions=str(borrowed["borrowed"]),
            donor=labels[borrowed["donor"]],
            time_scale=f"×{borrowed['scale']:.2f}",
        )
    return values


def expand(text: str, values: dict) -> str:
    for _ in range(3):
        text = VAR_RE.sub(lambda m: str(values.get(m.group(1), m.group(0))), text)
    return text


def expanded_texts(
    pages: dict, profile: Profile, data: dict, labels: dict[str, str]
) -> dict[str, dict]:
    """Per language: every text with its `{name}` variables filled in."""
    per_lang = {}
    for lang in LANGS:
        texts = layered_texts(pages, profile, lang, per_million(data))
        strings = {k: v for k, v in texts.items() if isinstance(v, str)}
        values = {**strings, **page_vars(data, profile, labels, texts)}
        per_lang[lang] = {
            **{k: expand(v, values) for k, v in strings.items()},
            "js": {k: expand(v, values) for k, v in texts["js"].items()},
        }
    return per_lang


def localized(key: str, per_lang: dict[str, dict]) -> str:
    """Both language versions of one text, side by side."""
    return "".join(
        f'<span data-l="{lang}">{per_lang[lang][key]}</span>' for lang in LANGS
    )


def fill_template(template: str, per_lang: dict[str, dict]) -> str:
    """Replace `[[key]]`; a line starting with `{?key}` is kept only if key has text."""
    lines = []
    for line in template.split("\n"):
        match = re.match(r"\{\?([a-z_0-9]+)\}", line)
        if match:
            if not per_lang["en"].get(match.group(1)):
                continue
            line = line[match.end():]
        lines.append(line)
    return re.sub(
        r"\[\[([a-z_0-9]+)\]\]",
        lambda m: localized(m.group(1), per_lang),
        "\n".join(lines),
    )


def js_strings(per_lang: dict[str, dict], title_key: str) -> dict:
    """The strings the page script needs, per language."""
    out = {}
    for lang in LANGS:
        texts = per_lang[lang]
        title = re.sub(r"</?code>", "", texts[title_key])
        out[lang] = {
            **texts["js"],
            "title": f"{title} | {texts['site_name']}" if title_key == "h1" else title,
            "pick_set": texts["pick_set"],
            "tip_set": texts["tip_set"],
            "x_axis": texts["x_axis"],
        }
    return out


def slim(rows: list[dict], field: str) -> list[list[float]]:
    return [
        [
            row["threshold"],
            row[field],
            row["compaction_prefill_seconds"],
            row["compaction_output_seconds"],
            row["compactions"],
        ]
        for row in rows
    ]


def page(strings: dict, back: str, body: str, script: str) -> str:
    head = (
        HEAD.replace("__TITLE_EN__", html.escape(strings["en"]["title"]))
        .replace("__GITHUB__", GITHUB_URL)
        .replace("__BACK__", back)
    )
    data = json.dumps(strings, ensure_ascii=False)
    return f"{head}{body}<script>\nconst T={data};\n{LANG_JS}{script}</script>\n</body>\n</html>\n"


def render_model(
    data: dict, profile: Profile, pages: dict, labels: dict[str, str]
) -> str:
    per_lang = expanded_texts(pages, profile, data, labels)
    fit, trigger = data["fitted_model"], profile.trigger
    payload = {
        "rows": {
            "c": slim(data["curves"]["central"], cost_field(data)),
            "lo": slim(data["curves"]["cost_low"], cost_field(data)),
            "hi": slim(data["curves"]["cost_high"], cost_field(data)),
        },
        "referenceSpeed": fit["output_speed_tokens_per_second"],
        "workSeconds": data["snapshot"]["work_seconds"],
        "timeAxisMax": profile.time_axis_max,
        "limits": list(profile.quick_limits),
        "buffer": trigger["buffer"] if trigger else None,
    }
    body = fill_template(MODEL_BODY, per_lang)
    for key, value in {
        "__SPEED_MIN__": profile.speed_slider["min"],
        "__SPEED_MAX__": profile.speed_slider["max"],
        "__SPEED_DEFAULT__": round(fit["output_speed_tokens_per_second"]),
    }.items():
        body = body.replace(key, str(value))
    back = f'<a class="back" href="{LANDING_NAME}">← {localized("nav_all", per_lang)}</a>'
    script = MODEL_JS.replace("__DATA__", json.dumps(payload))
    return page(js_strings(per_lang, "h1"), back, body, script)


def render_landing(
    results: dict[str, dict],
    profiles: dict[str, Profile],
    pages: dict,
    labels: dict[str, str],
) -> str:
    cards = []
    site = None
    for name, data in results.items():
        profile = profiles[name]
        per_lang = expanded_texts(pages, profile, data, labels)
        site = site or per_lang
        best = cheapest(data)["threshold"]
        trigger = profile.trigger
        for lang in LANGS:
            texts = per_lang[lang]
            stat = expand(texts["card_stat"], {"trigger": kfmt(best)})
            if trigger:
                stat += "<br>" + texts["pick_set"].replace(
                    "%window%", str(best + trigger["buffer"])
                )
            texts["card_stat"] = stat
        cards.append(
            f'      <a class="model-card" href="{name}.html">'
            f'<span class="chip">{localized("harness_name", per_lang)}</span>'
            f"<h2>{html.escape(profile.label)}</h2>"
            f'<p>{localized("blurb", per_lang)}</p>'
            f'<p class="stat">{localized("card_stat", per_lang)}</p>'
            f'<span class="cta">{localized("card_cta", per_lang)} →</span></a>'
        )
    body = fill_template(LANDING_BODY.replace("__CARDS__", "\n".join(cards)), site)
    strings = js_strings(site, "site_name")
    return page(strings, "<span></span>", body, LANDING_JS)

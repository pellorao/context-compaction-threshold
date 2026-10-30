#!/usr/bin/env python3
"""Render the standalone public report from analysis JSON."""

from __future__ import annotations

import json
from pathlib import Path


HERE = Path(__file__).resolve().parent


def render(data: dict) -> str:
    template = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>DeepSeek Best Compaction Threshold</title>
<style>
:root {
  --bg:#f5f3ed;
  --surface:#fffdf8;
  --surface-2:#eeebe3;
  --ink:#1d2633;
  --muted:#68707b;
  --line:#d9d5ca;
  --navy:#1f3148;
  --blue:#2b6fd6;
  --orange:#d76516;
  --limit:#7a7f87;
  --good:#24734f;
  --shadow:0 18px 50px rgb(29 38 51 / 8%);
}
@media (prefers-color-scheme:dark) {
  :root {
    --bg:#15181d;
    --surface:#1d2128;
    --surface-2:#252a32;
    --ink:#eef0f3;
    --muted:#a4acb8;
    --line:#363c46;
    --navy:#172231;
    --blue:#78a9ff;
    --orange:#ff9f58;
    --limit:#a4acb8;
    --good:#74d19e;
    --shadow:0 18px 50px rgb(0 0 0 / 22%);
  }
}
* { box-sizing:border-box; }
html { scroll-behavior:smooth; }
body {
  margin:0;
  background:
    radial-gradient(circle at 8% 0%, color-mix(in srgb,var(--blue) 10%,transparent), transparent 28rem),
    var(--bg);
  color:var(--ink);
  font:16px/1.65 ui-sans-serif,system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
}
a { color:var(--blue); }
.page { width:min(1180px,calc(100% - 40px)); margin:auto; padding:48px 0 56px; }
.hero-top { display:flex; align-items:center; padding-right:46px; }
.eyebrow { flex:1; min-width:0; color:var(--muted); font-size:13px; font-weight:700; letter-spacing:.12em; text-transform:uppercase; }
h1 { max-width:820px; margin:12px 0 14px; font-size:clamp(34px,5vw,62px); line-height:1.08; letter-spacing:-.04em; text-wrap:balance; }
.lede { max-width:760px; margin:0; color:var(--muted); font-size:18px; }
.hero { padding:22px 0 34px; }
.card { margin-top:22px; padding:28px; border:1px solid var(--line); border-radius:22px; background:var(--surface); box-shadow:var(--shadow); }
.section-head { display:flex; align-items:end; justify-content:space-between; gap:20px; margin-bottom:18px; }
.section-head > div { flex:1; min-width:0; }
.section-head h2 { margin:0; font-size:25px; letter-spacing:-.02em; }
.section-head p { margin:0; color:var(--muted); font-size:14px; }
.speed-control { display:grid; grid-template-columns:auto minmax(180px,1fr) auto; align-items:center; gap:14px; margin:0 0 18px; padding:13px 15px; border:1px solid var(--line); border-radius:14px; background:var(--surface-2); }
.speed-control label { font-size:14px; font-weight:700; white-space:nowrap; }
.speed-control output { min-width:92px; color:var(--blue); font-size:14px; font-weight:750; text-align:right; font-variant-numeric:tabular-nums; }
.speed-control input { width:100%; accent-color:var(--blue); cursor:pointer; }
.speed-control small { grid-column:2 / 4; margin-top:-7px; color:var(--muted); font-size:12px; }
.chart-shell { width:100%; overflow:hidden; }
#chart { display:block; width:100%; height:auto; }
.axis { stroke:var(--muted); stroke-width:1; }
.grid { stroke:var(--line); stroke-width:1; }
.tick { fill:var(--muted); font-size:12px; font-variant-numeric:tabular-nums; }
.cost-band { fill:var(--blue); opacity:.13; }
.time-band { fill:var(--orange); opacity:.11; }
.cost-line { fill:none; stroke:var(--blue); stroke-width:3.2; }
.time-line { fill:none; stroke:var(--orange); stroke-width:2.8; }
.cursor-line { stroke:var(--ink); stroke-width:1; stroke-dasharray:3 3; opacity:.35; pointer-events:none; }
.legend { display:flex; flex-wrap:wrap; gap:16px 22px; margin:8px 0 0 72px; color:var(--muted); font-size:13px; }
.legend span::before { content:""; display:inline-block; width:22px; height:3px; margin:0 8px 3px 0; background:var(--swatch); border-radius:2px; }
.legend .dash::before { background:repeating-linear-gradient(90deg,var(--swatch) 0 6px,transparent 6px 10px); }
.chart-readout { margin:10px 0 0 72px; min-height:24px; color:var(--ink); font-size:14px; font-weight:650; font-variant-numeric:tabular-nums; }
.chart-caption { margin:12px 0 0 72px; color:var(--muted); font-size:13px; }
.chart-mobile-hint { display:none; margin:5px 0 12px; color:var(--muted); font-size:12px; }
.grid-2 { display:grid; grid-template-columns:minmax(0,1.1fr) minmax(0,.9fr); gap:22px; }
.steps { display:grid; gap:12px; margin:0; padding:0; list-style:none; counter-reset:step; }
.steps li { position:relative; padding:15px 16px 15px 52px; border-radius:14px; background:var(--surface-2); }
.steps li::before { counter-increment:step; content:counter(step); position:absolute; left:16px; top:15px; display:grid; place-items:center; width:24px; height:24px; border-radius:50%; background:var(--ink); color:var(--surface); font-size:12px; font-weight:800; }
.steps strong { display:block; margin-bottom:2px; }
.steps span { color:var(--muted); font-size:14px; }
code, .formula { font-family:ui-monospace,SFMono-Regular,Consolas,"Liberation Mono",monospace; }
.formula { margin:12px 0; padding:15px 17px; overflow:auto; border:1px solid var(--line); border-radius:12px; background:var(--surface-2); font-size:13px; line-height:1.7; white-space:pre; }
.formula-note { margin:10px 0 0; color:var(--muted); font-size:14px; }
.definitions { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; margin-top:14px; }
.definitions div { padding:13px 14px; border:1px solid var(--line); border-radius:12px; }
.definitions code { color:var(--blue); font-weight:700; }
.definitions span { display:block; margin-top:3px; color:var(--muted); font-size:13px; }
.subhead { margin:24px 0 10px; font-size:17px; }
.callout { margin-top:18px; padding:15px 17px; border-left:3px solid var(--blue); background:color-mix(in srgb,var(--blue) 7%,transparent); border-radius:0 12px 12px 0; }
.callout strong { color:var(--blue); }
.caveats { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; margin:0; padding:0; list-style:none; }
.caveats li { padding:15px 16px; border-radius:14px; background:var(--surface-2); color:var(--muted); font-size:14px; }
.caveats strong { color:var(--ink); }
footer { margin-top:28px; color:var(--muted); font-size:12px; text-align:center; }
.github-link { position:fixed; z-index:10; top:18px; right:20px; display:inline-flex; color:var(--muted); transition:color .15s ease; }
.github-link:hover,.github-link:focus-visible { color:var(--ink); }
.github-link:focus-visible { outline:2px solid var(--blue); outline-offset:3px; }
.github-link svg { display:block; width:24px; height:24px; }
@media (max-width:820px) {
  .page { width:min(100% - 24px,1180px); padding-top:28px; }
  h1 { font-size:32px; }
  .grid-2 { grid-template-columns:1fr; }
  .definitions { grid-template-columns:1fr; }
  .card { padding:20px; border-radius:18px; }
  .chart-shell { overflow-x:auto; overscroll-behavior-x:contain; padding-bottom:6px; }
  #chart { min-width:760px; }
  .speed-control { grid-template-columns:1fr auto; }
  .speed-control input { grid-column:1 / 3; }
  .speed-control small { grid-column:1 / 3; margin-top:-4px; }
  .chart-mobile-hint { display:block; }
  .legend,.chart-caption,.chart-readout { margin-left:0; }
  .caveats { grid-template-columns:1fr; }
}
</style>
</head>
<body>
<main class="page">
  <header class="hero">
    <div class="hero-top">
      <div class="eyebrow">DeepSeek Best Compaction Threshold</div>
      <a class="github-link" href="https://github.com/pellorao/deepseek-compaction-threshold" target="_blank" rel="noopener noreferrer" aria-label="在 GitHub 查看项目（新标签页打开）" title="在 GitHub 查看项目（新标签页打开）">
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path fill="currentColor" d="M12 .7a11.3 11.3 0 0 0-3.57 22.02c.57.1.78-.25.78-.55v-2.16c-3.17.69-3.84-1.35-3.84-1.35-.52-1.32-1.27-1.67-1.27-1.67-1.04-.71.08-.7.08-.7 1.15.08 1.75 1.18 1.75 1.18 1.02 1.75 2.68 1.24 3.33.95.1-.74.4-1.24.73-1.53-2.53-.29-5.2-1.27-5.2-5.63 0-1.24.44-2.26 1.17-3.06-.12-.29-.51-1.45.11-3.02 0 0 .96-.31 3.13 1.17a10.9 10.9 0 0 1 5.7 0c2.17-1.48 3.12-1.17 3.12-1.17.62 1.57.23 2.73.11 3.02.73.8 1.17 1.82 1.17 3.06 0 4.37-2.67 5.34-5.21 5.62.41.35.77 1.05.77 2.12v3.14c0 .3.2.66.79.55A11.3 11.3 0 0 0 12 .7Z"/>
        </svg>
      </a>
    </div>
    <h1>DeepSeek 最佳压缩阈值</h1>
    <p class="lede">最佳阈值取决于缓存价格、摘要长度、上下文增长速度、压缩耗时以及工作所需的最低上下文。不同用户在成本、速度和可用上下文之间接受的程度不同，因此适合的阈值也会不同。</p>
  </header>

  <section class="card">
    <div class="section-head">
      <div>
        <h2>阈值、费用与压缩时间</h2>
        <p>蓝线是典型费用估计，橙线是典型压缩时间占比；浅色区间表示缓存前缀与摘要长度变化时的范围。</p>
      </div>
    </div>
    <div class="speed-control">
      <label for="output-speed">服务端输出速度</label>
      <input id="output-speed" type="range" min="30" max="300" step="1" value="168" aria-describedby="speed-note">
      <output id="speed-value" for="output-speed">168 tok/s</output>
      <small id="speed-note">只按比例调整摘要生成耗时，从而改变图表中的压缩时间占比；费用不变。</small>
    </div>
    <div class="chart-shell">
      <svg id="chart" viewBox="0 0 1080 500" role="img" aria-label="压缩阈值、预计费用与压缩时间占比关系图"></svg>
    </div>
    <p class="chart-readout" id="chart-readout">移动鼠标查看任一阈值的费用与时间范围。</p>
    <p class="chart-mobile-hint">左右滑动查看完整图表</p>
    <div class="legend">
      <span style="--swatch:var(--blue)">预计费用：典型值与范围（左轴）</span>
      <span style="--swatch:var(--orange)">压缩时间：典型值与范围（右轴）</span>
    </div>
    <p class="chart-caption">图表中的费用按 DeepSeek Flash 的低峰价格计算。压缩时间占比 = 压缩总耗时 ÷（正常工作时间 + 压缩总耗时）。</p>
  </section>

  <section class="card">
    <div class="section-head">
      <div>
        <h2>我们做了什么</h2>
        <p>先从真实工作会话提取请求和上下文增长，再重采样出更多等价工作负载，并用实际压缩数据计算不同阈值下的费用与耗时。</p>
      </div>
    </div>
    <div class="grid-2">
      <ol class="steps">
        <li><strong>提取工作负载</strong><span>对 DeepSeek Flash 的真实请求和上下文增长进行逐请求分析。</span></li>
        <li><strong>测量压缩</strong><span>用 9 次真实压缩的输入、缓存前缀、摘要输出和耗时校准模型；其中 6 次把真实会话上下文按语义裁剪到较小压缩点，3 次是当前会话的原生压缩。</span></li>
        <li><strong>经验重采样</strong><span>把每个真实 session 的连续请求变化按 __BOOTSTRAP_BLOCK__ 个请求一块做 circular block bootstrap，用固定随机种子生成 __BOOTSTRAP_REPLICATES__ 组工作负载。</span></li>
        <li><strong>重放并取期望</strong><span>在每组重采样序列上逐阈值重放，再对 __BOOTSTRAP_REPLICATES__ 组费用和压缩时间取平均，不对最终曲线另做平滑。</span></li>
      </ol>
      <div>
        <div class="callout">
          <strong>数据量</strong><br>
          <span id="data-volume">正在加载数据规模……</span>
        </div>
        <div class="callout">
          <strong>典型值与范围</strong><br>
          缓存按固定的可复用前缀建模，典型值取实测缓存前缀的中位数；区间覆盖实测前缀范围和摘要拟合残差。
        </div>
      </div>
    </div>
  </section>

  <section class="card">
    <div class="section-head">
      <div>
        <h2>公式与变量</h2>
        <p>先计算一次请求的价格，再把普通请求和压缩事件在整个工作负载上累加。</p>
      </div>
    </div>
    <div class="formula">单次请求费用
Q(x, c, y) = p_m · [(1-c) + αc] · x + p_o · y

价格比例
α = p_c / p_m
ρ = p_o / p_m
B = (1-β) + αβ

总费用
J(T) = Σ Q(普通请求)
     + Σ Q(压缩输入与摘要输出)

单次压缩耗时
t_c = a · (C - K) + G / v

时间占比
N_c(T) · t_c(T) / [W + N_c(T) · t_c(T)]

稳态近似
T* ≈ R + √( 2Δ · (BR + ρG) / α )</div>
    <div class="definitions">
      <div><code>x</code><span>单次请求输入中的上下文 token 数。</span></div>
      <div><code>y</code><span>该次请求生成的输出 token 数，按输出价格计费。</span></div>
      <div><code>c</code><span>普通请求输入中命中前缀缓存的比例。</span></div>
      <div><code>p_m / p_c / p_o</code><span>每 token 的缓存未命中输入、缓存命中输入和输出价格。</span></div>
      <div><code>α</code><span>缓存输入相对未缓存输入的价格比例；DeepSeek 当前为 0.02。</span></div>
      <div><code>ρ</code><span>输出相对未缓存输入的价格比例；DeepSeek 当前为 4。</span></div>
      <div><code>B</code><span>一段普通上下文按缓存命中率折算后的有效单位价格。</span></div>
      <div><code>C / K</code><span><code>C</code> 是压缩请求的输入 token；<code>K</code> 是可复用的缓存前缀 token。</span></div>
      <div><code>T / R</code><span><code>T</code> 是压缩阈值；<code>R</code> 是压缩后的有效上下文基线。</span></div>
      <div><code>Δ</code><span>每个普通请求之后，上下文平均增加多少 token。</span></div>
      <div><code>G</code><span>每次压缩实际生成并计费的摘要输出 token 数。</span></div>
      <div><code>β</code><span>压缩输入中命中缓存的比例，按固定前缀建模为 <code>β = min(1, K/C)</code>。</span></div>
      <div><code>a</code><span>未缓存输入的预处理时间，单位为秒 / token；由真实压缩耗时拟合。</span></div>
      <div><code>v</code><span>摘要生成的有效输出速度，单位为 token / 秒；图中滑块按比例改变这一项。</span></div>
      <div><code>N_c / t_c / W</code><span>压缩次数、单次压缩耗时、不含压缩的正常工作时间。</span></div>
    </div>
    <h3 class="subhead">各因素如何移动最佳阈值</h3>
    <ul class="caveats">
      <li><strong>缓存输入越便宜，阈值越高</strong><br><code>α</code> 越小，长期保留上下文的边际成本越低。</li>
      <li><strong>每请求增长越快，阈值越高</strong><br><code>Δ</code> 越大，低阈值会造成更频繁的压缩。</li>
      <li><strong>摘要越长，阈值越高</strong><br><code>G</code> 越大，每次压缩的输出费用越高。</li>
      <li><strong>工作最低上下文越高，可选阈值越高</strong><br>最终还要满足实际工作可接受的最小有效上下文。</li>
      <li><strong>输出越慢，可用阈值越高</strong><br><code>v</code> 越小，摘要生成段越长，为控制时间占比就需要减少压缩次数。</li>
    </ul>
    <p class="formula-note">9 次真实压缩对耗时模型的双因素拟合为 <code>R² = __R2_TWO__</code>；只使用摘要输出时仍为 <code>R² = __R2_OUTPUT__</code>，只使用输入时仅 <code>R² = __R2_INPUT__</code>。闭式公式用于解释变化方向；页面曲线在 __BOOTSTRAP_REPLICATES__ 组经验重采样工作负载上逐请求重放并取期望，因此保留了真实请求顺序、上下文增长和压缩时点。这里的 <code>v</code> 是图表上方滑块控制的“服务端输出速度”，只描述压缩摘要的生成段；默认值 <code>__OUTPUT_SPEED__ tok/s</code> 来自这 9 次真实压缩对摘要生成耗时的拟合，并不是整个请求端到端的总 token/s。滑块只调整摘要生成时间，不改变输入处理时间和费用。</p>
  </section>

  <section class="card">
    <div class="section-head"><div><h2>适用范围与注意事项</h2></div></div>
    <ul class="caveats">
      <li><strong>部分数据是插值模拟</strong><br>请求和上下文来自实际会话，阈值下的压缩费用与耗时由实测压缩数据插值得出，不是在历史会话中直接观测到的结果。</li>
      <li><strong>压缩样本仍然较少</strong><br>9 次真实校准中的摘要长度和缓存前缀仍有波动，区间表示这些实测变化，不是统计置信区间。</li>
      <li><strong>阈值依赖具体工作方式</strong><br>如果工作需要长期保留超过 200K 的上下文，应优先满足该下限，再比较相应区间的费用和压缩时间。</li>
      <li><strong>重采样不能代表所有未来负载</strong><br>曲线使用真实请求变化块生成 __BOOTSTRAP_REPLICATES__ 组经验重采样序列，只能覆盖样本中的变化模式；工作分布变化后应重新采样。</li>
    </ul>
  </section>

  <footer>© 2026 Tranzvision</footer>
</main>
<script>
const D=__DATA__;
const fmtK=n=>(n/1000).toFixed(0)+'K';
const independentSessions=D.snapshot.included_sessions;
document.getElementById('data-volume').textContent=
  `${independentSessions} 个独立工作会话${D.snapshot.included_active_tail?'，加上当前分析会话最后一次压缩后的连续片段':''}，`+
  `共 ${D.snapshot.requests.toLocaleString()} 个去重请求、约 ${Math.round(D.snapshot.work_seconds).toLocaleString()} 秒工作时间；`+
  `另有 ${D.measurements.length} 次真实压缩用于校准模型。smoke/test 和压缩校准测试不计入工作负载。`;

const svg=document.getElementById('chart'),NS='http://www.w3.org/2000/svg';
const W=1080,H=500,ML=72,MR=106,MT=30,MB=62,IW=W-ML-MR,IH=H-MT-MB;
const xMin=D.curves.central[0].threshold,xMax=900000,timeMax=.10;
const central=D.curves.central,costLowRows=D.curves.cost_low,costHighRows=D.curves.cost_high;
const referenceSpeed=D.fitted_model.output_speed_tokens_per_second;
const workSeconds=D.snapshot.work_seconds;
const speedInput=document.getElementById('output-speed'),speedOutput=document.getElementById('speed-value');
const readout=document.getElementById('chart-readout');
const costValues=costLowRows.concat(costHighRows).map(r=>r.cost_usd_off_peak);
const costMin=Math.floor(Math.min(...costValues)*20)/20,costMax=Math.ceil(Math.max(...costValues)*20)/20;
const x=v=>ML+(v-xMin)/(xMax-xMin)*IW;
const yc=v=>MT+IH-(v-costMin)/(costMax-costMin)*IH;
const yt=v=>MT+IH-v/timeMax*IH;
const timeShare=(row,speed)=>{
  const seconds=row.compaction_prefill_seconds+
    row.compaction_output_seconds*referenceSpeed/speed;
  return seconds/(workSeconds+seconds);
};
function draw(speed){
  svg.replaceChildren();
  const el=(name,attrs={},text)=>{
    const node=document.createElementNS(NS,name);
    for(const[k,v]of Object.entries(attrs))node.setAttribute(k,v);
    if(text!=null)node.textContent=text;
    svg.appendChild(node);
    return node;
  };
  const line=(rows,y,cls)=>el('polyline',{
    class:cls,points:rows.map(r=>`${x(r.threshold)},${y(r)}`).join(' ')
  });
  const defs=document.createElementNS(NS,'defs'),clip=document.createElementNS(NS,'clipPath'),rect=document.createElementNS(NS,'rect');
  clip.id='plot-clip';rect.setAttribute('x',ML);rect.setAttribute('y',MT);rect.setAttribute('width',IW);rect.setAttribute('height',IH);
  clip.appendChild(rect);defs.appendChild(clip);svg.appendChild(defs);
  for(let i=0;i<=5;i++){
    const gy=MT+IH*i/5;
    el('line',{class:'grid',x1:ML,x2:ML+IW,y1:gy,y2:gy});
  }
  for(let t=100000;t<=900000;t+=100000){
    const gx=x(t);
    el('line',{class:'grid',x1:gx,x2:gx,y1:MT,y2:MT+IH});
    el('text',{class:'tick',x:gx,y:H-MB+22,'text-anchor':'middle'},`${t/1000}K`);
  }
  for(let i=0;i<=4;i++){
    const v=costMin+(costMax-costMin)*i/4;
    el('text',{class:'tick',x:ML-10,y:yc(v)+4,'text-anchor':'end'},`$${v.toFixed(2)}`);
  }
  for(let i=0;i<=5;i++){
    const v=timeMax*i/5;
    el('text',{class:'tick',x:ML+IW+11,y:yt(v)+4},`${(v*100).toFixed(1)}%`);
  }
  const costBand=costLowRows.map(r=>`${x(r.threshold)},${yc(r.cost_usd_off_peak)}`)
    .concat(costHighRows.slice().reverse().map(r=>`${x(r.threshold)},${yc(r.cost_usd_off_peak)}`)).join(' ');
  const timeBand=costLowRows.map(r=>`${x(r.threshold)},${yt(timeShare(r,speed))}`)
    .concat(costHighRows.slice().reverse().map(r=>`${x(r.threshold)},${yt(timeShare(r,speed))}`)).join(' ');
  el('polygon',{class:'cost-band','clip-path':'url(#plot-clip)',points:costBand});
  el('polygon',{class:'time-band','clip-path':'url(#plot-clip)',points:timeBand});
  line(central,r=>yc(r.cost_usd_off_peak),'cost-line');
  line(central,r=>yt(timeShare(r,speed)),'time-line');
  el('line',{class:'axis',x1:ML,x2:ML,y1:MT,y2:MT+IH});
  el('line',{class:'axis',x1:ML+IW,x2:ML+IW,y1:MT,y2:MT+IH});
  el('line',{class:'axis',x1:ML,x2:ML+IW,y1:MT+IH,y2:MT+IH});
  el('text',{class:'tick',x:ML+IW/2,y:H-16,'text-anchor':'middle'},'自动压缩阈值（tokens）');
  el('text',{class:'tick',x:ML,y:16,'text-anchor':'middle'},'预计费用（USD）');
  el('text',{class:'tick',x:ML+IW,y:16,'text-anchor':'middle'},'压缩时间占比');
  for(const node of svg.querySelectorAll('.cost-line,.time-line'))node.setAttribute('clip-path','url(#plot-clip)');
  const cursor=el('line',{class:'cursor-line',x1:ML,x2:ML,y1:MT,y2:MT+IH,visibility:'hidden'});
  const costDot=el('circle',{cx:ML,cy:MT,r:4,fill:'var(--blue)',visibility:'hidden'});
  const timeDot=el('circle',{cx:ML,cy:MT,r:4,fill:'var(--orange)',visibility:'hidden'});
  const hit=el('rect',{x:ML,y:MT,width:IW,height:IH,fill:'transparent',cursor:'crosshair'});
  hit.addEventListener('pointermove',ev=>{
    const box=svg.getBoundingClientRect();
    const px=(ev.clientX-box.left)*W/box.width;
    const raw=xMin+(px-ML)/IW*(xMax-xMin);
    const idx=Math.max(0,Math.min(central.length-1,Math.round((raw-xMin)/(xMax-xMin)*(central.length-1))));
    const c=central[idx],lo=costLowRows[idx],hi=costHighRows[idx],gx=x(c.threshold);
    const tm=timeShare(c,speed),tlo=timeShare(lo,speed),thi=timeShare(hi,speed);
    cursor.setAttribute('x1',gx);cursor.setAttribute('x2',gx);cursor.setAttribute('visibility','visible');
    costDot.setAttribute('cx',gx);costDot.setAttribute('cy',yc(c.cost_usd_off_peak));costDot.setAttribute('visibility','visible');
    timeDot.setAttribute('cx',gx);timeDot.setAttribute('cy',yt(tm));timeDot.setAttribute('visibility','visible');
    readout.textContent=`${fmtK(c.threshold)} · 预计费用 $${c.cost_usd_off_peak.toFixed(3)}（范围 $${lo.cost_usd_off_peak.toFixed(3)}–$${hi.cost_usd_off_peak.toFixed(3)}） · 压缩时间 ${(tm*100).toFixed(2)}%（范围 ${(tlo*100).toFixed(2)}%–${(thi*100).toFixed(2)}%）`;
  });
  hit.addEventListener('pointerleave',()=>{
    for(const node of [cursor,costDot,timeDot])node.setAttribute('visibility','hidden');
    readout.textContent=`按 ${speed} tok/s 估计；移动鼠标查看任一阈值的费用与时间范围。`;
  });
}
let redrawTimer;
const updateSpeedLabel=()=>{
  const speed=Number(speedInput.value);
  speedOutput.textContent=`${speed} tok/s`;
  speedInput.setAttribute('aria-valuetext',`${speed} token每秒`);
};
const scheduleRedraw=()=>{
  updateSpeedLabel();
  clearTimeout(redrawTimer);
  redrawTimer=setTimeout(()=>draw(Number(speedInput.value)),500);
};
speedInput.addEventListener('input',scheduleRedraw);
speedInput.addEventListener('change',scheduleRedraw);
speedInput.value=Math.round(referenceSpeed);
updateSpeedLabel();
draw(Number(speedInput.value));
</script>
</body>
</html>
"""
    fitted = data["fitted_model"]
    return (
        template.replace("__DATA__", json.dumps(data, ensure_ascii=False))
        .replace("__R2_TWO__", f"{fitted['time_r2_two_factor']:.3f}")
        .replace("__R2_OUTPUT__", f"{fitted['time_r2_output_only']:.3f}")
        .replace("__R2_INPUT__", f"{fitted['time_r2_input_only']:.3f}")
        .replace(
            "__OUTPUT_SPEED__",
            f"{fitted['output_speed_tokens_per_second']:.1f}",
        )
        .replace(
            "__BOOTSTRAP_REPLICATES__",
            str(fitted["bootstrap_replicates"]),
        )
        .replace(
            "__BOOTSTRAP_BLOCK__",
            str(fitted["bootstrap_block_requests"]),
        )
    )


def main() -> None:
    data = json.loads((HERE.parent / "artifacts" / "result.json").read_text())
    output = HERE.parent / "artifacts" / "threshold-chart.html"
    output.write_text(render(data))
    print(output)


if __name__ == "__main__":
    main()

/* ============================================================
   MindScope 思镜 — Unified Agent Observatory (mock runtime)
   One app: SINGLE-AGENT ⇄ MULTI-AGENT modes + tool-call drill-in.
   Scripted traces — no real LLM yet. This is the北极星 prototype.
   ============================================================ */
const $ = (s)=>document.querySelector(s);
const sleep = (ms)=>new Promise(r=>setTimeout(r,ms));

let mode = 'single';
let gen = 0;                 // bumps on every mode switch; runners bail if stale
const alive = (g)=> g===gen;

/* ---------- shared refs ---------- */
const layout=$('#layout'), statusPill=$('#status-pill'), statusText=$('#status-text');
const btnSingle=$('#mode-single'), btnMulti=$('#mode-multi');
const viewSingle=$('#view-single'), viewMulti=$('#view-multi'), instruments=$('#instruments');

function setStatus(s, label){
  statusPill.className='status-pill '+(s||'');
  statusText.textContent = label || (s==='thinking'?'THINKING':s==='acting'?'ACTING':s==='done'?'COMPLETE':'IDLE');
}

/* ===================== TOKEN BARS (single) ===================== */
const barsEl=$('#bars'); let bars=[];
for(let i=0;i<26;i++){ const b=document.createElement('span'); b.style.height=(6+Math.random()*10)+'%'; barsEl.appendChild(b); bars.push(b); }

/* ===================== SINGLE-AGENT RUNNER ===================== */
const nodes={ thought:$('#node-thought'), action:$('#node-action'), observation:$('#node-observation') };
const links={ 1:$('#link-1'), 2:$('#link-2') };
const stRows={ thinking:$('#st-thinking'), acting:$('#st-acting') };
const readoutEl=$('#readout-text'), loopEl=$('#loop-count'), gaugeFill=$('#gauge-fill');
const tokenTotal=$('#token-total'), iterLabel=$('#iter-label'), ctxEl=$('#ctx'), latEl=$('#lat'), cmdEl=$('#cmd'), runBtn=$('#run');
const GMAX=6;

const TRACE=[
 {kind:'thought', text:'用户想保研。第一步：查计算机专业<span class="tag">培养方案</span>的学分要求。'},
 {kind:'action', tool:'course', ns:'course.', fn:'query', text:'调用 <span class="tag">course_query</span> { major:"计算机科学与技术", field:"培养方案" }',
   params:{ major:'计算机科学与技术', field:'培养方案' }, result:'{ total_credits: 152, core: 48, taken: 96, remaining: 56 }'},
 {kind:'observation', text:'返回 → 总学分 <span class="val">152</span> · 专业核心 48 · 已修 <span class="val">96</span> · 剩余 56'},

 {kind:'thought', text:'已知缺口。第二步：算保研 GPA 目标——当前 <span class="val">3.62</span>，目标 3.80。'},
 {kind:'action', tool:'calc', ns:'math.', fn:'eval', text:'调用 <span class="tag">calculator</span> { expr:"(3.80*152 − 3.62*96) / 56" }',
   params:{ expr:'(3.80*152 - 3.62*96) / 56' }, result:'4.1071  // 剩余课程需均分 ≈ 4.11 / 4.30'},
 {kind:'observation', text:'返回 → 剩余课程需均分 <span class="val">≈ 4.11</span> / 满绩 4.30 · 判定：偏紧但可达'},

 {kind:'thought', text:'第三步：从下学期可选课里挑「高绩点 + 核心」组合，凑学分。'},
 {kind:'action', tool:'course', ns:'course.', fn:'query', text:'调用 <span class="tag">course_query</span> { semester:"2026秋", filter:"高绩点+专业核心" }',
   params:{ semester:'2026秋', filter:'高绩点+专业核心', limit:5 }, result:'[5 courses · 17 credits · est_gpa_gain: +0.19]'},
 {kind:'observation', text:'返回 → 命中 5 门 · 17 学分 · 预测 GPA 贡献 <span class="val">+0.19</span>'},

 {kind:'thought', text:'方案成型。第四步：把选课计划写入本地文件，回复用户。'},
 {kind:'action', tool:'memory', ns:'file.', fn:'write', text:'调用 <span class="tag">file_write</span> { path:"保研冲刺选课计划.md", ... }',
   params:{ path:'保研冲刺选课计划.md', bytes:1183 }, result:'{ ok: true, written: "1.2 KB" }'},
 {kind:'observation', text:'返回 → 已写入 1.2 KB · plan.md ✓'},

 {kind:'final', text:'✓ 计划已生成：下学期选 <span class="val">5 门 / 17 学分</span>，保持均分 ≥4.11，可将 GPA 由 3.62 提到 <span class="val">3.81</span>，达保研线。详见 <span class="tag">保研冲刺选课计划.md</span>。'},
];

function resetNodes(){ Object.values(nodes).forEach(n=>n.classList.remove('live','done','clickable')); Object.values(links).forEach(l=>l.classList.remove('active')); }
async function streamText(html){
  const tmp=document.createElement('div'); tmp.innerHTML=html; const plain=tmp.textContent;
  readoutEl.innerHTML=''; for(let i=0;i<plain.length;i++){ readoutEl.textContent+=plain[i]; if(i%2===0) await sleep(7); }
  readoutEl.innerHTML=html;
}
let sTokens=0, loops=0, lastAction=null;
function sAddTok(n){ sTokens+=n; tokenTotal.textContent=sTokens.toLocaleString(); ctxEl.textContent=sTokens.toLocaleString()+' / 64K';
  for(let i=0;i<bars.length-1;i++) bars[i].style.height=bars[i+1].style.height;
  bars[bars.length-1].style.height=(18+Math.random()*78).toFixed(0)+'%';
  bars.forEach(b=>b.classList.remove('hot')); bars[bars.length-1].classList.add('hot'); }
function bumpLoop(){ loops++; loopEl.textContent=loops; iterLabel.textContent='ITERATION '+loops;
  gaugeFill.style.strokeDashoffset=314-Math.min(loops/GMAX,1)*314; }
function activateTool(t){ document.querySelectorAll('.tool').forEach(el=>el.classList.remove('active'));
  if(t){ const el=document.querySelector(`.tool[data-tool="${t}"]`); if(el) el.classList.add('active'); } }

let singleRunning=false;
async function runSingle(){
  if(singleRunning) return; singleRunning=true; runBtn.disabled=true;
  const g=gen;
  loops=0; sTokens=0; loopEl.textContent='0'; tokenTotal.textContent='0'; gaugeFill.style.strokeDashoffset=314;
  resetNodes(); setStatus('thinking');
  stRows.thinking.classList.add('on'); stRows.acting.classList.remove('on');
  await streamText('« 接收指令：'+(cmdEl.value||'（空）')); await sleep(450);

  for(const step of TRACE){
    if(!alive(g)){ singleRunning=false; runBtn.disabled=false; return; }
    if(step.kind==='thought'){
      resetNodes(); setStatus('thinking'); stRows.thinking.classList.add('on'); stRows.acting.classList.remove('on');
      nodes.thought.classList.add('live'); await streamText(step.text); sAddTok(40+Math.floor(Math.random()*60)); await sleep(420);
    } else if(step.kind==='action'){
      setStatus('acting'); stRows.acting.classList.add('on'); stRows.thinking.classList.remove('on');
      nodes.thought.classList.replace('live','done'); links[1].classList.add('active');
      nodes.action.classList.add('live','clickable'); activateTool(step.tool);
      lastAction=step; latEl.textContent=(180+Math.floor(Math.random()*900))+' ms';
      await streamText(step.text); sAddTok(25+Math.floor(Math.random()*40)); await sleep(680);
    } else if(step.kind==='observation'){
      nodes.action.classList.replace('live','done'); nodes.action.classList.remove('clickable');
      links[2].classList.add('active'); nodes.observation.classList.add('live');
      await streamText(step.text); sAddTok(60+Math.floor(Math.random()*120)); activateTool(null); bumpLoop(); await sleep(520);
    } else if(step.kind==='final'){
      resetNodes(); Object.values(nodes).forEach(n=>n.classList.add('done'));
      setStatus('done'); stRows.thinking.classList.remove('on'); stRows.acting.classList.remove('on');
      await streamText(step.text); sAddTok(80);
    }
  }
  singleRunning=false; runBtn.disabled=false;
}

/* ===================== MULTI-AGENT RUNNER ===================== */
const agents={ planner:$('#ag-planner'), executor:$('#ag-executor'), reflector:$('#ag-reflector') };
const badges={ planner:$('#badge-planner'), executor:$('#badge-executor'), reflector:$('#badge-reflector') };
const pipes={ 1:$('#pipe-1'), 2:$('#pipe-2') };
const dActive=$('#d-active'), dTokens=$('#d-tokens'), dMsgs=$('#d-msgs'), dElapsed=$('#d-elapsed'), phaseLabel=$('#phase-label');
let mTokens=0, msgs=0, mCycle=0, mT0=0, mTimer=null;

function mSetActive(name){ Object.entries(agents).forEach(([k,el])=>el.classList.toggle('active',k===name)); dActive.textContent=name?name.toUpperCase():'—'; }
function mDone(name){ agents[name].classList.add('done'); agents[name].classList.remove('active'); }
function mAddTok(n){ mTokens+=n; dTokens.textContent=mTokens.toLocaleString(); }
async function mHandoff(p,g){ pipes[p].classList.add('flow'); msgs++; dMsgs.textContent=msgs; await sleep(1000); pipes[p].classList.remove('flow'); }

async function multiCycle(g){
  phaseLabel.textContent='— PLANNING'; setStatus('thinking','PLANNING'); mSetActive('planner'); badges.planner.textContent='PLANNING';
  $('#p-sub').textContent='—'; $('#p-depth').textContent='—'; await sleep(700); if(!alive(g))return;
  $('#p-sub').textContent='4'; mAddTok(120); await sleep(450); $('#p-depth').textContent='2'; $('#p-tok').textContent='180'; mAddTok(60);
  await sleep(600); badges.planner.textContent='DONE'; mDone('planner');
  await mHandoff(1,g); if(!alive(g))return;

  phaseLabel.textContent='— EXECUTING'; setStatus('acting','EXECUTING'); mSetActive('executor'); badges.executor.textContent='EXECUTING';
  let calls=0,etok=0;
  for(let i=1;i<=4;i++){ if(!alive(g))return; $('#e-step').textContent=i+' / 4'; calls++; $('#e-calls').textContent=calls;
    etok+=90+Math.floor(Math.random()*70); $('#e-tok').textContent=etok; mAddTok(110); await sleep(620); }
  badges.executor.textContent='DONE'; mDone('executor');
  await mHandoff(2,g); if(!alive(g))return;

  phaseLabel.textContent='— REFLECTING'; setStatus('thinking','REFLECTING'); mSetActive('reflector'); badges.reflector.textContent='REVIEWING';
  await sleep(850); if(!alive(g))return;
  if(mCycle===0){
    $('#r-verdict').textContent='RETRY 1'; $('#r-retry').textContent='1'; mAddTok(80);
    badges.reflector.textContent='RETRY'; phaseLabel.textContent='— SELF-CORRECT'; await sleep(650);
    pipes[2].classList.add('flow'); await sleep(850); pipes[2].classList.remove('flow'); if(!alive(g))return;
    agents.reflector.classList.remove('active'); mSetActive('executor'); agents.executor.classList.remove('done');
    badges.executor.textContent='RE-RUN'; setStatus('acting','EXECUTING'); $('#e-step').textContent='2b / 4'; mAddTok(120); await sleep(850);
    badges.executor.textContent='DONE'; mDone('executor'); await mHandoff(2,g); if(!alive(g))return;
    mSetActive('reflector'); setStatus('thinking','REFLECTING'); badges.reflector.textContent='REVIEWING'; await sleep(750);
  }
  $('#r-verdict').textContent='PASS'; $('#r-tok').textContent='140'; mAddTok(60);
  badges.reflector.textContent='DONE'; mDone('reflector'); phaseLabel.textContent='— CYCLE COMPLETE'; setStatus('done','COMPLETE');
  await sleep(1300); if(!alive(g))return;
  Object.values(agents).forEach(el=>el.classList.remove('done','active'));
  Object.values(badges).forEach(b=>b.textContent='WAIT'); mCycle++; $('#r-retry').textContent='0';
}
async function runMulti(){
  const g=gen; mCycle=0; mTokens=0; msgs=0; dTokens.textContent='0'; dMsgs.textContent='0';
  mT0=Date.now(); clearInterval(mTimer);
  mTimer=setInterval(()=>{ if(alive(g)) dElapsed.textContent=((Date.now()-mT0)/1000).toFixed(1)+'s'; },100);
  while(alive(g)){ await multiCycle(g); if(!alive(g))break; await sleep(800); }
}

/* ===================== TOOL-CALL DRAWER ===================== */
const drawer=$('#drawer'); let drawerGen=0;
const TOOL_SAMPLES={
  search:{ns:'web.',fn:'search',params:{query:'Einstein birth year death year',count:5,lang:'en'},result:'[ "Albert Einstein 1879–1955", "Nobel Prize 1921", ... 5 hits ]'},
  calc:{ns:'math.',fn:'eval',params:{expr:'(3.80*152 - 3.62*96)/56'},result:'4.1071'},
  course:{ns:'course.',fn:'query',params:{major:'计算机科学与技术',field:'培养方案'},result:'{ total:152, core:48, taken:96, remaining:56 }'},
  memory:{ns:'memory.',fn:'recall',params:{key:'user.major'},result:'"计算机科学与技术 · 大二"'},
  code:{ns:'python.',fn:'exec',params:{code:'plt.bar(x,y); plt.savefig("g.png")'},result:'{ ok:true, artifact:"g.png" }'},
  browse:{ns:'web.',fn:'browse',params:{url:'https://zju.edu.cn/...'},result:'{ status:200, title:"培养方案" }'},
};
function pretty(o){ return JSON.stringify(o,null,2)
  .replace(/"([^"]+)":/g,'<span class="k">"$1"</span>:')
  .replace(/: "([^"]*)"/g,': <span class="s">"$1"</span>')
  .replace(/: (\d+\.?\d*)/g,': <span class="n">$1</span>'); }

async function openDrawer(data){
  const dg=++drawerGen; drawer.hidden=false;
  $('#d-ns').textContent=data.ns; $('#d-fn').textContent=data.fn;
  $('#d-params').innerHTML=pretty(data.params);
  $('#d-result').textContent='—'; $('#d-res-count').textContent='';
  $('#d-lat').textContent='— ms'; $('#d-tok').textContent='—'; $('#d-cost').textContent='—'; $('#d-ts').textContent='—';
  const fill=$('#d-exec-fill'), chip=$('#d-chip'), chipT=$('#d-chip-text');
  const stg={pending:$('#d-stg-pending'),exec:$('#d-stg-exec'),done:$('#d-stg-done')};
  const setStg=(n)=>{Object.values(stg).forEach(e=>e.classList.remove('on')); if(n)stg[n].classList.add('on');};
  fill.style.right='100%'; chip.className='tc-chip pending'; chipT.textContent='PENDING'; setStg('pending');
  await sleep(550); if(dg!==drawerGen) return;
  chip.className='tc-chip executing'; chipT.textContent='EXECUTING'; setStg('exec');
  const t0=Date.now(); const lt=setInterval(()=>$('#d-lat').textContent=(Date.now()-t0)+' ms',50);
  for(let p=10;p<=100;p+=18){ if(dg!==drawerGen){clearInterval(lt);return;} fill.style.right=(100-p)+'%'; await sleep(170); }
  clearInterval(lt); if(dg!==drawerGen) return;
  chip.className='tc-chip complete'; chipT.textContent='COMPLETE'; setStg('done');
  $('#d-result').textContent=data.result; $('#d-res-count').textContent='(ok)';
  $('#d-lat').textContent=(Date.now()-t0)+' ms'; $('#d-lat').classList.add('live');
  $('#d-tok').textContent='312'; $('#d-tok').classList.add('live'); $('#d-cost').textContent='$0.00021';
  $('#d-ts').textContent=new Date().toTimeString().slice(0,8);
}
function closeDrawer(){ drawerGen++; drawer.hidden=true; }
$('#drawer-close').addEventListener('click', closeDrawer);
drawer.addEventListener('click',(e)=>{ if(e.target===drawer) closeDrawer(); });

/* ===================== MODE SWITCH ===================== */
function setMode(m){
  if(m===mode && gen!==0) return;
  gen++; mode=m;
  btnSingle.classList.toggle('active', m==='single');
  btnMulti.classList.toggle('active', m==='multi');
  layout.classList.toggle('multi', m==='multi');
  viewSingle.hidden = m!=='single';
  viewMulti.hidden  = m!=='multi';
  closeDrawer();
  if(m==='single'){ singleRunning=false; setTimeout(runSingle, 250); }
  else { runMulti(); }
}
btnSingle.addEventListener('click', ()=>setMode('single'));
btnMulti.addEventListener('click', ()=>setMode('multi'));

/* ===================== WIRES ===================== */
runBtn.addEventListener('click', ()=>{ if(mode==='single') runSingle(); });
cmdEl.addEventListener('keydown',(e)=>{ if(e.key==='Enter'&&mode==='single') runSingle(); });
nodes.action.addEventListener('click', ()=>{ if(lastAction) openDrawer(lastAction); });
document.querySelectorAll('.tool').forEach(t=>{
  t.addEventListener('click', ()=>{ const s=TOOL_SAMPLES[t.dataset.tool]; if(s) openDrawer(s); });
});

/* uptime ticker */
let up=11*60+47;
setInterval(()=>{ up++; const h=String(Math.floor(up/3600)).padStart(2,'0'),m=String(Math.floor(up/60)%60).padStart(2,'0'),s=String(up%60).padStart(2,'0');
  const el=$('#uptime'); if(el) el.textContent=`${h}:${m}:${s}`; },1000);

/* boot */
window.addEventListener('load', ()=>{ gen=0; setTimeout(runSingle, 800); });

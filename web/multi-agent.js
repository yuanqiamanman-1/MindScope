/* MindScope 思镜 — Multi-Agent orchestration mock runtime */
const $ = (s)=>document.querySelector(s);
const sleep=(ms)=>new Promise(r=>setTimeout(r,ms));

const statusPill=$('#status-pill'), statusText=$('#status-text'), phaseLabel=$('#phase-label');
const agents={ planner:$('#ag-planner'), executor:$('#ag-executor'), reflector:$('#ag-reflector') };
const badges={ planner:$('#badge-planner'), executor:$('#badge-executor'), reflector:$('#badge-reflector') };
const pipes={ 1:$('#pipe-1'), 2:$('#pipe-2') };
const dActive=$('#d-active'), dTokens=$('#d-tokens'), dMsgs=$('#d-msgs'), dElapsed=$('#d-elapsed');
const ctxEl=$('#ctx'), handoffsEl=$('#handoffs'), cycleEl=$('#cycle');

let tokens=0, msgs=0, handoffs=0, cycle=1, t0=0, elapsedTimer=null;

function setStatus(s){
  statusPill.className='status-pill '+(s||'');
  statusText.textContent = s==='thinking'?'PLANNING':s==='acting'?'EXECUTING':s==='done'?'COMPLETE':'IDLE';
}
function setActive(name){
  Object.entries(agents).forEach(([k,el])=>{
    el.classList.toggle('active', k===name);
  });
  dActive.textContent = name ? name.toUpperCase() : '—';
}
function markDone(name){ agents[name].classList.add('done'); agents[name].classList.remove('active'); }
function addTok(n){ tokens+=n; dTokens.textContent=tokens.toLocaleString(); ctxEl.textContent=(tokens).toLocaleString()+' / 96K'; }
async function handoff(p){ pipes[p].classList.add('flow'); msgs++; handoffs++; dMsgs.textContent=msgs; handoffsEl.textContent=handoffs; await sleep(1100); pipes[p].classList.remove('flow'); }

async function cycleRun(){
  // ---- PLANNER ----
  phaseLabel.textContent='— PLANNING'; setStatus('thinking'); setActive('planner');
  badges.planner.textContent='PLANNING';
  $('#p-sub').textContent='—'; $('#p-depth').textContent='—';
  await sleep(700);
  $('#p-sub').textContent='4'; $('#p-sub').classList.add('live'); addTok(120);
  await sleep(500); $('#p-depth').textContent='2'; $('#p-depth').classList.add('live'); addTok(60);
  $('#p-tok').textContent='180';
  await sleep(700); badges.planner.textContent='DONE'; markDone('planner');

  await handoff(1);

  // ---- EXECUTOR ----
  phaseLabel.textContent='— EXECUTING'; setStatus('acting'); setActive('executor');
  badges.executor.textContent='EXECUTING';
  let calls=0, etok=0;
  for(let i=1;i<=4;i++){
    $('#e-step').textContent=i+' / 4'; $('#e-step').classList.add('live');
    calls++; $('#e-calls').textContent=calls;
    etok+=90+Math.floor(Math.random()*70); $('#e-tok').textContent=etok; addTok(110);
    await sleep(650);
  }
  badges.executor.textContent='DONE'; markDone('executor');

  await handoff(2);

  // ---- REFLECTOR (first cycle: catches an error, bounces back) ----
  phaseLabel.textContent='— REFLECTING'; setStatus('thinking'); setActive('reflector');
  badges.reflector.textContent='REVIEWING';
  await sleep(900);

  if(cycle===1){
    $('#r-verdict').textContent='RETRY 1'; $('#r-verdict').classList.add('live');
    $('#r-retry').textContent='1'; addTok(80);
    badges.reflector.textContent='RETRY'; phaseLabel.textContent='— SELF-CORRECT';
    await sleep(700);
    // bounce back to executor
    pipes[2].classList.add('flow'); await sleep(900); pipes[2].classList.remove('flow');
    agents.reflector.classList.remove('active'); setActive('executor'); agents.executor.classList.remove('done');
    badges.executor.textContent='RE-RUN'; setStatus('acting');
    $('#e-step').textContent='2b / 4'; addTok(120); await sleep(900);
    badges.executor.textContent='DONE'; markDone('executor');
    await handoff(2);
    setActive('reflector'); setStatus('thinking'); badges.reflector.textContent='REVIEWING';
    await sleep(800);
  }

  $('#r-verdict').textContent='PASS'; $('#r-verdict').classList.add('live');
  $('#r-tok').textContent='140'; addTok(60);
  badges.reflector.textContent='DONE'; markDone('reflector');
  phaseLabel.textContent='— CYCLE COMPLETE'; setStatus('done');
  await sleep(1400);

  // reset for next cycle
  Object.values(agents).forEach(el=>el.classList.remove('done','active'));
  Object.values(badges).forEach((b,i)=>{ b.textContent='WAIT'; });
  cycle++; cycleEl.textContent=cycle;
  ['#p-sub','#p-depth','#e-step','#r-verdict'].forEach(s=>$(s).classList.remove('live'));
  $('#r-retry').textContent='0';
}

async function loop(){
  t0=Date.now();
  elapsedTimer=setInterval(()=>{ dElapsed.textContent=((Date.now()-t0)/1000).toFixed(1)+'s'; },100);
  while(true){ await cycleRun(); await sleep(900); }
}
window.addEventListener('load', ()=> setTimeout(loop, 600));

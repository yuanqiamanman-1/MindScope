/* MindScope 思镜 — Tool Call detail mock runtime */
const $=(s)=>document.querySelector(s);
const sleep=(ms)=>new Promise(r=>setTimeout(r,ms));

const chip=$('#chip'), chipText=$('#chip-text');
const statusPill=$('#status-pill'), statusText=$('#status-text');
const execFill=$('#exec-fill');
const stg={ pending:$('#stg-pending'), exec:$('#stg-exec'), done:$('#stg-done') };
const resBody=$('#res-body'), resCount=$('#res-count');
const rerun=$('#rerun');

const RESULTS=[
  ['1','Albert Einstein — Wikipedia','wikipedia.org','0.98'],
  ['2','Albert Einstein (1879–1955), theoretical physicist','wikipedia.org','0.95'],
  ['3','Albert Einstein | Biography, Education, Discoveries','britannica.com','0.91'],
  ['4','Einstein and the Theory of Relativity','wikipedia.org','0.88'],
  ['5','The Nobel Prize in Physics 1921 — Einstein','nobelprize.org','0.85'],
];

/* spark bars */
const spark=$('#spark');
for(let i=0;i<28;i++){ const b=document.createElement('span'); b.style.height=(20+Math.random()*70)+'%'; spark.appendChild(b); }
setInterval(()=>{ spark.querySelectorAll('span').forEach(b=>{ b.style.height=(20+Math.random()*70)+'%'; }); }, 1400);

function setStatus(s){
  statusPill.className='status-pill '+(s||'');
  statusText.textContent = s==='acting'?'EXECUTING':s==='done'?'COMPLETE':s==='thinking'?'PENDING':'IDLE';
}
function setStage(name){
  Object.values(stg).forEach(e=>e.classList.remove('on'));
  if(name) stg[name].classList.add('on');
}
function setChip(cls,text){ chip.className='tc-chip '+cls; chipText.textContent=text; }

let running=false;
async function run(){
  if(running) return; running=true; rerun.disabled=true;

  // reset
  resBody.innerHTML=''; resCount.textContent='';
  execFill.style.right='100%';
  $('#f-lat').textContent='— ms'; $('#f-tok').textContent='—'; $('#f-cost').textContent='—'; $('#f-ts').textContent='—';
  $('#f-lat').classList.remove('live'); $('#f-tok').classList.remove('live');
  $('#g-tok').textContent='0%'; $('#g-tok-fill').style.width='0%';

  // PENDING
  setChip('pending','PENDING'); setStatus('thinking'); setStage('pending');
  await sleep(700);

  // EXECUTING
  setChip('executing','EXECUTING'); setStatus('acting'); setStage('exec');
  const t0=Date.now();
  const latTimer=setInterval(()=>{ $('#f-lat').textContent=(Date.now()-t0)+' ms'; $('#f-lat').classList.add('live'); }, 60);

  // progress + stream rows
  const N=RESULTS.length;
  for(let i=0;i<N;i++){
    const pct=Math.round(((i+1)/N)*100);
    execFill.style.right=(100-pct)+'%';
    $('#g-tok').textContent=pct+'%'; $('#g-tok-fill').style.width=pct+'%';
    $('#g-ctx-fill').style.width=(5+pct*0.18).toFixed(0)+'%'; $('#g-ctx').textContent=(5+pct*0.18).toFixed(0)+'%';
    const r=RESULTS[i];
    const tr=document.createElement('tr'); tr.className='in';
    tr.innerHTML=`<td>${r[0]}</td><td>${r[1]}</td><td>${r[2]}</td><td class="score">${r[3]}</td>`;
    resBody.appendChild(tr);
    resCount.textContent=`(${i+1})`;
    await sleep(360);
  }
  await sleep(300);
  clearInterval(latTimer);

  // COMPLETE
  setChip('complete','COMPLETE'); setStatus('done'); setStage('done');
  const lat=Date.now()-t0;
  $('#f-lat').textContent=lat+' ms';
  $('#f-tok').textContent='312'; $('#f-tok').classList.add('live');
  $('#f-cost').textContent='$0.00021';
  const d=new Date();
  $('#f-ts').textContent=d.toTimeString().slice(0,8);

  running=false; rerun.disabled=false;
}

rerun.addEventListener('click', run);
window.addEventListener('load', ()=> setTimeout(run, 700));

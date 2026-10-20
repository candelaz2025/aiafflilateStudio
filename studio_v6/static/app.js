'use strict';
const $ = id => document.getElementById(id);
const state = {products:[],drafts:[],queue:[],currentDraft:null,status:null,radar:[],radarStatus:null,external:[],externalStatus:null,selectedExternal:null};
const esc = s => String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const link = name => '/studio/api/assets/'+encodeURIComponent(name);
const validHttp = u => {try{return /^https?:$/.test(new URL(u).protocol)}catch{return false}};
const api = async (path,opts={})=>{
 const extra=Object.assign({},opts);
 // V7.3 main application validates a CSRF token before every Studio write.
 if(!['GET','HEAD','OPTIONS'].includes(String(extra.method||'GET').toUpperCase())){
   const who=await fetch('/api/me',{credentials:'same-origin'});
   if(!who.ok)throw Error('โปรดล็อกอินเป็นแอดมินอีกครั้ง');
   const me=await who.json();
   extra.headers=Object.assign({},extra.headers||{}, {'X-CSRF-Token':me.csrf});
 }
 const res=await fetch(path,Object.assign({credentials:'same-origin'},extra));let payload;
 try {payload=await res.json()} catch {payload={detail:'เซิร์ฟเวอร์ไม่ตอบกลับเป็น JSON'}}
 if(!res.ok) throw new Error(typeof payload.detail === 'string'?payload.detail:`การทำงานผิดพลาด (${res.status})`);
 return payload;
};
const json = (method,obj)=>({method,headers:{'Content-Type':'application/json'},body:JSON.stringify(obj)});
const toast = (msg,error=false) => {const el=$('toast');el.textContent=msg;el.className=error?'error':'';el.style.display='block';clearTimeout(toast._id);toast._id=setTimeout(()=>el.style.display='none',5000)};
const run = async (task,success)=>{try{await task();if(success)toast(success)}catch(e){toast(e.message||'มีข้อผิดพลาด',true);console.error(e)}};
function tab(name){
 document.querySelectorAll('.tab').forEach(n=>n.classList.toggle('active',n.id===name));
 document.querySelectorAll('.nav-button').forEach(n=>n.classList.toggle('active',n.dataset.tab===name));
 window.scrollTo({top:0,behavior:'smooth'});
}
document.querySelectorAll('[data-tab]').forEach(b=>b.addEventListener('click',()=>tab(b.dataset.tab)));
document.querySelectorAll('[data-goto]').forEach(b=>b.addEventListener('click',()=>tab(b.dataset.goto)));
async function refresh(){
 const [products,drafts,queue,status,radarStatus,radar,externalStatus,external]=await Promise.all([
  api('/studio/api/products'),api('/studio/api/drafts'),api('/studio/api/queue'),api('/studio/api/status'),api('/studio/api/radar/status'),radarSearch(),api('/studio/api/external/status'),externalSearch()]);
 Object.assign(state,{products,drafts,queue,status,radarStatus,radar,externalStatus,external});
 renderStats();renderProducts();renderDrafts();renderQueue();renderRadar();renderExternal();
 if(state.currentDraft){const latest=drafts.find(d=>d.id===state.currentDraft.id);if(latest)selectDraft(latest.id)}
}
function renderStats(){
 const c=state.status.counts;
 ['radar','products','drafts','videos','queue'].forEach(k=>$('stat-'+k).textContent=c[k]);
 $('api-mode-pill').textContent=state.status.google_omni_api?'พร้อมใช้ (มีค่าใช้จ่าย)':'ยังไม่ตั้งค่า API key';
 $('omni-create').disabled=!state.status.google_omni_api;
}
function renderProducts(){
 const target=$('product-list'), sel=$('product-select');
 const selected=sel.value;
 sel.innerHTML='<option value="">เลือกสินค้าเพื่อสร้างคลิป</option>'+state.products.map(p=>`<option value="${p.id}">${esc(p.title)}</option>`).join('');
 if(state.products.some(p=>String(p.id)===selected))sel.value=selected;
 target.innerHTML=state.products.length?state.products.map(p=>`<div class="item">
  ${p.reference_filename?`<img class="thumb" alt="ภาพสินค้า" src="${link(p.reference_filename)}">`:'<div class="thumb placeholder">▣</div>'}
  <div class="item-body"><strong>${esc(p.title)}</strong><small>${esc(p.audience||'ยังไม่ระบุกลุ่มเป้าหมาย')}${p.price?' · '+esc(p.price):''}</small></div>
  <button class="button button-quiet" data-create-product="${p.id}">สร้างคลิป →</button>
 </div>`).join(''):'<p class="empty">ยังไม่มีสินค้า ลองเพิ่มสินค้าแรกทางซ้าย</p>';
 document.querySelectorAll('[data-create-product]').forEach(b=>b.addEventListener('click',()=>{$('product-select').value=b.dataset.createProduct;tab('drafts')}));
}
function renderDrafts(){
 $('draft-list').innerHTML=state.drafts.length?state.drafts.map(d=>`<div class="item ${state.currentDraft?.id===d.id?'selected':''}">
  ${d.reference_filename?`<img class="thumb" src="${link(d.reference_filename)}" alt="ภาพสินค้า">`:'<div class="thumb placeholder">✺</div>'}
  <div class="item-body"><strong>${esc(d.product_title)}</strong><small>#${d.id} · ${d.video_filename?'✓ มีไฟล์วิดีโอ':'◷ รอสร้างคลิป'} · ${esc(d.platforms||'')}</small></div>
  <button class="button button-quiet" data-select-draft="${d.id}">เปิด</button>
 </div>`).join(''):'<p class="empty">ยังไม่มีบทรีวิว</p>';
 document.querySelectorAll('[data-select-draft]').forEach(b=>b.addEventListener('click',()=>selectDraft(Number(b.dataset.selectDraft))));
}
function selectDraft(id){
 const d=state.drafts.find(x=>x.id===id);if(!d)return;
 state.currentDraft=d;
 $('draft-empty').hidden=true;$('draft-editor').hidden=false;
 $('draft-selected').textContent=`บท #${d.id} · ${d.product_title}`;
 for(const key of ['hook','voiceover','onscreen','caption'])$('field-'+key).value=d[key]||'';
 $('field-prompt').value=d.video_prompt||'';
 const video=Boolean(d.video_filename);
 $('video-spot').hidden=!video;
 if(video){$('preview-video').src=link(d.video_filename);$('video-download').href=link(d.video_filename)}
 $('omni-create').disabled=!state.status?.google_omni_api||video;
 renderDrafts();
}
function renderQueue(){
 const labels={pending_review:'รอตรวจสอบ',ready_manual:'พร้อมโพสต์ด้วยตัวเอง',posted:'โพสต์แล้ว'};
 const el=$('queue-list');
 if(!state.queue.length){el.innerHTML='<p class="empty">ยังไม่มีคิว</p>';return}
 el.innerHTML=state.queue.map(q=>`<div class="queue-card" data-queue="${q.id}"><div>
  <span class="platform ${q.platform==='shopee'?'shopee':''}">${q.platform==='shopee'?'Shopee Video':'TikTok Affiliate'}</span>
  <span class="status ${q.status==='posted'?'posted':q.status==='pending_review'?'waiting':''}">${esc(labels[q.status]||q.status)}</span>
  <h3 style="margin:9px 0 4px">${esc(q.product_title)}</h3><p>${esc(q.caption||'').slice(0,170)}</p>
  ${q.video_filename?`<p><a href="${link(q.video_filename)}" target="_blank" rel="noopener noreferrer" style="color:#73e0db">เปิดวิดีโอ MP4 ↗</a></p>`:'<p>ยังไม่มีไฟล์ MP4</p>'}
  ${q.product_link&&validHttp(q.product_link)?`<p><a target="_blank" rel="noopener noreferrer" href="${esc(q.product_link)}" style="color:#bbcaff">ดูหน้าสินค้า ↗</a></p>`:''}
  </div><div class="queue-controls">
  <label>สถานะ <select class="queue-status">
   ${Object.entries(labels).map(([value,label])=>`<option value="${value}" ${q.status===value?'selected':''}>${label}</option>`).join('')}</select></label>
  <label>วันที่/เวลาโพสต์ (ใส่เองได้) <input class="queue-time" placeholder="2026-10-19 18:00" value="${esc(q.scheduled_at||'')}"></label>
  <label>ลิงก์คลิปที่โพสต์จริง <input class="queue-url" type="url" placeholder="https://..." value="${esc(q.post_url||'')}"></label>
  <div class="queue-actions"><button class="button button-primary save-queue">บันทึกคิว</button><button class="button button-quiet edit-queue" data-draft="${q.draft_id}">เปิดบทรีวิว</button></div>
  </div></div>`).join('');
 document.querySelectorAll('.save-queue').forEach(b=>b.addEventListener('click',()=>run(async()=>{
  const row=b.closest('[data-queue]'),id=row.dataset.queue;
  await api('/studio/api/queue/'+id,json('PATCH',{status:row.querySelector('.queue-status').value,
   scheduled_at:row.querySelector('.queue-time').value,post_url:row.querySelector('.queue-url').value}));
  await refresh();
 },'บันทึกคิวแล้ว')));
 document.querySelectorAll('.edit-queue').forEach(b=>b.addEventListener('click',()=>{selectDraft(Number(b.dataset.draft));tab('drafts')}));
}
$('product-form').addEventListener('submit',e=>{e.preventDefault();run(async()=>{
 const f=e.currentTarget, fd=new FormData(f);
 const data={title:fd.get('title'),price:fd.get('price'),features:fd.get('features'),audience:fd.get('audience'),
   tiktok_link:fd.get('tiktok_link'),shopee_link:fd.get('shopee_link')};
 const p=await api('/studio/api/products',json('POST',data));
 const file=$('new-reference').files[0];
 if(file){const form=new FormData();form.append('file',file);await api(`/studio/api/products/${p.id}/reference`,{method:'POST',body:form})}
 f.reset();await refresh();$('product-select').value=String(p.id);tab('drafts');
},'เพิ่มสินค้าเรียบร้อย — พร้อมสร้างบทรีวิว')});
$('draft-form').addEventListener('submit',e=>{e.preventDefault();run(async()=>{
 const id=Number($('product-select').value);if(!id)throw Error('กรุณาเลือกสินค้าก่อน');
 const result=await api('/studio/api/drafts',json('POST',{product_id:id,platforms:['tiktok','shopee']}));
 await refresh();selectDraft(result.draft.id);
},'สร้างบทและคิวทั้งสองแพลตฟอร์มแล้ว')});
$('save-draft').addEventListener('click',()=>run(async()=>{
 if(!state.currentDraft)throw Error('เลือกบทรีวิวก่อน');
 const data={hook:$('field-hook').value,voiceover:$('field-voiceover').value,onscreen:$('field-onscreen').value,
 caption:$('field-caption').value,video_prompt:$('field-prompt').value};
 await api('/studio/api/drafts/'+state.currentDraft.id,json('PATCH',data));await refresh();
},'บันทึกบทรีวิวแล้ว'));
async function copyText(str){
 if(!str.trim())throw Error('ไม่มีข้อความให้คัดลอก');
 if(navigator.clipboard?.writeText){await navigator.clipboard.writeText(str);return}
 const t=document.createElement('textarea');t.value=str;t.style.position='fixed';t.style.left='-99999px';document.body.appendChild(t);t.select();
 const ok=document.execCommand('copy');t.remove();if(!ok)throw Error('คัดลอกไม่ได้ กรุณาเลือกข้อความแล้วคัดลอกเอง');
}
$('copy-prompt').addEventListener('click',()=>run(async()=>{
 await copyText($('field-prompt').value);
},'คัดลอกพรอมต์แล้ว — เปิด Google Flow แล้ววางได้เลย'));
$('import-flow-form').addEventListener('submit',e=>{e.preventDefault();run(async()=>{
 if(!state.currentDraft)throw Error('เลือกบทรีวิวก่อน');
 const file=$('flow-video-file').files[0];if(!file)throw Error('กรุณาเลือกไฟล์ MP4');
 const form=new FormData();form.append('file',file);
 await api(`/studio/api/drafts/${state.currentDraft.id}/import_flow`,{method:'POST',body:form});
 $('flow-video-file').value='';await refresh();
},'นำเข้าคลิปสำเร็จ — เพิ่มคิว TikTok และ Shopee แล้ว')});
$('omni-create').addEventListener('click',()=>{
 if(!state.currentDraft)return toast('เลือกบทรีวิวก่อน',true);
 if(!window.confirm('ต้องการให้ระบบสั่ง Gemini Omni API สร้างคลิปใหม่หรือไม่? การสร้างนี้อาจมีค่าใช้จ่ายจริง และไม่ใช้เครดิต Google Flow'))return;
 run(async()=>{const b=$('omni-create');b.disabled=true;b.textContent='กำลังสร้างวิดีโอ…';
 try{await api(`/studio/api/drafts/${state.currentDraft.id}/omni`,{method:'POST'});await refresh()}
 finally{b.textContent='สร้างวิดีโอด้วย API (มีค่าใช้จ่าย)';b.disabled=!state.status?.google_omni_api||Boolean(state.currentDraft?.video_filename)}
 },'สร้างคลิปผ่าน Google Gemini API เสร็จแล้ว');
});
$('refresh-queue').addEventListener('click',()=>run(refresh,'อัปเดตคิวล่าสุดแล้ว'));
run(refresh);

// PRODUCT RADAR — only uses authorized feed or imported real product records.
function radarSearch(){
 const opts=new URLSearchParams({platform:$('radar-platform').value,
  min_sales:$('radar-min-sales').value,min_commission:$('radar-min-commission').value,
  query:$('radar-query').value.trim()});
 return api('/studio/api/radar?'+opts.toString());
}
const readableNumber = value => value===null||value===undefined?'ไม่ระบุ':Number(value).toLocaleString('th-TH',{maximumFractionDigits:1});
function renderRadar(){
 const st=state.radarStatus;
 if(!st)return;
 for(const plat of ['tiktok','shopee']){
  const connected=st.feeds_configured[plat];
  $('radar-'+plat+'-status').textContent=connected?'ตั้งค่าฟีดแล้ว':'ยังไม่เชื่อม API/ฟีด';
 }
 $('radar-sync').disabled=!Object.values(st.feeds_configured).some(Boolean);
 $('radar-last-scan').textContent=st.last_scan?`สแกนล่าสุด: ${st.last_scan.ran_at} · ที่มา: ${st.last_scan.source} · ${st.last_scan.imported} รายการ${st.last_scan.errors?' · ข้อผิดพลาด: '+st.last_scan.errors:''}`:'ยังไม่มีประวัติการสแกน';
 $('radar-warning').textContent=st.auto_sync_enabled?`ตั้งการสแกนซ้ำทุก ${st.interval_minutes} นาทีไว้แล้ว ระบบจะทำงานเมื่อเครื่องที่รันเซิร์ฟเวอร์เปิดอยู่เท่านั้น`:'ยังไม่ได้เปิดสแกนอัตโนมัติ การนำเข้า CSV ทำได้ทันที ส่วนการค้นหาออนไลน์ต้องมีแหล่งฟีด/API ที่ได้รับอนุญาต';
 $('radar-results').innerHTML=state.radar.length?state.radar.map((p,i)=>{
  const sales=p.units_sold===null?'ไม่มีข้อมูลยอดขาย':`${readableNumber(p.units_sold)} ชิ้น ${p.sales_period==='30d'?'(30 วัน)':'(ช่วงเวลาไม่ระบุ)'}`;
  const source=p.source_type==='authorized_feed'?'ฟีดผู้ให้บริการ':'CSV ที่นำเข้า';
  return `<article class="radar-card">
   <div class="radar-score"><strong>${readableNumber(p.score)}</strong><small>คะแนนคัดเลือก</small></div>
   <div class="radar-details"><div><span class="platform ${p.platform==='shopee'?'shopee':''}">${p.platform==='shopee'?'Shopee':'TikTok'}</span><span class="radar-category">${esc(p.category||'ไม่ระบุหมวดหมู่')}</span></div>
    <strong>${esc(p.title)}</strong>
    <p>ยอดขายที่แหล่งข้อมูลรายงาน: <b>${esc(sales)}</b> · ค่าคอม: <b>${p.commission_pct===null?'ไม่ระบุ':readableNumber(p.commission_pct)+'%'}</b> · ราคา: <b>${p.price===null?'ไม่ระบุ':'฿'+readableNumber(p.price)}</b></p>
    <small>⭐ ${p.rating===null?'ไม่ระบุ':readableNumber(p.rating)+'/5'} · รีวิว ${readableNumber(p.reviews)} · ${esc(source)} · อัปเดต ${esc(p.fetched_at.slice(0,16))}</small>
    ${p.url&&validHttp(p.url)?`<a class="radar-source-link" href="${esc(p.url)}" target="_blank" rel="noopener noreferrer">เปิดหน้าสินค้า ↗</a>`:''}
   </div><div class="radar-controls"><button class="button ${p.draft_id?'button-quiet':'button-primary'}" data-radar-prepare="${p.id}">${p.draft_id?'เปิดบทรีวิว':'เตรียมบทรีวิว →'}</button>
   </div></article>`;
 }).join(''):'<p class="empty">ยังไม่พบสินค้าตรงเงื่อนไข หรือยังไม่ได้เชื่อมข้อมูลจริง</p>';
 document.querySelectorAll('[data-radar-prepare]').forEach(b=>b.addEventListener('click',()=>run(async()=>{
  const result=await api('/studio/api/radar/'+b.dataset.radarPrepare+'/prepare',{method:'POST'});
  await refresh();selectDraft(result.draft_id);tab('drafts');
 },'เตรียมบทและคิวแล้ว — ส่งพรอมต์ไปสร้างคลิปใน Google Flow ได้เลย')));
}
$('radar-filter').addEventListener('click',()=>run(refresh));
$('radar-import-form').addEventListener('submit',e=>{e.preventDefault();run(async()=>{
 const file=$('radar-csv').files[0];if(!file)throw Error('เลือกไฟล์ CSV ก่อน');
 const fd=new FormData();fd.append('file',file);
 const result=await api('/studio/api/radar/import?platform='+$('radar-import-platform').value,{method:'POST',body:fd});
 await refresh();$('radar-csv').value='';toast('อ่านข้อมูลสินค้า '+result.count+' รายการแล้ว');
 })});
$('radar-sync').addEventListener('click',()=>run(async()=>{
 const result=await api('/studio/api/radar/sync',{method:'POST'});
 await refresh();
 const errors=Object.values(result.sources).filter(x=>x.state==='error');
 if(errors.length)throw Error('สแกนบางแหล่งไม่สำเร็จ: '+errors.map(x=>x.message).join('; '));
 toast('ดึงข้อมูลล่าสุด '+result.count+' รายการ');
}));
$('radar-prepare-top').addEventListener('click',()=>run(async()=>{
 const result=await api('/studio/api/radar/prepare-top',json('POST',{
  platform:$('radar-platform').value,limit:3,min_sales:100,min_commission:5}));
 await refresh();
 toast(result.prepared?`สร้างบทรีวิวให้สินค้า ${result.prepared} รายการแล้ว`:'ยังไม่พบสินค้าใหม่ที่มีข้อมูลยอดขาย ≥100 และค่าคอม ≥5%');
}));

// EXTERNAL PRODUCT RADAR: external popularity signals, manually confirmed listings.
async function externalSearch(){
 const params=new URLSearchParams({query:$('external-query').value.trim(),state:$('external-state').value});
 return api('/studio/api/external?'+params.toString());
}
function renderExternal(){
 const st=state.externalStatus;
 $('external-count').textContent=state.external.length+' รายการ';
 $('external-last').textContent=st?.latest?`สแกนล่าสุด: ${st.latest.at} · ${st.latest.source} · พบ ${st.latest.found} รายการ${st.latest.message?' · '+st.latest.message:''}`:'ยังไม่เคยสแกนข้อมูลเว็บภายนอก';
 $('external-list').innerHTML=state.external.length?state.external.map(x=>{
  const confirmation=(x.confirmed_tiktok?'TikTok ✓ ':'')+(x.confirmed_shopee?'Shopee ✓':'');
  return `<article class="radar-card">
   <div class="radar-score"><strong>${Number(x.score).toFixed(0)}</strong><small>คะแนนเบาะแส</small></div>
   <div class="radar-details"><strong>${esc(x.title)}</strong>
   <p>ที่มา: ${esc(x.source_name)} · ${esc(x.category||'ไม่ได้ระบุหมวดหมู่')}</p>
   <p>${x.trend_traffic===null?'ไม่มีข้อมูลจำนวนค้นหา':'ยอดค้นหาที่แหล่งข้อมูลรายงาน ≥'+Number(x.trend_traffic).toLocaleString('th-TH')+' (ไม่ใช่ยอดขาย)'}</p>
   <small>${confirmation?'ตรวจโดยผู้ใช้: '+esc(confirmation):'ยังไม่ได้ยืนยันว่ามีสินค้าบน TikTok / Shopee'} · ${esc(x.discovered_at.slice(0,16))}</small>
   <p><a href="${esc(x.source_url)}" target="_blank" rel="noopener noreferrer" class="radar-source-link">เปิดแหล่งข้อมูล ↗</a></p>
   </div><div class="radar-controls"><button class="button ${x.draft_id?'button-quiet':'button-primary'}" data-external-id="${x.id}">${x.draft_id?'เปิดบทรีวิว':'ตรวจสินค้าในแอป →'}</button></div>
   </article>`;
 }).join(''):'<p class="empty">ยังไม่มีข้อมูลที่ตรงเงื่อนไข · ลองเพิ่มสินค้าจากเว็บภายนอก หรือสแกน Google Trends</p>';
 document.querySelectorAll('[data-external-id]').forEach(b=>b.addEventListener('click',()=>{
  const x=state.external.find(item=>String(item.id)===b.dataset.externalId);
  if(!x)return;
  if(x.draft_id){selectDraft(x.draft_id);tab('drafts');return}
  selectExternal(x);
 }));
 if(state.selectedExternal){
  const updated=state.external.find(x=>x.id===state.selectedExternal.id);
  if(updated)state.selectedExternal=updated;
 }
}
function selectExternal(x){
 state.selectedExternal=x;
 $('external-check-panel').hidden=false;
 $('external-selection').textContent=x.title+' · '+x.source_name;
 const term=x.title;
 $('external-tiktok-search').href='https://www.google.com/search?q='+encodeURIComponent('site:shop.tiktok.com/th/pdp/ '+term);
 $('external-shopee-search').href='https://shopee.co.th/search?keyword='+encodeURIComponent(term);
 $('external-tiktok-link').value=x.tiktok_link||'';
 $('external-shopee-link').value=x.shopee_link||'';
 $('external-tiktok-confirm').checked=!!x.confirmed_tiktok;
 $('external-shopee-confirm').checked=!!x.confirmed_shopee;
 $('external-features').value=x.features||'';
 $('external-audience').value=x.audience||'';
 $('external-check-panel').scrollIntoView({behavior:'smooth',block:'start'});
}
$('external-scan').addEventListener('click',()=>run(async()=>{
 const btn=$('external-scan');btn.disabled=true;
 try{
  const r=await api('/studio/api/external/scan',{method:'POST'});
  await refresh();
  toast(`สแกนพบ ${r.imported} หัวข้อ · ไม่ใช่ยอดขายจริง`);
 }finally{btn.disabled=false}
}));
$('external-add-form').addEventListener('submit',e=>{e.preventDefault();run(async()=>{
 const f=e.currentTarget,fd=new FormData(f);
 const r=await api('/studio/api/external/manual',json('POST',Object.fromEntries(fd.entries())));
 f.reset();await refresh();
 toast(`เพิ่มสินค้าเว็บภายนอก ${r.count} รายการ`);
})});
$('external-import-button').addEventListener('click',()=>run(async()=>{
 const f=$('external-import-csv').files[0];if(!f)throw Error('เลือกไฟล์ CSV ก่อน');
 const fd=new FormData();fd.append('file',f);
 const r=await api('/studio/api/external/import',{method:'POST',body:fd});
 $('external-import-csv').value='';await refresh();toast(`นำเข้า ${r.imported} รายการ`);
}));
$('external-filter').addEventListener('click',()=>run(refresh));
$('external-cancel').addEventListener('click',()=>{$('external-check-panel').hidden=true;state.selectedExternal=null});
function externalPayload(){
 return {tiktok_link:$('external-tiktok-link').value.trim(),shopee_link:$('external-shopee-link').value.trim(),
  confirmed_tiktok:$('external-tiktok-confirm').checked,confirmed_shopee:$('external-shopee-confirm').checked,
  features:$('external-features').value.trim(),audience:$('external-audience').value.trim()};
}
async function saveExternal(){
 if(!state.selectedExternal)throw Error('กรุณาเลือกสินค้า');
 const selectedId=state.selectedExternal.id;
 await api(`/studio/api/external/${selectedId}/match`,json('PATCH',externalPayload()));
 await refresh();
 const latest=state.external.find(x=>x.id===selectedId);
 if(latest)selectExternal(latest);
}
$('external-match-form').addEventListener('submit',e=>{e.preventDefault();run(saveExternal,'บันทึกผลการตรวจสินค้าแล้ว')});
$('external-prepare').addEventListener('click',()=>run(async()=>{
 if(!state.selectedExternal)throw Error('กรุณาเลือกสินค้า');
 const id=state.selectedExternal.id;
 await saveExternal();
 const r=await api(`/studio/api/external/${id}/prepare`,{method:'POST'});
 await refresh();selectDraft(r.draft_id);tab('drafts');
 $('external-check-panel').hidden=true;
 toast(r.created?'สร้างบทรีวิวและคิวตามแพลตฟอร์มที่ยืนยันแล้ว':'เปิดบทรีวิวเดิม');
}));

// V4: Autopilot dashboard — real runs, no fake sales or fake posted statuses.
let autoData=null, tiktokData=null, tiktokJobs=[], approveId=null;
async function refreshAuto(){
 const [a,t,jobs,q]=await Promise.all([api('/studio/api/autopilot/status'),api('/studio/api/tiktok/status'),api('/studio/api/tiktok/jobs'),api('/studio/api/queue')]);
 autoData=a;tiktokData=t;tiktokJobs=jobs;
 const c=a.config;
 $('auto-live').textContent=c.enabled?'● เปิดระบบ':'○ ปิดระบบ';
 $('auto-running').textContent=a.running?'กำลังประมวลผลคิวจริง...':'พร้อมรับคำสั่ง';
 for(const [name,val] of [['enabled',c.enabled],['discover',c.auto_discover],['prepare',c.auto_prepare],['generate',c.auto_generate],['no-ref',c.allow_without_reference]])$('auto-'+name).checked=val;
 $('auto-max-drafts').value=c.max_new_drafts_per_cycle;
 $('auto-max-videos').value=c.max_videos_per_day;
 $('auto-hours').value=c.scan_hours;
 $('auto-providers').innerHTML=`<p>Google Veo API: <b>${a.providers.google_veo?'มี API key':'ยังไม่ตั้งค่า'}</b></p>
 <p>Brave Search API: <b>${a.providers.brave_search?'มี API key':'ยังไม่ตั้งค่า'}</b></p>
 <p>TikTok Developer App: <b>${t.app_configured?'ตั้งค่าแล้ว':'ยังไม่ได้ตั้งค่า'}</b></p>
 <p>TikTok OAuth: <b>${t.connected&&t.publish_scope?'ได้สิทธิ์โพสต์':'ยังไม่เชื่อม/ยังไม่ได้ video.publish'}</b></p>
 <p>Shopee Video API: <b>ยังไม่ยืนยันช่องทางเผยแพร่อัตโนมัติ</b></p>`;
 $('tiktok-note').textContent=t.connected&&t.publish_scope?
 'ได้รับ token video.publish แล้ว; ให้ดูคลิปและยืนยันแต่ละโพสต์ก่อนจัดเวลา (API ไม่เชื่อมตะกร้า)':'ยังไม่ได้รับ token video.publish จาก TikTok · ขั้นตอนนี้ยังใช้งานไม่ได้';
 $('auto-possible').innerHTML=a.possible_matches.length?a.possible_matches.slice(0,8).map(x=>`<div class="item"><div class="item-body"><b>${esc(x.title)}</b><small>${esc(x.platform)} · ยังไม่ได้ยืนยันรุ่นและค่าคอม</small></div><a class="button button-quiet" href="${esc(x.url)}" target="_blank" rel="noopener noreferrer">ตรวจเว็บ ↗</a></div>`).join(''):'<p class="empty">ยังไม่พบรายการเว็บที่ตรงเงื่อนไข (ต้องมี Brave API key)</p>';
 $('auto-logs').innerHTML=a.logs.length?a.logs.map(x=>`<div class="item"><div class="item-body"><b>${esc(x.kind)} · ${esc(x.state)}</b><small>${esc(x.at)} · ${esc(x.detail)}</small></div></div>`).join(''):'<p class="empty">ยังไม่มีประวัติการทำงาน</p>';
 const jt=Object.fromEntries(jobs.map(x=>[x.queue_id,x]));
 $('auto-publish-list').innerHTML=q.filter(x=>x.platform==='tiktok'&&x.video_filename).map(x=>{
  const j=jt[x.id];
  const status=j?j.state:'ยังไม่อนุมัติ';
  return `<div class="item"><div class="item-body"><b>${esc(x.product_title)}</b><small>#${x.id} · ${esc(status)} ${j?.detail?'· '+esc(j.detail):''}</small>
  <div><a href="${link(x.video_filename)}" target="_blank" rel="noopener noreferrer">ดูคลิป MP4 ↗</a></div></div>
  ${j?.publish_id?`<button class="button button-quiet" data-check-post="${x.id}">ตรวจผลโพสต์</button>`:
   `<button class="button button-outline" data-approve-post="${x.id}">ดูและอนุมัติโพสต์</button>`}</div>`;
 }).join('')||'<p class="empty">ยังไม่มีวิดีโอ MP4 สำหรับ TikTok · สร้างวิดีโอจากหน้าคลิป AI หรือเปิดออโต้ผลิตวิดีโอก่อน</p>';
 document.querySelectorAll('[data-approve-post]').forEach(b=>b.addEventListener('click',()=>run(async()=>{
   if(!t.connected||!t.publish_scope)throw Error('ยังเชื่อม TikTok Login Kit พร้อม video.publish ไม่สำเร็จ');
   const info=await api('/studio/api/tiktok/creator');
   approveId=Number(b.dataset.approvePost);
   const row=q.find(x=>x.id===approveId);
   $('auto-approve-title').textContent='ตรวจและยืนยันโพสต์: '+row.product_title;
   $('auto-creator-name').textContent=`บัญชี @${info.creator_username||'?'} · ${info.creator_nickname||''}`;
   $('auto-privacy').innerHTML=(info.privacy_level_options||[]).map(k=>`<option value="${esc(k)}">${esc(k)}</option>`).join('');
   $('auto-approved-caption').value=row.caption||'';
   $('auto-post-at').value='';$('auto-no-basket-ack').checked=false;$('auto-aigc-ack').checked=false;
   $('auto-approve-panel').hidden=false;
   $('auto-approve-panel').scrollIntoView({behavior:'smooth',block:'center'});
 })));
 document.querySelectorAll('[data-check-post]').forEach(b=>b.addEventListener('click',()=>run(async()=>{
   const r=await api('/studio/api/tiktok/jobs/'+b.dataset.checkPost+'/check',{method:'POST'});
   toast('TikTok: '+r.tiktok_status);await refreshAuto();await refresh();
 })));
}
$('auto-form').addEventListener('submit',e=>{e.preventDefault();run(async()=>{
 const settings={enabled:$('auto-enabled').checked,auto_discover:$('auto-discover').checked,
 auto_prepare:$('auto-prepare').checked,auto_generate:$('auto-generate').checked,
 allow_without_reference:$('auto-no-ref').checked,
 max_new_drafts_per_cycle:Number($('auto-max-drafts').value),max_videos_per_day:Number($('auto-max-videos').value),
 scan_hours:Number($('auto-hours').value),max_video_wait_minutes:15};
 await api('/studio/api/autopilot/settings',json('PUT',settings));await refreshAuto();
},'บันทึกการตั้งค่าระบบแล้ว')});
$('auto-now').addEventListener('click',()=>run(async()=>{
 const r=await api('/studio/api/autopilot/tick',{method:'POST'});
 await refreshAuto();toast('ส่งคำสั่งงาน: '+r.state+' — ตรวจประวัติด้านล่าง');
}));
$('auto-refresh').addEventListener('click',()=>run(refreshAuto));
$('auto-approve-cancel').addEventListener('click',()=>{$('auto-approve-panel').hidden=true;approveId=null});
$('auto-approve-go').addEventListener('click',()=>run(async()=>{
 if(approveId===null)throw Error('เลือกโพสต์ก่อน');
 const at=$('auto-post-at').value;
 if(!at)throw Error('ต้องเลือกวันและเวลาโพสต์');
 const iso=new Date(at).toISOString();
 await api('/studio/api/tiktok/queue/'+approveId+'/approve',json('POST',{
 privacy_level:$('auto-privacy').value,scheduled_at:iso,caption:$('auto-approved-caption').value.trim(),
 acknowledge_no_basket:$('auto-no-basket-ack').checked,
 acknowledge_aigc_and_rights:$('auto-aigc-ack').checked}));
 approveId=null;$('auto-approve-panel').hidden=true;await refreshAuto();
},'อนุมัติโพสต์พร้อมกำหนดเวลาแล้ว · รอส่งตามเวลาและตรวจผล TikTok'));
refreshAuto().catch(e=>console.warn('Autopilot status:',e));
setInterval(()=>{if(document.getElementById('autopilot').classList.contains('active'))refreshAuto().catch(()=>{});},25000);

// PC V6: credentials entered only on the locally running server; never echo saved values.
async function refreshSetup(){
 const st=await api('/studio/api/setup');
 $('setup-status').textContent=[
  'Veo API: '+(st.gemini_api_key?'ตั้งค่าแล้ว':'ยังไม่ตั้งค่า'),
  'Brave Search: '+(st.brave_search_api_key?'ตั้งค่าแล้ว':'ยังไม่ตั้งค่า'),
  'OpenAI: '+(st.openai_api_key?'ตั้งค่าแล้ว':'ยังไม่ตั้งค่า'),
  'TikTok Developer: '+(st.tiktok_developer?'ตั้งค่าบางส่วนแล้ว':'ยังไม่ตั้งค่า')
 ].join(' · ');
}
$('setup-form').addEventListener('submit',e=>{e.preventDefault();run(async()=>{
 const f=e.currentTarget;
 const values=Object.fromEntries(new FormData(f).entries());
 await api('/studio/api/setup/keys',json('POST',values));
 f.reset();await refreshSetup();await refresh();
 toast('บันทึกคีย์ไว้บนเครื่องนี้แล้ว');
})});
document.querySelector('[data-tab="setup"]').addEventListener('click',()=>run(refreshSetup));

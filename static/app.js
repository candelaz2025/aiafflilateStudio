(() => {
  'use strict';
  let me=null;
  const $=id=>document.getElementById(id);
  const esc=s=>String(s??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const msg=t=>{$('message').textContent=t;};
  const val=form=>Object.fromEntries(new FormData(form));
  async function api(path,method='GET',data){
    const headers={};
    if(data!==undefined)headers['Content-Type']='application/json';
    if(me&&method!=='GET')headers['X-CSRF-Token']=me.csrf;
    const r=await fetch(path,{method,headers,credentials:'same-origin',body:data===undefined?undefined:JSON.stringify(data)});
    const body=await r.json().catch(()=>({}));
    if(!r.ok)throw Error(typeof body.detail==='string'?body.detail:'คำขอล้มเหลว '+r.status);
    return body;
  }
  // Browser validation bubbles follow the browser's language; replace them with Thai for every form.
  function fieldName(el){
    const label=el.closest('label');const first=label&&label.firstChild;
    // Drop trailing hints such as "12 ตัวขึ้นไป..." or "(ไม่จำเป็น)" from the label text.
    const text=first&&first.nodeType===Node.TEXT_NODE?first.nodeValue.trim().split(/\s+(?=[0-9(])/)[0]:'';
    return text||'ช่องนี้';
  }
  function thaiValidity(el){
    const v=el.validity;
    if(v.valueMissing)return el.type==='checkbox'?'กรุณาติ๊กยืนยันก่อนดำเนินการต่อ':el.tagName==='SELECT'?'กรุณาเลือก '+fieldName(el):'กรุณากรอก '+fieldName(el);
    if(v.typeMismatch&&el.type==='email')return 'อีเมลไม่ถูกต้อง ต้องมีรูปแบบ name@example.com';
    if(v.typeMismatch&&el.type==='url')return 'ลิงก์ไม่ถูกต้อง ต้องขึ้นต้นด้วย https://';
    if(v.tooShort)return fieldName(el)+' ต้องมีอย่างน้อย '+el.minLength+' ตัวอักษร (ตอนนี้ '+el.value.length+')';
    if(v.tooLong)return fieldName(el)+' ยาวได้ไม่เกิน '+el.maxLength+' ตัวอักษร';
    if(v.rangeUnderflow)return fieldName(el)+' ต้องไม่น้อยกว่า '+el.min;
    if(v.rangeOverflow)return fieldName(el)+' ต้องไม่เกิน '+el.max;
    if(v.stepMismatch||v.badInput)return fieldName(el)+' ต้องเป็นตัวเลขที่ถูกต้อง';
    if(v.patternMismatch)return fieldName(el)+' มีรูปแบบไม่ถูกต้อง';
    return 'ข้อมูลในช่องนี้ไม่ถูกต้อง';
  }
  document.addEventListener('invalid',e=>{
    const el=e.target;if(!el.setCustomValidity)return;
    el.setCustomValidity('');
    if(!el.validity.valid)el.setCustomValidity(thaiValidity(el));
    el.setAttribute('aria-invalid','true');
  },true);
  const clearValidity=e=>{const el=e.target;if(el.setCustomValidity){el.setCustomValidity('');el.removeAttribute('aria-invalid');}};
  document.addEventListener('input',clearValidity,true);
  document.addEventListener('change',clearValidity,true);
  function show(){
    $('auth').hidden=!!me;$('app').hidden=!me;
    const cta=$('hero-cta');cta.textContent=me?'▶ ไปที่พื้นที่ทำงานของฉัน':'✦ สมัครฟรีเพื่อเริ่มใช้งาน';cta.href=me?'#app':'#register';$('signup-hint').hidden=!!me;const studioLink=$('studio-top-link');if(studioLink)studioLink.hidden=!(me&&me.role==='admin');$('admin-top-link').hidden=!(me&&me.role==='admin');
    $('who').innerHTML=me?`<span>${esc(me.username)}${me.role==='admin'?' (Admin)':''}</span><button id="logout" type="button">ออกจากระบบ</button>`:'';
    if(me)$('logout').addEventListener('click',async()=>{try{await api('/api/logout','POST');me=null;show();msg('ออกจากระบบแล้ว');}catch(e){msg(e.message);}});
  }
  async function signedIn(info){me=info;show();await loadIdeas();await refreshWorkspace();msg('เข้าสู่ระบบแล้ว');}
  $('loginform').addEventListener('submit',async e=>{e.preventDefault();try{await signedIn(await api('/api/login','POST',val(e.target)));e.target.reset();}catch(err){msg(err.message);}});
  $('registerform').addEventListener('submit',async e=>{e.preventDefault();try{await signedIn(await api('/api/register','POST',val(e.target)));e.target.reset();}catch(err){msg(err.message);}});
  async function loadIdeas(){
    const data=await api('/api/ideas?order='+encodeURIComponent($('sort').value));
    $('feed').innerHTML=data.length?data.map(x=>{
      const statuses={proposed:'เสนอใหม่',planned:'อยู่ในแผน',building:'กำลังพัฒนา',released:'เปิดใช้แล้ว',declined:'ยังไม่รับทำ'};
      const kinds={feature:'ฟีเจอร์',bug:'แจ้งบั๊ก',feedback:'ความคิดเห็น'};
      return `<article class="idea"><div class="votes"><div>${x.votes}</div><button class="${x.voted?'selected':''}" data-vote="${x.id}">${x.voted?'ถอนโหวต':'▲ โหวต'}</button></div><div><h3>${esc(x.title)}</h3><div class="meta">${esc(x.author)} · ${esc(kinds[x.kind]||x.kind)} · <span class="status">${esc(statuses[x.status]||x.status)}</span> · ${esc((x.created_at||'').slice(0,10))}</div><div class="desc">${esc(x.body)}</div><div class="actions"><button class="mini secondary" data-comments="${x.id}">💬 ความคิดเห็น (${x.comments})</button>${me.role==='admin'?`<select aria-label="เปลี่ยนสถานะ" class="admin-select" data-status="${x.id}">${Object.entries(statuses).map(([k,v])=>`<option value="${k}" ${x.status===k?'selected':''}>${v}</option>`).join('')}</select>`:''}</div><div id="comments-${x.id}" hidden></div></div></article>`;
    }).join(''):'<div class="panel">ยังไม่มีไอเดีย ลองเสนอเรื่องแรกได้เลย</div>';
  }
  $('sort').addEventListener('change',()=>loadIdeas().catch(e=>msg(e.message)));
  $('feed').addEventListener('click',async e=>{
    const vote=e.target.closest('[data-vote]');const comments=e.target.closest('[data-comments]');
    try{
      if(vote){await api(`/api/ideas/${vote.dataset.vote}/vote`,'POST');await loadIdeas();return;}
      if(comments){
        const id=comments.dataset.comments,box=$('comments-'+id);
        if(!box.hidden){box.hidden=true;return;}
        const items=await api(`/api/ideas/${id}/comments`);
        box.innerHTML=`<div class="comment-list">${items.length?items.map(c=>`<div class="comment-item"><strong>${esc(c.author)}:</strong> ${esc(c.body)}</div>`).join(''):'ยังไม่มีความคิดเห็น'}</div><form data-comment-form="${id}"><label>แสดงความคิดเห็น<input name="body" minlength="2" maxlength="800" required></label><button class="mini" type="submit">ส่งความคิดเห็น</button></form>`;
        box.hidden=false;
      }
    }catch(ex){msg(ex.message);}
  });
  $('feed').addEventListener('submit',async e=>{
    const form=e.target.closest('[data-comment-form]');if(!form)return;e.preventDefault();
    try{await api(`/api/ideas/${form.dataset.commentForm}/comments`,'POST',val(form));await loadIdeas();msg('ส่งความคิดเห็นแล้ว');}catch(ex){msg(ex.message);}
  });
  $('feed').addEventListener('change',async e=>{
    const sel=e.target.closest('[data-status]');if(!sel)return;
    try{await api(`/api/ideas/${sel.dataset.status}/status`,'PATCH',{status:sel.value});msg('อัปเดตสถานะแล้ว');}catch(ex){msg(ex.message);await loadIdeas();}
  });
  $('ideaform').addEventListener('submit',async e=>{e.preventDefault();try{await api('/api/ideas','POST',val(e.target));e.target.reset();selectTab('ideas');await loadIdeas();msg('เสนอไอเดียเรียบร้อยแล้ว');}catch(ex){msg(ex.message);}});
  // Import data provided voluntarily by the signed-in member. No Shopee cookies
  // or cross-origin requests, no background scraping, and no private page access.
  let shopeeScanned=[];
  const scanStatus=$('shopee-scan-status'), scanResults=$('shopee-scan-results');
  function renderShopeeScan(data){
    shopeeScanned=Array.isArray(data.items)?data.items:[];
    scanStatus.textContent=`พบ ${shopeeScanned.length} รายการจากข้อมูลที่คุณส่งมา · ยังไม่ยืนยันยอดขายหรือสิทธิ์ EXTRA COMM`;
    scanResults.innerHTML=shopeeScanned.length?shopeeScanned.map((item,i)=>`<article class="radar-result listing"><div class="radar-result-main"><div class="meta">${esc(item.source)} · ไม่ได้ตรวจผ่าน Shopee API</div><h3>${esc(item.title)}</h3><p>${item.price!==null?'ราคาตามข้อมูลที่ส่งมา ฿'+esc(item.price):'ราคาไม่ปรากฏ'}${item.extra_comm_rate_hint!==null?' · Extra Comm ที่พบในข้อความ '+esc(item.extra_comm_rate_hint)+'% (ยังไม่ยืนยัน)':''}${item.orders!==null?' · ออเดอร์ที่รายงาน '+esc(item.orders):''}</p><div class="radar-label">${item.url?'มีลิงก์ Shopee':'ยังไม่มีลิงก์สินค้า'} · ตรวจสอบสินค้าตรงรุ่นและอัตราคอมจากบัญชีของคุณก่อนใช้</div></div><div class="radar-result-actions">${item.url?`<a href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">ดูสินค้า ↗</a>`:''}<button type="button" data-save-shopee="${i}">บันทึกในสินค้าของฉัน</button></div></article>`).join(''):'<div class="notice">ไม่มีรายการสินค้าที่ระบบอ่านได้ ตรวจหัวคอลัมน์ของ CSV หรือข้อมูลที่คัดลอกอีกครั้ง</div>';
  }
  $('shopee-paste-form').addEventListener('submit',async e=>{
    e.preventDefault();const b=e.target.querySelector('button[type=submit]');b.disabled=true;
    scanStatus.textContent='กำลังอ่านข้อมูลที่คัดลอก...';
    try{renderShopeeScan(await api('/api/my/shopee/preview','POST',{content:$('shopee-paste-input').value}));}
    catch(err){scanStatus.textContent='อ่านข้อมูลไม่สำเร็จ: '+err.message;scanResults.replaceChildren();}
    finally{b.disabled=false;}
  });
  $('shopee-csv-form').addEventListener('submit',async e=>{
    e.preventDefault();const b=e.target.querySelector('button[type=submit]'),f=$('shopee-csv-file').files[0];
    if(!f){scanStatus.textContent='กรุณาเลือกไฟล์ CSV';return;}
    if(f.size>2*1024*1024){scanStatus.textContent='ไฟล์เกิน 2MB';return;}
    b.disabled=true;scanStatus.textContent='กำลังอ่านรายงาน CSV...';
    try{const fd=new FormData();fd.append('file',f);const res=await fetch('/api/my/shopee/report-preview',{method:'POST',headers:{'X-CSRF-Token':me.csrf},credentials:'same-origin',body:fd});const data=await res.json();if(!res.ok)throw Error(data.detail||'อ่านไฟล์ไม่สำเร็จ');renderShopeeScan(data);}
    catch(err){scanStatus.textContent='อ่าน CSV ไม่สำเร็จ: '+err.message;scanResults.replaceChildren();}
    finally{b.disabled=false;}
  });
  scanResults.addEventListener('click',async e=>{
    const btn=e.target.closest('[data-save-shopee]');if(!btn)return;
    const row=shopeeScanned[Number(btn.dataset.saveShopee)];if(!row)return;
    if(!confirm('ยืนยันว่าคุณจะบันทึกข้อมูลที่คัดลอก/นำเข้ามาเอง และจะตรวจสิทธิ์ Affiliate กับ Extra Comm อีกครั้งก่อนทำคลิป?'))return;
    btn.disabled=true;
    try{await api('/api/my/products','POST',{title:row.title,url:row.url||'',platform:'shopee',extra_comm_checked:false});btn.textContent='บันทึกแล้ว';await refreshWorkspace();msg('เพิ่มสินค้าเรียบร้อย · ค่าคอมยังไม่ได้ยืนยัน');}
    catch(err){msg('บันทึกไม่สำเร็จ: '+err.message);btn.disabled=false;}
  });

  const radarResults = $('radar-results');
  $('radar-auto').addEventListener('click',async()=>{
    const button=$('radar-auto');button.disabled=true;
    $('radar-topics').textContent='กำลังสำรวจคำค้นจากกระแสและข่าว...';
    try{
      const info=await api('/api/my/radar/trending');
      $('radar-topics').innerHTML=info.topics.length?`<div class="panel"><strong>หัวข้อสินค้าจากเว็บจริง (ไม่ใช่ยอดขาย)</strong><div class="radar-tags">${info.topics.map((t,i)=>`<button type="button" data-radar-topic="${i}">${esc(t.keyword)} · ${esc(t.source)}</button>`).join('')}</div></div>`:'<div class="panel">ยังไม่พบคำค้นเกี่ยวกับสินค้าจากกระแสวันนี้ ลองพิมพ์ชื่อสินค้าเองหรือใช้หมวดแนะนำด้านบน (ระบบไม่สร้างผลลัพธ์ปลอม)</div>';
      $('radar-topics').dataset.topics=JSON.stringify(info.topics);
    }catch(err){$('radar-topics').textContent='ค้นหากระแสไม่สำเร็จ: '+err.message;}
    finally{button.disabled=false;}
  });
  $('radar-topics').addEventListener('click',e=>{
    const b=e.target.closest('[data-radar-topic]');if(!b)return;
    try{const t=JSON.parse($('radar-topics').dataset.topics||'[]')[Number(b.dataset.radarTopic)];
      if(t){$('radar-query').value=t.keyword;$('radarform').requestSubmit();}}
    catch(_){msg('ไม่สามารถอ่านคำค้นได้');}
  });
  let radarItems = [];
  $('radarform').addEventListener('submit', async e => {
    e.preventDefault();
    const q = $('radar-query').value.trim();
    $('radar-submit').disabled = true;
    $('radar-status').textContent='กำลังค้นหาจากแหล่งข้อมูลภายนอก...';
    radarResults.replaceChildren();
    $('radar-sources').replaceChildren();
    $('radar-shop-links').replaceChildren();
    try {
      const extra=$('extra-comm-mode').checked;
      const response=await api('/api/my/radar/search?q='+encodeURIComponent(q)+(extra?'&extra_comm_only=true':''));
      radarItems=response.items;
      const candidate=radarItems.filter(x=>x.kind==='marketplace_candidate').length;
      $('radar-status').textContent=`พบผล ${radarItems.length} รายการ · ลิงก์หน้าสินค้าที่ต้องตรวจสอบ ${candidate} รายการ · ${response.cached?'ใช้ผลค้นหาที่แคชไว้':'ค้นล่าสุด'} · ${extra?'เฉพาะเบาะแส EXTRA COMM · ':''}ยังไม่ยืนยันยอดขาย/ค่าคอม`;
      $('radar-shop-links').innerHTML=`<a target="_blank" rel="noopener noreferrer" href="${esc(response.search_links.shopee)}">ค้นใน Shopee เอง ↗</a><a target="_blank" rel="noopener noreferrer" href="${esc(response.search_links.tiktok)}">ค้น TikTok Shop ผ่านเว็บ ↗</a>`;
      radarResults.innerHTML=radarItems.length?radarItems.map((item,i)=>{
        const listing=item.kind==='marketplace_candidate';
        return `<article class="radar-result ${listing?'listing':'news'}"><div class="radar-result-main"><div class="meta">${esc(item.source)} · ${esc(item.platform==='shopee'?'Shopee (ลิงก์ที่อาจเป็นหน้าสินค้า)':item.platform==='tiktok'?'TikTok Shop (ลิงก์ที่อาจเป็นหน้าสินค้า)':'ข่าว/บทความสินค้า')}</div><h3>${esc(item.title)}</h3><p>${esc(item.description||'ยังไม่มีรายละเอียดสินค้า')}</p><div class="radar-label">${item.extra_comm_mentioned?'เว็บกล่าวถึง EXTRA COMM แต่ต้องตรวจจาก Shopee Affiliate ด้วยตัวเอง':'ต้องตรวจรุ่น ราคา และสิทธิ์ Affiliate ก่อนนำไปใช้'}</div></div><div class="radar-result-actions"><a href="${esc(item.url)}" rel="noopener noreferrer" target="_blank">ดูแหล่งข้อมูล ↗</a>${listing?`<button type="button" data-save-radar="${i}">ตรวจแล้ว · บันทึกสินค้า</button>`:''}</div></article>`;
      }).join(''):'<div class="panel">ยังไม่พบผลจริงจากแหล่งที่ใช้ได้ ลองเปลี่ยนคำค้นหรือตั้งค่า Brave Search API เพิ่มเติม ระบบจะไม่สร้างสินค้าปลอมขึ้นมาแทน</div>';
      $('radar-sources').innerHTML='<div class="meta">ที่มาข้อมูล:</div>'+response.sources.map(src=>`<div class="meta">${esc(src.name)} — ${src.status==='ok'?'รับข้อมูลได้ ('+Number(src.found||0)+' รายการ)':'ติดต่อไม่ได้: '+esc(src.message||'ไม่ทราบสาเหตุ')}</div>`).join('');
    }catch(err){$('radar-status').textContent='ค้นหาไม่สำเร็จ: '+err.message;}
    finally{$('radar-submit').disabled=false;}
  });
  document.querySelectorAll('[data-radar-example]').forEach(b=>b.addEventListener('click',()=>{
    $('radar-query').value=b.dataset.radarExample;
    $('radarform').requestSubmit();
  }));
  radarResults.addEventListener('click',async e=>{
    const b=e.target.closest('[data-save-radar]'); if(!b)return;
    const item=radarItems[Number(b.dataset.saveRadar)];if(!item||item.kind!=='marketplace_candidate')return;
    if(!confirm('ตรวจสอบจากลิงก์แล้วหรือยังว่าสินค้าตรงรุ่น และมีอยู่ในบัญชี Affiliate ของคุณ?\n\nระบบยังไม่ยืนยันยอดขายและค่าคอม'))return;
    b.disabled=true;
    try{
      await api('/api/my/products','POST',{title:item.title,url:item.url,platform:item.platform});
      msg('บันทึกลิงก์เป็นสินค้าส่วนตัวแล้ว ตรวจสอบสิทธิ์ก่อนเริ่มสร้างบท');
      await refreshWorkspace();await goTab('products');
    }catch(err){msg(err.message);b.disabled=false;}
  });
  async function loadProducts(){
    const products=await api('/api/my/products');
    $('productlist').innerHTML=products.length?products.map(p=>`<div class="simple-row"><div><strong>${esc(p.title)}</strong><div class="meta">${esc(p.platform)} · ${p.extra_comm_checked?`EXTRA COMM ยืนยันโดยสมาชิกเอง${p.extra_comm_rate!==null?' · '+esc(p.extra_comm_rate)+'%':''} · ตรวจเมื่อ ${esc((p.extra_comm_checked_at||'').slice(0,10))}`:'ไม่ได้ยืนยัน Extra Comm'}</div></div><div class="radar-result-actions">${p.url?`<a href="${esc(p.url)}" target="_blank" rel="noopener noreferrer">เปิดลิงก์สินค้า ↗</a>`:''}${p.platform==='shopee'?`<button type="button" data-check-extra="${p.id}">${p.extra_comm_checked?'แก้เรท Extra Comm':'ตรวจ Extra Comm แล้ว'}</button>`:''}<button type="button" data-reuse-product="${p.id}" class="mini">↻ ทำคลิปใหม่ / จำเวลา</button><button type="button" data-track-product="${p.id}" class="mini secondary">◷ ดูผลขาย</button></div></div>`).join(''):'<div class="panel">ยังไม่มีสินค้าในบัญชีนี้</div>';
  }
  $('product-extra-checked').addEventListener('change',e=>{$('product-extra-rate').disabled=!e.target.checked;if(!e.target.checked)$('product-extra-rate').value='';});
  $('productlist').addEventListener('click',async e=>{
    const reuse=e.target.closest('[data-reuse-product]');
    if(reuse){
      if(!confirm('สร้างสคริปต์ใหม่สำหรับสินค้าตัวนี้ และบันทึกเวลาที่หยิบมาทำซ้ำหรือไม่?'))return;
      reuse.disabled=true;
      try{const d=await api('/api/my/drafts','POST',{product_id:Number(reuse.dataset.reuseProduct),style:'pov'});
        await refreshWorkspace();await goTab('tracking');msg('บันทึกการทำคลิปครั้งที่ '+d.use_number+' แล้ว (ยังไม่สร้าง MP4)');
      }catch(err){msg(err.message);}finally{reuse.disabled=false;}
      return;
    }
    const track=e.target.closest('[data-track-product]');
    if(track){await goTab('tracking');await showProductHistory(Number(track.dataset.trackProduct));return;}
    const b=e.target.closest('[data-check-extra]');if(!b)return;
    const id=Number(b.dataset.checkExtra);
    const ok=confirm('คุณตรวจจาก Shopee Affiliate ของบัญชีตัวเองแล้วหรือไม่ว่า EXTRA COMM ยังมีอยู่? กด ยกเลิก เพื่อถอดป้ายหรือไม่แก้ไข');
    if(!ok){if(confirm('ต้องการถอนป้าย Extra Comm ที่บันทึกไว้หรือไม่?')){try{await api('/api/my/products/'+id+'/extra-comm','PATCH',{checked:false,rate:null});await loadProducts();msg('ถอนป้าย Extra Comm แล้ว');}catch(err){msg(err.message);}}return;}
    const v=prompt('กรอกเปอร์เซ็นต์ค่าคอมพิเศษตามที่ Shopee แสดง (0–100) หรือเว้นว่างหากยังไม่ทราบ','');
    if(v===null)return;
    if(v.trim()&&!/^(?:100(?:\.0{1,2})?|\d{1,2}(?:\.\d{1,2})?)$/.test(v.trim())){msg('กรอกเรท 0–100 สูงสุด 2 ตำแหน่ง');return;}
    try{await api('/api/my/products/'+id+'/extra-comm','PATCH',{checked:true,rate:v.trim()?Number(v):null});await loadProducts();msg('บันทึก Extra Comm (ผู้ใช้ยืนยันเอง) แล้ว');}catch(err){msg(err.message);}
  });
  $('productform').addEventListener('submit',async e=>{e.preventDefault();try{const data=val(e.target);data.extra_comm_checked=!!$('product-extra-checked').checked;data.extra_comm_rate=$('product-extra-rate').value.trim()||null;await api('/api/my/products','POST',data);e.target.reset();$('product-extra-rate').disabled=true;await loadProducts();msg('บันทึกสินค้าส่วนตัวแล้ว');}catch(ex){msg(ex.message);}});
  const thTime=s=>{if(!s)return 'ยังไม่มี';const dt=new Date(s);return Number.isNaN(dt.getTime())?String(s):dt.toLocaleString('th-TH',{timeZone:'Asia/Bangkok',year:'numeric',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});};
  const thNum=n=>(Number(n||0)).toLocaleString('th-TH');
  const thBaht=s=>((Number(s||0))/100).toLocaleString('th-TH',{minimumFractionDigits:2,maximumFractionDigits:2});
  let trackingEvents=[];
  async function showProductHistory(productId){
    try{
      const r=await api('/api/my/products/'+productId+'/history');
      trackingEvents=r.events;
      $('tracking-detail').innerHTML=`<div class="panel"><h3>ประวัติ: ${esc(r.product.title)}</h3><div class="tracking-history">${r.events.length?r.events.map(e=>`<div class="tracking-event"><div><strong>ครั้งที่ ${e.use_number} · สคริปต์ #${e.draft_id}</strong><div class="meta">บันทึกเวลา ${esc(thTime(e.created_at))} · ${esc(e.style)}</div><div class="meta">${e.recorded_at?'👁 '+thNum(e.views)+' วิว · '+thNum(e.clicks)+' คลิก · 🛒 '+thNum(e.orders)+' ออเดอร์ · ฿'+thBaht(e.commission_satang)+' ค่าคอม':'ยังไม่ได้บันทึกผลขาย'}</div></div><button type="button" data-edit-perf="${e.draft_id}" class="mini secondary">บันทึกผล</button></div>`).join(''):'ยังไม่มีครั้งที่หยิบสินค้ามาสร้างบท'}</div></div>`;
    }catch(err){msg(err.message);}
  }
  async function loadTracking(){
    const [r,drafts]=await Promise.all([api('/api/my/product-tracking'),api('/api/my/drafts')]);
    $('tracking-overview').innerHTML=r.products.length?r.products.map(p=>`<article class="panel tracking-card"><div class="meta">${esc(p.platform)} · ${p.use_count} ครั้ง · ครั้งล่าสุด ${esc(thTime(p.last_used_at))}</div><h3>${esc(p.title)}</h3><div class="tracking-stats"><div><strong>${thNum(p.orders)}</strong><span>ออเดอร์</span></div><div><strong>${thNum(p.views)}</strong><span>วิว</span></div><div><strong>฿${thBaht(p.commission_satang)}</strong><span>ค่าคอม</span></div></div><p class="hint">${esc(p.performance_label)}</p><button type="button" class="mini" data-show-history="${p.id}">ประวัติแต่ละครั้ง ↗</button></article>`).join(''):'<div class="panel">ยังไม่มีสินค้า ให้เพิ่มสินค้าก่อน แล้วกด “ทำคลิปใหม่”</div>';
    $('perf-draft').innerHTML=drafts.length?drafts.map(d=>`<option value="${d.id}">#${d.id} — ${esc(d.title)} · ${esc(d.created_at.slice(0,10))}</option>`).join(''):'<option value="">ยังไม่มีบทรีวิว</option>';
  }
  $('tracking-overview').addEventListener('click',async e=>{const b=e.target.closest('[data-show-history]');if(b)await showProductHistory(Number(b.dataset.showHistory));});
  $('tracking-detail').addEventListener('click',e=>{const b=e.target.closest('[data-edit-perf]');if(!b)return;
    const ev=trackingEvents.find(x=>String(x.draft_id)===String(b.dataset.editPerf));
    const form=$('performance-form');form.elements['draft_id'].value=b.dataset.editPerf;
    if(ev){for(const k of ['views','clicks','orders'])form.elements[k].value=ev[k]??0;
      form.elements['sales_baht'].value=((ev.sales_satang??0)/100).toFixed(2);
      form.elements['commission_baht'].value=((ev.commission_satang??0)/100).toFixed(2);
      form.elements['note'].value=ev.note||'';}
    form.scrollIntoView({behavior:'smooth',block:'center'});
  });
  $('performance-form').addEventListener('submit',async e=>{
    e.preventDefault();
    const v=val(e.target);const draftId=Number(v.draft_id);
    const body={views:Number(v.views),clicks:Number(v.clicks),orders:Number(v.orders),sales_baht:v.sales_baht,commission_baht:v.commission_baht,note:v.note};
    try{await api('/api/my/drafts/'+draftId+'/performance','PUT',body);await loadTracking();$('tracking-detail').textContent='';msg('บันทึกสถิติที่สมาชิกกรอกเองแล้ว · อัปเดตผลขาย ไม่บวกยอดซ้ำ');}
    catch(err){msg(err.message);}
  });
  async function loadKeys(){
    const data=await api('/api/my/connections');
    const containers=$('connectionlist');
    containers.innerHTML=data.providers.map(p=>{
      const info=p.configured?'บันทึกคีย์แล้ว · ยังไม่ได้ทดสอบสิทธิ์':'ยังไม่มีคีย์';
      const actions=['gemini','xai','openrouter','brave','openai'].includes(p.id);
      return `<div class="connection-card"><div class="connection-head"><strong>${esc(p.label)}</strong><span class="status">${p.enabled?(p.configured?esc(info):'ยังไม่เชื่อม'):'ยังไม่รองรับการเชื่อมจริง'}</span></div><p class="meta">${esc(p.supports)}</p>${actions?`<form data-keyprovider="${p.id}"><label>API key ของ ${esc(p.label)}<input name="key" type="password" minlength="8" maxlength="1500" autocomplete="new-password" placeholder="วาง API key ของคุณ" required></label><div class="actions"><button type="submit" class="mini">บันทึกคีย์เข้ารหัส</button>${p.configured?`<button type="button" class="mini secondary" data-delkey="${p.id}">ลบคีย์</button>`:''}</div></form>`:'<p class="hint">ไม่ต้องใส่รหัสผ่านหรือ OTP · ระบบนี้ยังไม่มีช่องทางเชื่อมที่อนุมัติแล้ว</p>'}</div>`;
    }).join('');
  }
  $('passwordform').addEventListener('submit',async e=>{
    e.preventDefault();
    try{await api('/api/my/password','POST',val(e.target));e.target.reset();msg('เปลี่ยนรหัสผ่านแล้ว · อุปกรณ์อื่นถูกออกจากระบบ');}catch(ex){msg(ex.message);}
  });
  $('connectionlist').addEventListener('submit',async e=>{
    const form=e.target.closest('[data-keyprovider]');if(!form)return;e.preventDefault();
    const provider=form.dataset.keyprovider,key=form.elements.key.value;
    try{await api('/api/my/keys/'+provider,'PUT',{key});form.reset();await loadKeys();msg('บันทึก API key แบบเข้ารหัสแล้ว · ความพร้อมใช้งานจริงจะตรวจเมื่อเรียกบริการ');}catch(ex){msg(ex.message);}
  });
  $('connectionlist').addEventListener('click',async e=>{
    const b=e.target.closest('[data-delkey]');if(!b)return;
    if(!confirm('ลบคีย์ของบริการนี้ออกจากบัญชี?'))return;
    try{await api('/api/my/keys/'+b.dataset.delkey,'DELETE');await loadKeys();msg('ลบ API key แล้ว');}catch(ex){msg(ex.message);}
  });
  const videoProviderNames={xai:'Grok Imagine',gemini:'Google Veo',openrouter:'OpenRouter',platform:'ฟรีจากระบบ'};
  async function loadVideos(){
    const jobs=await api('/api/my/video-jobs');
    const labels={submitting:'กำลังส่งคำขอ',running:'กำลังสร้าง',ready:'วิดีโอพร้อมแล้ว',failed:'ไม่สำเร็จ'};
    $('videolist').innerHTML=jobs.length?jobs.map(v=>{
      const path='/api/my/video-jobs/'+v.id+'/file';
      return `<article class="video-job"><div class="connection-head"><strong>${esc(v.title)}</strong><span class="status">${esc(labels[v.status]||v.status)}</span></div><p class="meta">งาน #${v.id} · ${esc(v.created_at)} · ${esc(videoProviderNames[v.provider]||v.provider)} ${Number(v.duration)||8} วินาที · ${esc(v.model||'')}</p>${v.error_message?`<p class="error-line">${esc(v.error_message)}</p>`:''}${v.status==='running'?`<button type="button" class="mini secondary" data-refreshvideo="${v.id}">⟳ ตรวจสถานะ</button>`:''}${v.status==='ready'?`<video controls playsinline preload="metadata" src="${path}" width="230" style="max-width:100%;border-radius:12px;display:block"></video><div class="actions"><a class="mini-link" href="${path}" target="_blank" rel="noopener noreferrer">ดูคลิป</a><button type="button" class="mini" data-videoqueue="${v.id}" data-draftid="${v.draft_id}">ส่งเข้าคิวโพสต์</button></div>`:''}</article>`;
    }).join(''):'<div class="notice">ยังไม่มีงานสร้างวิดีโอ · สร้างบทรีวิวแล้วเลือกสั่งสร้างจากหน้านี้</div>';
    $('queue-video').innerHTML='<option value="">ไม่มีไฟล์ AI (ใช้ลิงก์แทนได้)</option>'+jobs.filter(v=>v.status==='ready').map(v=>`<option value="${v.id}">${esc('#'+v.id+' — '+v.title)}</option>`).join('');
  }
  async function prepareVideoStudio(){
    const drafts=await api('/api/my/drafts');
    $('video-draft').innerHTML=drafts.length?drafts.map(d=>`<option value="${d.id}">${esc('#'+d.id+' — '+d.title)}</option>`).join(''):'<option value="">กรุณาสร้างบทรีวิวก่อน</option>';
    await loadVideoQuota();
    await loadVideos();
  }
  // Free mode (owner's server-side OpenRouter key): shown only when the server enables it.
  let platformQuota={enabled:false};
  let enabledModels=null; // null until the server answers; then {provider:[model ids]}
  const periodText={day:'วันนี้',month:'เดือนนี้',total:''};
  async function loadVideoQuota(){
    const quota=await api('/api/my/video-quota');
    platformQuota=quota.platform;enabledModels=quota.enabled_models;
    const select=$('video-provider');let opt=select.querySelector('option[value="platform"]');
    // Hide providers whose models are all switched off for now.
    for(const o of select.options)if(o.value!=='platform')o.hidden=o.disabled=!(enabledModels[o.value]||[]).length;
    if(select.selectedOptions[0]&&select.selectedOptions[0].disabled){const next=[...select.options].find(o=>!o.disabled);if(next)select.value=next.value;}
    if(!platformQuota.enabled){if(opt)opt.remove();changeVideoProvider();return;}
    if(!opt){opt=document.createElement('option');opt.value='platform';opt.defaultSelected=true;select.prepend(opt);select.value='platform';}
    const out=!platformQuota.remaining||!platformQuota.budget_available;
    opt.textContent='✦ ฟรีจากระบบ · '+(platformQuota.remaining?'เหลือ '+platformQuota.remaining+'/'+platformQuota.limit+' คลิป'+(periodText[platformQuota.period]||''):'ใช้โควตาครบแล้ว')+(platformQuota.remaining&&!platformQuota.budget_available?' (งบวันนี้หมด)':'');
    opt.disabled=out;
    if(out&&select.value==='platform'){const next=[...select.options].find(o=>!o.disabled);if(next)select.value=next.value;}
    videoModels.platform=platformQuota.models.map(m=>[m.id,((videoModels.openrouter.find(([id])=>id===m.id)||[m.id,m.id])[1]).replace(' · มีเสียง','')+' · ไม่มีเสียง']);
    changeVideoProvider();
  }
  const videoModels={xai:[['grok-imagine-video-1.5-lite','Grok Imagine 1.5 Lite · 10 วินาที'],['grok-imagine-video-1.5','Grok Imagine 1.5 · 10 วินาที']],gemini:[['veo-3.1-generate-preview','Google Veo 3.1 · 8 วินาที']],
    openrouter:[['google/veo-3.1-lite','Veo 3.1 Lite · 8 วินาที · มีเสียง'],['x-ai/grok-imagine-video-1.5-lite','Grok Imagine 1.5 Lite · 8 วินาที'],['google/veo-3.1-fast','Veo 3.1 Fast · 8 วินาที · มีเสียง'],['alibaba/wan-3.0','Wan 3.0 · 8 วินาที · มีเสียง'],['kwaivgi/kling-v3.0-std','Kling 3.0 Standard · 8 วินาที · มีเสียง']]};
  // Approximate OpenRouter list price per 8 s 720p clip (Oct 2026); members must check the live price.
  const openrouterCost={'google/veo-3.1-lite':'$0.40','x-ai/grok-imagine-video-1.5-lite':'$0.24','google/veo-3.1-fast':'$0.80','alibaba/wan-3.0':'$0.80','kwaivgi/kling-v3.0-std':'$1.01'};
  function changeVideoModel(){
    const provider=$('video-provider').value,model=$('video-model').value;
    const paid=$('videoform').elements.confirm_paid;paid.required=provider!=='platform';paid.closest('label').hidden=provider==='platform';
    if(provider==='platform'){$('video-cost-hint').textContent='ฟรี · ระบบออกค่าใช้จ่ายให้ · เหลือ '+platformQuota.remaining+' คลิป'+(periodText[platformQuota.period]||'')+' · คลิปไม่มีเสียงจากโมเดล ใส่เสียงพากย์/เพลงตอนโพสต์ได้';return;}
    $('video-cost-hint').textContent=provider==='xai'?'xAI API คิดตามวินาทีและความละเอียด · Lite 720p ตามเอกสารประมาณ $0.30 ต่อ 10 วินาที ไม่รวมค่าอินพุต/ภาษี · ตรวจราคาล่าสุดก่อนสร้าง':provider==='openrouter'?'OpenRouter หักเครดิตที่เติมไว้ล่วงหน้า · รุ่นนี้ประมาณ '+(openrouterCost[model]||'-')+' ต่อคลิป 8 วินาที 720p · ตรวจราคาล่าสุดที่ openrouter.ai ก่อนสร้าง':'Google Veo 8 วินาที · คิดเงินตามราคา API ของ Google ตามโมเดล/สิทธิ์ที่ใช้';
  }
  function changeVideoProvider(){
    const provider=$('video-provider').value;
    const allowed=provider==='platform'||!enabledModels?null:enabledModels[provider]||[];
    $('video-model').innerHTML=(videoModels[provider]||[]).filter(([v])=>!allowed||allowed.includes(v)).map(([v,label])=>`<option value="${v}">${label}</option>`).join('');
    changeVideoModel();
  }
  $('video-provider').addEventListener('change',changeVideoProvider);
  $('video-model').addEventListener('change',changeVideoModel);
  changeVideoProvider();
  $('videoform').addEventListener('submit',async e=>{
    e.preventDefault();const form=e.target;const b=$('video-start');
    const data=new FormData(form);
    if(!data.get('draft_id')){msg('ต้องสร้างบทรีวิวก่อน');return;}
    const img=data.get('image');if(img&&img.size===0)data.delete('image');
    if(img&&img.size>5*1024*1024){msg('รูปใหญ่เกิน 5MB');return;}
    b.disabled=true;b.textContent='กำลังส่งงานให้ AI...';
    try{
      const r=await fetch('/api/my/video-jobs',{method:'POST',headers:{'X-CSRF-Token':me.csrf},credentials:'same-origin',body:data});
      const body=await r.json().catch(()=>({}));
      if(!r.ok)throw Error(body.detail||'สร้างคลิปไม่สำเร็จ');
      form.reset();await loadVideoQuota();await loadVideos();msg('ส่งงานให้ '+(videoProviderNames[body.provider]||body.provider)+' แล้ว งาน #'+body.id+' · ตรวจสถานะอีกครั้งหลัง 10–30 วินาที');
    }catch(ex){msg(ex.message);}finally{b.disabled=false;b.textContent='▶ สร้างคลิปด้วย AI ที่เลือก';}
  });
  $('videolist').addEventListener('click',async e=>{
    const b=e.target.closest('[data-refreshvideo],[data-videoqueue]');if(!b)return;
    try{
      if(b.dataset.refreshvideo){
        b.disabled=true;const response=await api('/api/my/video-jobs/'+b.dataset.refreshvideo+'/refresh','POST');
        await loadVideos();msg(response.notice||'สถานะ: '+response.status);
      }else{
        await goTab('queue');$('queue-draft').value=b.dataset.draftid;$('queue-video').value=b.dataset.videoqueue;
        msg('เลือกคลิปสำเร็จ · เลือกแพลตฟอร์มแล้วกดเพิ่มคิว (ยังไม่โพสต์อัตโนมัติ)');
      }
    }catch(ex){msg(ex.message);b.disabled=false;}
  });
  function selectTab(name){
    document.querySelectorAll('.tabs button').forEach(b=>b.classList.toggle('active',b.dataset.tab===name));
    document.querySelectorAll('.tab').forEach(b=>b.classList.toggle('active',b.id===name));
  }
  document.querySelectorAll('.tabs button').forEach(b=>b.addEventListener('click',async()=>{await goTab(b.dataset.tab);}));
  const platformNames={tiktok:'TikTok',shopee:'Shopee'};
  const queueStatuses={needs_review:'รอตรวจคลิป',ready_manual:'พร้อมโพสต์เอง',completed_manual:'ผู้ใช้ระบุว่าโพสต์แล้ว',cancelled:'ยกเลิก'};
  async function loadDrafts(){
    const items=await api('/api/my/drafts');
    $('draftlist').innerHTML=items.length?items.map(d=>`<article class="simple-row draft-row"><div><div class="meta">#${d.id} · ${esc(d.platform)} · ${esc(d.style)}</div><strong>${esc(d.title)}</strong><p class="prewrap">${esc(d.script)}</p><details><summary>แสดง Prompt สำหรับ AI Video</summary><p class="prewrap">${esc(d.prompt)}</p><button type="button" class="mini secondary" data-copy-prompt="${d.id}">คัดลอก Prompt</button></details></div><button type="button" class="mini" data-queue-draft="${d.id}">เตรียมคิวโพสต์ →</button></article>`).join(''):'<div class="panel">ยังไม่มีสคริปต์ เริ่มจากเพิ่มสินค้าแล้วเลือกสร้างบทรีวิว</div>';
    $('queue-draft').innerHTML=items.length?items.map(d=>`<option value="${d.id}">${esc('#'+d.id+' — '+d.title)}</option>`).join(''):'<option value="">สร้างบทรีวิวก่อน</option>';
    return items;
  }
  async function loadQueue(){
    const items=await api('/api/my/queue');
    $('queuelist').innerHTML=items.length?items.map(q=>`<div class="simple-row"><div><div class="meta">#${q.id} · ${esc(platformNames[q.platform]||q.platform)}</div><strong>${esc(q.title)}</strong><p class="meta">${esc(queueStatuses[q.status]||q.status)}</p>${q.video_url?`<a href="${esc(q.video_url)}" target="_blank" rel="noopener noreferrer">ดูวิดีโอ ↗</a>`:''}</div><div class="actions">${q.status==='needs_review'||q.status==='ready_manual'?`<button class="mini secondary" data-qdone="${q.id}">บันทึกว่าลงแล้ว</button><button class="mini secondary" data-qcancel="${q.id}">ยกเลิก</button>`:''}</div></div>`).join(''):'<div class="panel">ยังไม่มีงานในคิว สร้างบทก่อนแล้วเลือก “เตรียมคิวโพสต์”</div>';
    return items;
  }
  async function refreshWorkspace(){
    const [products,drafts,queue]=await Promise.all([api('/api/my/products'),api('/api/my/drafts'),api('/api/my/queue')]);
    $('countProducts').textContent=products.length;$('countDrafts').textContent=drafts.length;$('countQueue').textContent=queue.length;
    $('draft-product').innerHTML=products.length?products.map(p=>`<option value="${p.id}">${esc(p.title)}</option>`).join(''):'<option value="">เพิ่มสินค้าก่อน</option>';
  }
  async function goTab(name){
    selectTab(name);
    try{
      if(name==='dashboard')await refreshWorkspace();
      if(name==='products')await loadProducts();
      if(name==='tracking')await loadTracking();
      if(name==='drafts'){await refreshWorkspace();await loadDrafts();}
      if(name==='videolab')await prepareVideoStudio();
      if(name==='queue'){await loadDrafts();await loadQueue();await loadVideos();}
      if(name==='keys')await loadKeys();
      if(name==='ideas')await loadIdeas();
    }catch(e){msg(e.message);}
  }
  document.querySelectorAll('[data-goto]').forEach(b=>b.addEventListener('click',()=>goTab(b.dataset.goto)));
  $('productform').addEventListener('submit',()=>{setTimeout(()=>refreshWorkspace().catch(()=>{}),250);});
  $('draftform').addEventListener('submit',async e=>{
    e.preventDefault();try{
      const raw=val(e.target);const result=await api('/api/my/drafts','POST',{product_id:Number(raw.product_id),style:raw.style});
      await loadDrafts();await refreshWorkspace();msg('สร้างบทพร้อมบันทึกเวลาใช้สินค้าครั้งที่ '+result.use_number+' แล้ว · ไปแท็บสร้างคลิป AI เพื่อเรียก Veo ได้เลย');
    }catch(err){msg(err.message);}
  });
  $('draftlist').addEventListener('click',async e=>{
    const b=e.target.closest('[data-copy-prompt],[data-queue-draft]');if(!b)return;
    if(b.dataset.queueDraft){await goTab('queue');$('queue-draft').value=b.dataset.queueDraft;return;}
    const id=Number(b.dataset.copyPrompt),data=await api('/api/my/drafts');const match=data.find(x=>x.id===id);
    if(!match)return;
    try{await navigator.clipboard.writeText(match.prompt);msg('คัดลอก Prompt แล้ว');}
    catch(_){msg('เบราว์เซอร์ไม่อนุญาตให้คัดลอก กรุณาเลือกข้อความ Prompt ด้วยตัวเอง');}
  });
  $('queueform').addEventListener('submit',async e=>{
    e.preventDefault();try{
      const raw=val(e.target);await api('/api/my/queue','POST',{draft_id:Number(raw.draft_id),platform:raw.platform,video_url:raw.video_url,video_job_id:raw.video_job_id?Number(raw.video_job_id):null});
      await loadQueue();await refreshWorkspace();msg('เพิ่มคิวสำเร็จ (ยังไม่ได้โพสต์อัตโนมัติ)');
    }catch(err){msg(err.message);}
  });
  $('queuelist').addEventListener('click',async e=>{
    const b=e.target.closest('[data-qdone],[data-qcancel]');if(!b)return;
    const done=!!b.dataset.qdone;const id=b.dataset.qdone||b.dataset.qcancel;
    if(!confirm(done?'ยืนยันว่าคุณได้โพสต์วิดีโอนี้ด้วยตัวเองแล้ว?':'ยกเลิกคิวนี้?'))return;
    try{await api(`/api/my/queue/${id}`,'PATCH',{status:done?'completed_manual':'cancelled'});await loadQueue();msg('บันทึกสถานะแล้ว');}catch(err){msg(err.message);}
  });
  api('/api/beta/capacity').then(cap=>{
    $('capacity').textContent='เปิดรับ '+cap.registered+' / '+cap.limit+' บัญชี · เหลือ '+cap.remaining+' สิทธิ์';
    $('capacity-register').textContent=cap.remaining?'เหลือ '+cap.remaining+' จาก '+cap.limit+' สิทธิ์':'รอบนี้เต็มแล้ว · ติดตามรอบถัดไปที่ Update Center';
    $('invite-field').hidden=!cap.invite_only;
    if(!cap.remaining){const b=$('registerform').querySelector('button[type=submit]');b.disabled=true;b.textContent='รอบ Beta เต็มแล้ว';}
  }).catch(()=>{$('capacity').textContent='ไม่สามารถตรวจสอบจำนวนสิทธิ์';});
  api('/api/me').then(signedIn).catch(()=>{me=null;show();});
})();

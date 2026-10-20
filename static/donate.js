(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const esc = s => String(s ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const statusLabels = {pending:'รอตรวจสอบ',confirmed:'ตรวจสอบยอดแล้ว',rejected:'ไม่สามารถยืนยันได้'};
  const fmt = satang => (Number(satang)/100).toLocaleString('th-TH',{minimumFractionDigits:2,maximumFractionDigits:2}) + ' บาท';
  const message = text => {$('donateMessage').textContent=text;};
  let me = null;
  let bankInfo = null;
  async function api(path, method='GET', data) {
    const headers = {};
    if (data !== undefined) headers['Content-Type']='application/json';
    if (me && method !== 'GET') headers['X-CSRF-Token']=me.csrf;
    const r=await fetch(path,{method,headers,credentials:'same-origin',body:data===undefined?undefined:JSON.stringify(data)});
    const body=await r.json().catch(()=>({}));
    if(!r.ok) { const error=Error(typeof body.detail==='string'?body.detail:'คำขอล้มเหลว: '+r.status); error.status=r.status; throw error; }
    return body;
  }
  async function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) { await navigator.clipboard.writeText(text); return; }
    const textarea=document.createElement('textarea');
    textarea.value=text;textarea.setAttribute('readonly','');textarea.style.position='absolute';textarea.style.left='-9999px';
    document.body.appendChild(textarea);textarea.select();
    const ok=document.execCommand('copy');textarea.remove();
    if(!ok) throw Error('คัดลอกไม่สำเร็จ กรุณาเลือกข้อความแล้วคัดลอกเอง');
  }
  async function initBank() {
    try {
      bankInfo=await api('/api/donate/info');
      $('bank').textContent=bankInfo.bank;
      $('account').textContent=bankInfo.account_number;
      $('payee').textContent=bankInfo.account_name;
      $('notice').textContent=bankInfo.notice;
      $('copyAccount').disabled=false;
      $('copyAll').disabled=false;
    } catch(e) {message('โหลดข้อมูลธนาคารไม่สำเร็จ: '+e.message);}
  }
  $('copyAccount').addEventListener('click',async()=>{
    if(!bankInfo)return;
    try{await copyText(bankInfo.account_number);message('คัดลอกเลขบัญชีแล้ว กรุณาตรวจสอบชื่อผู้รับก่อนโอน');}
    catch(e){message(e.message);}
  });
  $('copyAll').addEventListener('click',async()=>{
    if(!bankInfo)return;
    try{await copyText([bankInfo.bank,bankInfo.account_number,bankInfo.account_name].join('\n'));message('คัดลอกข้อมูลบัญชีแล้ว');}
    catch(e){message(e.message);}
  });
  async function loadMine() {
    const data=await api('/api/my/donation-reports');
    $('myList').innerHTML=data.length?data.map(d=>`<div class="donation-item"><div><strong>${esc(fmt(d.amount_satang))}</strong><small>${esc(d.created_at.slice(0,16).replace('T',' '))} · ${esc(d.note)}</small></div><span class="review-${esc(d.status)}">${esc(statusLabels[d.status]||d.status)}</span></div>`).join(''):'<p>ยังไม่มีรายการแจ้งโอน</p>';
  }
  async function loadAdmin() {
    const items=await api('/api/admin/donation-reports');
    $('adminList').innerHTML=items.length?items.map(d=>`<div class="donation-item"><div><strong>${esc(d.member)} · ${esc(fmt(d.amount_satang))}</strong><small>#${d.id} · ${esc(d.created_at.slice(0,16).replace('T',' '))} · ${esc(d.note)}</small><small class="review-${esc(d.status)}">${esc(statusLabels[d.status]||d.status)}</small></div>${d.status==='pending'?`<div class="button-group"><button class="mini" data-report="${d.id}" data-setstatus="confirmed">ยืนยันหลังตรวจบัญชี</button><button class="mini secondary" data-report="${d.id}" data-setstatus="rejected">ปฏิเสธ</button></div>`:''}</div>`).join(''):'<p>ยังไม่มีรายการแจ้งโอน</p>';
  }
  $('adminList').addEventListener('click',async e=>{
    const btn=e.target.closest('[data-report]');if(!btn)return;
    const newStatus=btn.dataset.setstatus;
    if(!confirm(newStatus==='confirmed'?'คุณตรวจสอบยอดเงินเข้าบัญชี SCB จริงแล้วใช่หรือไม่?':'ปฏิเสธการยืนยันรายการนี้?'))return;
    try{await api('/api/admin/donation-reports/'+btn.dataset.report,'PATCH',{status:newStatus});await loadAdmin();await loadMine();message('บันทึกผลตรวจสอบแล้ว');}
    catch(err){message(err.message);}
  });
  $('reportForm').addEventListener('submit',async e=>{
    e.preventDefault();
    const form=e.currentTarget;
    const v=Object.fromEntries(new FormData(form));
    try {
      const amount=Number(v.amount_baht);
      if(!Number.isFinite(amount)||amount<1||amount>1000000||Math.abs(Math.round(amount*100)-amount*100)>1e-6)throw Error('จำนวนเงินไม่ถูกต้อง');
      await api('/api/my/donation-reports','POST',{amount_baht:v.amount_baht,note:v.note});
      form.reset();await loadMine();if(me.role==='admin')await loadAdmin();
      message('บันทึกข้อมูลแจ้งโอนแล้ว สถานะ: รอตรวจสอบยอดจริง');
    }catch(err){message(err.message);}
  });
  async function initMember() {
    try {
      me=await api('/api/me');
      $('loginPrompt').hidden=true;
      $('reportForm').hidden=false;
      $('myHistory').hidden=false;
      await loadMine();
      if(me.role==='admin'){$('adminArea').hidden=false;await loadAdmin();}
    } catch(e) {
      if(e.status!==401)message('ไม่สามารถตรวจสถานะสมาชิกได้: '+e.message);
    }
  }
  Promise.allSettled([initBank(),initMember()]);
})();

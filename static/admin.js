(() => {
  'use strict';
  const $=id=>document.getElementById(id);
  const esc=s=>String(s??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const msg=t=>{$('message').textContent=t;};
  // Stored as UTC ISO strings; show Thai local time.
  const day=s=>s?new Date(s).toLocaleString('th-TH',{timeZone:'Asia/Bangkok',dateStyle:'medium',timeStyle:'short'}):'-';
  const usd=n=>'$'+Number(n||0).toFixed(2);
  const periodText={day:'ต่อวัน',month:'ต่อเดือน',total:'ครั้งเดียว'};
  let members=[],me=null;
  async function api(path,method='GET',data){
    const headers={};
    if(data!==undefined)headers['Content-Type']='application/json';
    if(method!=='GET'&&me)headers['X-CSRF-Token']=me.csrf;
    const r=await fetch(path,{method,headers,credentials:'same-origin',body:data===undefined?undefined:JSON.stringify(data)});
    const body=await r.json().catch(()=>({}));
    if(!r.ok){const e=Error(typeof body.detail==='string'?body.detail:'คำขอล้มเหลว '+r.status);e.status=r.status;throw e;}
    return body;
  }
  function gate(title,text,showLogin){
    $('console').hidden=true;$('gate').hidden=false;
    $('gate-title').textContent=title;$('gate-text').textContent=text;$('gate-link').hidden=!showLogin;
  }
  function stat(label,value,note){return `<div class="panel stat"><span>${esc(label)}</span><b>${esc(value)}</b><small>${esc(note||'')}</small></div>`;}
  function renderOverview(o){
    const f=o.free_mode,done=o.video_jobs.ready||0,total=Object.values(o.video_jobs).reduce((a,b)=>a+b,0);
    $('overview').innerHTML=[
      stat('สมาชิก',o.members+' / '+o.seat_limit,'แอดมิน '+o.admins+' คน · เหลือ '+Math.max(0,o.seat_limit-o.members)+' ที่'),
      stat('คลิปทั้งหมด',done+' / '+total,'สำเร็จ / สั่งสร้าง · ล้มเหลว '+(o.video_jobs.failed||0)),
      stat('คลิปฟรีเดือนนี้',f.clips_this_month,f.enabled?'โควตา '+f.limit+' คลิป/คน '+(periodText[f.period]||''):'โหมดฟรีปิดอยู่'),
      stat('ค่าใช้จ่ายฟรี',usd(f.spent_today_usd)+' วันนี้','เพดาน '+usd(f.daily_budget_usd)+'/วัน · เดือนนี้ '+usd(f.spent_this_month_usd)),
    ].join('');
    const models=Object.entries(o.enabled_models).filter(([,m])=>m.length).map(([p,m])=>p+': '+m.join(', ')).join(' · ')||'ไม่มี';
    $('settings').innerHTML=`โหมดฟรี: <strong>${f.enabled?'เปิด':'ปิด'}</strong>${f.enabled?' · รุ่น '+esc(f.models.join(', ')):' (ยังไม่ได้ใส่ PLATFORM_OPENROUTER_API_KEY)'}<br>รุ่นที่สมาชิกเลือกได้: ${esc(models)}<br>จำนวนที่นั่ง Beta: ${esc(o.seat_limit)}`;
  }
  function renderMembers(){
    const q=$('search').value.trim().toLowerCase();
    const rows=members.filter(m=>!q||m.username.toLowerCase().includes(q)||m.email.toLowerCase().includes(q));
    $('members').innerHTML=rows.length?rows.map(m=>`<tr><td>${m.id}</td><td><strong>${esc(m.username)}</strong></td><td>${esc(m.email)}</td><td><span class="status">${m.role==='admin'?'แอดมิน':'สมาชิก'}</span></td><td>${esc(day(m.created_at))}</td><td>${esc(day(m.last_login_at))}</td><td>${m.products}</td><td>${m.drafts}</td><td>${m.clips_ready} / ${m.clips}</td><td>${m.free_limit?m.free_used+' / '+m.free_limit:'-'}</td><td>${usd(m.free_cost_month_usd)}</td><td>${esc(m.own_keys.join(', ')||'-')}</td><td>${m.role==='admin'?'<span class="hint">จัดการผ่านเซิร์ฟเวอร์</span>':`<div class="actions" style="margin:0;flex-wrap:nowrap"><button type="button" class="mini secondary" data-reset="${m.id}">รีเซ็ตรหัส</button><button type="button" class="mini" style="background:#7a1d3a;border-color:#b0305a" data-delete="${m.id}">ลบ</button></div>`}</td></tr>`).join('')
      :`<tr><td colspan="13" class="hint">${members.length?'ไม่พบสมาชิกที่ตรงกับคำค้น':'ยังไม่มีสมาชิก'}</td></tr>`;
  }
  const actionText={reset_password:'รีเซ็ตรหัสผ่าน',delete_member:'ลบสมาชิก'};
  function renderAudit(rows){
    $('audit').innerHTML=rows.length?rows.map(a=>`<div class="simple-row"><div><strong>${esc(actionText[a.action]||a.action)}</strong> · ${esc(a.target_username)} (${esc(a.target_email)})<p class="meta">โดย ${esc(a.admin_username)} · ${esc(day(a.created_at))}</p></div></div>`).join(''):'<p class="hint">ยังไม่มีการจัดการสมาชิก</p>';
  }
  async function load(){
    try{
      me=await api('/api/me');
      $('who').innerHTML=`<span>${esc(me.username)}${me.role==='admin'?' (Admin)':''}</span>`;
      if(me.role!=='admin'){gate('เฉพาะผู้ดูแลระบบ','บัญชี '+me.username+' ไม่มีสิทธิ์เปิดหน้านี้',false);return;}
      const [overview,list,log]=await Promise.all([api('/api/admin/overview'),api('/api/admin/members'),api('/api/admin/audit')]);
      members=list;renderOverview(overview);renderMembers();renderAudit(log);
      $('gate').hidden=true;$('console').hidden=false;
      $('updated').textContent='อัปเดตล่าสุด '+new Date().toLocaleString('th-TH');
    }catch(e){
      if(e.status===401)gate('กรุณาเข้าสู่ระบบ','เข้าสู่ระบบด้วยบัญชีแอดมินที่เว็บหลัก แล้วกลับมาที่หน้านี้',true);
      else if(e.status===403)gate('เฉพาะผู้ดูแลระบบ',e.message,false);
      else msg(e.message);
    }
  }
  $('search').addEventListener('input',renderMembers);
  $('members').addEventListener('click',async e=>{
    const b=e.target.closest('[data-reset],[data-delete]');if(!b)return;
    const m=members.find(x=>String(x.id)===(b.dataset.reset||b.dataset.delete));if(!m)return;
    try{
      if(b.dataset.reset){
        if(!confirm('รีเซ็ตรหัสผ่านของ '+m.username+' ('+m.email+')?\nสมาชิกจะถูกออกจากระบบทุกอุปกรณ์ และต้องใช้รหัสชั่วคราวที่ได้ในการล็อกอิน'))return;
        const r=await api('/api/admin/members/'+m.id+'/reset-password','POST',{});
        $('temp-for').textContent='สำหรับ '+r.username+' ('+r.email+')';$('temp-value').textContent=r.temporary_password;$('temp-password').hidden=false;
        $('temp-password').scrollIntoView({behavior:'smooth',block:'center'});
        msg('รีเซ็ตรหัสผ่านของ '+r.username+' แล้ว');
      }else{
        const typed=prompt('ลบ '+m.username+' ('+m.email+') ถาวร?\nข้อมูลทั้งหมดของสมาชิกนี้จะหาย: สินค้า บท คลิป คิว คีย์ที่บันทึก ไอเดีย และรายการแจ้งโอน · ย้อนกลับไม่ได้\n\nพิมพ์ชื่อผู้ใช้ "'+m.username+'" เพื่อยืนยัน');
        if(typed===null)return;
        await api('/api/admin/members/'+m.id+'/delete','POST',{confirm_username:typed});
        msg('ลบ '+m.username+' แล้ว');
      }
      await load();
    }catch(ex){msg(ex.message);}
  });
  $('temp-copy').addEventListener('click',async()=>{try{await navigator.clipboard.writeText($('temp-value').textContent);msg('คัดลอกรหัสชั่วคราวแล้ว');}catch{msg('คัดลอกไม่สำเร็จ กรุณาคัดลอกเอง');}});
  $('temp-close').addEventListener('click',()=>{$('temp-value').textContent='';$('temp-password').hidden=true;});
  $('refresh').addEventListener('click',()=>load().then(()=>msg('รีเฟรชแล้ว')));
  load();
})();

/* Affiliate Auto Studio V8 — Phase 1 guided studio, real connectors, Shopee import, help center + realtime chat. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const AAS = window.AAS;
  if (!AAS) { console.error('AAS core missing'); return; }
  const esc = AAS.esc;
  const api = AAS.api;
  const csrf = () => (AAS.getMe() || {}).csrf || '';
  const stateBox = (...a) => window.AASstateBox(...a);
  const jsArg = v => esc(window.AASjsArg(v));
  const baht = v => (v === null || v === undefined || v === '') ? '-' : '฿' + Number(v).toLocaleString('th-TH', { maximumFractionDigits: 2 });
  const pct = v => (v === null || v === undefined) ? '-' : Number(v).toLocaleString('th-TH', { maximumFractionDigits: 2 }) + '%';
  const PLACEHOLDER = '/static/samples/no-image.svg';
  const SAMPLE_IMG = '/static/samples/sample-fan.svg';
  const localTime = iso => { if (!iso) return ''; const d = new Date(/Z|[+-]\d\d:\d\d$/.test(iso) ? iso : iso + 'Z'); return isNaN(d) ? iso : d.toLocaleString('th-TH-u-ca-gregory', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }); };
  const PLATFORM_LABEL = { facebook: 'Facebook Page', instagram: 'Instagram', line_oa: 'LINE OA', tiktok: 'TikTok', shopee: 'Shopee Video' };
  const PLATFORM_ICON = { facebook: '📘', instagram: '📸', line_oa: '💬', tiktok: '🎵', shopee: '🛒' };

  function toast(text, type = 'info') {
    const t = $('v8Toast');
    if (!t) return AAS.msg(text, type);
    t.textContent = text;
    t.className = 'v8-toast ' + (type === 'error' ? 'is-error' : type === 'success' ? 'is-success' : '');
    t.hidden = false;
    clearTimeout(toast._t);
    toast._t = setTimeout(() => { t.hidden = true; }, type === 'error' ? 7000 : 4500);
  }
  async function form(path, fd, method = 'POST') {
    const r = await fetch(path, { method, body: fd, credentials: 'same-origin', headers: { 'X-CSRF-Token': csrf() } });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw Error(typeof body.detail === 'string' ? body.detail : 'คำขอล้มเหลว ' + r.status);
    return body;
  }
  const isAuthError = e => /เข้าสู่ระบบ|เซสชัน|401|CSRF/.test(e.message || '');
  function loginBox(target) {
    target.innerHTML = `<div class="mf-card" style="text-align:center;padding:24px">🔐 กรุณาเข้าสู่ระบบก่อนใช้งานส่วนนี้ <button class="btn btn-primary btn-sm" onclick="document.getElementById('authModalTriggerBtn').click()">เข้าสู่ระบบ / สมัคร</button></div>`;
  }
  function imgTag(src, alt, cls = 'v8-thumb') {
    return `<img class="${cls}" src="${esc(src || PLACEHOLDER)}" alt="${esc(alt || '')}" loading="lazy" referrerpolicy="no-referrer" onerror="this.onerror=null;this.src='${PLACEHOLDER}'">`;
  }
  function setCredits(n) {
    if (n === undefined || n === null) return;
    const el = $('topbarEnergy');
    if (el) el.textContent = `⚡ ${Number(n).toLocaleString()} เครดิต`;
    try { localStorage.setItem('aas_credits', n); } catch {}
  }

  // =========================================================== SHOPEE (products tab)
  const Shopee = {
    page: 1, keyword: '', sort: 'commission', configured: false,
    async status() {
      const st = $('v8ShopeeStatus');
      if (!st) return;
      try {
        const s = await api('/api/shopee/status');
        this.configured = s.configured;
        st.innerHTML = s.configured
          ? `<span class="v8-ok">✅ เชื่อมต่อ Shopee Affiliate API แล้ว</span> · AppID ${esc(s.app_id)}`
          : '⚪ ยังไม่เชื่อมต่อ — ใส่ AppID/Secret ของบัญชี Shopee Affiliate คุณ (ขอได้ที่ affiliate.shopee.co.th → Open API)';
        $('v8ShopeeCredForm').hidden = s.configured;
        $('v8ShopeeTools').hidden = !s.configured;
        $('v8ShopeeCredCancel').hidden = true;
      } catch (e) {
        if (isAuthError(e)) { st.textContent = '🔐 เข้าสู่ระบบเพื่อเชื่อม Shopee'; return; }
        st.innerHTML = `<span class="v8-err">ตรวจสถานะไม่สำเร็จ: ${esc(e.message)}</span> <button class="btn btn-ghost btn-sm" onclick="AASv8.shopeeStatus()">ลองใหม่</button>`;
      }
    },
    card(it, ctx = 'products') {
      const range = it.price_max && it.price_min && it.price_max !== it.price_min ? `${baht(it.price_min)}–${baht(it.price_max)}` : baht(it.price);
      const added = it.already_added;
      return `<div class="v8-pcard">
        ${imgTag(it.image_url, it.title, 'v8-pcard-img')}
        <div class="v8-pcard-body">
          <div class="v8-pcard-title" title="${esc(it.title)}">${esc(it.title)}</div>
          <div class="v8-pcard-price">${range}</div>
          <div class="v8-pcard-comm"><strong>${pct(it.commission_rate)}</strong> ค่าคอม ≈ <strong>${baht(it.commission_baht)}</strong>/ชิ้น</div>
          ${!it.commission_rate ? '<div class="v8-warn v8-small" style="margin:4px 0">⚠ ตอนนี้ไม่มีค่าคอมสำหรับสินค้านี้</div>' : ''}
          <div class="v8-muted v8-small">Seller ${pct(it.seller_comm_rate)} · Shopee ${pct(it.shopee_comm_rate)}</div>
          <div class="v8-muted v8-small">⭐ ${it.rating ?? '-'} · ขายแล้ว ${Number(it.sales || 0).toLocaleString()} · ${esc(it.shop_name || '')}</div>
          <div class="v8-pcard-actions">
            ${added ? `<span class="chip chip-success">อยู่ในคลังแล้ว #${added}</span>
                       <button class="btn btn-primary btn-sm" onclick="AASv8.studioWithProduct(${added})">✨ สร้างบท & คลิป</button>`
                    : `<button class="btn btn-primary btn-sm" onclick="AASv8.importItem('${esc(it.item_id)}','${esc(it.shop_id)}', ${ctx === 'radar' ? 'true' : 'false'})">➕ เพิ่มสินค้า</button>`}
          </div>
        </div></div>`;
    },
    async importItem(itemId, shopId, toStudio) {
      try {
        const r = await api('/api/shopee/import', 'POST', { item_id: String(itemId), shop_id: String(shopId || '') });
        toast('✅ ' + r.message, 'success');
        AAS.reloadProducts();
        if (toStudio) return Studio.open(r.id);
        if (this.keyword) this.search(false); else $('v8ShopeeResults').innerHTML = '';
      } catch (e) { toast(e.message, 'error'); }
    },
    async search(append) {
      const box = $('v8ShopeeResults');
      if (!append) { this.page = 1; box.innerHTML = stateBox('loading', 'กำลังค้นหาใน Shopee Affiliate…'); }
      try {
        const r = await api(`/api/shopee/search?keyword=${encodeURIComponent(this.keyword)}&sort=${this.sort}&page=${this.page}`);
        const html = r.items.map(it => this.card(it)).join('');
        if (!append) box.innerHTML = html || stateBox('empty', 'ไม่พบสินค้าที่เข้าร่วม Affiliate สำหรับคำค้นนี้');
        else box.insertAdjacentHTML('beforeend', html);
        $('v8ShopeeMore').hidden = !(r.page_info && r.page_info.hasNextPage);
      } catch (e) {
        box.innerHTML = stateBox('error', e.message, null);
      }
    },
    bind() {
      $('v8ShopeeCredForm')?.addEventListener('submit', async e => {
        e.preventDefault();
        const btn = e.submitter; if (btn) { btn.disabled = true; btn.textContent = 'กำลังทดสอบกับ Shopee…'; }
        try {
          const d = Object.fromEntries(new FormData(e.target));
          await api('/api/shopee/credentials', 'PUT', d);
          e.target.reset();
          toast('✅ บันทึกและทดสอบคีย์ Shopee สำเร็จ', 'success');
          this.status();
        } catch (err) { toast(err.message, 'error'); }
        finally { if (btn) { btn.disabled = false; btn.textContent = 'บันทึก & ทดสอบ'; } }
      });
      $('v8ShopeeEditCred')?.addEventListener('click', () => { $('v8ShopeeCredForm').hidden = false; $('v8ShopeeCredCancel').hidden = false; });
      $('v8ShopeeCredCancel')?.addEventListener('click', () => { $('v8ShopeeCredForm').hidden = true; });
      $('v8ShopeeLinkForm')?.addEventListener('submit', async e => {
        e.preventDefault();
        const box = $('v8ShopeeResults');
        box.innerHTML = stateBox('loading', 'กำลังดึงข้อมูลจาก Shopee…');
        try {
          const r = await api('/api/shopee/lookup', 'POST', { url: e.target.url.value.trim() });
          box.innerHTML = this.card(r.item);
          $('v8ShopeeMore').hidden = true;
        } catch (err) { box.innerHTML = stateBox('error', err.message, null); }
      });
      $('v8ShopeeSearchForm')?.addEventListener('submit', e => {
        e.preventDefault();
        this.keyword = e.target.keyword.value.trim(); this.sort = e.target.sort.value;
        this.search(false);
      });
      $('v8ShopeeMore')?.addEventListener('click', () => { this.page += 1; this.search(true); });

      // Replace the legacy JSON product form with the multipart manual form handler.
      const old = $('productform');
      if (old) {
        const f = old.cloneNode(true);
        old.replaceWith(f);
        f.addEventListener('submit', async e => {
          e.preventDefault();
          const fd = new FormData(f);
          if (!fd.get('image') || !fd.get('image').name) fd.delete('image');
          try {
            const r = await form('/api/my/products/manual', fd);
            f.reset(); $('addProductCard').style.display = 'none';
            toast('✅ ' + r.message, 'success');
            AAS.reloadProducts();
          } catch (err) { toast(err.message, 'error'); }
        });
        $('cancelAddProductBtn')?.addEventListener('click', () => { $('addProductCard').style.display = 'none'; });
      }
    },
  };

  // =========================================================== FETCH FROM SHOPEE (Open API, bulk)
  const Fetch = {
    mode: 'category', listType: 'highest_commission', sort: 'relevance', job: null, pollT: 0,
    async open() {
      const me = AAS.getMe() || {};
      if (!me.id) { toast('กรุณาเข้าสู่ระบบก่อน', 'error'); return; }
      clearInterval(this.pollT); this.job = null;
      $('v8Fetch').hidden = false; $('v8FetchTitle').textContent = 'ตั้งค่าการดึงสินค้า Shopee';
      const body = $('v8FetchBody'); body.innerHTML = stateBox('loading', 'กำลังตรวจการเชื่อมต่อ Shopee…');
      let st; try { st = await api('/api/shopee/status'); } catch (e) { body.innerHTML = stateBox('error', e.message, null); return; }
      if (!st.configured) { this.credForm(); return; }
      this.form();
    },
    credForm() {
      $('v8FetchTitle').textContent = 'ก่อนดึงสินค้าจาก Shopee Affiliate';
      $('v8FetchBody').innerHTML = `
        <div class="v8-fetch-note"><strong>🛍️ ระบบดึงผ่าน Shopee Affiliate Open API ด้วย AppID/Secret ของคุณ</strong><br>
          ไม่ใช้ cookie ไม่ต้องเปิดหน้าต่างซ่อน ไม่เสี่ยงโดนระงับบัญชี — ได้รูป ราคา ค่าคอม ยอดขาย และลิงก์ affiliate (s.shopee.co.th) ของคุณเองทุกชิ้น</div>
        <form id="v8FetchCred" class="v8-form-grid" autocomplete="off" style="margin-top:12px">
          <label>Shopee Affiliate AppID<input class="form-input" name="app_id" inputmode="numeric" required minlength="4" maxlength="40" pattern="[0-9]+" placeholder="เช่น 15012345678"></label>
          <label>Secret<input class="form-input" name="secret" type="password" required minlength="8" maxlength="128" placeholder="••••••••"></label>
          <div class="v8-span2" style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap">
            <button type="button" class="btn btn-ghost btn-sm" data-help-article="shopee-credentials">วิธีขอ AppID / Secret</button>
            <button class="btn btn-primary" type="submit">บันทึก & ต่อไป</button>
          </div>
        </form>`;
      bindHelpLinks($('v8FetchBody'));
      $('v8FetchCred').addEventListener('submit', async e => {
        e.preventDefault(); const btn = e.submitter; btn.disabled = true; btn.textContent = 'กำลังทดสอบกับ Shopee…';
        try { await api('/api/shopee/credentials', 'PUT', Object.fromEntries(new FormData(e.target))); toast('✅ เชื่อม Shopee API สำเร็จ', 'success'); Shopee.status(); this.form(); }
        catch (err) { toast(err.message, 'error'); btn.disabled = false; btn.textContent = 'บันทึก & ต่อไป'; }
      });
    },
    seg(name, opts, cur, onPick) {
      return `<div class="v8-seg" data-seg="${name}">${opts.map(([v, l]) => `<button type="button" class="${v === cur ? 'is-on' : ''}" data-v="${v}">${l}</button>`).join('')}</div>`;
    },
    form() {
      $('v8FetchTitle').textContent = 'ตั้งค่าการดึงสินค้า Shopee';
      const cat = this.mode === 'category';
      $('v8FetchBody').innerHTML = `
        <p class="v8-muted v8-small">เลือกวิธีดึงจาก Shopee Affiliate แล้วกด "เริ่มดึง" — ระบบดึงผ่าน Open API ของคุณและบันทึกเข้าคลังให้อัตโนมัติ</p>
        ${this.seg('mode', [['category', 'หมวดหมู่'], ['search', 'ค้นหา']], this.mode)}
        <div id="v8FetchOpts">
        ${cat ? `<label class="v8-lbl">เลือกหมวด (ได้อย่างเดียว)</label>
          ${this.seg('listType', [['highest_commission', 'Commissions XTRA'], ['top_performing', 'Top Performing']], this.listType)}`
        : `<label class="v8-lbl">คีย์เวิร์ด<input class="form-input" id="v8FetchKw" placeholder="เช่น หูฟังบลูทูธ, บังแดด" maxlength="120"></label>
          <label class="v8-onb-skip"><input type="checkbox" id="v8FetchAms" checked> เอาเฉพาะ Comm Xtra (คอมมิชชั่นพิเศษ)</label>
          <label class="v8-lbl">เรียงจาก</label>
          ${this.seg('sort', [['relevance', 'Relevance'], ['sales', 'Top Sales'], ['commission', 'ค่าคอมสูงสุด']], this.sort)}`}
        </div>
        <hr class="v8-hr">
        <label class="v8-lbl">จำนวนสูงสุด
          <select class="form-select" id="v8FetchLimit" style="max-width:220px">${[10, 20, 30, 40, 50, 100].map(n => `<option value="${n}" ${n === 20 ? 'selected' : ''}>${n} รายการ</option>`).join('')}</select></label>
        <p class="v8-muted v8-small">ดึงลิงก์ affiliate ให้อัตโนมัติทุกรายการ (offerLink จาก Open API) · สินค้าที่มีอยู่แล้วจะอัปเดตทับตามรหัสสินค้า ไม่เพิ่มซ้ำ</p>
        <div class="v8-onb-nav" style="justify-content:flex-end;margin-top:14px">
          <button class="btn btn-ghost" id="v8FetchCancel">ยกเลิก</button>
          <button class="btn btn-primary" id="v8FetchGo">เริ่มดึง</button>
        </div>`;
      $('v8FetchBody').querySelectorAll('.v8-seg').forEach(seg => seg.addEventListener('click', e => {
        const b = e.target.closest('[data-v]'); if (!b) return;
        this[seg.dataset.seg] = b.dataset.v;
        if (seg.dataset.seg === 'mode') this.form(); else seg.querySelectorAll('button').forEach(x => x.classList.toggle('is-on', x === b));
      }));
      $('v8FetchCancel').addEventListener('click', () => this.close());
      $('v8FetchGo').addEventListener('click', () => this.start());
      $('v8FetchKw')?.focus();
    },
    async start() {
      const body = { mode: this.mode, list_type: this.listType, sort: this.sort, limit: +$('v8FetchLimit').value,
                     keyword: $('v8FetchKw')?.value.trim() || '', ams_only: this.mode === 'category' ? true : !!$('v8FetchAms')?.checked };
      if (body.mode === 'search' && body.keyword.length < 2) return toast('พิมพ์คีย์เวิร์ดอย่างน้อย 2 ตัวอักษร', 'error');
      const btn = $('v8FetchGo'); btn.disabled = true; btn.textContent = 'กำลังเริ่ม…';
      this.fetchedIds = [];
      try { const r = await api('/api/shopee/fetch', 'POST', body); this.job = { id: r.job_id, since: 0, items: [] }; this.progress({ status: 'running', total: body.limit, done: 0, added: 0, updated: 0, items: [] }); this.poll(); }
      catch (e) { toast(e.message, 'error'); btn.disabled = false; btn.textContent = 'เริ่มดึง'; }
    },
    progress(j) {
      const total = Math.max(j.total || 0, j.done || 0, 1);
      const pct = Math.min(100, Math.round((j.done || 0) / total * 100));
      if (!$('v8FetchProg')) {
        $('v8FetchTitle').textContent = '⬇ กำลังดึงสินค้าจาก Shopee…';
        $('v8FetchBody').innerHTML = `
          <div class="v8-fetch-stat"><span id="v8FetchMsg">เชื่อมต่อ Shopee Affiliate Open API…</span><strong id="v8FetchCount">0 / ${j.total || '?'}</strong></div>
          <div class="v8-prog"><div class="v8-prog-bar" id="v8FetchProg" style="width:0%"></div></div>
          <div class="v8-fetch-list" id="v8FetchList"></div>
          <div class="v8-onb-nav" style="justify-content:flex-end;margin-top:12px;flex-wrap:wrap" id="v8FetchDone" hidden>
            <button class="btn btn-ghost" id="v8FetchAgain">ดึงเพิ่ม</button>
            <button class="btn btn-ai" id="v8FetchAi" hidden>✨ ให้ AI ปรับสินค้าที่เพิ่งดึง</button>
            <button class="btn btn-primary" id="v8FetchView">ดูสินค้าของฉัน</button>
          </div>`;
        $('v8FetchAgain').addEventListener('click', () => this.open());
        $('v8FetchAi').addEventListener('click', () => { const ids = [...new Set(this.fetchedIds || [])]; this.close(); AiProducts.open(ids, 'สินค้าที่เพิ่งดึง'); });
        $('v8FetchView').addEventListener('click', () => { this.close(); AAS.switchTab('products'); });
      }
      $('v8FetchProg').style.width = pct + '%';
      $('v8FetchCount').textContent = `${j.done || 0} / ${j.total || this.job?.limit || '?'}`;
      const list = $('v8FetchList');
      (j.items || []).forEach(it => { if (it.id) (this.fetchedIds = this.fetchedIds || []).push(it.id); });
      (j.items || []).forEach(it => list.insertAdjacentHTML('afterbegin', `<div class="v8-fetch-row">${it.image_url ? `<img src="${esc(it.image_url)}" alt="">` : '<span class="v8-fetch-noimg"></span>'}
        <div class="v8-fetch-txt"><div class="v8-fetch-title">${esc(it.title)}</div><div class="v8-small v8-muted">${baht(it.price)} · ค่าคอม ${it.commission_rate != null ? it.commission_rate + '%' : '-'}${it.sales ? ' · ขายได้ ' + Number(it.sales).toLocaleString('th-TH') : ''}${it.discount_rate ? ' · ' + Math.round(it.discount_rate) + '% OFF' : ''}</div></div>
        <span class="chip ${it.updated ? '' : 'chip-success'}">${it.updated ? 'อัปเดต' : 'เพิ่มใหม่'}</span></div>`));
      if (j.status === 'done') {
        $('v8FetchTitle').textContent = '✅ ดึงสินค้าเสร็จแล้ว';
        $('v8FetchMsg').textContent = `เพิ่มใหม่ ${j.added} · อัปเดต ${j.updated} รายการ`;
        $('v8FetchProg').style.width = '100%'; $('v8FetchDone').hidden = false;
        if ((this.fetchedIds || []).length) { $('v8FetchAi').hidden = false; $('v8FetchAi').textContent = `✨ ให้ AI ปรับ ${new Set(this.fetchedIds).size} รายการที่เพิ่งดึง`; }
        AAS.reloadProducts(); toast(`✅ ดึงสินค้าเสร็จ เพิ่ม ${j.added} อัปเดต ${j.updated}`, 'success');
        if (!j.added && !j.updated) $('v8FetchMsg').textContent = 'ไม่พบสินค้าที่ตรงเงื่อนไข — ลองคีย์เวิร์ดอื่น หรือปิด "เฉพาะ Comm Xtra"';
      } else if (j.status === 'error') {
        $('v8FetchTitle').textContent = '❌ ดึงสินค้าไม่สำเร็จ';
        $('v8FetchMsg').innerHTML = `<span class="v8-err">${esc(j.error || 'เกิดข้อผิดพลาด')}</span>`;
        $('v8FetchDone').hidden = false; if (j.done) AAS.reloadProducts();
      } else $('v8FetchMsg').textContent = 'กำลังดึงข้อมูลและบันทึกเข้าคลัง…';
    },
    poll() {
      clearInterval(this.pollT);
      this.pollT = setInterval(async () => {
        if (!this.job) return clearInterval(this.pollT);
        try {
          const j = await api(`/api/shopee/fetch/${this.job.id}?since=${this.job.since}`);
          this.job.since = j.next; this.progress(j);
          if (j.status !== 'running') { clearInterval(this.pollT); this.job = null; }
        } catch (e) { clearInterval(this.pollT); this.progress({ status: 'error', error: e.message, done: 0, total: 0, items: [] }); this.job = null; }
      }, 900);
    },
    close() { clearInterval(this.pollT); $('v8Fetch').hidden = true; },
    bind() {
      $('v8FetchBtn')?.addEventListener('click', () => this.open());
      $('v8FetchClose')?.addEventListener('click', () => this.close());
      $('v8Fetch')?.addEventListener('click', e => { if (e.target.id === 'v8Fetch') this.close(); });
    },
  };

  // =========================================================== AI: listing + images
  // Rewrites names and descriptions from what the record actually says, and makes new
  // product photos from the real photo. Old names stay recoverable (↩ on the card) and
  // the original photo is kept beside the AI one, so nothing here is a one-way door.
  const AI_STYLES = [
    { id: 'studio', label: 'สตูดิโอพื้นขาว' }, { id: 'lifestyle', label: 'ใช้งานจริงในบ้าน' },
    { id: 'flatlay', label: 'Flat lay ด้านบน' }, { id: 'promo', label: 'แบนเนอร์โปรโมต' },
  ];
  const AiProducts = {
    ids: [], job: null, pollT: null, style: 'studio',
    async open(ids = [], label = '') {
      this.ids = ids; clearInterval(this.pollT); this.job = null;
      $('v8Ai').hidden = false;
      $('v8AiTitle').textContent = '✨ ให้ AI ปรับสินค้า';
      const body = $('v8AiBody');
      body.innerHTML = stateBox('loading', 'กำลังตรวจคีย์ Gemini…');
      let hasKey = false, count = ids.length;
      try {
        const [keys, prods] = await Promise.all([api('/api/my/keys'), ids.length ? null : api('/api/my/products')]);
        hasKey = (keys.connected || []).some(k => k.provider === 'gemini');
        if (prods) count = prods.filter(p => p.active !== 0).length;
      } catch (e) { /* show the form anyway */ }
      const scope = ids.length === 1 ? 'สินค้า 1 รายการ' : ids.length ? `${label || 'สินค้าที่เลือก'} ${ids.length} รายการ` : `สินค้าที่เปิดใช้งานทั้งหมด ${count} รายการ`;
      body.innerHTML = `
        ${hasKey ? '' : `<div class="v8-writer is-tip" style="margin-top:0"><strong>ต้องเชื่อมคีย์ Gemini ก่อน</strong>
          <div class="v8-small">ทั้งการเขียนชื่อ/รายละเอียดและการสร้างรูปใช้คีย์ Gemini ของคุณเอง — ค่าใช้จ่ายคิดกับบัญชี Google ของคุณ ไม่หักเครดิตระบบ</div>
          <div class="v8-writer-act"><button class="btn btn-primary btn-sm" onclick="AASv8.closeAi();AASv8.goKeys()">เชื่อมคีย์ Gemini</button>
          <span class="v8-small v8-muted">ขอคีย์ฟรีที่ <a href="https://aistudio.google.com/apikey" target="_blank" rel="noopener">Google AI Studio</a></span></div></div>`}
        <p class="v8-small v8-muted" style="margin:6px 0 12px">ขอบเขต: <strong>${esc(scope)}</strong></p>
        <label class="v8-ai-opt"><input type="checkbox" id="v8AiText" checked>
          <div><strong>เขียนชื่อสินค้าและรายละเอียดใหม่</strong>
          <div class="v8-small v8-muted">ชื่ออ่านง่าย ค้นเจอ ไม่เกิน 100 ตัวอักษร + รายละเอียด 3–5 บรรทัด · ใช้เฉพาะข้อมูลที่มีจริง ไม่เติมสเปกเอง · คืนชื่อเดิมได้ทุกเมื่อ</div></div></label>
        <label class="v8-ai-opt"><input type="checkbox" id="v8AiImg">
          <div><strong>สร้างรูปสินค้าใหม่</strong>
          <div class="v8-small v8-muted">ใช้รูปจริงของสินค้าเป็นต้นแบบ เปลี่ยนแค่ฉากและแสง ตัวสินค้าต้องเหมือนเดิม · รูปเดิมยังเก็บไว้ สลับกลับได้</div>
          <div class="v8-seg v8-ai-styles" id="v8AiStyles">${AI_STYLES.map(x => `<button type="button" data-v="${x.id}" class="${x.id === this.style ? 'is-on' : ''}">${x.label}</button>`).join('')}</div>
          <label class="v8-small" style="display:flex;gap:6px;align-items:center;margin-top:6px"><input type="checkbox" id="v8AiOnlyMissing"> เฉพาะสินค้าที่ยังไม่มีรูป</label>
          </div></label>
        <div class="v8-small v8-muted" style="margin-top:8px">⏱ ข้อความราว 5 วินาที/รายการ · รูปราว 15–30 วินาที/รายการ${count > 1 ? ` (${count} รายการ ≈ ${Math.max(1, Math.ceil(count * 25 / 60))} นาทีถ้าทำครบทั้งสองอย่าง)` : ''} · ปิดหน้าต่างนี้ได้ งานยังทำต่อ</div>
        <div class="v8-ep-foot">
          <button class="btn btn-ghost" onclick="AASv8.closeAi()">ยกเลิก</button>
          <button class="btn btn-ai" id="v8AiGo" ${hasKey ? '' : 'disabled'}>✨ เริ่มให้ AI ปรับ</button>
        </div>`;
      $('v8AiStyles').addEventListener('click', e => {
        const b = e.target.closest('[data-v]'); if (!b) return;
        this.style = b.dataset.v; $('v8AiStyles').querySelectorAll('button').forEach(x => x.classList.toggle('is-on', x === b));
        $('v8AiImg').checked = true;
      });
      $('v8AiGo').addEventListener('click', () => this.start());
    },
    async start() {
      const doText = $('v8AiText').checked, doImage = $('v8AiImg').checked;
      if (!doText && !doImage) return toast('เลือกอย่างน้อย 1 อย่าง', 'error');
      const btn = $('v8AiGo'); btn.disabled = true; btn.textContent = 'กำลังเริ่ม…';
      try {
        const r = await api('/api/products/ai', 'POST', { product_ids: this.ids, do_text: doText, do_image: doImage,
          image_style: this.style, only_missing_image: $('v8AiOnlyMissing').checked });
        this.job = { id: r.job_id, since: 0 };
        this.renderProgress({ status: 'running', total: r.total, done: 0, failed: 0, items: [] });
        this.poll();
      } catch (e) { toast(e.message, 'error'); btn.disabled = false; btn.textContent = '✨ เริ่มให้ AI ปรับ'; }
    },
    renderProgress(j) {
      if (!$('v8AiProg')) {
        $('v8AiTitle').textContent = '✨ AI กำลังปรับสินค้า…';
        $('v8AiBody').innerHTML = `
          <div class="v8-fetch-stat"><span id="v8AiMsg">เริ่มงาน…</span><strong id="v8AiCount">0 / ${j.total}</strong></div>
          <div class="v8-prog"><div class="v8-prog-bar v8-prog-ai" id="v8AiProg" style="width:0%"></div></div>
          <div class="v8-fetch-list v8-ai-list" id="v8AiList"></div>
          <div class="v8-ep-foot">
            <button class="btn btn-ghost" id="v8AiStop">หยุด</button>
            <button class="btn btn-primary" id="v8AiDone" hidden>ดูสินค้าของฉัน</button>
          </div>`;
        $('v8AiStop').addEventListener('click', () => this.stop());
        $('v8AiDone').addEventListener('click', () => { this.close(); AAS.switchTab('products'); });
      }
      const total = Math.max(j.total || 1, 1);
      $('v8AiProg').style.width = Math.round((j.done || 0) / total * 100) + '%';
      $('v8AiCount').textContent = `${j.done || 0} / ${j.total}`;
      (j.items || []).forEach(it => $('v8AiList').insertAdjacentHTML('afterbegin', `
        <div class="v8-fetch-row v8-ai-row ${it.ok ? '' : 'is-bad'}">
          ${it.ai_image ? `<img src="${esc(it.ai_image)}" alt="">` : '<span class="v8-fetch-noimg"></span>'}
          <div class="v8-fetch-txt">
            ${it.old_title && it.old_title !== it.title ? `<div class="v8-ai-old">${esc(it.old_title)}</div>` : ''}
            <div class="v8-fetch-title">${esc(it.title)}</div>
            ${it.description ? `<div class="v8-small v8-muted v8-ai-desc">${esc(it.description)}</div>` : ''}
            ${(it.notes || []).map(n => `<div class="v8-small ${it.ok ? 'v8-muted' : 'v8-err'}">${esc(n)}</div>`).join('')}
          </div>
          <span class="chip ${it.ok ? 'chip-success' : 'v8-chip-err'}">${it.ok ? 'เสร็จ' : 'ไม่สำเร็จ'}</span>
        </div>`));
      if (j.status === 'running') { $('v8AiMsg').textContent = `เขียนชื่อแล้ว ${j.text_done || 0} · สร้างรูปแล้ว ${j.image_done || 0}`; return; }
      $('v8AiTitle').textContent = j.error ? '⚠ AI หยุดกลางทาง' : '✅ AI ปรับสินค้าเสร็จแล้ว';
      $('v8AiMsg').innerHTML = j.error ? `<span class="v8-err">${esc(j.error)}</span>`
        : `เขียนชื่อใหม่ ${j.text_done || 0} · สร้างรูป ${j.image_done || 0}${j.failed ? ` · ไม่สำเร็จ ${j.failed}` : ''}`;
      $('v8AiProg').style.width = '100%';
      $('v8AiStop').hidden = true; $('v8AiDone').hidden = false;
      AAS.reloadProducts();
      toast(j.error ? '⚠ ' + j.error : `✅ AI ปรับสินค้าเสร็จ ${j.done} รายการ`, j.error ? 'error' : 'success');
    },
    poll() {
      clearInterval(this.pollT);
      this.pollT = setInterval(async () => {
        if (!this.job) return clearInterval(this.pollT);
        try {
          const j = await api(`/api/products/ai/${this.job.id}?since=${this.job.since}`);
          this.job.since = j.next;
          if ($('v8AiProg')) this.renderProgress(j);
          if (j.status !== 'running') { clearInterval(this.pollT); this.job = null; if (!$('v8AiProg')) { AAS.reloadProducts(); toast('✅ AI ปรับสินค้าเสร็จแล้ว', 'success'); } }
          else if (j.items && j.items.length) AAS.reloadProducts();
        } catch (e) { clearInterval(this.pollT); this.job = null; toast(e.message, 'error'); }
      }, 1500);
    },
    async stop() {
      if (!this.job) return;
      try { await api(`/api/products/ai/${this.job.id}/cancel`, 'POST'); toast('กำลังหยุดหลังรายการปัจจุบัน', 'info'); } catch (e) { toast(e.message, 'error'); }
    },
    // Closing only hides the window; polling keeps going so the cards still refresh.
    close() { $('v8Ai').hidden = true; },
    bind() {
      $('v8AiAllBtn')?.addEventListener('click', () => this.open([]));
      $('v8AiClose')?.addEventListener('click', () => this.close());
      $('v8Ai')?.addEventListener('click', e => { if (e.target.id === 'v8Ai') this.close(); });
    },
  };

  // =========================================================== IMPORT FROM FILE (CSV / Excel)
  const FIELD_LABELS = { title: 'ชื่อสินค้า *', price: 'ราคา', aff_link: 'ลิงก์ affiliate', image_url: 'URL ภาพสินค้า', item_id: 'รหัสสินค้า (ถ้ามี)', commission_rate: 'ค่าคอม %' };
  const ImportFile = {
    file: null, data: null,
    open() {
      const me = AAS.getMe() || {};
      if (!me.id) { toast('กรุณาเข้าสู่ระบบก่อนนำเข้าสินค้า', 'error'); return; }
      this.file = null; this.data = null;
      $('v8Import').hidden = false; $('v8ImportTitle').textContent = '↓ นำเข้าสินค้าจากไฟล์';
      $('v8ImportTitle').textContent = 'นำเข้าสินค้าจาก CSV / Excel';
      $('v8ImportBody').innerHTML = `
        <p class="v8-muted">ทำไฟล์ให้มี 4 คอลัมน์นี้ (ชื่อหัวตารางจะเป็นไทยหรืออังกฤษก็ได้ สลับลำดับได้ ระบบเดาให้เอง แล้วให้ยืนยันอีกที)</p>
        <table class="v8-onb-table v8-col-table"><thead><tr><th>คอลัมน์</th><th>ตัวอย่างข้อมูล</th><th>จำเป็น</th></tr></thead><tbody>
          <tr><th>ชื่อสินค้า</th><td>หูฟังบลูทูธ TWS รุ่นใหม่</td><td>ต้องมี</td></tr>
          <tr><th>ราคา</th><td>฿199 หรือ 199</td><td>ไม่บังคับ</td></tr>
          <tr><th>ลิงค์ aff</th><td>https://s.shopee.co.th/xxxxxxxx</td><td>ไม่บังคับ</td></tr>
          <tr><th>url ภาพสินค้า</th><td>https://down-bs-th.img.susercontent.com/…webp</td><td>ไม่บังคับ</td></tr>
        </tbody></table>
        <ul class="v8-import-notes">
          <li><strong>ภาพจะถูกโหลดมาเก็บในเครื่องให้</strong> ไม่ได้ลิงก์ไว้เฉย ๆ — ลิงก์ภาพของร้านหมดอายุแล้วคลังจะไม่โล่ง</li>
          <li>นำเข้าไฟล์เดิมซ้ำ = <strong>อัพเดททับ ไม่เพิ่มซ้ำ</strong> (ดูจากลิงก์ affiliate หรือรหัสสินค้า)</li>
          <li>รองรับ <strong>.csv</strong> (UTF-8) และ <strong>.xlsx</strong> — ไฟล์ Excel จะอ่าน<strong>ชีทแรก</strong>เท่านั้น · ไฟล์ cookie ของเบราว์เซอร์จะถูกปฏิเสธ</li>
        </ul>
        <div class="v8-import-btns">
          <button class="btn btn-ghost" id="v8ImportCancel">ยกเลิก</button>
          <a class="btn btn-secondary" href="/api/my/products/import-file/sample.xlsx" download>⬇ ตัวอย่าง .xlsx</a>
          <a class="btn btn-secondary" href="/api/my/products/import-file/sample.csv" download>⬇ ดาวน์โหลดไฟล์ตัวอย่าง (.csv)</a>
        </div>
        <div class="v8-import-btns" style="justify-content:flex-end">
          <input type="file" id="v8ImportFile" accept=".csv,.xlsx,.txt" hidden>
          <span class="v8-muted v8-small" id="v8ImportName"></span>
          <button class="btn btn-primary" id="v8ImportPick">📄 เลือกไฟล์แล้วนำเข้า</button>
        </div>
        <div id="v8ImportStage"></div>
        <div id="v8ImportClean" hidden style="margin-top:14px;padding-top:12px;border-top:1px solid var(--color-border)"></div>`;
      $('v8ImportCancel').addEventListener('click', () => { $('v8Import').hidden = true; });
      $('v8ImportPick').addEventListener('click', () => $('v8ImportFile').click());
      $('v8ImportFile').addEventListener('change', e => this.picked(e.target.files[0]));
      this.cleanupOffer();
    },
    async cleanupOffer() {
      try {
        const prods = await api('/api/my/products');
        const n = prods.filter(p => p.source === 'file_import').length;
        const box = $('v8ImportClean'); if (!box || !n) return;
        box.hidden = false;
        box.innerHTML = `<span class="v8-small v8-muted">มีสินค้าที่นำเข้าจากไฟล์อยู่ ${n} รายการ</span>
          <button class="btn btn-ghost btn-sm v8-danger" id="v8ImpCleanBtn">🧹 ลบสินค้าที่นำเข้าจากไฟล์ทั้งหมด</button>`;
        $('v8ImpCleanBtn').addEventListener('click', async () => {
          if (!confirm(`ลบสินค้าที่นำเข้าจากไฟล์ทั้ง ${n} รายการ? (สินค้าที่เพิ่มเองหรือดึงจาก Shopee API จะไม่ถูกลบ)`)) return;
          try { const r = await api('/api/my/products/bulk-delete', 'POST', { source: 'file_import' }); toast('✅ ' + r.message, 'success'); AAS.reloadProducts(); box.hidden = true; }
          catch (e) { toast(e.message, 'error'); }
        });
      } catch {}
    },
    sample() {
      const csv = '﻿ชื่อสินค้า,ราคา,ลิงก์ affiliate,URL ภาพสินค้า,รหัสสินค้า\n' +
        'หูฟังบลูทูธ TWS รุ่นใหม่,199,https://s.shopee.co.th/xxxxxxxx,,\n' +
        'เซรั่มบำรุงผิวหน้า,390,,,\n';
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
      a.download = 'ตัวอย่างสินค้า.csv'; a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    },
    async picked(f) {
      if (!f) return;
      this.file = f; $('v8ImportName').textContent = f.name;
      $('v8ImportStage').innerHTML = stateBox('loading', 'กำลังอ่านไฟล์…');
      const fd = new FormData(); fd.append('file', f);
      try { this.data = await form('/api/my/products/import-file/preview', fd); this.map(); }
      catch (e) { $('v8ImportStage').innerHTML = stateBox('error', e.message, null); }
    },
    map() {
      const d = this.data, opts = c => ['<option value="">— ไม่ใช้ —</option>'].concat(
        d.columns.map(col => `<option value="${esc(col)}" ${d.guess[c] === col ? 'selected' : ''}>${esc(col)}</option>`)).join('');
      $('v8ImportStage').innerHTML = `
        <div class="v8-import-map">
          <p class="v8-small"><strong>${esc(d.filename)}</strong> · พบ ${d.total} แถว — จับคู่คอลัมน์:</p>
          <div class="v8-map-grid">${d.fields.map(f => `
            <label>${esc(FIELD_LABELS[f] || f)}<select data-field="${f}" class="form-select">${opts(f)}</select></label>`).join('')}</div>
          <details class="v8-acc-sec"><summary>ดูตัวอย่าง 5 แถวแรก</summary>
            <div style="overflow:auto"><table class="v8-onb-table"><thead><tr>${d.columns.map(c => `<th>${esc(c)}</th>`).join('')}</tr></thead>
            <tbody>${d.sample.map(r => `<tr>${d.columns.map(c => `<td>${esc(String(r[c] ?? '').slice(0, 40))}</td>`).join('')}</tr>`).join('')}</tbody></table></div>
          </details>
          <label class="v8-onb-skip"><input type="checkbox" id="v8ImpImg" checked> ดาวน์โหลดภาพจาก URL มาเก็บในเครื่อง (แนะนำ — ลิงก์ภาพของร้านหมดอายุได้)</label>
          <label class="v8-onb-skip"><input type="checkbox" id="v8ImpOver"> โหลดทับภาพเดิมของสินค้าที่เคยนำเข้าแล้ว</label>
          <div class="v8-onb-nav" style="margin-top:12px">
            <button class="btn btn-ghost btn-sm" id="v8ImpReset">← เลือกไฟล์อื่น</button>
            <button class="btn btn-primary" id="v8ImpGo">นำเข้า ${d.total} รายการ</button>
          </div>
        </div>`;
      $('v8ImpReset').addEventListener('click', () => this.open());
      $('v8ImpGo').addEventListener('click', () => this.commit());
    },
    async commit() {
      const mapping = {};
      document.querySelectorAll('#v8ImportStage [data-field]').forEach(s => { if (s.value) mapping[s.dataset.field] = s.value; });
      if (!mapping.title) return toast('กรุณาเลือกคอลัมน์ "ชื่อสินค้า" ก่อน', 'error');
      const btn = $('v8ImpGo'); btn.disabled = true; btn.textContent = 'กำลังนำเข้า…';
      const fd = new FormData();
      fd.append('file', this.file); fd.append('mapping', JSON.stringify(mapping));
      fd.append('download_images', $('v8ImpImg').checked ? '1' : '0');
      fd.append('overwrite_images', $('v8ImpOver').checked ? '1' : '0');
      try {
        const r = await form('/api/my/products/import-file/commit', fd);
        $('v8ImportTitle').textContent = '✅ นำเข้าสำเร็จ';
        $('v8ImportBody').innerHTML = `
          <div class="v8-pay-done">
            <div class="v8-pay-check" aria-hidden="true">✓</div>
            <div class="v8-pay-plus">+${r.added} รายการ</div>
            <p>เพิ่มใหม่ <strong>${r.added}</strong> · อัปเดต <strong>${r.updated}</strong>${r.images ? ` · ดาวน์โหลดรูป <strong>${r.images}</strong>` : ''}${r.skipped ? ` · ข้าม ${r.skipped}` : ''}</p>
            <div class="v8-pay-actions" style="justify-content:center">
              <button class="btn btn-primary" id="v8ImpToProducts">ดูสินค้าของฉัน</button>
              <button class="btn btn-ghost" id="v8ImpMore">นำเข้าไฟล์อื่น</button>
            </div>
          </div>`;
        AAS.reloadProducts();
        $('v8ImpToProducts').addEventListener('click', () => { $('v8Import').hidden = true; AAS.switchTab('products'); });
        $('v8ImpMore').addEventListener('click', () => this.open());
      } catch (e) { toast(e.message, 'error'); btn.disabled = false; btn.textContent = 'ลองใหม่'; }
    },
    bind() {
      $('v8ImportFileBtn')?.addEventListener('click', () => this.open());
      $('v8ImportClose')?.addEventListener('click', () => { $('v8Import').hidden = true; });
      $('v8Import')?.addEventListener('click', e => { if (e.target.id === 'v8Import') $('v8Import').hidden = true; });
      document.addEventListener('keydown', e => { if (e.key === 'Escape' && !$('v8Import').hidden) $('v8Import').hidden = true; });
    },
  };

  function sourceChip(p) {
    const map = { shopee_affiliate_api: ['chip-success', 'Shopee API ✓'], file_import: ['', 'นำเข้าไฟล์'], manual: ['', 'กรอกเอง'], sample: ['', 'สินค้าตัวอย่าง'], radar: ['', 'จาก Radar'] };
    const [cls, label] = map[p.source] || ['', p.source || 'กรอกเอง'];
    return `<span class="chip ${cls} mono">${label}</span>`;
  }
  function productRows(prods) {
    const badge = $('badge-products-count'); if (badge) badge.textContent = prods.length;
    return prods.map(p => {
      const img = p.image_url || p.image_path || (p.source === 'sample' ? SAMPLE_IMG : '');
      const range = p.price_max && p.price_min && p.price_max !== p.price_min ? `${baht(p.price_min)}–${baht(p.price_max)}` : baht(p.price);
      return `<tr>
        <td><div class="v8-prod-cell">${imgTag(img, p.title)}<div><div style="font-weight:700">${esc(p.title)}</div>
          <div class="v8-muted v8-small">#${p.id} · ${esc(p.platform)}${p.shop_name ? ' · ' + esc(p.shop_name) : ''}${p.synced_at ? ' · อัปเดต ' + esc(localTime(p.synced_at)) : ''}</div></div></div></td>
        <td class="mono">${range}</td>
        <td class="mono"><strong>${pct(p.commission_rate)}</strong><div class="v8-small">${baht(p.commission_baht)}/ชิ้น</div></td>
        <td class="mono v8-small">${p.rating ? '⭐ ' + p.rating : '-'}<br>${p.sales ? Number(p.sales).toLocaleString() + ' ชิ้น' : ''}</td>
        <td><label style="display:flex;align-items:center;gap:6px;cursor:pointer;"><input type="checkbox" ${p.extra_comm_checked ? 'checked' : ''} onchange="window.appToggleExtraComm(${p.id}, this.checked)"><span class="mono v8-small">${p.extra_comm_rate ? p.extra_comm_rate + '%' : 'ยืนยันเอง'}</span></label></td>
        <td>${sourceChip(p)}</td>
        <td><div class="v8-row-actions">
          <button class="btn btn-primary btn-sm" onclick="AASv8.studioWithProduct(${p.id})" title="สร้างบท UGC และคลิป">✨ บท & คลิป</button>
          <button class="btn btn-secondary btn-sm" onclick="AASv8.openPublish(${p.id})" title="โพสต์ไปเพจ/IG/LINE">📤 โพสต์</button>
          ${p.item_id || (p.url || '').includes('shopee') ? `<button class="btn btn-ghost btn-sm" onclick="AASv8.refreshProduct(${p.id}, this)" title="อัปเดตราคา/ค่าคอมจาก Shopee">🔄</button>` : ''}
          <button class="btn btn-ghost btn-sm" onclick="window.appScheduleProduct(${p.id}, ${jsArg(p.title)})" title="วางแผนลงปฏิทิน">📅</button>
          <button class="btn btn-ghost btn-sm v8-danger" onclick="AASv8.deleteProduct(${p.id})" title="ลบสินค้า" aria-label="ลบสินค้า">🗑</button>
        </div></td></tr>`;
    }).join('');
  }

  // =========================================================== PRODUCT CARDS (คลังสินค้า)
  function productStatus(p) {
    if (p.source === 'shopee_affiliate_api') return '<span class="v8-pc-status is-live">ขายอยู่</span>';
    if (p.source === 'file_import') return '<span class="v8-pc-status">นำเข้าไฟล์</span>';
    if (p.source === 'sample') return '<span class="v8-pc-status">ตัวอย่าง</span>';
    return '<span class="v8-pc-status">กรอกเอง</span>';
  }
  function productCard(p) {
    const img = (p.use_ai_image && p.ai_image_path) || p.image_url || p.image_path || (p.source === 'sample' ? SAMPLE_IMG : '');
    const price = p.price_max && p.price_min && p.price_max !== p.price_min ? `${baht(p.price_min)}–${baht(p.price_max)}` : (p.price != null ? '฿' + Number(p.price).toLocaleString('th-TH', { minimumFractionDigits: 2 }) : '-');
    const link = p.offer_link || '';
    const off = p.active === 0;
    return `<div class="v8-pc ${off ? 'is-off' : ''}" data-pid="${p.id}">
      <div class="v8-pc-img">${img ? `<img src="${esc(img)}" alt="" loading="lazy">` : '<div class="v8-pc-noimg">ไม่มีรูป</div>'}${p.discount_rate ? `<span class="v8-pc-off">${Math.round(Number(p.discount_rate))}% OFF</span>` : ''}
        ${p.ai_image_path ? `<button class="v8-pc-imgswitch" onclick="AASv8.toggleAiImage(${p.id}, ${p.use_ai_image ? 'false' : 'true'})"
            title="สลับรูป">${p.use_ai_image ? '✨ รูป AI · ใช้รูปเดิม' : '📷 รูปเดิม · ใช้รูป AI'}</button>` : ''}</div>
      <div class="v8-pc-body">
        <div class="v8-pc-title-row">
          <button class="v8-pc-title v8-inline" data-field="title" data-pid="${p.id}" data-value="${esc(p.title)}"
                  onclick="AASv8.inlineEdit(this)" title="คลิกเพื่อแก้ชื่อ">${esc(p.title)}<span class="v8-pc-pen" aria-hidden="true">✎</span></button>
          <button class="btn btn-ghost btn-sm" onclick="AASv8.editProduct(${p.id})" title="แก้ไขรายละเอียดทั้งหมด">⋯ แก้ทั้งหมด</button></div>
        <div class="v8-pc-price-row">
          <button class="v8-pc-price v8-inline" data-field="price" data-pid="${p.id}" data-value="${p.price != null ? Number(p.price) : ''}"
                  onclick="AASv8.inlineEdit(this)" title="คลิกเพื่อแก้ราคา">${price}<span class="v8-pc-pen" aria-hidden="true">✎</span></button>
          ${productStatus(p)}</div>
        <div class="v8-pc-commbox">
          <div><span class="v8-small v8-muted">ค่าคอม</span>
            <button class="v8-pc-rate v8-inline" data-field="commission_rate" data-pid="${p.id}" data-value="${p.commission_rate != null ? Number(p.commission_rate) : ''}"
                    onclick="AASv8.inlineEdit(this)" title="คลิกเพื่อแก้ % ค่าคอม">${p.commission_rate != null ? Number(p.commission_rate) + '%' : 'ใส่ %'}<span class="v8-pc-pen" aria-hidden="true">✎</span></button></div>
          <div class="v8-pc-earn"><span class="v8-small v8-muted">ได้ต่อชิ้น</span>
            <strong>${commBaht(p)}</strong></div>
        </div>
        <div class="v8-muted v8-small">${p.sales ? 'ขายได้ ' + Number(p.sales).toLocaleString('th-TH') + ' ชิ้น' : '&nbsp;'}</div>
        ${p.description ? `<details class="v8-pc-desc"><summary>รายละเอียด</summary><div>${esc(p.description)}</div></details>` : ''}
        <div class="v8-pc-ai">
          <button class="btn btn-ai btn-sm" onclick="AASv8.aiProduct(${p.id})">✨ AI ปรับ</button>
          ${p.can_undo_ai ? `<button class="btn btn-ghost btn-sm" onclick="AASv8.undoAi(${p.id})" title="คืนชื่อและรายละเอียดก่อน AI แก้">↩ คืนชื่อเดิม</button>` : ''}
        </div>
        <div class="v8-pc-link"><span class="v8-pc-linkbox ${link ? 'has' : ''}" title="${esc(link)}">${link ? esc(link.replace(/^https:\/\//, '')) : 'ยังไม่มีลิงก์ affiliate'}</span>
          <button class="btn btn-ghost btn-sm" onclick="AASv8.editLink(${p.id}, ${jsArg(link)})" title="แก้ลิงก์ affiliate">✎</button></div>
        <div class="v8-muted v8-small">ID ${esc(p.item_id || ('#' + p.id))}</div>
        <div class="v8-pc-actions">
          <button class="btn btn-primary btn-sm" onclick="AASv8.studioWithProduct(${p.id})">✨ สร้างคอนเทนต์</button>
          <button class="btn btn-secondary btn-sm" onclick="AASv8.openPublish(${p.id})">📤 โพสต์</button>
          ${p.item_id && p.source === 'shopee_affiliate_api' ? `<button class="btn btn-ghost btn-sm" onclick="AASv8.refreshProduct(${p.id}, this)" title="อัปเดตราคา/ค่าคอมจาก Shopee">🔄</button>` : ''}
        </div>
        <div class="v8-pc-foot">
          <label class="v8-switch"><input type="checkbox" ${off ? '' : 'checked'} onchange="AASv8.toggleProduct(${p.id}, this.checked)"><span class="v8-switch-track"></span><span>ใช้งาน</span></label>
          <button class="btn btn-ghost btn-sm v8-danger" onclick="AASv8.deleteProduct(${p.id})">🗑 ลบ</button>
        </div>
      </div></div>`;
  }
  function renderProducts(prods) {
    const badge = $('badge-products-count'); if (badge) badge.textContent = prods.length;
    const head = $('v8ProductCount'); if (head) head.textContent = `สินค้า ${prods.length} รายการ`;
    const grid = $('v8ProductGrid'); if (!grid) return;
    grid.innerHTML = prods.length ? prods.map(productCard).join('')
      : stateBox('empty', 'ยังไม่มีสินค้า — กด "↓ นำเข้า CSV/Excel" หรือ "+ เพิ่มสินค้าเอง" หรือดึงจาก Shopee ด้านบน', null);
  }
  function commBaht(p) {
    const v = p.commission_baht != null ? Number(p.commission_baht)
      : (p.price != null && p.commission_rate != null ? Number(p.price) * Number(p.commission_rate) / 100 : null);
    return v != null && isFinite(v) ? '฿' + v.toLocaleString('th-TH', { maximumFractionDigits: 2 }) : '-';
  }
  const INLINE = {
    title: { type: 'text', label: 'ชื่อสินค้า', min: 3, max: 200, cls: 'v8-in-title' },
    price: { type: 'number', label: 'ราคา', min: 0, max: 10000000, step: '0.01', prefix: '฿', cls: 'v8-in-num' },
    commission_rate: { type: 'number', label: 'ค่าคอม %', min: 0, max: 100, step: '0.1', suffix: '%', cls: 'v8-in-num v8-in-rate' },
  };
  // Click a value on the card, type, Enter. Escape or an unchanged value puts it back.
  function inlineEdit(btn) {
    const field = btn.dataset.field, id = Number(btn.dataset.pid), cfg = INLINE[field];
    if (!cfg || btn.dataset.editing === '1') return;
    const current = btn.dataset.value || '';
    const holder = document.createElement('span');
    holder.className = 'v8-in-box';
    holder.innerHTML = (cfg.prefix ? `<span class="v8-in-fix">${cfg.prefix}</span>` : '') +
      `<input class="${cfg.cls}" type="${cfg.type}" aria-label="${cfg.label}" value="${esc(current)}"` +
      (cfg.type === 'number' ? ` min="${cfg.min}" max="${cfg.max}" step="${cfg.step}" inputmode="decimal"` : ` maxlength="${cfg.max}"`) + '>' +
      (cfg.suffix ? `<span class="v8-in-fix">${cfg.suffix}</span>` : '');
    btn.replaceWith(holder);
    const input = holder.querySelector('input');
    input.focus(); input.select();
    let done = false;
    const restore = () => { if (done) return; done = true; holder.replaceWith(btn); };
    const save = () => {
      if (done) return;
      const raw = input.value.trim();
      if (raw === String(current).trim()) return restore();
      let val = raw;
      if (cfg.type === 'number') {
        if (raw === '') return restore();
        val = Number(raw);
        if (!isFinite(val) || val < cfg.min || val > cfg.max) { toast(`${cfg.label}ต้องอยู่ระหว่าง ${cfg.min}–${cfg.max}`, 'error'); return restore(); }
      } else if (raw.length < cfg.min) { toast(`${cfg.label}ต้องยาวอย่างน้อย ${cfg.min} ตัวอักษร`, 'error'); return restore(); }
      done = true;
      input.disabled = true;
      const shown = field === 'price' ? '฿' + val.toLocaleString('th-TH') : field === 'commission_rate' ? val + '%' : `"${String(val).slice(0, 30)}"`;
      patchProduct(id, { [field]: val }, `บันทึก${cfg.label} ${shown} แล้ว`);
    };
    input.addEventListener('keydown', e => {
      if (e.key === 'Enter') { e.preventDefault(); save(); }
      if (e.key === 'Escape') { e.preventDefault(); restore(); }
    });
    input.addEventListener('blur', save);
  }

  async function patchProduct(id, body, okMsg) {
    try { await api(`/api/my/products/${id}`, 'PATCH', body); if (okMsg) toast(okMsg, 'success'); AAS.reloadProducts(); }
    catch (e) { toast(e.message, 'error'); AAS.reloadProducts(); }
  }

  // ===================================================== EDIT PRODUCT (full form)
  // Same fields as the manual add form — editing a product should not be a weaker
  // version of creating one.
  const EditProduct = {
    product: null,
    async open(id) {
      let p;
      try { p = (await api('/api/my/products')).find(x => x.id === id); }
      catch (e) { return toast(e.message, 'error'); }
      if (!p) return toast('ไม่พบสินค้านี้', 'error');
      this.product = p;
      const f = $('v8EpForm');
      f.product_id.value = p.id;
      f.title.value = p.title || '';
      f.platform.value = ['shopee', 'tiktok', 'other'].includes(p.platform) ? p.platform : 'other';
      f.url.value = p.offer_link || p.url || '';
      f.price.value = p.price != null ? p.price : '';
      f.commission_rate.value = p.commission_rate != null ? p.commission_rate : '';
      f.image_url.value = (p.image_url || '').startsWith('https://') ? p.image_url : '';
      f.image.value = '';
      this.syncComm();
      this.syncPreview();
      $('v8EditProduct').hidden = false;
      setTimeout(() => f.title.focus(), 50);
    },
    close() { $('v8EditProduct').hidden = true; this.product = null; },
    syncComm() {
      const f = $('v8EpForm');
      const price = parseFloat(f.price.value), rate = parseFloat(f.commission_rate.value);
      $('v8EpComm').value = (isFinite(price) && isFinite(rate))
        ? '≈ ฿' + (price * rate / 100).toLocaleString('th-TH', { maximumFractionDigits: 2 }) + ' /ชิ้น'
        : 'กรอกราคาและค่าคอมเพื่อคำนวณ';
    },
    syncPreview() {
      const f = $('v8EpForm');
      const p = this.product || {};
      const file = f.image.files && f.image.files[0];
      const url = f.image_url.value.trim();
      const current = p.image_url || p.image_path || '';
      const box = $('v8EpPreview');
      if (file) {
        box.innerHTML = `<span class="v8-small v8-muted">รูปใหม่ที่จะอัปโหลด:</span><img src="${URL.createObjectURL(file)}" alt="">`;
      } else if (url) {
        box.innerHTML = `<span class="v8-small v8-muted">รูปจากลิงก์:</span><img src="${esc(url)}" alt="" onerror="this.replaceWith(Object.assign(document.createElement('span'),{className:'v8-small v8-warn',textContent:'โหลดรูปจากลิงก์นี้ไม่ได้'}))">`;
      } else if (current) {
        box.innerHTML = `<span class="v8-small v8-muted">รูปปัจจุบัน (เก็บไว้ถ้าไม่เปลี่ยน):</span><img src="${esc(current)}" alt="">`;
      } else {
        box.innerHTML = '<span class="v8-small v8-muted">ยังไม่มีรูป</span>';
      }
    },
    async submit(e) {
      e.preventDefault();
      const f = e.target;
      const btn = e.submitter; btn.disabled = true; btn.textContent = 'กำลังบันทึก…';
      const fd = new FormData(f);
      const id = fd.get('product_id');
      fd.delete('product_id');
      if (!(fd.get('image') instanceof File) || !fd.get('image').size) fd.delete('image');
      fd.set('keep_image', '1');
      try {
        const r = await form(`/api/my/products/${id}/manual`, fd, 'PUT');
        toast('✅ ' + r.message, 'success');
        this.close();
        AAS.reloadProducts();
      } catch (err) { toast(err.message, 'error'); }
      finally { btn.disabled = false; btn.textContent = 'บันทึกการแก้ไข'; }
    },
    bind() {
      const f = $('v8EpForm'); if (!f) return;
      f.addEventListener('submit', e => this.submit(e));
      ['price', 'commission_rate'].forEach(n => f[n].addEventListener('input', () => this.syncComm()));
      f.image.addEventListener('change', () => this.syncPreview());
      f.image_url.addEventListener('input', () => this.syncPreview());
      $('v8EpCancel')?.addEventListener('click', () => this.close());
      $('v8EpClose')?.addEventListener('click', () => this.close());
      $('v8EditProduct')?.addEventListener('click', e => { if (e.target.id === 'v8EditProduct') this.close(); });
    },
  };

  // =========================================================== PUBLISH MODAL
  const Publish = {
    product: null, channels: [],
    async open(productId, caption) {
      const m = $('v8PublishModal'); m.hidden = false;
      $('v8PublishResults').innerHTML = '';
      $('v8PublishChannels').innerHTML = stateBox('loading', 'กำลังโหลดช่องทาง…');
      try {
        const [prods, conn] = await Promise.all([api('/api/my/products'), api('/api/connectors')]);
        this.product = prods.find(p => p.id === productId);
        if (!this.product) throw Error('ไม่พบสินค้า');
        this.channels = conn.channels.filter(c => c.has_token);
        const p = this.product;
        const img = p.image_url || p.image_path || '';
        $('v8PublishProduct').innerHTML = `${imgTag(img, p.title)}<div><strong>${esc(p.title)}</strong><div class="v8-muted v8-small">${baht(p.price)} · ค่าคอม ${pct(p.commission_rate)}</div>
          ${img.startsWith('https://') ? '' : '<div class="v8-warn v8-small">⚠ สินค้านี้ไม่มีรูปจาก URL https สาธารณะ — Instagram จะโพสต์ไม่ได้ / Facebook จะโพสต์เป็นข้อความ</div>'}</div>`;
        const link = p.offer_link || p.url || '';
        $('v8PublishCaption').value = caption || [`🔥 ${p.title}`, p.price ? `💰 ราคาเริ่ม ฿${Number(p.price).toLocaleString()}` : '', link ? `🛒 สั่งซื้อ: ${link}` : '', '#ShopeeAffiliate #ของดีบอกต่อ'].filter(Boolean).join('\n');
        const groups = ['facebook', 'instagram', 'line_oa'].map(pl => {
          const list = this.channels.filter(c => c.platform === pl);
          if (!list.length) return `<div class="v8-pub-row is-off">${PLATFORM_ICON[pl]} ${PLATFORM_LABEL[pl]} — <span class="v8-muted">ยังไม่เชื่อมต่อ</span> <button class="btn btn-ghost btn-sm" onclick="AASv8.goConnectors()">เชื่อมต่อ</button></div>`;
          return list.map(c => `<label class="v8-pub-row"><input type="checkbox" name="v8pubch" value="${c.id}" data-platform="${pl}"> ${PLATFORM_ICON[pl]} ${esc(c.account_name)} <span class="chip v8-chip-wait">${PLATFORM_LABEL[pl]}</span></label>`).join('');
        }).join('') + `<div class="v8-pub-row is-off">🎵 TikTok — <span class="v8-muted">ยังไม่เชื่อมต่อ (โพสต์เอง: ดาวน์โหลดคลิปจากหน้า "สร้างคอนเทนต์")</span></div>`;
        $('v8PublishChannels').innerHTML = groups;
        $('v8PublishChannels').querySelectorAll('input[name=v8pubch]').forEach(cb => cb.addEventListener('change', () => this.syncLine()));
        this.syncLine();
      } catch (e) {
        $('v8PublishChannels').innerHTML = isAuthError(e) ? '' : stateBox('error', e.message, null);
        if (isAuthError(e)) loginBox($('v8PublishChannels'));
      }
    },
    syncLine() {
      const any = [...document.querySelectorAll('input[name=v8pubch]:checked')].some(c => c.dataset.platform === 'line_oa');
      $('v8LineMode').hidden = !any;
    },
    async submit() {
      const ids = [...document.querySelectorAll('input[name=v8pubch]:checked')].map(c => Number(c.value));
      if (!ids.length) return toast('เลือกอย่างน้อย 1 ช่องทางที่เชื่อมต่อแล้ว', 'error');
      const mode = document.querySelector('input[name=v8linemode]:checked')?.value || 'push';
      let confirmB = false;
      if (mode === 'broadcast' && ids.some(id => this.channels.find(c => c.id === id)?.platform === 'line_oa')) {
        confirmB = confirm('Broadcast จะส่งหาเพื่อนทุกคนของ LINE OA และนับโควต้าข้อความ ยืนยันหรือไม่?');
        if (!confirmB) return;
      }
      const btn = $('v8PublishSubmit'); btn.disabled = true; btn.textContent = 'กำลังส่ง…';
      $('v8PublishResults').innerHTML = stateBox('loading', 'กำลังโพสต์ไปยังผู้ให้บริการจริง…');
      try {
        const r = await api(`/api/products/${this.product.id}/publish`, 'POST', { channel_ids: ids, caption: $('v8PublishCaption').value, line_mode: mode, confirm_broadcast: confirmB });
        $('v8PublishResults').innerHTML = `<div class="v8-small" style="font-weight:700;margin-bottom:6px">${esc(r.message)}</div>` + r.results.map(x =>
          `<div class="v8-result ${x.ok ? 'ok' : 'bad'}">${x.ok ? '✅' : '❌'} ${PLATFORM_ICON[x.platform] || ''} ${esc(x.account_name || '#' + x.channel_id)} — ${x.ok ? 'สำเร็จ ' + esc(x.kind || '') + (x.post_id ? ' · ' + esc(x.post_id) : '') : esc(x.error)}</div>`).join('');
        toast(r.message, r.ok_count ? 'success' : 'error');
      } catch (e) { $('v8PublishResults').innerHTML = stateBox('error', e.message, null); }
      finally { btn.disabled = false; btn.textContent = 'ส่งโพสต์'; }
    },
  };

  // =========================================================== CONNECTORS
  const Conn = {
    data: null,
    async load() {
      const box = $('v8ConnectorCards');
      if (!box) return;
      box.innerHTML = stateBox('loading', 'กำลังโหลดสถานะการเชื่อมต่อ…');
      try {
        this.data = await api('/api/connectors');
        this.render();
        this.loadLogs();
        if (this.data.is_admin) this.loadAdmin(); else $('v8AdminIntegrations').hidden = true;
      } catch (e) {
        if (isAuthError(e)) return loginBox(box);
        box.innerHTML = stateBox('error', 'โหลดสถานะไม่สำเร็จ: ' + e.message, null) + '<button class="btn btn-secondary btn-sm" onclick="AASv8.loadConnectors()">ลองใหม่</button>';
      }
    },
    chanRow(c) {
      const m = c.meta || {};
      const status = c.status === 'error' ? `<span class="chip v8-chip-err mono">⚠ ${esc(c.last_error || 'error')}</span>` : `<span class="chip chip-success">🟢 เชื่อมต่อจริง</span>`;
      const extra = c.platform === 'line_oa'
        ? `<div class="v8-small v8-muted">${esc(m.basic_id || '')} · โควต้า ${m.quota && m.quota.limit != null ? `${m.quota.used}/${m.quota.limit}` : 'ไม่จำกัด/ไม่ทราบ'} · ผู้รับที่รู้จัก ${c.recipients || 0} คน</div>
           <div class="v8-small">Webhook: <code class="v8-code">${esc(c.webhook_url || '-')}</code> <button class="btn btn-ghost btn-sm" onclick="AASv8.copy(${jsArg(c.webhook_url || '')})">คัดลอก</button></div>`
        : c.platform === 'tiktok'
          ? `<div class="v8-small v8-muted">${esc(m.display_name || '')}${m.followers != null ? ' · ผู้ติดตาม ' + Number(m.followers).toLocaleString() : ''}</div>
             ${m.privacy_options ? (m.audited
               ? '<div class="v8-small" style="color:var(--color-success,#16a34a)">✓ แอปผ่าน audit แล้ว — โพสต์สาธารณะได้</div>'
               : '<div class="v8-warn v8-small">⚠ แอปยังไม่ผ่าน audit ของ TikTok — คลิปที่โพสต์จะเป็น <strong>ส่วนตัว (เห็นคนเดียว)</strong> จนกว่าจะเปลี่ยนเป็นสาธารณะเองในแอป</div>') : ''}`
        : c.platform === 'instagram'
          ? `<div class="v8-small v8-muted">${m.via === 'facebook' ? 'ผ่านเพจ ' + esc(m.page_name || '') : 'Instagram Login'}${c.token_expires_at ? ' · token หมดอายุ ' + esc(c.token_expires_at.slice(0, 10)) : ''}</div>`
          : `<div class="v8-small v8-muted">${esc(m.category || '')} · Page ID ${esc(c.account_id)}</div>`;
      return `<div class="v8-chan">
        <div class="v8-chan-head">${imgTag(m.picture || '', c.account_name, 'v8-avatar')}<div style="flex:1;min-width:0"><strong>${esc(c.account_name)}</strong>${extra}</div>${status}</div>
        <div class="v8-chan-actions">
          <button class="btn btn-ghost btn-sm" onclick="AASv8.verify(${c.id}, this)">📡 ตรวจสอบ</button>
          ${c.platform === 'tiktok'
            ? `<button class="btn btn-primary btn-sm" onclick="AASv8.tiktokPost(${c.id})">🎬 โพสต์คลิป</button>`
            : `<button class="btn btn-ghost btn-sm" onclick="AASv8.testPost(${c.id}, '${c.platform}')">📤 ทดสอบส่ง</button>`}
          ${c.platform === 'line_oa' ? `<button class="btn btn-ghost btn-sm" onclick="AASv8.testPost(${c.id}, 'line_broadcast')">📣 Broadcast</button>` : ''}
          <button class="btn btn-ghost btn-sm v8-danger" onclick="AASv8.disconnect(${c.id}, ${jsArg(c.account_name)})">ตัดการเชื่อมต่อ</button>
        </div></div>`;
    },
    render() {
      const d = this.data, cfg = d.config;
      const by = pl => d.channels.filter(c => c.platform === pl);
      const badge = $('badge-connectors-count'); if (badge) badge.textContent = d.channels.length;
      const notReady = who => `<div class="v8-warn v8-small">⚠ ผู้ดูแลระบบยังไม่ได้ตั้งค่า ${who} — ${d.is_admin ? 'ตั้งค่าได้ที่กล่อง "ตั้งค่าแอป" ด้านล่าง' : 'แจ้งผู้ดูแลระบบ หรือเชื่อม IG ผ่านเพจ Facebook'}</div>`;
      const head = (pl, title, desc) => {
        const n = by(pl).length;
        return `<div class="v8-card-head"><div><h3>${PLATFORM_ICON[pl]} ${title}</h3><p class="v8-muted v8-small">${desc}</p></div>
          <span class="chip ${n ? 'chip-success' : ''} mono">${n ? `เชื่อมต่อแล้ว ${n}` : 'ยังไม่เชื่อมต่อ'}</span></div>`;
      };
      $('v8ConnectorCards').innerHTML = `
        <div class="mf-card v8-conn-card">
          ${head('facebook', 'เพจ Facebook (โพส Reels ผ่าน API)', 'วาง Page Access Token ของเพจ — ระบบเช็คและดึงชื่อเพจให้อัตโนมัติ')}
          <div class="v8-warn v8-small" style="line-height:1.6">🌐 <strong>ตั้งภาษาหน้า developers.facebook.com เป็น English</strong> ตอนขอ Page Access Token ปุ่มบนหน้าจอจะตรงกับคู่มือ (Generate Access Token · Permissions · User or Page) — การโพสต์ใช้ Graph API ไม่ได้อ่านหน้าจอ ภาษาจึงไม่ทำให้โพสต์พลาด</div>
          <form id="v8FbTokenForm" class="v8-token-form" autocomplete="off">
            <div>
              <strong style="font-size:14px">Page Access Token</strong>
              <div class="v8-small v8-muted">ต้องมีสิทธิ์ pages_manage_posts + pages_read_engagement (+ pages_manage_engagement ถ้าจะคอมเมนต์ลิงก์)</div>
            </div>
            <div class="v8-token-row">
              <input class="form-input" name="token" type="password" required minlength="40" maxlength="1000" placeholder="วาง token ของเพจที่นี่" aria-label="Page Access Token">
              <button type="button" class="btn btn-ghost btn-sm" id="v8FbTokenEye" aria-label="แสดง/ซ่อน">👁</button>
              <button type="button" class="btn btn-ghost btn-sm" data-help-article="connect-facebook">วิธีขอ token</button>
              <button class="btn btn-primary" type="submit">เพิ่มเพจ</button>
            </div>
          </form>
          <div class="v8-chan-list">${by('facebook').map(c => this.chanRow(c)).join('') || '<div class="v8-empty">ยังไม่มีเพจที่เชื่อม</div>'}</div>
          ${cfg.facebook.ready ? '<button class="btn btn-secondary btn-sm v8-fb-btn" onclick="AASv8.oauth(\'facebook\', this)">หรือเชื่อมผ่านปุ่ม Login กับ Facebook</button>' : ''}
        </div>
        <div class="mf-card v8-conn-card">
          ${head('instagram', 'Instagram (Business/Creator)', 'วาง token ของ IG หรือของเพจที่ผูก IG ไว้ — ระบบหาบัญชีให้เอง')}
          <div class="v8-muted v8-small">💡 ถ้าเชื่อม Facebook Page ที่ผูก IG ไว้แล้ว ระบบเพิ่ม IG ให้อัตโนมัติ ไม่ต้องทำซ้ำที่นี่</div>
          <form id="v8IgTokenForm" class="v8-token-form" autocomplete="off">
            <div>
              <strong style="font-size:14px">Instagram หรือ Page Access Token</strong>
              <div class="v8-small v8-muted">ใส่ได้ทั้ง 2 แบบ: token ของ Instagram โดยตรง หรือ Page Access Token ของเพจที่ผูกบัญชี IG แบบ Business/Creator</div>
            </div>
            <div class="v8-token-row">
              <input class="form-input" name="token" type="password" required minlength="40" maxlength="1000" placeholder="วาง token ที่นี่" aria-label="Instagram access token">
              <button type="button" class="btn btn-ghost btn-sm" id="v8IgTokenEye" aria-label="แสดง/ซ่อน">👁</button>
              <button type="button" class="btn btn-ghost btn-sm" data-help-article="connect-instagram">วิธีขอ token</button>
              <button class="btn btn-primary" type="submit">เพิ่มบัญชี IG</button>
            </div>
          </form>
          <div class="v8-chan-list">${by('instagram').map(c => this.chanRow(c)).join('') || '<div class="v8-empty">ยังไม่มีบัญชี IG ที่เชื่อม</div>'}</div>
          ${cfg.instagram.ready ? '<button class="btn btn-secondary btn-sm v8-ig-btn" onclick="AASv8.oauth(\'instagram\', this)">หรือเชื่อมผ่านปุ่ม Login กับ Instagram</button>' : ''}
        </div>
        <div class="mf-card v8-conn-card">
          ${head('tiktok', 'TikTok (โพสต์คลิปผ่าน Content Posting API)', 'กดปุ่มเดียว — TikTok จะถามยืนยันแล้วส่งกลับมาเอง ไม่ต้องคัดลอก token')}
          ${cfg.tiktok.ready ? '' : notReady('TikTok Client Key/Secret')}
          <div class="v8-chan-list">${by('tiktok').map(c => this.chanRow(c)).join('') || '<div class="v8-empty">ยังไม่มีบัญชี TikTok ที่เชื่อม</div>'}</div>
          <button class="btn btn-primary v8-tt-btn" ${cfg.tiktok.ready ? '' : 'disabled'} onclick="AASv8.tiktokConnect()">Continue with TikTok</button>
          <button class="btn btn-ghost btn-sm" data-help-article="${d.is_admin && !cfg.tiktok.ready ? 'admin-tiktok-app' : 'connect-tiktok'}">วิธีใช้งาน TikTok</button>
          <div class="v8-small v8-muted">ขอสิทธิ์ <code class="v8-code">user.info.basic</code> + <code class="v8-code">video.publish</code> เท่านั้น · ยกเลิกได้ทุกเมื่อทั้งในแอป TikTok และปุ่ม "ตัดการเชื่อมต่อ" ที่นี่</div>
        </div>
        <div class="mf-card v8-conn-card">
          ${head('line_oa', 'LINE Official Account', 'ใช้ Messaging API: Channel ID + Channel secret (+ access token) ระบบตรวจกับ LINE จริงและตั้ง Webhook ให้')}
          <div class="v8-chan-list">${by('line_oa').map(c => this.chanRow(c)).join('') || '<div class="v8-empty">ยังไม่มี LINE OA ที่เชื่อม</div>'}</div>
          <form id="v8LineForm" class="v8-form-grid" autocomplete="off">
            <label>Channel ID<input class="form-input" name="channel_id" inputmode="numeric" required minlength="5" maxlength="20" placeholder="1650000000"></label>
            <label>Channel secret<input class="form-input" name="channel_secret" type="password" required minlength="16" maxlength="64"></label>
            <label class="v8-span2">Channel access token (long-lived) — ไม่ใส่ได้ ระบบจะออก token 30 วันให้<input class="form-input" name="access_token" type="password" maxlength="600"></label>
            <div class="v8-span2" style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap">
              <button type="button" class="btn btn-ghost btn-sm" data-help-article="connect-line">วิธีหา Channel ID / Secret</button>
              <button class="btn btn-primary" type="submit">เชื่อมต่อ & ตรวจสอบ</button>
            </div>
          </form>
        </div>`;
      $('v8LineForm').addEventListener('submit', e => this.connectLine(e));
      $('v8FbTokenForm')?.addEventListener('submit', e => this.connectFbToken(e));
      $('v8FbTokenEye')?.addEventListener('click', () => {
        const i = $('v8FbTokenForm').token; i.type = i.type === 'password' ? 'text' : 'password';
      });
      $('v8IgTokenForm')?.addEventListener('submit', e => this.connectIgToken(e));
      $('v8IgTokenEye')?.addEventListener('click', () => {
        const i = $('v8IgTokenForm').token; i.type = i.type === 'password' ? 'text' : 'password';
      });
      bindHelpLinks($('v8ConnectorCards'));
    },
    async connectFbToken(e) {
      e.preventDefault();
      const btn = e.submitter; btn.disabled = true; btn.textContent = 'กำลังตรวจกับ Facebook…';
      try {
        const r = await api('/api/connectors/facebook/token', 'POST', { token: e.target.token.value.trim() });
        e.target.reset();
        toast('✅ ' + r.message, 'success');
        this.load();
      } catch (err) { toast(err.message, 'error'); }
      finally { btn.disabled = false; btn.textContent = 'เพิ่มเพจ'; }
    },
    async connectIgToken(e) {
      e.preventDefault();
      const btn = e.submitter; btn.disabled = true; btn.textContent = 'กำลังตรวจกับ Instagram…';
      try {
        const r = await api('/api/connectors/instagram/token', 'POST', { token: e.target.token.value.trim() });
        e.target.reset();
        toast('✅ ' + r.message, 'success');
        this.load();
      } catch (err) { toast(err.message, 'error'); }
      finally { btn.disabled = false; btn.textContent = 'เพิ่มบัญชี IG'; }
    },
    async connectLine(e) {
      e.preventDefault();
      const btn = e.submitter; btn.disabled = true; btn.textContent = 'กำลังตรวจกับ LINE…';
      const d = Object.fromEntries(new FormData(e.target));
      if (!d.access_token) delete d.access_token;
      try {
        const r = await api('/api/connectors/line', 'POST', d);
        if (r.webhook.set) toast('✅ ' + r.message + ' · ตั้ง Webhook ให้แล้ว', 'success');
        else toast('✅ ' + r.message + '\n⚠ ยังตั้ง Webhook อัตโนมัติไม่ได้: ' + r.webhook.reason + ' — คัดลอก Webhook URL ในการ์ดไปวางใน LINE Developers เอง', 'info');
        this.load();
      } catch (err) { toast(err.message, 'error'); btn.disabled = false; btn.textContent = 'เชื่อมต่อ & ตรวจสอบ'; }
    },
    async loadLogs() {
      const tb = $('v8PublishLogs');
      try {
        const r = await api('/api/connectors/logs');
        tb.innerHTML = r.logs.length ? r.logs.map(l => `<tr><td class="mono v8-small">${esc(localTime(l.created_at))}</td>
          <td>${PLATFORM_ICON[l.platform] || ''} ${esc(l.account_name || l.platform)}</td><td>${esc(l.product_title || '-')}</td>
          <td>${l.ok ? '✅ สำเร็จ' : '❌ ล้มเหลว'}</td><td class="v8-small">${esc(l.external_id || l.detail)}</td></tr>`).join('')
          : stateBox('empty', 'ยังไม่มีการโพสต์', null, 5);
      } catch (e) { tb.innerHTML = stateBox('error', e.message, null, 5); }
    },
    async loadAdmin() {
      const card = $('v8AdminIntegrations'); card.hidden = false;
      try {
        const d = await api('/api/admin/integrations');
        const f = $('v8IntegrationForm');
        ['meta_app_id', 'ig_app_id', 'tiktok_client_key', 'public_base_url'].forEach(k => { f[k].value = d[k].value || ''; f[k].disabled = d[k].from_env; f[k].title = d[k].from_env ? 'ตั้งค่าจาก ENV' : ''; });
        ['meta_app_secret', 'ig_app_secret', 'tiktok_client_secret'].forEach(k => { f[k].placeholder = d[k].set ? '•••••• (ตั้งไว้แล้ว — เว้นว่าง = ไม่เปลี่ยน)' : 'ยังไม่ได้ตั้ง'; f[k].disabled = d[k].from_env; });
        const cfg = this.data.config;
        $('v8RedirectInfo').innerHTML = `<div class="v8-small">ใส่ใน Meta App → Facebook Login → Valid OAuth Redirect URIs:<br><code class="v8-code">${esc(cfg.facebook.redirect_uri)}</code> <button type="button" class="btn btn-ghost btn-sm" onclick="AASv8.copy(${jsArg(cfg.facebook.redirect_uri)})">คัดลอก</button></div>
          <div class="v8-small">Instagram Business login → Redirect URL:<br><code class="v8-code">${esc(cfg.instagram.redirect_uri)}</code> <button type="button" class="btn btn-ghost btn-sm" onclick="AASv8.copy(${jsArg(cfg.instagram.redirect_uri)})">คัดลอก</button></div>
          <div class="v8-small">TikTok → Login Kit → Redirect URI:<br><code class="v8-code">${esc(cfg.tiktok.redirect_uri)}</code> <button type="button" class="btn btn-ghost btn-sm" onclick="AASv8.copy(${jsArg(cfg.tiktok.redirect_uri)})">คัดลอก</button></div>
          <div class="v8-small v8-muted">Graph API ${esc(cfg.graph_version)} · ${cfg.line_oa.public_https ? 'เว็บเป็น https สาธารณะ ✓' : '⚠ เว็บยังไม่ใช่ https สาธารณะ: OAuth/Webhook จากภายนอกจะยังใช้ไม่ได้'}</div>`;
      } catch (e) { card.hidden = true; }
    },
    bind() {
      $('v8IntegrationForm')?.addEventListener('submit', async e => {
        e.preventDefault();
        const body = {};
        for (const [k, v] of new FormData(e.target)) { if (!e.target[k].disabled && (v || !k.endsWith('secret'))) body[k] = v; }
        try { const r = await api('/api/admin/integrations', 'PUT', body); toast('✅ บันทึกแล้ว: ' + r.updated.join(', '), 'success'); this.load(); }
        catch (err) { toast(err.message, 'error'); }
      });
      $('v8ReloadLogs')?.addEventListener('click', () => this.loadLogs());
    },
  };

  // =================================================== TIKTOK CONNECT CONSENT
  // Shown before the redirect. TikTok's own consent screen comes next and is the one
  // that actually grants access — this one exists so the person knows what they are
  // about to approve, and what the app deliberately cannot do, while still in our UI.
  const TikTokConnect = {
    open() {
      const note = $('v8TtConnNote');
      const audited = (Conn.data?.channels || []).some(c => c.platform === 'tiktok' && c.meta?.audited);
      note.innerHTML = audited ? '' :
        '⚠ แอปนี้ยังไม่ผ่าน audit ของ TikTok — คลิปที่โพสต์ผ่านระบบจะเป็น <strong>ส่วนตัว (เห็นคนเดียว)</strong> ' +
        'จนกว่าคุณจะเปิดแอป TikTok แล้วเปลี่ยนเป็นสาธารณะเอง';
      note.hidden = !note.innerHTML;
      $('v8TtConnect').hidden = false;
      setTimeout(() => $('v8TtConnGo')?.focus(), 50);
    },
    close() { $('v8TtConnect').hidden = true; },
    async go() {
      const btn = $('v8TtConnGo'); btn.disabled = true; btn.textContent = 'กำลังเปิดหน้า TikTok…';
      try {
        const r = await api('/api/connectors/tiktok/start?return_tab=connectors', 'POST');
        location.href = r.auth_url;
      } catch (e) {
        toast(e.message, 'error');
        btn.disabled = false; btn.textContent = 'ดำเนินการต่อ';
      }
    },
    bind() {
      $('v8TtConnClose')?.addEventListener('click', () => this.close());
      $('v8TtConnCancel')?.addEventListener('click', () => this.close());
      $('v8TtConnGo')?.addEventListener('click', () => this.go());
      $('v8TtConnect')?.addEventListener('click', e => { if (e.target.id === 'v8TtConnect') this.close(); });
    },
  };

  // =========================================================== TIKTOK DIRECT POST
  // TikTok's Content Sharing Guidelines require the creator to see who they are posting
  // as, choose from THEIR OWN privacy options, declare commercial content, and confirm
  // the music terms. None of that is optional dressing — a post that skips it is a
  // policy violation, so every field here is driven by a live creator_info call.
  const TikTokPost = {
    channelId: null, info: null, projects: [], publishId: null, timer: null,
    close() {
      clearTimeout(this.timer); this.timer = null;
      $('v8TtModal').hidden = true;
    },
    async open(channelId) {
      this.channelId = channelId; this.publishId = null;
      const box = $('v8TtBody');
      $('v8TtModal').hidden = false;
      box.innerHTML = stateBox('loading', 'กำลังดึงข้อมูลบัญชีจาก TikTok…');
      try {
        const [info, pr] = await Promise.all([
          api(`/api/connectors/${channelId}/tiktok/creator-info`),
          api('/api/studio/projects'),
        ]);
        this.info = info;
        this.projects = (pr.projects || []).filter(p => p.clip_url || p.preview_url);
        this.render();
      } catch (e) {
        box.innerHTML = stateBox('error', e.message, null);
      }
    },
    render() {
      const i = this.info;
      if (!this.projects.length) {
        $('v8TtBody').innerHTML = stateBox('empty', 'ยังไม่มีคลิปที่พร้อมโพสต์ — ไปสร้างคลิปที่หน้า "สร้างคอนเทนต์" ก่อน', null)
          + '<button class="btn btn-primary btn-sm" onclick="AASv8.closeTiktok();AAS.switchTab(\'studio\')">ไปสร้างคลิป</button>';
        return;
      }
      const lock = (on, label) => on ? ` <span class="chip v8-chip-wait">บัญชีล็อกไว้: ${label}</span>` : '';
      $('v8TtBody').innerHTML = `
        <div class="v8-tt-creator">${imgTag(i.avatar || '', i.nickname, 'v8-avatar')}
          <div><strong>${esc(i.nickname || i.username)}</strong><div class="v8-small v8-muted">@${esc(i.username)}</div></div>
        </div>
        ${i.audited ? '' : '<div class="v8-warn v8-small">⚠ แอปนี้ยังไม่ผ่าน audit ของ TikTok — โพสต์ได้เฉพาะแบบ <strong>ส่วนตัว</strong> เท่านั้น หลังโพสต์ให้เปิดแอป TikTok แล้วเปลี่ยนเป็นสาธารณะเอง</div>'}
        <label class="v8-tt-field">เลือกคลิป
          <select class="form-input" id="v8TtProject">
            ${this.projects.map(p => `<option value="${p.id}">#${p.id} · ${esc(p.product.title).slice(0, 60)}${p.clip_url ? ' (คลิป AI)' : ' (พรีวิว)'}</option>`).join('')}
          </select>
        </label>
        <label class="v8-tt-field">แคปชัน <span class="v8-muted v8-small">(สูงสุด 2,200 ตัวอักษร · แฮชแท็กและ @ ใช้ได้)</span>
          <textarea class="form-input" id="v8TtCaption" rows="3" maxlength="2200" placeholder="รีวิวของดีบอกต่อ #ShopeeAffiliate"></textarea>
        </label>
        <label class="v8-tt-field">ใครดูคลิปนี้ได้
          <select class="form-input" id="v8TtPrivacy">
            ${i.privacy_options.map(o => `<option value="${o}">${esc(i.privacy_labels[o] || o)}</option>`).join('')}
          </select>
        </label>
        <fieldset class="v8-tt-group"><legend>การมีส่วนร่วม</legend>
          <label><input type="checkbox" id="v8TtNoComment" ${i.comment_disabled ? 'checked disabled' : ''}> ปิดคอมเมนต์${lock(i.comment_disabled, 'คอมเมนต์ปิด')}</label>
          <label><input type="checkbox" id="v8TtNoDuet" ${i.duet_disabled ? 'checked disabled' : ''}> ปิด Duet${lock(i.duet_disabled, 'Duet ปิด')}</label>
          <label><input type="checkbox" id="v8TtNoStitch" ${i.stitch_disabled ? 'checked disabled' : ''}> ปิด Stitch${lock(i.stitch_disabled, 'Stitch ปิด')}</label>
        </fieldset>
        <fieldset class="v8-tt-group"><legend>เปิดเผยเนื้อหาเชิงพาณิชย์</legend>
          <p class="v8-small v8-muted">คลิป Affiliate คือเนื้อหาเชิงพาณิชย์ — TikTok กำหนดให้ประกาศ ไม่ประกาศถือว่าผิดนโยบาย</p>
          <label><input type="checkbox" id="v8TtBrandOrganic"> โปรโมตแบรนด์ของฉันเอง <span class="v8-muted v8-small">(ติดป้าย "โปรโมตเอง")</span></label>
          <label><input type="checkbox" id="v8TtBrandContent"> ได้รับค่าตอบแทนจากแบรนด์อื่น <span class="v8-muted v8-small">(ติดป้าย "ได้รับการสนับสนุน")</span></label>
          <div class="v8-small v8-warn" id="v8TtBrandWarn" hidden>⚠ TikTok ไม่ให้ตั้งคลิป Branded content เป็น "ส่วนตัว" — เลือกความเป็นส่วนตัวแบบอื่น หรือเอาติ๊กนี้ออก</div>
        </fieldset>
        <label class="v8-tt-check"><input type="checkbox" id="v8TtAigc" checked> คลิปนี้สร้างด้วย AI <span class="v8-muted v8-small">(TikTok จะติดป้าย AI-generated ให้)</span></label>
        <label class="v8-tt-check"><input type="checkbox" id="v8TtMusic"> ฉันยอมรับ
          <a href="https://www.tiktok.com/legal/page/global/music-usage-confirmation/en" target="_blank" rel="noopener">เงื่อนไขการใช้เพลงของ TikTok</a></label>
        <div class="v8-tt-foot">
          <button class="btn btn-ghost" onclick="AASv8.closeTiktok()">ยกเลิก</button>
          <button class="btn btn-primary" id="v8TtSubmit">โพสต์ขึ้น TikTok</button>
        </div>
        <div id="v8TtStatus" class="v8-tt-status"></div>`;
      const sync = () => {
        const clash = $('v8TtBrandContent').checked && $('v8TtPrivacy').value === 'SELF_ONLY';
        $('v8TtBrandWarn').hidden = !clash;
        $('v8TtSubmit').disabled = clash || !$('v8TtMusic').checked;
      };
      ['v8TtBrandContent', 'v8TtPrivacy', 'v8TtMusic'].forEach(id => $(id).addEventListener('change', sync));
      $('v8TtSubmit').addEventListener('click', () => this.submit());
      sync();
    },
    async submit() {
      const btn = $('v8TtSubmit'); btn.disabled = true; btn.textContent = 'กำลังอัปโหลดคลิป…';
      const st = $('v8TtStatus');
      st.innerHTML = stateBox('loading', 'กำลังส่งคลิปไปยัง TikTok…');
      try {
        const r = await api(`/api/connectors/${this.channelId}/tiktok/post`, 'POST', {
          project_id: Number($('v8TtProject').value),
          title: $('v8TtCaption').value,
          privacy_level: $('v8TtPrivacy').value,
          disable_comment: $('v8TtNoComment').checked,
          disable_duet: $('v8TtNoDuet').checked,
          disable_stitch: $('v8TtNoStitch').checked,
          brand_content_toggle: $('v8TtBrandContent').checked,
          brand_organic_toggle: $('v8TtBrandOrganic').checked,
          is_aigc: $('v8TtAigc').checked,
          agreed_music_terms: $('v8TtMusic').checked,
        });
        this.publishId = r.publish_id;
        st.innerHTML = stateBox('loading', r.message);
        this.poll(0);
      } catch (e) {
        st.innerHTML = stateBox('error', e.message, null);
        btn.disabled = false; btn.textContent = 'โพสต์ขึ้น TikTok';
      }
    },
    async poll(n) {
      if (!this.publishId || n > 40) return;
      const st = $('v8TtStatus');
      try {
        const r = await api(`/api/connectors/${this.channelId}/tiktok/status?publish_id=${encodeURIComponent(this.publishId)}`);
        if (!r.done) {
          st.innerHTML = stateBox('loading', r.label);
          this.timer = setTimeout(() => this.poll(n + 1), 3000);
          return;
        }
        if (r.status === 'FAILED') {
          st.innerHTML = stateBox('error', `${r.label}${r.fail_reason ? ' — ' + r.fail_reason : ''}`, null);
          $('v8TtSubmit').disabled = false; $('v8TtSubmit').textContent = 'ลองโพสต์อีกครั้ง';
          return;
        }
        st.innerHTML = `<div class="v8-result ok">✅ ${esc(r.label)}${r.post_url ? ` · <a href="${esc(r.post_url)}" target="_blank" rel="noopener">เปิดดูคลิป</a>` : ''}</div>`;
        toast('✅ ' + r.label, 'success');
        Conn.loadLogs();
      } catch (e) {
        st.innerHTML = stateBox('error', e.message, null);
      }
    },
  };

  // =========================================================== HELP CENTER + CHAT

  // =========================================================== FAQ (replaces live chat)
  const FAQ_Q = {
    quickstart: 'เริ่มใช้งานครั้งแรกต้องทำอะไรบ้าง?',
    navigation: 'แต่ละเมนูใน Sidebar ใช้ทำอะไร?',
    studio: 'สร้างคลิป TikTok แบบ UGC ได้อย่างไร?',
    autopost: 'ตั้งเวลา Auto-Post ไป Facebook / Instagram / LINE ได้อย่างไร?',
    'shopee-credentials': 'จะขอ Shopee Affiliate AppID / Secret ได้จากที่ไหน?',
    'shopee-add-product': 'เพิ่มสินค้าจาก Shopee พร้อมรูป ราคา และค่าคอมได้อย่างไร?',
    'import-file': 'นำเข้าสินค้าทีละหลายรายการจากไฟล์ CSV / Excel ได้อย่างไร?',
    radar: 'Product Radar ใช้ค้นหาสินค้าอย่างไร?',
    scripts: 'บทรีวิวแบบเดิม (AI Video Factory) ต่างจากบท UGC ใหม่อย่างไร?',
    video: 'คลิป AI ใช้เครดิตเท่าไร และดูสถานะงานได้ที่ไหน?',
    'connect-facebook': 'เชื่อม Facebook Page ได้อย่างไร?',
    'connect-instagram': 'เชื่อม Instagram ได้อย่างไร?',
    'connect-line': 'เชื่อม LINE Official Account ได้อย่างไร?',
    'admin-meta-app': '(ผู้ดูแลระบบ) ตั้งค่า Meta App ให้ปุ่ม Connect ใช้ได้อย่างไร?',
    'publish-now': 'โพสต์สินค้าไปเพจ / IG / LINE ทันทีได้อย่างไร?',
    calendar: 'ปฏิทินคอนเทนต์และคิวโพสต์ TikTok / Shopee ใช้อย่างไร?',
    tracking: 'บันทึกยอดขายและวัดผลรายคลิปได้อย่างไร?',
    security: 'ข้อมูลบัญชี คีย์ และ Token ปลอดภัยแค่ไหน?',
    credits: 'เครดิตคืออะไร และมีค่าใช้จ่ายไหม?',
    'faq-fb-no-pages': 'เชื่อม Facebook แล้วไม่เจอเพจ หรือขึ้น error ต้องทำอย่างไร?',
    'faq-line': 'LINE OA ส่งข้อความไม่ได้ / ไม่มี User ID ให้ทดสอบ ต้องทำอย่างไร?',
    'faq-shopee': 'ดึงสินค้า Shopee ไม่ได้ หรือไม่มีค่าคอม ต้องทำอย่างไร?',
  };
  const FAQ_EXTRA = [
    { id: 'mvp-menu', category: 'start', title: 'เมนูแต่ละอันใช้ทำอะไร?',
      summary: 'Phase 1 (MVP) มีเฉพาะเมนูที่จำเป็นสำหรับเส้นทางหลัก: สินค้า → คลิป → โพสต์',
      steps: ['สร้างคอนเทนต์ — เลือกสินค้า เลือกสไตล์ UGC สร้างบท ทำคลิปพรีวิว แล้วบันทึกหรือตั้งเวลาโพสต์ (เริ่มที่นี่)',
              'ภาพรวม — สรุปจำนวนสินค้า บท และคิวโพสต์ของคุณ',
              'สินค้าของฉัน — ดึงสินค้าจาก Shopee พร้อมรูป ราคา ค่าคอม หรือเพิ่มสินค้าเอง',
              'เชื่อมต่อช่องทาง — เชื่อม Facebook Page / Instagram / LINE OA สำหรับโพสต์อัตโนมัติ',
              'คิวโพสต์และตารางงาน — ดูคลิปที่รอโพสต์ TikTok (โพสต์เอง) และสถานะงาน',
              'ติดตามยอดขายและสถิติ — บันทึกยอดขายรายคลิปเพื่อวัดผล',
              'เสนอไอเดีย / แจ้งปัญหา — ส่งความเห็นหรือแจ้งบั๊กถึงทีมงาน'],
      tips: ['ฟีเจอร์อื่น (เรดาร์สินค้า, ปฏิทิน, ชุมชน) พักไว้ก่อนใน Phase 1 เพื่อให้เส้นทางหลักใช้ได้จริงและเรียบง่าย'], keywords: ['เมนู', 'sidebar', 'ใช้ทำอะไร'], goto: 'studio' },
    { id: 'beta-status', category: 'beta', title: 'ระบบนี้ใช้งานจริงได้แล้วหรือยัง?',
      summary: 'ตอนนี้เป็นระบบทดสอบ (Beta) อยู่ระหว่างการพัฒนา ยังใช้งานจริงไม่ได้ทั้งหมด',
      steps: ['Phase 1 ใช้ได้ทันที: สร้างบท UGC 6 สไตล์, คลิปพรีวิว 9:16 (ดาวน์โหลดได้), สินค้าตัวอย่าง/เพิ่มสินค้าเอง และหน้า FAQ นี้',
              'ใช้ได้เมื่อตั้งค่าแล้ว: ดึงสินค้าจาก Shopee (ต้องใส่ AppID/Secret ของคุณ), เชื่อม Facebook / Instagram / LINE OA และ Auto-Post (ต้องให้ผู้ดูแลตั้งค่า Meta App), คลิป AI จริง (ต้องเปิดเอนจิน AI)',
              'ยังไม่รองรับ: โพสต์ TikTok / Shopee Video อัตโนมัติ — ดาวน์โหลดคลิปไปโพสต์เองก่อน'],
      tips: ['ข้อมูลในช่วงทดสอบอาจถูกรีเซ็ต — อย่าเก็บงานสำคัญไว้ที่นี่ที่เดียว'], keywords: ['beta', 'ทดสอบ', 'phase 1', 'ใช้ได้'], goto: 'studio' },
    { id: 'beta-free', category: 'beta', title: 'ใช้ฟรีไหม?',
      summary: 'ช่วง Beta ใช้ฟรีด้วยรหัสเชิญ (จำกัด 100 ที่นั่ง)',
      steps: ['สร้างบทและคลิปพรีวิวไม่ใช้เครดิต', 'คลิป AI จริงใช้เครดิต และคืนเครดิตอัตโนมัติถ้างานล้มเหลว', 'ยังไม่มีระบบเติมเงินในช่วงนี้'],
      tips: [], keywords: ['ฟรี', 'ราคา', 'เครดิต', 'invite', 'รหัสเชิญ'], goto: 'studio' },
    { id: 'beta-data', category: 'beta', title: 'ข้อมูลที่ใส่ในระบบจะหายไหม?',
      summary: 'ในช่วงทดสอบ ข้อมูลอาจถูกรีเซ็ตเมื่อมีการอัปเดตใหญ่',
      steps: ['ดาวน์โหลดคลิปที่ต้องการเก็บไว้ในเครื่อง', 'อย่าใส่รหัสผ่านของแพลตฟอร์มอื่นในช่องข้อความใด ๆ', 'Token และ Secret ที่เชื่อมต่อจะถูกเข้ารหัสก่อนบันทึก'],
      tips: [], keywords: ['ข้อมูล', 'หาย', 'รีเซ็ต', 'privacy'], goto: '' },
    { id: 'beta-feedback', category: 'beta', title: 'เจอบั๊กหรืออยากได้ฟีเจอร์ แจ้งได้ที่ไหน?',
      summary: 'แจ้งผ่านเมนู "เสนอไอเดีย / แจ้งปัญหา" ใน Sidebar',
      steps: ['เปิดเมนู เสนอไอเดีย / แจ้งปัญหา', 'เลือกประเภท "แจ้งบั๊ก / ปัญหา" หรือ "เสนอฟีเจอร์"', 'อธิบายขั้นตอนที่ทำ ผลที่เกิด และผลที่คาดหวัง แล้วกดส่ง'],
      tips: ['แนบหน้าที่เกิดปัญหาและเวลาโดยประมาณ จะช่วยให้แก้ได้เร็วขึ้น'], keywords: ['บั๊ก', 'bug', 'ติดต่อ', 'feedback', 'ทีมงาน'], goto: 'ideas' },
  ];
  const Help = {
    data: null, cat: 'all', loaded: false,
    async load() {
      if (!this.loaded) {
        const box = $('v8HelpArticles');
        box.innerHTML = stateBox('loading', 'กำลังโหลดคู่มือ…');
        try {
          const d = await api('/api/help/articles');
          const HIDE = new Set(['support-chat', 'radar', 'scripts', 'calendar', 'navigation']);
          const arts = d.articles.filter(a => !HIDE.has(a.id)).map(a => ({ ...a, title: FAQ_Q[a.id] || a.title,
            goto: a.goto && AAS.isHiddenTab?.(a.goto) ? 'studio' : a.goto }));
          this.data = { categories: [{ id: 'beta', label: 'ระบบ Beta & ทั่วไป', icon: '🧪' }, ...d.categories.map(c => c.id === 'faq' ? { ...c, label: 'แก้ปัญหา' } : c)], articles: [...FAQ_EXTRA, ...arts] };
          this.loaded = true;
        }
        catch (e) { box.innerHTML = stateBox('error', 'โหลดคู่มือไม่สำเร็จ: ' + e.message, null) + '<button class="btn btn-secondary btn-sm" onclick="AASv8.loadHelp()">ลองใหม่</button>'; return; }
        $('v8HelpCats').innerHTML = [{ id: 'all', label: 'ทั้งหมด', icon: '📚' }, ...this.data.categories].map(c =>
          `<button class="v8-chip ${c.id === 'all' ? 'is-on' : ''}" role="tab" aria-selected="${c.id === 'all'}" data-cat="${c.id}">${c.icon} ${esc(c.label)}</button>`).join('');
        $('v8HelpCats').querySelectorAll('[data-cat]').forEach(b => b.addEventListener('click', () => {
          this.cat = b.dataset.cat;
          $('v8HelpCats').querySelectorAll('[data-cat]').forEach(x => { x.classList.toggle('is-on', x === b); x.setAttribute('aria-selected', String(x === b)); });
          this.render();
        }));
      }
      this.render();
    },
    render() {
      const q = ($('v8HelpSearch').value || '').trim().toLowerCase();
      const list = this.data.articles.filter(a => (this.cat === 'all' || a.category === this.cat) &&
        (!q || (a.title + ' ' + a.summary + ' ' + a.steps.join(' ') + ' ' + a.tips.join(' ') + ' ' + a.keywords.join(' ')).toLowerCase().includes(q)));
      const tabNames = { dash: 'ภาพรวม', products: 'สินค้าของฉัน', radar: 'เรดาร์สินค้ามาแรง', drafts: 'โรงงานบทรีวิว', video: 'สร้างคลิปวิดีโอ', connectors: 'เชื่อมต่อช่องทาง', calendar: 'ปฏิทินคอนเทนต์', tracking: 'ติดตามยอดขายและสถิติ', keys: 'คีย์และการตั้งค่า', help: 'ช่วยเหลือ', studio: 'สร้างคอนเทนต์', ideas: 'เสนอไอเดีย / แจ้งปัญหา' };
      $('v8HelpArticles').innerHTML = list.length ? list.map(a => `
        <details class="v8-article" id="help-${a.id}">
          <summary><span>❓ ${esc(a.title)}</span><small>${esc(a.summary)}</small></summary>
          <ol>${a.steps.map(s => `<li>${linkify(esc(s))}</li>`).join('')}</ol>
          ${a.tips.length ? `<div class="v8-tips">${a.tips.map(t => `<div>💡 ${linkify(esc(t))}</div>`).join('')}</div>` : ''}
          <div class="v8-article-actions">
            ${a.goto && a.goto !== 'help' ? `<button class="btn btn-primary btn-sm" data-tab-go="${a.goto}">ไปที่หน้า ${esc(tabNames[a.goto] || a.goto)} →</button>` : ''}
          </div>
        </details>`).join('') : stateBox('empty', 'ไม่พบคำถามที่ตรงกับคำค้น — ลองคำอื่น หรือแจ้งเราที่เมนู "เสนอไอเดีย / แจ้งปัญหา"', null);
      bindTabGo($('v8HelpArticles'));
    },
    openArticle(id) {
      AAS.switchTab('help');
      const go = () => {
        const el = $('help-' + id);
        if (!el) return;
        el.open = true; el.scrollIntoView({ behavior: 'smooth', block: 'start' });
        el.classList.add('v8-flash'); setTimeout(() => el.classList.remove('v8-flash'), 1600);
      };
      if (this.loaded) setTimeout(go, 50); else this.load().then(() => setTimeout(go, 50));
    },
  };
  function linkify(s) { return s.replace(/https:\/\/[^\s<]+/g, u => `<a href="${u}" target="_blank" rel="noopener noreferrer">${u}</a>`); }

  const Chat = {
    ws: null, started: false, lastId: 0, threadId: null, admin: false, viewThread: null, pollTimer: null, retry: 0, seen: new Set(),
    start() {
      if (this.started) { this.markRead(); return; }
      const me = AAS.getMe() || {};
      if (!me.id) {
        loginBox($('v8ChatBody')); $('v8ChatForm').hidden = true;
        this.status('กรุณาเข้าสู่ระบบเพื่อใช้แชท', false);
        return;
      }
      this.started = true;
      $('v8ChatForm').hidden = false;
      this.admin = me.role === 'admin';
      $('v8ChatAdminActions').hidden = !this.admin;
      if (this.admin) { $('v8ChatTitle').textContent = 'กล่องข้อความซัพพอร์ต (Admin)'; this.showThreads(); }
      else this.loadThread();
      this.connect();
    },
    status(text, on) { $('v8ChatStatus').textContent = text; $('v8ChatDot').classList.toggle('is-on', !!on); },
    connect() {
      try {
        const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const ws = new WebSocket(`${proto}//${location.host}/ws/support`);
        this.ws = ws;
        ws.onopen = () => { this.retry = 0; this.status('เชื่อมต่อแบบ Real-time', true); clearInterval(this.pollTimer); this.pollTimer = null; };
        ws.onmessage = ev => this.onEvent(JSON.parse(ev.data));
        ws.onclose = ev => {
          this.ws = null;
          if (ev.code === 4401) { this.status('กรุณาเข้าสู่ระบบเพื่อใช้แชท', false); clearInterval(this.pollTimer); this.pollTimer = null; return; }
          if (!this.started) return;
          this.fallback();
          const wait = Math.min(30000, 2000 * 2 ** this.retry++);
          setTimeout(() => this.connect(), wait);
        };
      } catch { this.fallback(); }
    },
    fallback() {
      this.status('โหมดสำรอง (อัปเดตทุก 4 วินาที)', false);
      if (!this.pollTimer) this.pollTimer = setInterval(() => this.poll(), 4000);
    },
    onEvent(ev) {
      if (ev.type === 'presence') {
        if (!this.admin) $('v8ChatTitle').textContent = ev.admins_online ? 'แชทกับทีมงาน · 🟢 แอดมินออนไลน์' : 'แชทกับทีมงาน · ผู้ช่วยอัตโนมัติตอบก่อน';
      } else if (ev.type === 'message') {
        if (this.admin && this.viewThread !== ev.thread_id) {
          // Never pull the admin out of an open conversation; just refresh the list if it's the current view.
          if (!this.viewThread) this.showThreads(); else toast('💬 มีข้อความใหม่จากสมาชิกคนอื่น (กด ← รายการ เพื่อดู)');
          Unread.bump(); return;
        }
        if (this.admin && ev.message.sender_role === 'user' && this._threadStatus === 'resolved') {
          this._threadStatus = 'open'; $('v8ChatResolve').textContent = '✓ ปิดเคส';
        }
        if (!this.admin) this.threadId = ev.thread_id;
        this.append(ev.message);
        $('v8Typing').hidden = true;
        if (document.querySelector('#help.active')) this.markRead(); else Unread.bump();
      } else if (ev.type === 'typing') {
        if ((this.admin && ev.thread_id === this.viewThread) || (!this.admin && ev.from === 'admin')) {
          $('v8Typing').hidden = false; clearTimeout(this._tt); this._tt = setTimeout(() => { $('v8Typing').hidden = true; }, 3000);
        }
      } else if (ev.type === 'thread') {
        toast(ev.status === 'resolved' ? 'เคสนี้ถูกปิดแล้ว ส่งข้อความใหม่เพื่อเปิดอีกครั้ง' : 'เปิดเคสอีกครั้ง');
      } else if (ev.type === 'error') {
        toast(ev.detail, 'error');
        if (this._pending && !$('v8ChatInput').value) $('v8ChatInput').value = this._pending;
      }
    },
    bubble(m) {
      const mine = this.admin ? m.sender_role === 'admin' : m.sender_role === 'user';
      const who = m.sender_role === 'bot' ? '🤖 ผู้ช่วยอัตโนมัติ' : m.sender_role === 'admin' ? '🛟 ทีมงาน' + (m.sender_name ? ' (' + esc(m.sender_name) + ')' : '') : esc(m.sender_name || 'คุณ');
      return `<div class="v8-msg ${mine ? 'is-mine' : ''} is-${m.sender_role}" data-id="${m.id}"><div class="v8-msg-who">${who} · ${esc(localTime(m.created_at).split(' ').pop())}</div><div class="v8-msg-body">${esc(m.body).replace(/\n/g, '<br>')}</div></div>`;
    },
    append(m) {
      if (this.seen.has(m.id)) return;
      this.seen.add(m.id);
      const body = $('v8ChatBody');
      body.querySelector('.v8-chat-empty')?.remove();
      body.insertAdjacentHTML('beforeend', this.bubble(m));
      this.lastId = Math.max(this.lastId, m.id);
      body.scrollTop = body.scrollHeight;
    },
    resetBody(msgs, emptyText) {
      this.seen = new Set(); this.lastId = 0;
      $('v8ChatBody').innerHTML = msgs.length ? '' : `<div class="v8-chat-empty">${emptyText}</div>`;
      msgs.forEach(m => this.append(m));
    },
    async loadThread() {
      $('v8ChatBody').innerHTML = stateBox('loading', 'กำลังโหลดแชท…');
      try {
        const r = await api('/api/support/thread');
        this.threadId = r.thread && r.thread.id;
        this.resetBody(r.messages, '👋 สวัสดีครับ พิมพ์คำถามได้เลย ผู้ช่วยอัตโนมัติจะแนะนำคู่มือทันที และทีมงานจะตอบในแชทนี้');
        this.markRead();
      } catch (e) {
        if (isAuthError(e)) { loginBox($('v8ChatBody')); $('v8ChatForm').hidden = true; return; }
        $('v8ChatBody').innerHTML = stateBox('error', e.message, null);
      }
    },
    async showThreads() {
      this.viewThread = null;
      $('v8ThreadList').hidden = false; $('v8ChatBody').hidden = true; $('v8ChatForm').hidden = true;
      $('v8ChatBack').hidden = true; $('v8ChatResolve').hidden = true;
      try {
        const r = await api('/api/support/threads');
        $('v8ThreadList').innerHTML = r.threads.length ? r.threads.map(t => `
          <button class="v8-thread ${t.unread_admin ? 'is-unread' : ''}" onclick="AASv8.openThread(${t.id})">
            <div><strong>${esc(t.username)}</strong> <span class="chip v8-chip-wait">${t.status === 'open' ? 'เปิด' : 'ปิดแล้ว'}</span>${t.unread_admin ? ` <span class="v8-pill">${t.unread_admin}</span>` : ''}</div>
            <div class="v8-small v8-muted">${esc((t.last_role === 'bot' ? '🤖 ' : '') + (t.last_body || '').slice(0, 80))}</div>
            <div class="v8-small v8-muted">${esc(localTime(t.last_message_at))}</div></button>`).join('')
          : '<div class="v8-chat-empty">ยังไม่มีข้อความจากสมาชิก</div>';
      } catch (e) { $('v8ThreadList').innerHTML = stateBox('error', e.message, null); }
    },
    async openThread(id) {
      this.viewThread = id;
      $('v8ThreadList').hidden = true; $('v8ChatBody').hidden = false; $('v8ChatForm').hidden = false;
      $('v8ChatBack').hidden = false; $('v8ChatResolve').hidden = false;
      try {
        const r = await api(`/api/support/thread?thread_id=${id}`);
        $('v8ChatTitle').textContent = 'คุยกับสมาชิก #' + id;
        this.resetBody(r.messages, 'ยังไม่มีข้อความ');
        this._threadStatus = r.thread.status;
        $('v8ChatResolve').textContent = r.thread.status === 'open' ? '✓ ปิดเคส' : '↺ เปิดเคสอีกครั้ง';
        this.markRead();
      } catch (e) { $('v8ChatBody').innerHTML = stateBox('error', e.message, null); }
    },
    async poll() {
      if (!this.started) return;
      try {
        if (this.admin && !this.viewThread) return this.showThreads();
        const tid = this.admin ? this.viewThread : null;
        const r = await api(`/api/support/thread?after=${this.lastId}${tid ? '&thread_id=' + tid : ''}`);
        if (r.thread) this.threadId = r.thread.id;
        r.messages.forEach(m => this.append(m));
        if (r.messages.length && !document.querySelector('#help.active')) Unread.refresh();
      } catch (e) { if (isAuthError(e)) { this.stop(); loginBox($('v8ChatBody')); $('v8ChatForm').hidden = true; } }
    },
    stop() {
      this.started = false; clearInterval(this.pollTimer); this.pollTimer = null;
      if (this.ws) { try { this.ws.close(); } catch {} this.ws = null; }
    },
    async send(text) {
      text = text.trim();
      if (!text) return;
      const tid = this.admin ? this.viewThread : null;
      if (this.admin && !tid) return toast('เลือกห้องแชทก่อน', 'error');
      $('v8ChatInput').value = '';
      this._pending = text; clearTimeout(this._pt); this._pt = setTimeout(() => { this._pending = null; }, 3000);
      if (this.ws && this.ws.readyState === 1) {
        this.ws.send(JSON.stringify({ type: 'send', body: text, thread_id: tid }));
      } else {
        try {
          const r = await api('/api/support/messages', 'POST', { body: text, thread_id: tid || undefined });
          r.messages.forEach(m => this.append(m));
        } catch (e) { toast(e.message, 'error'); $('v8ChatInput').value = text; }
      }
    },
    async markRead() {
      const tid = this.admin ? this.viewThread : this.threadId;
      if (!tid) return Unread.refresh();
      try { await api(`/api/support/threads/${tid}/read`, 'POST'); } catch {}
      Unread.refresh();
    },
    bind() {
      $('v8ChatForm')?.addEventListener('submit', e => { e.preventDefault(); this.send($('v8ChatInput').value); });
      $('v8ChatInput')?.addEventListener('keydown', e => {
        if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); this.send(e.target.value); }
        else if (this.ws && this.ws.readyState === 1 && !this._typingSent) {
          this._typingSent = true; setTimeout(() => { this._typingSent = false; }, 2000);
          this.ws.send(JSON.stringify({ type: 'typing', thread_id: this.admin ? this.viewThread : null }));
        }
      });
      $('v8ChatBack')?.addEventListener('click', () => this.showThreads());
      $('v8ChatResolve')?.addEventListener('click', async () => {
        if (!this.viewThread) return;
        const next = this._threadStatus === 'open' ? 'resolved' : 'open';
        try { await api(`/api/support/threads/${this.viewThread}`, 'PATCH', { status: next }); toast(next === 'resolved' ? 'ปิดเคสแล้ว' : 'เปิดเคสแล้ว', 'success'); this.openThread(this.viewThread); }
        catch (e) { toast(e.message, 'error'); }
      });
      $('v8ChatFab')?.addEventListener('click', () => { AAS.switchTab('help'); setTimeout(() => $('v8ChatInput')?.focus(), 200); });
    },
  };

  const Unread = {
    n: 0,
    paint() {
      const b = $('badge-help-unread'), f = $('v8FabBadge');
      if (b) { b.textContent = this.n ? String(this.n) : 'LIVE'; b.classList.toggle('has-unread', !!this.n); }
      if (f) { f.hidden = !this.n; f.textContent = this.n; }
      const nb = $('v8NotifBadge'); if (nb) { nb.hidden = !this.n; nb.textContent = this.n; }
    },
    bump() { if (!document.querySelector('#help.active')) { this.n += 1; this.paint(); } },
    async refresh() { /* live chat removed — help is FAQ only */ },
  };

  // =========================================================== STUDIO (Phase 1 guided flow)
  const STEP_LABELS = {
    script_ready: [2, 'บทพร้อม — ต่อไปสร้างคลิปตัวอย่าง'],
    preview_ready: [4, 'คลิปพรีวิวพร้อม — บันทึก/ดาวน์โหลดได้'],
    clip_running: [3, 'กำลังสร้างคลิป AI…'],
    clip_ready: [4, 'คลิป AI พร้อม'],
    clip_failed: [3, 'คลิป AI ล้มเหลว (คืนเครดิตแล้ว)'],
    saved: [4, 'บันทึกแล้ว'],
    queued_tiktok: [4, 'อยู่ในคิว TikTok'],
  };
  const Studio = {
    boot: null, productId: null, tpl: '', avatarId: null, style: 'ugc_pov', project: null, img: null, playing: false, raf: 0, pollT: 0,
    async load(keepProject) {
      const grid = $('v8StudioProducts');
      if (!grid) return;
      if (!this.boot) grid.innerHTML = stateBox('loading', 'กำลังเตรียมสตูดิโอ…');
      try {
        this.boot = await api('/api/studio/bootstrap');
      } catch (e) {
        if (isAuthError(e)) return loginBox(grid);
        grid.innerHTML = stateBox('error', 'โหลดสตูดิโอไม่สำเร็จ: ' + e.message, null) + '<button class="btn btn-secondary btn-sm" onclick="AASv8.loadStudio()">ลองใหม่</button>';
        return;
      }
      setCredits(this.boot.credits);
      this.renderEngine(); this.renderProducts(); this.renderStyles(); this.renderProjects(); this.renderPlatforms();
      AutoPost.render(); AutoPost.load();
      if (this.pendingProduct) { const id = this.pendingProduct; this.pendingProduct = null; this.selectProduct(id, true); return; }
      if (keepProject && this.project) return this.openProject(this.project.id);
      if (!this.project && this.boot.projects.length) this.openProject(this.boot.projects[0].id);
      else this.paintSteps();
    },
    renderEngine() {
      const e = this.boot.engine;
      const w = this.boot.writer || {};
      // One key covers both halves of the job — writing the script and rendering the
      // clip — so the recommendation sits here, where the person is about to generate.
      const needKey = w.mode !== 'gemini';
      $('v8Engine').innerHTML = `<div><strong>🎬 เอนจินวิดีโอ (Phase 1):</strong> ${esc(e.label)}</div>
        <div class="v8-small v8-muted">${esc(e.note)}</div>
        <div class="v8-engine-cost">ต้นทุนคลิป AI: <strong>${e.cost_credits} เครดิต</strong> · คงเหลือ <strong id="v8CreditsLeft">${this.boot.credits}</strong> เครดิต · คลิปพรีวิว UGC: <strong>ฟรี</strong></div>
        <div class="v8-writer ${needKey ? 'is-tip' : 'is-on'}">
          <div><strong>✍️ คนเขียนบท:</strong> ${esc(w.label || '')}</div>
          ${needKey ? `<div class="v8-small">เชื่อมคีย์ Gemini ของคุณแล้วจะได้: บทที่เขียนใหม่ทุกครั้งแบบไม่ซ้ำ (ไม่ใช่สลับสำนวนจากชุดเดิม) ·
            เลือกมุมเล่าให้เหมาะกับสินค้าแต่ละชิ้น · และสร้างคลิปจริงได้โดย<strong>ไม่หักเครดิตระบบ</strong></div>
            <div class="v8-writer-act">
              <button class="btn btn-primary btn-sm" onclick="AASv8.goKeys()">เชื่อมคีย์ Gemini</button>
              <span class="v8-small v8-muted">ขอคีย์ฟรีที่ <a href="https://aistudio.google.com/apikey" target="_blank" rel="noopener">Google AI Studio</a> · ใช้ได้ทันที</span>
            </div>` : ''}
        </div>`;
    },
    renderProducts() {
      const ps = this.boot.products;
      $('v8StudioProducts').innerHTML = ps.length ? ps.map(p => `
        <button class="v8-sprod ${p.id === this.productId ? 'is-on' : ''}" data-pid="${p.id}" aria-pressed="${p.id === this.productId}">
          ${imgTag(p.image, p.title, 'v8-sprod-img')}
          <span class="v8-sprod-title">${esc(p.title)}</span>
          <span class="v8-small">${baht(p.price)}${p.commission_rate != null ? ' · คอม ' + pct(p.commission_rate) : ''}</span>
          ${sourceChip(p)}
        </button>`).join('') : stateBox('empty', 'ยังไม่มีสินค้า — พิมพ์ชื่อสินค้าด้านบน หรือดึงจาก Shopee', null);
      $('v8StudioProducts').querySelectorAll('[data-pid]').forEach(b => b.addEventListener('click', () => this.selectProduct(Number(b.dataset.pid), true)));
    },
    renderStyles() {
      $('v8Styles').innerHTML = this.boot.styles.map(s => `
        <button class="v8-style ${s.id === this.style ? 'is-on' : ''}" role="radio" aria-checked="${s.id === this.style}" data-style="${s.id}">
          <span class="v8-style-emoji">${s.emoji}</span><strong>${esc(s.label)}</strong><small>${esc(s.desc)}</small></button>`).join('');
      $('v8Styles').querySelectorAll('[data-style]').forEach(b => b.addEventListener('click', () => {
        this.style = b.dataset.style; this.renderStyles();
        if (this.project && this.project.product_id === this.productId && this.project.style !== this.style) {
          $('v8MakeScript').textContent = '✨ สร้างบทใหม่ด้วยสไตล์นี้';
        }
      }));
    },
    selectProduct(id, scroll) {
      this.productId = id;
      const p = (this.boot.products || []).find(x => x.id === id);
      if (!p) { this.pendingProduct = id; return this.load(); }
      this.renderProducts();
      $('v8SelectedProductChip').textContent = '📦 ' + p.title.slice(0, 40);
      $('v8MakeScript').disabled = false;
      $('v8MakeScript').textContent = '✨ สร้างบทอัตโนมัติ';
      if (this.project && this.project.product_id !== id) { this.project = null; $('v8ScriptEditor').hidden = true; this.resetPreview(); }
      this.paintSteps();
      if (scroll) $('v8Step2').scrollIntoView({ behavior: 'smooth', block: 'start' });
    },
    async makeScript() {
      if (!this.productId) return toast('เลือกสินค้าก่อน', 'error');
      const btn = $('v8MakeScript'); btn.disabled = true; btn.textContent = 'กำลังเขียนบท…';
      try {
        const p = this.project;
        const reuse = p && p.product_id === this.productId && !p.preview_url && !p.clip_url && p.status === 'script_ready';
        if (reuse && this.dirty && !confirm('เปลี่ยนสไตล์จะเขียนบทใหม่แทนบทที่แก้ไว้ ยืนยัน?')) return;
        const r = reuse
          ? await api(`/api/studio/projects/${p.id}`, 'PATCH', { style: this.style, regenerate: true })
          : await api('/api/studio/projects', 'POST', { product_id: this.productId, style: this.style });
        if (reuse) r.message = 'เปลี่ยนสไตล์และเขียนบทใหม่แล้ว (ใช้โปรเจกต์เดิม)';
        toast('✅ ' + r.message, 'success');
        if (r.notice) toast('⚠ ' + r.notice, 'info');
        this.project = r.project;
        await this.load(true);
        $('v8ScriptEditor').scrollIntoView({ behavior: 'smooth', block: 'start' });
      } catch (e) { toast(e.message, 'error'); }
      finally { btn.disabled = false; btn.textContent = '✨ สร้างบทอัตโนมัติ'; }
    },
    async openProject(id) {
      try {
        const r = await api(`/api/studio/projects/${id}`);
        this.project = r.project; setCredits(r.credits);
        if ($('v8CreditsLeft')) $('v8CreditsLeft').textContent = r.credits;
      } catch (e) { return toast(e.message, 'error'); }
      const p = this.project;
      this.productId = p.product_id; this.style = p.style;
      this.renderProducts(); this.renderStyles();
      $('v8SelectedProductChip').textContent = '📦 ' + (p.product.title || '').slice(0, 40);
      $('v8MakeScript').disabled = false;
      this.renderScript();
      await this.loadImage(p.product.image);
      this.drawFrame(0.4);
      if (p.clip_url) this.showVideo(p.clip_url); else if (p.preview_url) this.showVideo(p.preview_url); else this.resetPreview();
      this.renderClips(); this.renderAi(); this.renderGemini(); this.renderPlatforms(); this.paintSteps(); this.renderProjects(); AutoPost.render();
      if (p.status === 'clip_running') this.schedulePoll();
    },
    renderScript() {
      const p = this.project;
      $('v8ScriptEditor').hidden = false;
      $('v8ScriptRows').innerHTML = p.script.scenes.map((s, i) => `<tr data-i="${i}">
        <td class="mono v8-small"><input class="form-input v8-cell" data-k="t" value="${esc(s.t)}" aria-label="เวลา ฉาก ${i + 1}"></td>
        <td><textarea class="form-input v8-cell" data-k="visual" rows="2" aria-label="ภาพ ฉาก ${i + 1}">${esc(s.visual)}</textarea></td>
        <td><textarea class="form-input v8-cell" data-k="text" rows="2" aria-label="ข้อความบนจอ ฉาก ${i + 1}">${esc(s.text)}</textarea></td>
        <td><textarea class="form-input v8-cell" data-k="voice" rows="2" aria-label="เสียงพากย์ ฉาก ${i + 1}">${esc(s.voice)}</textarea></td></tr>`).join('');
      $('v8Caption').value = p.caption;
      $('v8ScriptRows').querySelectorAll('.v8-cell').forEach(el => el.addEventListener('input', () => { this.dirty = true; this.readScript(); this.drawFrame(this._lastT || 0.4); }));
      $('v8Caption').oninput = () => { this.dirty = true; };
      this.dirty = false;
      this.lockEditor();
    },
    lockEditor() {
      const busy = !!(this.project && this.project.status === 'clip_running');
      document.querySelectorAll('#v8ScriptEditor .v8-cell, #v8Caption').forEach(el => { el.readOnly = busy; });
      ['v8SaveScript', 'v8Regenerate'].forEach(id => { if ($(id)) $(id).disabled = busy; });
    },
    readScript() {
      const scenes = [...$('v8ScriptRows').querySelectorAll('tr')].map(tr => {
        const o = {}; tr.querySelectorAll('.v8-cell').forEach(c => { o[c.dataset.k] = c.value; }); return o;
      });
      this.project.script.scenes = scenes;
      return { ...this.project.script, scenes };
    },
    async saveScript(quiet) {
      if (!this.project) return;
      if (this.project.status === 'clip_running') { toast('กำลังสร้างคลิป AI อยู่ — แก้บทได้หลังงานเสร็จ', 'error'); throw Error('busy'); }
      try {
        const r = await api(`/api/studio/projects/${this.project.id}`, 'PATCH', { script: this.readScript(), caption: $('v8Caption').value });
        this.project = r.project; this.dirty = false;
        if (!quiet) toast('💾 ' + r.message, 'success');
        this.resetPreview(); this.renderClips(); this.paintSteps(); this.renderProjects();
      } catch (e) { toast(e.message, 'error'); throw e; }
    },
    async regenerate() {
      if (!this.project) return;
      if (this.dirty && !confirm('บทที่แก้ไว้จะถูกแทนที่ด้วยบทใหม่ ยืนยัน?')) return;
      try {
        const r = await api(`/api/studio/projects/${this.project.id}`, 'PATCH', { regenerate: true, style: this.style });
        this.project = r.project; this.renderScript(); this.resetPreview(); this.drawFrame(0.4); this.renderClips(); this.paintSteps();
        toast((this.boot.writer || {}).mode === 'gemini' ? '✍️ Gemini เขียนบทใหม่ให้แล้ว' : '🎲 สุ่มบทใหม่แล้ว', 'success');
        if (r.notice) toast('⚠ ' + r.notice, 'info');
      } catch (e) { toast(e.message, 'error'); }
    },

    // ---------- canvas renderer
    async loadImage(src) {
      this.img = null;
      if (!src) return;
      let url = src;
      if (/^https?:\/\//.test(src) && !src.startsWith(location.origin)) url = '/api/studio/image?url=' + encodeURIComponent(src);
      await new Promise(res => {
        const im = new Image();
        im.onload = () => { this.img = im; res(); };
        im.onerror = () => { this.img = null; res(); };
        im.src = url;
      });
    },
    timeline() {
      const sc = this.project ? this.project.script.scenes : [];
      const d = sc.map((_, i) => (i === 0 ? 2 : i === sc.length - 1 ? 2 : 3));
      const total = d.reduce((a, b) => a + b, 0) || 1;
      return { sc, d, total };
    },
    drawFrame(t) {
      this._lastT = t;
      const cv = $('v8Canvas'); if (!cv || !this.project) return;
      const ctx = cv.getContext('2d'), W = cv.width, H = cv.height;
      const { sc, d, total } = this.timeline();
      let acc = 0, idx = 0;
      for (let i = 0; i < d.length; i++) { if (t < acc + d[i]) { idx = i; break; } acc += d[i]; idx = i; }
      const local = Math.min(1, Math.max(0, (t - acc) / d[idx]));
      const s = sc[idx] || { text: '' };
      const palettes = { ugc_pov: ['#0F172A', '#1E3A8A'], ugc_unboxing: ['#3B0764', '#9D174D'], ugc_problem: ['#7C2D12', '#B45309'],
        ugc_before_after: ['#064E3B', '#0E7490'], ugc_3reasons: ['#1E1B4B', '#4338CA'], ugc_budget: ['#7F1D1D', '#EA580C'] };
      const [c1, c2] = palettes[this.project.style] || palettes.ugc_pov;
      const g = ctx.createLinearGradient(0, 0, W, H); g.addColorStop(0, c1); g.addColorStop(1, c2);
      ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
      // product image with gentle Ken Burns zoom
      const zoom = 1 + 0.08 * (t / total);
      const box = { x: 40, y: 150, w: W - 80, h: H * 0.5 };
      ctx.save();
      roundRect(ctx, box.x, box.y, box.w, box.h, 28); ctx.clip();
      ctx.fillStyle = '#F8FAFC'; ctx.fillRect(box.x, box.y, box.w, box.h);
      if (this.img) {
        const r = Math.max(box.w / this.img.width, box.h / this.img.height) * zoom;
        const iw = this.img.width * r, ih = this.img.height * r;
        ctx.drawImage(this.img, box.x + (box.w - iw) / 2, box.y + (box.h - ih) / 2, iw, ih);
      } else {
        ctx.fillStyle = '#CBD5E1'; ctx.font = '120px sans-serif'; ctx.textAlign = 'center'; ctx.fillText('🛍️', W / 2, box.y + box.h / 2 + 40);
      }
      ctx.restore();
      // story progress bars
      let x = 24; const bw = (W - 48 - (d.length - 1) * 6) / d.length;
      d.forEach((_, i) => {
        ctx.fillStyle = 'rgba(255,255,255,.3)'; roundRect(ctx, x, 24, bw, 6, 3); ctx.fill();
        ctx.fillStyle = '#fff'; roundRect(ctx, x, 24, bw * (i < idx ? 1 : i === idx ? local : 0), 6, 3); ctx.fill();
        x += bw + 6;
      });
      // header chip
      ctx.font = '600 24px "Noto Sans Thai", sans-serif'; ctx.textAlign = 'left'; ctx.fillStyle = 'rgba(255,255,255,.9)';
      ctx.fillText('● รีวิวจริง · UGC', 32, 80);
      const pr = this.project.product;
      if (pr.price) {
        const label = '฿' + Number(pr.price).toLocaleString('th-TH');
        ctx.font = '800 34px sans-serif'; const tw = ctx.measureText(label).width;
        ctx.fillStyle = '#EE4D2D'; roundRect(ctx, W - tw - 72, 52, tw + 40, 54, 27); ctx.fill();
        ctx.fillStyle = '#fff'; ctx.textAlign = 'center'; ctx.fillText(label, W - tw / 2 - 52, 91);
      }
      // caption box (pop-in)
      const pop = Math.min(1, local * 4);
      ctx.save(); ctx.globalAlpha = pop;
      ctx.translate(W / 2, H * 0.78); ctx.scale(0.9 + 0.1 * pop, 0.9 + 0.1 * pop);
      ctx.font = '800 46px "Noto Sans Thai", sans-serif'; ctx.textAlign = 'center';
      const lines = wrap(ctx, s.text || '', W - 120).slice(0, 3);
      const lh = 58, bh = lines.length * lh + 36;
      ctx.fillStyle = idx === sc.length - 1 ? '#FACC15' : '#FFFFFF';
      roundRect(ctx, -(W - 80) / 2, -bh / 2, W - 80, bh, 24); ctx.fill();
      ctx.fillStyle = '#0F172A';
      lines.forEach((ln, i) => ctx.fillText(ln, 0, -bh / 2 + 18 + lh * (i + 0.78)));
      ctx.restore();
      // footer
      ctx.font = '500 22px "Noto Sans Thai", sans-serif'; ctx.textAlign = 'center'; ctx.fillStyle = 'rgba(255,255,255,.85)';
      ctx.fillText((pr.title || '').slice(0, 42), W / 2, H - 70);
      if (idx === sc.length - 1) { ctx.font = '700 28px sans-serif'; ctx.fillText('🛒 กดตะกร้า / ลิงก์ในไบโอ', W / 2, H - 30); }
    },
    play(onDone) {
      if (!this.project) return toast('สร้างบทก่อน', 'error');
      cancelAnimationFrame(this.raf);
      $('v8Video').hidden = true; $('v8Canvas').hidden = false;
      const { total } = this.timeline();
      const start = performance.now();
      this.playing = true;
      const tick = now => {
        const t = (now - start) / 1000;
        this.drawFrame(Math.min(t, total - 0.001));
        const bar = $('v8RecordProgress');
        if (!bar.hidden) bar.firstElementChild.style.width = Math.min(100, (t / total) * 100) + '%';
        if (t < total) this.raf = requestAnimationFrame(tick);
        else { this.playing = false; onDone && onDone(); }
      };
      this.raf = requestAnimationFrame(tick);
    },
    async record() {
      if (!this.project) return toast('สร้างบทก่อน', 'error');
      if (this.dirty) { try { await this.saveScript(true); } catch { return; } }
      const cv = $('v8Canvas');
      if (!cv.captureStream || !window.MediaRecorder) return this.status3('เบราว์เซอร์นี้ไม่รองรับการบันทึกวิดีโอ — ใช้ Chrome/Edge/Safari รุ่นล่าสุด หรือเลือกคลิป AI', 'error');
      const types = ['video/mp4;codecs=avc1', 'video/mp4', 'video/webm;codecs=vp9', 'video/webm;codecs=vp8', 'video/webm'];
      const mime = types.find(t => MediaRecorder.isTypeSupported(t));
      if (!mime) return this.status3('เบราว์เซอร์ไม่รองรับ WebM/MP4 recorder', 'error');
      const stream = cv.captureStream(30);
      const rec = new MediaRecorder(stream, { mimeType: mime, videoBitsPerSecond: 4_000_000 });
      const chunks = [];
      rec.ondataavailable = e => e.data.size && chunks.push(e.data);
      const btn = $('v8RecordPreview'); btn.disabled = true;
      $('v8RecordProgress').hidden = false;
      this.status3('⏺ กำลังบันทึกคลิปพรีวิว… (ประมาณ ' + Math.round(this.timeline().total) + ' วินาที)', 'running');
      rec.onstop = async () => {
        $('v8RecordProgress').hidden = true;
        const blob = new Blob(chunks, { type: mime.split(';')[0] });
        this.status3('⬆️ กำลังบันทึกไฟล์ลงคลัง…', 'running');
        try {
          const fd = new FormData();
          fd.append('file', blob, `ugc_${this.project.id}.${mime.includes('mp4') ? 'mp4' : 'webm'}`);
          const r = await form(`/api/studio/projects/${this.project.id}/preview`, fd);
          this.project = r.project;
          this.status3('✅ คลิปพรีวิวพร้อม — ดาวน์โหลด/โพสต์ได้ที่ขั้นตอนที่ 4', 'ok');
          toast('✅ ' + r.message, 'success');
          this.showVideo(r.project.preview_url);
          this.renderClips(); this.paintSteps(); this.renderProjects();
        } catch (e) { this.status3('❌ บันทึกไม่สำเร็จ: ' + e.message + ' — กด "สร้างไฟล์คลิปพรีวิว" อีกครั้ง', 'error'); }
        finally { btn.disabled = false; }
      };
      rec.start(250);
      this.play(() => setTimeout(() => rec.stop(), 150));
    },
    showVideo(url) {
      const v = $('v8Video');
      v.src = url + (url.includes('?') ? '&' : '?') + 't=' + Date.now();
      v.hidden = false; $('v8Canvas').hidden = true;
    },
    resetPreview() {
      $('v8Video').hidden = true; $('v8Canvas').hidden = false;
      this.status3('', '');
    },
    status3(text, kind) { const el = $('v8Step3Status'); el.textContent = text; el.className = 'v8-status ' + (kind ? 'is-' + kind : ''); },

    // ---------- AI clip with credits
    renderAi() {
      const e = this.boot.engine, p = this.project;
      $('v8AiInfo').innerHTML = `${esc(e.label)}<br>ต้นทุน: <strong>${e.cost_credits} เครดิต</strong> · คงเหลือ <strong>${this.boot.credits}</strong> · ใช้เวลาประมาณ ${e.seconds ? e.seconds + ' วินาที' : '-'}<br><span class="v8-small">${esc(e.note)}</span>`;
      const btn = $('v8AiClip'), retry = $('v8AiRetry'), st = $('v8AiStatus');
      const short = e.cost_credits > this.boot.credits;
      btn.disabled = e.mode === 'sample' || !p || p.status === 'clip_running' || short;
      btn.textContent = e.mode === 'sample' ? '🎬 คลิป AI (ยังไม่เชื่อม AI)'
        : p && p.status === 'clip_failed' ? `↻ ลองใหม่ · ${e.cost_credits} เครดิต` : `🎬 สร้างคลิป AI · ${e.cost_credits} เครดิต`;
      retry.hidden = true;
      this.lockEditor();
      if (short && e.mode !== 'sample' && (!p || p.status !== 'clip_running')) {
        st.innerHTML = `<div class="v8-result bad">เครดิตไม่พอ: ต้องใช้ ${e.cost_credits} เครดิต แต่มี ${this.boot.credits} <button class="btn btn-primary btn-sm" onclick="document.getElementById('topupModalTriggerBtn').click()">⚡ เติมเครดิต</button><br><span class="v8-small">หรือใช้ "คลิปพรีวิว UGC" ฟรีด้านบน</span></div>`;
        return;
      }
      if (!p) { st.innerHTML = ''; return; }
      const job = p.job;
      if (p.status === 'clip_running') st.innerHTML = `<div class="v8-run"><span class="v8-spinner"></span> กำลังสร้าง… (หัก ${p.credits_charged} เครดิตแล้ว · ถ้าล้มเหลวคืนอัตโนมัติ) ระบบตรวจสถานะให้ทุก 5 วินาที</div>`;
      else if (p.status === 'clip_failed') st.innerHTML = `<div class="v8-result bad">❌ ล้มเหลว: ${esc(p.error || (job && job.error_message) || '')}<br>${p.credits_refunded ? `💸 คืน ${p.credits_charged} เครดิตแล้ว` : ''} · แก้บทแล้วกด "ลองใหม่" ได้</div>`;
      else if (p.clip_url) st.innerHTML = `<div class="v8-result ok">✅ คลิป AI พร้อม <button class="btn btn-ghost btn-sm" onclick="AASv8.showClip()">▶ ดูคลิป</button></div>`;
      else st.innerHTML = '';
      if (p.status === 'clip_failed' && p.clip_url) st.innerHTML += `<div class="v8-small v8-muted" style="margin-top:4px">คลิป AI ก่อนหน้ายังดาวน์โหลดได้ในขั้นตอนที่ 4</div>`;
    },
    // ---------- Gemini: templates + avatars
    renderGemini() {
      const e = this.boot.engine, panel = $('v8GeminiPanel');
      if (!panel) return;
      const on = !!e.supports_template;
      panel.hidden = !on;
      if (!on) return;
      const tpls = this.boot.templates || [];
      if (!this.tpl || !tpls.some(t => t.id === this.tpl)) this.tpl = (tpls[0] || {}).id;
      $('v8TplGrid').innerHTML = tpls.map(t => `<button type="button" class="v8-tpl ${t.id === this.tpl ? 'is-on' : ''}" data-tpl="${esc(t.id)}">
        <span class="v8-tpl-ico">${t.icon}</span><span class="v8-tpl-name">${esc(t.name)}</span><span class="v8-tpl-desc">${esc(t.desc)}</span></button>`).join('');
      $('v8TplGrid').querySelectorAll('[data-tpl]').forEach(b => b.addEventListener('click', () => { this.tpl = b.dataset.tpl; this.renderGemini(); }));
      const avs = this.boot.avatars || [];
      $('v8AvatarRow').innerHTML = `<button type="button" class="v8-av ${!this.avatarId ? 'is-on' : ''}" data-av="">
          <span class="v8-av-none">ไม่ใช้</span><span class="v8-av-name">ไม่มีตัวละคร</span></button>` +
        avs.map(a => `<button type="button" class="v8-av ${this.avatarId === a.id ? 'is-on' : ''}" data-av="${a.id}">
          <img src="${esc(a.url)}" alt=""><span class="v8-av-name">${esc(a.name)}</span>
          <span class="v8-av-del" data-del="${a.id}" title="ลบตัวละคร">✕</span></button>`).join('') +
        `<button type="button" class="v8-av v8-av-add" id="v8AvatarAdd"><span class="v8-av-none">＋</span><span class="v8-av-name">อัปโหลดรูป</span></button>`;
      $('v8AvatarRow').querySelectorAll('[data-av]').forEach(b => b.addEventListener('click', e2 => {
        if (e2.target.dataset.del) return;
        this.avatarId = b.dataset.av ? +b.dataset.av : null; this.renderGemini();
      }));
      $('v8AvatarRow').querySelectorAll('[data-del]').forEach(x => x.addEventListener('click', async e2 => {
        e2.stopPropagation();
        if (!confirm('ลบตัวละครนี้?')) return;
        try { const r = await api(`/api/studio/avatars/${x.dataset.del}`, 'DELETE'); this.boot.avatars = r.avatars; if (this.avatarId === +x.dataset.del) this.avatarId = null; this.renderGemini(); toast('ลบแล้ว', 'success'); }
        catch (err) { toast(err.message, 'error'); }
      }));
      $('v8AvatarAdd').addEventListener('click', () => $('v8AvatarFile').click());
    },
    async uploadAvatar(file) {
      if (!file) return;
      const fd = new FormData(); fd.append('file', file); fd.append('name', file.name.replace(/\.[^.]+$/, '').slice(0, 40));
      try { const r = await form('/api/studio/avatars', fd); this.boot.avatars = r.avatars; this.avatarId = r.id; this.renderGemini(); toast('✅ ' + r.message, 'success'); }
      catch (e) { toast(e.message, 'error'); }
    },
    async aiClip() {
      const e = this.boot.engine;
      if (!this.project) return toast('สร้างบทก่อน', 'error');
      if (e.cost_credits && !confirm(`สร้างคลิป AI ด้วย ${e.label}\nใช้ ${e.cost_credits} เครดิต (คงเหลือ ${this.boot.credits})\nถ้าล้มเหลว ระบบคืนเครดิตอัตโนมัติ\n\nยืนยัน?`)) return;
      if (this.dirty) { try { await this.saveScript(true); } catch { return; } }
      $('v8AiClip').disabled = true;
      try {
        const opts = this.boot.engine.supports_template ? {
          template: this.tpl, avatar_id: this.avatarId || null,
          aspect: $('v8GmAspect').value, resolution: $('v8GmRes').value,
          seconds: +$('v8GmSec').value, voice_over: !!$('v8GmVoice').checked,
        } : {};
        const r = await api(`/api/studio/projects/${this.project.id}/ai-clip`, 'POST', opts);
        this.project = r.project; this.boot.credits = r.credits; setCredits(r.credits); this.renderEngine();
        toast(r.message, 'success');
        this.renderAi(); this.paintSteps(); this.schedulePoll();
      } catch (err) {
        toast(err.message, 'error');
        await this.openProject(this.project.id);
        const b = await api('/api/studio/bootstrap').catch(() => null);
        if (b) { this.boot.credits = b.credits; setCredits(b.credits); this.renderEngine(); this.renderAi(); }
      }
    },
    schedulePoll() {
      clearTimeout(this.pollT);
      this.pollT = setTimeout(async () => {
        if (!this.project || this.project.status !== 'clip_running') return;
        try {
          const r = await api(`/api/studio/projects/${this.project.id}/ai-clip/refresh`, 'POST');
          this.project = r.project; this.boot.credits = r.credits; setCredits(r.credits);
          if (r.project.status === 'clip_ready') { toast('✅ คลิป AI พร้อมแล้ว', 'success'); this.showVideo(r.project.clip_url); }
          if (r.project.status === 'clip_failed') toast('❌ สร้างคลิปไม่สำเร็จ — คืนเครดิตแล้ว', 'error');
          this.renderEngine(); this.renderAi(); this.renderClips(); this.paintSteps(); this.renderProjects();
          if (r.project.status === 'clip_running') this.schedulePoll();
        } catch (e) { this.schedulePoll(); }
      }, 5000);
    },

    // ---------- step 4
    renderClips() {
      const p = this.project, box = $('v8Downloads');
      if (!p || !(p.preview_url || p.clip_url)) {
        box.innerHTML = 'ยังไม่มีคลิป — ทำขั้นตอนที่ 3 ก่อน';
        $('v8SaveLibrary').disabled = true;
        $('v8Step4Status').textContent = '';
        return;
      }
      box.innerHTML = [
        p.preview_url ? `<a class="btn btn-primary btn-sm" href="${p.preview_url}" download>⬇ ดาวน์โหลดคลิปพรีวิว UGC</a>` : '',
        p.clip_url ? `<a class="btn btn-primary btn-sm" href="${p.clip_url}" download>⬇ ดาวน์โหลดคลิป AI (MP4)</a>` : '',
      ].join(' ');
      const stored = ['saved', 'queued_tiktok'].includes(p.status);
      $('v8SaveLibrary').disabled = stored;
      $('v8SaveLibrary').textContent = stored ? '✅ บันทึกในคลังแล้ว' : '💾 บันทึกลงคลัง';
      $('v8Step4Status').textContent = p.status_label;
    },
    renderPlatforms() {
      const box = $('v8PlatformStatus'); if (!box || !this.boot) return;
      const p = this.project;
      const hasClip = p && (p.preview_url || p.clip_url);
      const chans = this.boot.channels || [];
      const row = (pl) => {
        const list = chans.filter(c => c.platform === pl);
        return `<div class="v8-plat ${list.length ? 'is-on' : ''}"><span>${PLATFORM_ICON[pl]} <strong>${PLATFORM_LABEL[pl]}</strong></span>
          ${list.length ? `<span class="chip chip-success">เชื่อมแล้ว ${list.length}</span>
            <button class="btn btn-secondary btn-sm" ${p ? '' : 'disabled'} onclick="AASv8.openPublish(${p ? p.product_id : 0}, AASv8.currentCaption())">📤 โพสต์รูป+แคปชั่น</button>`
          : `<span class="chip v8-chip-wait">ยังไม่เชื่อมต่อ</span><button class="btn btn-ghost btn-sm" onclick="AASv8.goConnectors()">เชื่อมต่อ</button>`}</div>`;
      };
      box.innerHTML = `<div class="v8-plat is-primary"><span>🎵 <strong>TikTok</strong> <span class="v8-small v8-muted">(แพลตฟอร์มหลัก Phase 1)</span></span>
          <span class="chip v8-chip-wait">ยังไม่เชื่อมต่อ API · โพสต์เอง</span></div>
        <div class="v8-tiktok-steps v8-small">1) ดาวน์โหลดคลิป 2) คัดลอกแคปชั่น 3) อัปโหลดที่ <a href="https://www.tiktok.com/upload" target="_blank" rel="noopener noreferrer">tiktok.com/upload</a> แล้วปักตะกร้า/ลิงก์</div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin:8px 0 12px">
          <button class="btn btn-primary btn-sm" id="v8QueueTiktok" ${hasClip && p.status !== 'queued_tiktok' ? '' : 'disabled'}>${p && p.status === 'queued_tiktok' ? '✅ อยู่ในคิว TikTok แล้ว' : '➕ เพิ่มเข้าคิว TikTok'}</button>
          <a class="btn btn-ghost btn-sm" href="https://www.tiktok.com/upload" target="_blank" rel="noopener noreferrer">เปิด TikTok Upload ↗</a>
        </div>
        ${['facebook', 'instagram', 'line_oa'].map(row).join('')}`;
      $('v8QueueTiktok')?.addEventListener('click', () => this.save('tiktok_queue'));
    },
    async save(target) {
      if (!this.project) return;
      try {
        const r = await api(`/api/studio/projects/${this.project.id}/save?target=${target}`, 'POST');
        this.project = r.project; toast('✅ ' + r.message, 'success');
        this.renderClips(); this.renderPlatforms(); this.paintSteps(); this.renderProjects(); refreshQueueBadge();
      } catch (e) { toast(e.message, 'error'); }
    },
    paintSteps() {
      const p = this.project;
      const st = { 1: this.productId ? 'done' : 'current', 2: 'todo', 3: 'todo', 4: 'todo' };
      const txt = { 1: this.productId ? 'เลือกแล้ว ✓' : 'รอเลือก', 2: 'รอสร้าง', 3: 'รอสร้าง', 4: 'รอคลิป' };
      if (this.productId && !p) { st[2] = 'current'; txt[2] = 'เลือกสไตล์แล้วกดสร้าง'; }
      if (p) {
        st[2] = 'done'; txt[2] = 'บทพร้อม ✓';
        const hasClip = p.preview_url || p.clip_url;
        if (p.status === 'clip_running') { st[3] = 'running'; txt[3] = 'กำลังสร้างคลิป AI…'; }
        else if (p.status === 'clip_failed' && !p.preview_url) { st[3] = 'error'; txt[3] = 'ล้มเหลว · คืนเครดิตแล้ว'; }
        else if (hasClip) { st[3] = 'done'; txt[3] = p.clip_url ? 'คลิป AI พร้อม ✓' : 'คลิปพรีวิวพร้อม ✓'; }
        else { st[3] = 'current'; txt[3] = 'กดเล่น/สร้างคลิปพรีวิว'; }
        if (['saved', 'queued_tiktok'].includes(p.status)) { st[4] = 'done'; txt[4] = p.status_label + ' ✓'; }
        else if (hasClip) { st[4] = 'current'; txt[4] = 'ดาวน์โหลด / บันทึก / โพสต์'; }
      }
      document.querySelectorAll('#v8Stepper li').forEach(li => {
        const n = li.dataset.step; li.className = 'is-' + st[n];
        li.querySelector('small').textContent = txt[n];
      });
    },
    renderProjects() {
      const tb = $('v8Projects'); if (!tb || !this.boot) return;
      api('/api/studio/projects').then(r => {
        const styleLabel = Object.fromEntries(this.boot.styles.map(s => [s.id, s.emoji + ' ' + s.label]));
        tb.innerHTML = r.projects.length ? r.projects.map(p => `<tr class="${this.project && this.project.id === p.id ? 'v8-row-on' : ''}">
          <td class="mono">#${p.id}${p.is_sample ? ' <span class="chip v8-chip-wait">ตัวอย่าง</span>' : ''}</td><td>${esc(p.product.title || '')}</td><td>${esc(styleLabel[p.style] || p.style)}</td>
          <td><span class="chip mono v8-st-${p.status}">${esc(p.status_label)}</span></td><td class="mono v8-small">${esc(localTime(p.updated_at))}</td>
          <td><button class="btn btn-ghost btn-sm" onclick="AASv8.openProject(${p.id})">เปิด</button>
              <button class="btn btn-ghost btn-sm v8-danger" onclick="AASv8.deleteProject(${p.id})" aria-label="ลบโปรเจกต์">🗑</button></td></tr>`).join('')
          : stateBox('empty', 'ยังไม่มีโปรเจกต์ — เริ่มจากขั้นตอนที่ 1', null, 6);
      }).catch(e => { tb.innerHTML = stateBox('error', e.message, null, 6); });
    },
    async open(productId) {
      this.project = null;
      $('v8ScriptEditor') && ($('v8ScriptEditor').hidden = true);
      this.pendingProduct = productId;
      AAS.switchTab('studio');
    },
    bind() {
      $('v8MakeScript')?.addEventListener('click', () => this.makeScript());
      $('v8SaveScript')?.addEventListener('click', () => this.saveScript().catch(() => {}));
      $('v8Regenerate')?.addEventListener('click', () => this.regenerate());
      $('v8GotoPreview')?.addEventListener('click', async () => {
        if (this.dirty) { try { await this.saveScript(true); } catch { return; } }
        $('v8Step3').scrollIntoView({ behavior: 'smooth', block: 'start' }); this.play();
      });
      $('v8PlayPreview')?.addEventListener('click', () => this.play());
      $('v8RecordPreview')?.addEventListener('click', () => this.record());
      $('v8AvatarFile')?.addEventListener('change', e => { this.uploadAvatar(e.target.files[0]); e.target.value = ''; });
      $('v8GeminiVerify')?.addEventListener('click', async b => {
        const btn = b.target, msg = $('v8GeminiVerifyMsg');
        btn.disabled = true; msg.textContent = 'กำลังตรวจกับ Google…';
        try { const r = await api('/api/studio/gemini/verify', 'POST', {}); msg.innerHTML = `<span class="${r.has_omni ? 'v8-ok' : 'v8-warn'}">${r.has_omni ? '✅' : '⚠'} ${esc(r.message)}</span>`; }
        catch (e) { msg.innerHTML = `<span class="v8-err">❌ ${esc(e.message)}</span>`; }
        finally { btn.disabled = false; }
      });
      $('v8AiClip')?.addEventListener('click', () => this.aiClip());
      $('v8AiRetry')?.addEventListener('click', () => this.aiClip());
      $('v8SaveLibrary')?.addEventListener('click', () => this.save('library'));
      $('v8CopyCaption')?.addEventListener('click', () => copy(this.project ? $('v8Caption').value : ''));
      $('v8ReloadProjects')?.addEventListener('click', () => this.renderProjects());
      $('v8QuickProduct')?.addEventListener('submit', async e => {
        e.preventDefault();
        try {
          const r = await api('/api/studio/quick-product', 'POST', { title: e.target.title.value.trim(), platform: 'other' });
          e.target.reset(); toast(r.reused ? 'มีสินค้านี้อยู่แล้ว — เลือกให้แล้ว' : '✅ เพิ่มสินค้าแล้ว', 'success');
          this.project = null; $('v8ScriptEditor').hidden = true;
          this.pendingProduct = r.id; await this.load();
        } catch (err) { toast(err.message, 'error'); }
      });
    },
  };


  // =========================================================== AUTO-POST (scheduled publishing)
  const AP_STATE = { pending: ['⏳', 'รอเวลา'], fb_scheduled: ['🗓', 'ฝากคิวที่ Facebook แล้ว'], posted: ['✅', 'โพสต์แล้ว'],
    failed: ['❌', 'ล้มเหลว'], cancelled: ['✕', 'ยกเลิก'] };
  const AP_STATUS = { scheduled: ['', '⏳ ตั้งเวลาแล้ว'], posting: ['', '📤 กำลังโพสต์'], posted: ['chip-success', '✅ โพสต์แล้ว'],
    partial: ['', '⚠ สำเร็จบางช่องทาง'], failed: ['v8-chip-err', '❌ ล้มเหลว'], cancelled: ['', '✕ ยกเลิก'] };
  const toLocalInput = d => { const p = n => String(n).padStart(2, '0'); return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`; };
  const AutoPost = {
    timer: 0,
    render() {
      const box = $('v8ApChannels'); if (!box || !Studio.boot) return;
      const chans = Studio.boot.channels || [];
      const fb = chans.filter(c => c.platform === 'facebook');
      const group = pl => chans.filter(c => c.platform === pl).map(c =>
        `<label class="v8-pub-row"><input type="checkbox" name="v8apch" value="${c.id}" data-platform="${pl}" ${pl === 'facebook' ? 'checked' : ''}> ${PLATFORM_ICON[pl]} ${esc(c.account_name)} <span class="chip v8-chip-wait">${PLATFORM_LABEL[pl]}</span></label>`).join('');
      box.innerHTML = (fb.length ? '' : `<div class="v8-ap-connect"><div><strong>📘 ยังไม่ได้เชื่อม Facebook</strong><div class="v8-small v8-muted">กด Connect → ล็อกอิน Facebook → เลือกเพจ → กลับมาหน้านี้อัตโนมัติ</div></div>
          <button class="btn btn-primary v8-fb-btn" onclick="AASv8.oauth('facebook', this, 'studio')">Connect with Facebook</button></div>`)
        + group('facebook') + group('instagram') + group('line_oa')
        + (chans.length ? '' : '') + `<div class="v8-small v8-muted" style="margin-top:4px">IG / LINE เพิ่มได้ที่เมนู <button class="btn btn-ghost btn-sm" data-tab-go="connectors">Connectors</button> · TikTok ยังเป็นการโพสต์เอง</div>`;
      bindTabGo(box);
      box.querySelectorAll('input[name=v8apch]').forEach(cb => cb.addEventListener('change', () => this.syncLine()));
      this.syncLine();
      if (!$('v8ApWhen').value) this.quick('1h');
      $('v8ApSubmit').disabled = !chans.length || !Studio.project;
      $('v8ApSubmit').title = !chans.length ? 'เชื่อมต่อช่องทางก่อน' : !Studio.project ? 'สร้างบทก่อน' : '';
    },
    syncLine() {
      $('v8ApLine').hidden = ![...document.querySelectorAll('input[name=v8apch]:checked')].some(c => c.dataset.platform === 'line_oa');
    },
    quick(kind) {
      const d = new Date();
      if (kind === 'now') { $('v8ApWhen').value = ''; $('v8ApSubmit').textContent = '📤 โพสต์ทันที'; return; }
      if (kind === '1h') d.setHours(d.getHours() + 1);
      if (kind === 'tonight') { d.setHours(20, 0, 0, 0); if (d < new Date()) d.setDate(d.getDate() + 1); }
      if (kind === 'tomorrow') { d.setDate(d.getDate() + 1); d.setHours(12, 0, 0, 0); }
      $('v8ApWhen').value = toLocalInput(d); $('v8ApSubmit').textContent = '⏰ ตั้งเวลาโพสต์';
    },
    async submit() {
      const p = Studio.project;
      if (!p) return toast('สร้างบทก่อน (ขั้นตอนที่ 2)', 'error');
      const ids = [...document.querySelectorAll('input[name=v8apch]:checked')].map(c => Number(c.value));
      if (!ids.length) return toast('เลือกอย่างน้อย 1 ช่องทาง', 'error');
      const whenRaw = $('v8ApWhen').value;
      const when = whenRaw ? new Date(whenRaw) : null;
      if (when && when < new Date(Date.now() - 60000)) return toast('เวลาที่เลือกผ่านไปแล้ว', 'error');
      const lineMode = document.querySelector('input[name=v8aplinemode]:checked')?.value || 'broadcast';
      const hasLine = [...document.querySelectorAll('input[name=v8apch]:checked')].some(c => c.dataset.platform === 'line_oa');
      let confirmB = false;
      if (hasLine && lineMode === 'broadcast') { confirmB = confirm('LINE Broadcast จะส่งหาเพื่อนทุกคนและนับโควต้าข้อความ ยืนยัน?'); if (!confirmB) return; }
      if (Studio.dirty) { try { await Studio.saveScript(true); } catch { return; } }
      const btn = $('v8ApSubmit'); btn.disabled = true; const label = btn.textContent; btn.textContent = when ? 'กำลังตั้งเวลา…' : 'กำลังโพสต์…';
      try {
        const r = await api('/api/scheduled-posts', 'POST', { product_id: p.product_id, project_id: p.id, channel_ids: ids,
          caption: $('v8Caption').value, scheduled_at: when ? when.toISOString() : null, use_video: $('v8ApVideo').checked,
          line_mode: lineMode, confirm_broadcast: confirmB });
        const bad = r.post.channels.filter(c => c.state === 'failed');
        toast((bad.length ? '⚠ ' : '✅ ') + r.message + (bad.length ? ` — ล้มเหลว ${bad.length} ช่องทาง: ${bad[0].error}` : ''), bad.length ? 'error' : 'success');
        this.load();
      } catch (e) { toast(e.message, 'error'); }
      finally { btn.disabled = false; btn.textContent = label; }
    },
    async load() {
      const tb = $('v8ApList'); if (!tb) return;
      clearTimeout(this.timer);
      try {
        const r = await api('/api/scheduled-posts');
        tb.innerHTML = r.posts.length ? r.posts.map(p => {
          const [cls, label] = AP_STATUS[p.status] || ['', p.status];
          return `<tr><td class="mono v8-small">${esc(localTime(p.scheduled_at))}</td><td>${esc(p.product_title)}${p.has_video ? ' <span class="chip v8-chip-wait">🎬 คลิป</span>' : ''}</td>
            <td>${p.channels.map(c => { const [i, t] = AP_STATE[c.state] || ['', c.state];
              return `<div class="v8-small">${i} ${PLATFORM_ICON[c.platform] || ''} ${esc(c.account_name)} — ${t}${c.error ? `<div class="v8-err">${esc(c.error)}</div>` : ''}</div>`; }).join('')}</td>
            <td><span class="chip ${cls} mono">${label}</span></td>
            <td>${['scheduled', 'partial', 'failed'].includes(p.status) && p.channels.some(c => ['pending', 'fb_scheduled'].includes(c.state)) ? `<button class="btn btn-ghost btn-sm v8-danger" onclick="AASv8.cancelPost(${p.id})">ยกเลิก</button>` : ''}
                ${['failed', 'partial'].includes(p.status) && p.channels.some(c => c.state === 'failed') ? `<button class="btn btn-secondary btn-sm" onclick="AASv8.retryPost(${p.id})">↻ ลองใหม่</button>` : ''}</td></tr>`;
        }).join('') : stateBox('empty', 'ยังไม่มีโพสต์ที่ตั้งเวลา', null, 5);
        if (r.posts.some(p => ['scheduled', 'posting'].includes(p.status)) && document.querySelector('#studio.active')) this.timer = setTimeout(() => this.load(), 20000);
      } catch (e) { tb.innerHTML = isAuthError(e) ? '' : stateBox('error', e.message, null, 5); }
    },
    bind() {
      $('v8ApSubmit')?.addEventListener('click', () => this.submit());
      document.querySelectorAll('[data-ap-quick]').forEach(b => b.addEventListener('click', () => this.quick(b.dataset.apQuick)));
      $('v8ApWhen')?.addEventListener('change', () => { $('v8ApSubmit').textContent = $('v8ApWhen').value ? '⏰ ตั้งเวลาโพสต์' : '📤 โพสต์ทันที'; });
    },
  };




  // =========================================================== PROMPTPAY TOP-UP
  const Pay = {
    cfg: null, order: null, pollT: 0, tickT: 0,
    step(n) { document.querySelectorAll('#v8Pay [data-ps]').forEach(li => { const k = +li.dataset.ps; li.classList.toggle('is-on', k === n); li.classList.toggle('is-done', k < n); }); },
    stop() { clearInterval(this.pollT); clearInterval(this.tickT); this.pollT = this.tickT = 0; },
    close() { this.stop(); $('v8Pay').hidden = true; },
    baht(n) { return '฿' + Number(n).toLocaleString('th-TH', { minimumFractionDigits: Number(n) % 1 ? 2 : 0, maximumFractionDigits: 2 }); },
    async open() {
      const me = AAS.getMe() || {};
      if (!me.id) { toast('กรุณาเข้าสู่ระบบก่อนเติมเครดิต', 'error'); $('authModal').hidden = false; return; }
      $('v8Pay').hidden = false; this.stop(); this.step(1);
      $('v8PayTitle').textContent = '💳 เติมเครดิต — เลือกแพ็กเกจ';
      const box = $('v8PayBody'); box.innerHTML = stateBox('loading', 'กำลังโหลดแพ็กเกจ…');
      try { this.cfg = await api('/api/payments/packages'); }
      catch (e) { box.innerHTML = stateBox('error', 'โหลดแพ็กเกจไม่สำเร็จ: ' + e.message, null) + '<button class="btn btn-secondary btn-sm" onclick="AASv8.openPay()">ลองใหม่</button>'; return; }
      const c = this.cfg;
      box.innerHTML = `
        ${c.mode === 'simulate' ? `<div class="v8-onb-warn"><strong>🧪 โหมดจำลองการชำระเงิน</strong> — ไม่มีการตัดเงินจริง กด "จำลองการชำระเงินสำเร็จ" ในขั้นถัดไปแล้วเครดิตจะเข้าบัญชีจริงทันที</div>` : ''}
        <p class="v8-muted v8-small">เครดิตคงเหลือ <strong>⚡ ${Number(me.credits || 0).toLocaleString('th-TH')}</strong> · คลิป AI 1 คลิปใช้ ${c.clip_cost} เครดิต · เครดิตไม่มีวันหมดอายุ · จ่ายครั้งเดียว ไม่ตัดรอบอัตโนมัติ</p>
        <div class="v8-pkg-grid">${c.packages.map(p => `
          <button class="v8-pkg ${p.popular ? 'is-pop' : ''}" data-pkg="${p.id}">
            ${p.popular ? '<span class="v8-pkg-pop">ยอดนิยม</span>' : ''}
            <span class="v8-pkg-name">${esc(p.name)}</span>
            <span class="v8-pkg-credits">⚡ ${p.credits.toLocaleString('th-TH')} <small>เครดิต</small></span>
            ${p.bonus ? `<span class="v8-pkg-bonus">โบนัส +${p.bonus.toLocaleString('th-TH')}</span>` : '<span class="v8-pkg-bonus is-none">ราคาปกติ</span>'}
            <span class="v8-pkg-desc">${esc(p.desc)}</span>
            <span class="v8-pkg-price">${this.baht(p.price)}</span>
            <span class="v8-pkg-cta">เลือกแพ็กเกจนี้ →</span>
          </button>`).join('')}</div>`;
      box.querySelectorAll('[data-pkg]').forEach(b => b.addEventListener('click', () => this.create(b.dataset.pkg, b)));
    },
    async create(pkgId, btn) {
      if (btn) { btn.disabled = true; btn.querySelector('.v8-pkg-cta').textContent = 'กำลังสร้าง QR…'; }
      try { this.order = await api('/api/payments/orders', 'POST', { package_id: pkgId }); this.renderQR(); }
      catch (e) { toast('สร้างรายการชำระเงินไม่สำเร็จ: ' + e.message, 'error'); if (btn) { btn.disabled = false; btn.querySelector('.v8-pkg-cta').textContent = 'เลือกแพ็กเกจนี้ →'; } }
    },
    renderQR() {
      const o = this.order, sim = o.mode === 'simulate';
      this.step(2); $('v8PayTitle').textContent = '📱 สแกนจ่ายผ่าน PromptPay';
      $('v8PayBody').innerHTML = `
        <div class="v8-pay-grid">
          <div class="v8-qr-card">
            <div class="v8-qr-head"><span class="v8-pp-logo">PromptPay</span><span>Thai QR Payment</span></div>
            <div class="v8-qr-img ${o.payable ? '' : 'is-demo'}">${o.qr_svg || '<div class="v8-muted">ไม่สามารถสร้างภาพ QR</div>'}${o.payable ? '' : '<span class="v8-qr-stamp">QR จำลอง<br>สแกนจ่ายจริงไม่ได้</span>'}</div>
            <div class="v8-qr-amount">${this.baht(o.amount_thb)}</div>
            ${o.payable ? `<div class="v8-small v8-muted">ผู้รับเงิน ${esc(o.payee_name || 'PromptPay')} · ${esc(o.payee)}</div>` : ''}
            <div class="v8-qr-timer">QR หมดอายุใน <strong id="v8PayTimer">--:--</strong></div>
          </div>
          <div class="v8-pay-side">
            <table class="v8-onb-table"><tbody>
              <tr><th>เลขที่รายการ</th><td class="mono">${esc(o.ref)}</td></tr>
              <tr><th>แพ็กเกจ</th><td>${esc(o.package_name)}</td></tr>
              <tr><th>เครดิตที่ได้รับ</th><td><strong>⚡ +${o.credits.toLocaleString('th-TH')}</strong></td></tr>
              <tr><th>ยอดชำระ</th><td><strong>${this.baht(o.amount_thb)}</strong>${o.mode === 'manual' ? '<div class="v8-small v8-muted">โอนให้ตรงทุกสตางค์ เพื่อให้ระบบจับคู่รายการได้</div>' : ''}</td></tr>
            </tbody></table>
            <ol class="v8-onb-steps v8-small">
              <li>เปิดแอปธนาคารหรือ e-Wallet → เลือก "สแกน QR"</li>
              <li>สแกน QR ด้านซ้าย ตรวจยอด ${this.baht(o.amount_thb)} แล้วยืนยันการโอน</li>
              <li>${sim ? 'กด "จำลองการชำระเงินสำเร็จ" ด้านล่าง (โหมดทดสอบ)' : 'รอระบบยืนยันยอดโอน หน้านี้จะอัปเดตเอง'}</li>
            </ol>
            <div class="v8-pay-status" id="v8PayStatus"><span class="v8-spin" aria-hidden="true"></span> รอการชำระเงิน…</div>
            <div class="v8-pay-actions">
              ${sim ? '<button class="btn btn-primary" id="v8PaySim">✅ จำลองการชำระเงินสำเร็จ</button>' : ''}
              ${o.qr_svg ? '<button class="btn btn-secondary btn-sm" id="v8PaySave">⬇ บันทึก QR</button>' : ''}
              <button class="btn btn-ghost btn-sm" id="v8PayBack">← เปลี่ยนแพ็กเกจ</button>
            </div>
          </div>
        </div>`;
      $('v8PaySim')?.addEventListener('click', () => this.simulate());
      $('v8PayBack').addEventListener('click', async () => { try { await api(`/api/payments/orders/${o.id}/cancel`, 'POST', {}); } catch {} this.open(); });
      $('v8PaySave')?.addEventListener('click', () => {
        const a = document.createElement('a');
        a.href = URL.createObjectURL(new Blob([o.qr_svg], { type: 'image/svg+xml' })); a.download = `promptpay-${o.ref}.svg`; a.click();
        setTimeout(() => URL.revokeObjectURL(a.href), 2000);
      });
      const end = new Date(o.expires_at).getTime();
      const tick = () => {
        const left = Math.max(0, Math.round((end - Date.now()) / 1000));
        const t = $('v8PayTimer'); if (t) t.textContent = `${String(Math.floor(left / 60)).padStart(2, '0')}:${String(left % 60).padStart(2, '0')}`;
        if (!left) this.poll();
      };
      tick(); this.tickT = setInterval(tick, 1000);
      this.pollT = setInterval(() => this.poll(), 4000);
    },
    async poll() {
      if (!this.order) return;
      try {
        const r = await api(`/api/payments/orders/${this.order.id}`);
        if (r.status === 'paid') this.success(r);
        else if (r.status === 'expired' || r.status === 'cancelled') this.expired(r.status);
      } catch {}
    },
    async simulate() {
      const b = $('v8PaySim'); b.disabled = true;
      $('v8PayStatus').innerHTML = '<span class="v8-spin" aria-hidden="true"></span> กำลังตรวจสอบการชำระเงินกับธนาคาร…';
      await new Promise(r => setTimeout(r, 1400));
      try { const r = await api(`/api/payments/orders/${this.order.id}/simulate-paid`, 'POST', {}); this.success(r); }
      catch (e) { $('v8PayStatus').innerHTML = '❌ ' + esc(e.message); b.disabled = false; }
    },
    async success(r) {
      this.stop(); this.step(3); $('v8PayTitle').textContent = '🎉 เติมเครดิตสำเร็จ';
      await AAS.refreshSession();
      const bal = r.balance ?? (AAS.getMe() || {}).credits;
      $('v8PayBody').innerHTML = `
        <div class="v8-pay-done">
          <div class="v8-pay-check" aria-hidden="true">✓</div>
          <div class="v8-pay-plus">+${r.credits.toLocaleString('th-TH')} เครดิต</div>
          <p>เครดิตคงเหลือตอนนี้ <strong>⚡ ${Number(bal || 0).toLocaleString('th-TH')}</strong></p>
          <table class="v8-onb-table v8-pay-receipt"><tbody>
            <tr><th>เลขที่รายการ</th><td class="mono">${esc(r.ref)}</td></tr>
            <tr><th>แพ็กเกจ</th><td>${esc(r.package_name)}</td></tr>
            <tr><th>ยอดชำระ</th><td>${this.baht(r.amount_thb)} ${r.mode === 'simulate' ? '<span class="chip v8-chip-wait">จำลอง</span>' : ''}</td></tr>
            <tr><th>เวลา</th><td>${new Date(r.paid_at || Date.now()).toLocaleString('th-TH-u-ca-gregory')}</td></tr>
          </tbody></table>
          <div class="v8-pay-actions" style="justify-content:center">
            <button class="btn btn-primary" id="v8PayGo">🚀 ไปสร้างคอนเทนต์</button>
            <button class="btn btn-ghost" id="v8PayDone">ปิด</button>
          </div>
        </div>`;
      $('v8PayGo').addEventListener('click', () => { this.close(); AAS.switchTab('studio'); });
      $('v8PayDone').addEventListener('click', () => this.close());
      toast(`เติมเครดิตสำเร็จ +${r.credits.toLocaleString('th-TH')} เครดิต`, 'success');
    },
    expired(status) {
      this.stop();
      $('v8PayStatus').innerHTML = status === 'expired' ? '⏰ QR หมดอายุแล้ว — ยังไม่มีการตัดเงิน' : 'รายการนี้ถูกยกเลิกแล้ว';
      $('v8PaySim')?.remove();
      const t = $('v8PayTimer'); if (t) t.textContent = '00:00';
      const a = document.querySelector('#v8PayBody .v8-pay-actions');
      if (a && !$('v8PayNew')) { a.insertAdjacentHTML('afterbegin', '<button class="btn btn-primary" id="v8PayNew">🔄 สร้าง QR ใหม่</button>'); $('v8PayNew').addEventListener('click', () => this.create(this.order.package_id)); }
    },
    bind() {
      $('v8PayClose')?.addEventListener('click', () => this.close());
      $('v8Pay')?.addEventListener('click', e => { if (e.target.id === 'v8Pay') this.close(); });
      document.addEventListener('keydown', e => { if (e.key === 'Escape' && !$('v8Pay').hidden) this.close(); });
    },
  };
  // =========================================================== PROFILE MENU (top-right)
  const Profile = {
    paint() {
      const me = AAS.getMe() || {}, on = !!me.id, demo = !!me.is_demo;
      $('v8Profile').hidden = !on;
      const trig = $('authModalTriggerBtn'); if (trig) trig.hidden = on && !demo;
      if (!on) { this.close(); return; }
      document.querySelectorAll('#v8ProfileMenu .v8-pm-demo').forEach(b => { b.hidden = !demo; });
      const lo = document.querySelector('#v8ProfileMenu [data-pm=logout]'); if (lo) lo.hidden = demo;
      const sep = document.querySelector('#v8ProfileMenu .v8-pm-sep'); if (sep) sep.hidden = demo;
      const name = demo ? 'ผู้ใช้ทดลอง' : (me.username || '-'), ini = demo ? 'D' : name.slice(0, 1).toUpperCase();
      $('v8PfAv').textContent = ini; $('v8PmAv').textContent = ini;
      $('v8PfName').textContent = name; $('v8PmName').textContent = name;
      $('v8PfRole').textContent = demo ? 'DEMO' : me.role === 'admin' ? 'ADMIN' : 'MEMBER';
      $('v8PmEmail').textContent = demo ? 'บัญชีทดลอง · เก็บงานไว้ 7 วัน' : (me.email || '');
      $('v8PmCredit').textContent = `⚡ ${Number(me.credits || 0).toLocaleString('th-TH')} เครดิต`;
    },
    open() { $('v8ProfileMenu').hidden = false; $('v8ProfileBtn').setAttribute('aria-expanded', 'true'); $('v8ProfileMenu').querySelector('[data-pm]')?.focus(); },
    close() { const m = $('v8ProfileMenu'); if (m && !m.hidden) { m.hidden = true; $('v8ProfileBtn').setAttribute('aria-expanded', 'false'); } },
    async account() {
      const box = $('v8AccBody'); $('v8Account').hidden = false;
      box.innerHTML = stateBox('loading', 'กำลังโหลดข้อมูลบัญชี…');
      try {
        const me = await api('/api/me');
        const row = (k, v) => `<tr><th>${k}</th><td>${v}</td></tr>`;
        box.innerHTML = `<table class="v8-onb-table v8-acc-table"><tbody>
          ${me.is_demo ? '' : row('ชื่อผู้ใช้', esc(me.username)) + row('อีเมล', esc(me.email || '-'))}
          ${row('สถานะ', me.is_demo ? '<span class="chip v8-chip-wait">บัญชีทดลอง (Demo)</span>' : me.role === 'admin' ? '<span class="chip chip-success">ผู้ดูแลระบบ</span>' : '<span class="chip">สมาชิก Beta</span>')}
          ${row('เครดิตคงเหลือ', `⚡ ${Number(me.credits || 0).toLocaleString('th-TH')} เครดิต`)}
        </tbody></table>
        <div class="v8-onb-nav" style="margin:12px 0 4px"><button class="btn btn-secondary btn-sm" data-acc="topup">💳 เติมเงิน</button><button class="btn btn-ghost btn-sm" data-acc="logout">🚪 ออกจากระบบ</button></div>
        ${me.is_demo ? '<div class="v8-demo-note">🧪 นี่คือบัญชีทดลองบนเบราว์เซอร์นี้ งานจะถูกเก็บไว้ 7 วัน <button class="btn btn-primary btn-sm" data-acc="signup">✨ สมัครสมาชิกเพื่อเก็บงานถาวร</button></div>' : ''}
        <details class="v8-acc-sec" ${me.is_demo ? 'hidden' : ''}><summary>🔑 เปลี่ยนรหัสผ่าน</summary>
          <form id="v8PwForm" class="v8-pw-form" autocomplete="off">
            <label>รหัสผ่านปัจจุบัน<input class="form-input" type="password" name="current_password" required autocomplete="current-password"></label>
            <label>รหัสผ่านใหม่ (อย่างน้อย 12 ตัว มีตัวอักษรและตัวเลข)<input class="form-input" type="password" name="new_password" minlength="12" required autocomplete="new-password"></label>
            <label>ยืนยันรหัสผ่านใหม่<input class="form-input" type="password" name="confirm" minlength="12" required autocomplete="new-password"></label>
            <button class="btn btn-primary btn-sm" type="submit">บันทึกรหัสผ่านใหม่</button>
            <p class="v8-small v8-muted">เมื่อเปลี่ยนแล้ว อุปกรณ์อื่นที่ล็อกอินอยู่จะถูกออกจากระบบ</p>
          </form>
        </details>
        <details class="v8-acc-sec" id="v8AccHist"><summary>🧾 ประวัติการเติมเครดิต</summary><div id="v8AccHistBody">${stateBox('loading', 'กำลังโหลด…')}</div></details>`;
        $('v8PwForm').addEventListener('submit', async e => {
          e.preventDefault();
          const f = e.target, btn = f.querySelector('button[type=submit]');
          if (f.new_password.value !== f.confirm.value) return toast('รหัสผ่านใหม่ทั้งสองช่องไม่ตรงกัน', 'error');
          btn.disabled = true;
          try { await api('/api/my/password', 'POST', { current_password: f.current_password.value, new_password: f.new_password.value }); f.reset(); toast('เปลี่ยนรหัสผ่านเรียบร้อย', 'success'); f.closest('details').open = false; }
          catch (err) { toast(err.message, 'error'); }
          finally { btn.disabled = false; }
        });
        $('v8AccHist').addEventListener('toggle', async ev => {
          if (!ev.target.open || ev.target._loaded) return;
          try {
            const r = await api('/api/payments/orders'); ev.target._loaded = true;
            const st = { paid: '<span class="chip chip-success">สำเร็จ</span>', pending: '<span class="chip v8-chip-wait">รอชำระ</span>', expired: '<span class="chip">หมดอายุ</span>', cancelled: '<span class="chip">ยกเลิก</span>' };
            $('v8AccHistBody').innerHTML = r.orders.length ? `<table class="v8-onb-table"><thead><tr><th>วันที่</th><th>แพ็กเกจ</th><th>ยอด</th><th>สถานะ</th></tr></thead><tbody>${r.orders.map(o => `<tr><td>${new Date(o.created_at).toLocaleDateString('th-TH-u-ca-gregory')}</td><td>${esc(o.package_name)} <small class="v8-muted">+${o.credits}</small></td><td>${Pay.baht(o.amount_thb)}</td><td>${st[o.status] || esc(o.status)}</td></tr>`).join('')}</tbody></table>` : stateBox('empty', 'ยังไม่มีประวัติการเติมเครดิต', null);
          } catch (err) { $('v8AccHistBody').innerHTML = stateBox('error', err.message, null); }
        });
        box.querySelector('[data-acc=topup]').addEventListener('click', () => { $('v8Account').hidden = true; Pay.open(); });
        const lo = box.querySelector('[data-acc=logout]');
        if (me.is_demo) lo.remove(); else lo.addEventListener('click', () => AAS.logout());
        box.querySelector('[data-acc=signup]')?.addEventListener('click', () => { $('v8Account').hidden = true; this.act('signup'); });
      } catch (e) { box.innerHTML = stateBox('error', 'โหลดข้อมูลบัญชีไม่สำเร็จ: ' + e.message, null); }
    },
    act(k) {
      this.close();
      const me = AAS.getMe() || {};
      if (k === 'signup' || k === 'login') {
        $('authModal').hidden = false; $(k === 'signup' ? 'tabRegisterBtn' : 'tabLoginBtn')?.click();
        const n = $('regDemoNote'); if (n) n.hidden = false; return;
      }
      if (k === 'members') return me.role === 'admin' ? AAS.switchTab('users_mgmt') : this.account();
      if (k === 'topup') return Pay.open();
      if (k === 'report') return AAS.switchTab('tracking');
      if (k === 'logout') return AAS.logout();
    },
    bind() {
      $('v8ProfileBtn')?.addEventListener('click', e => { e.stopPropagation(); $('v8ProfileMenu').hidden ? this.open() : this.close(); });
      $('v8ProfileMenu')?.addEventListener('click', e => { const b = e.target.closest('[data-pm]'); if (b) this.act(b.dataset.pm); });
      $('v8ProfileMenu')?.addEventListener('keydown', e => {
        const items = [...$('v8ProfileMenu').querySelectorAll('[data-pm]')], i = items.indexOf(document.activeElement);
        if (e.key === 'ArrowDown') { e.preventDefault(); items[(i + 1) % items.length].focus(); }
        if (e.key === 'ArrowUp') { e.preventDefault(); items[(i - 1 + items.length) % items.length].focus(); }
      });
      document.addEventListener('click', e => { if (!e.target.closest('#v8Profile')) this.close(); });
      document.addEventListener('keydown', e => { if (e.key === 'Escape') { if (!$('v8ProfileMenu').hidden) { this.close(); $('v8ProfileBtn').focus(); } $('v8Account').hidden = true; } });
      $('v8AccClose')?.addEventListener('click', () => { $('v8Account').hidden = true; });
      $('v8Account')?.addEventListener('click', e => { if (e.target.id === 'v8Account') $('v8Account').hidden = true; });
      this.paint();
    },
  };
  // =========================================================== ONBOARDING (first visit)
  const ONB_KEY = 'aas_onboarding_v8_hide';
  const Onboard = {
    i: 0,
    slides: [
      { title: '👋 ยินดีต้อนรับสู่ Affiliate Auto Studio', html: `
        <div class="v8-onb-warn"><strong>🧪 นี่คือระบบทดสอบ (Beta)</strong><br>
        ระบบอยู่ระหว่างการพัฒนา <strong>ยังใช้งานจริงไม่ได้ทั้งหมด</strong> บางฟีเจอร์ต้องรอการตั้งค่าหรือการอนุมัติจากแพลตฟอร์ม
        ข้อมูลทดสอบอาจถูกรีเซ็ตได้ — กรุณาอย่าใส่ข้อมูลสำคัญหรือรหัสผ่านของแพลตฟอร์มอื่น</div>
        <p>✅ <strong>ใช้ได้ทันทีไม่ต้องสมัคร</strong> — ระบบเปิดบัญชีทดลอง (Demo) ให้อัตโนมัติ เพิ่มสินค้า นำเข้าสินค้า สร้างบทและคลิปได้ครบ สมัครทีหลังงานก็ย้ายตามไปด้วย</p>
        <p>ระบบช่วยนักทำ Affiliate: <strong>หาสินค้า Shopee → สร้างคลิปรีวิวแบบ UGC → โพสต์ลงโซเชียล</strong> ในหน้าเดียว</p>
        <p class="v8-muted v8-small">ใช้เวลาอ่าน 1 นาที — กด "ถัดไป" เพื่อดูว่า Phase 1 ทำอะไรได้บ้าง</p>` },
      { title: '✅ Phase 1 ทำอะไรได้บ้าง', html: `
        <table class="v8-onb-table"><thead><tr><th>ฟีเจอร์</th><th>สถานะ</th></tr></thead><tbody>
        <tr><td>สร้างบท UGC 6 สไตล์ + คลิปพรีวิว 9:16 (ดาวน์โหลดได้)</td><td><span class="chip chip-success">ใช้ได้เลย</span></td></tr>
        <tr><td>สินค้าตัวอย่าง / เพิ่มสินค้าเอง พร้อมรูป ราคา ค่าคอม</td><td><span class="chip chip-success">ใช้ได้เลย</span></td></tr>
        <tr><td>ศูนย์ช่วยเหลือ + คำถามที่พบบ่อย (FAQ)</td><td><span class="chip chip-success">ใช้ได้เลย</span></td></tr>
        <tr><td>ดึงสินค้าจาก Shopee (รูป ราคา ค่าคอมจริง)</td><td><span class="chip v8-chip-wait">ต้องใส่ AppID/Secret ของคุณ</span></td></tr>
        <tr><td>เชื่อม Facebook / Instagram / LINE OA + Auto-Post ตั้งเวลา</td><td><span class="chip v8-chip-wait">รอผู้ดูแลตั้งค่า Meta App</span></td></tr>
        <tr><td>คลิป AI จริง (Veo 3.1 Lite)</td><td><span class="chip v8-chip-wait">รอเปิดเอนจิน AI</span></td></tr>
        <tr><td>โพสต์ TikTok / Shopee Video อัตโนมัติ</td><td><span class="chip v8-chip-wait">ยังไม่รองรับ (โพสต์เอง)</span></td></tr>
        </tbody></table>` },
      { title: '🧭 เริ่มใช้งานใน 4 ขั้นตอน', html: `
        <ol class="v8-onb-steps">
          <li><strong>สร้างคอนเทนต์</strong> — มีสินค้าและบทตัวอย่างให้ลองทันที <button class="btn btn-ghost btn-sm" data-onb-go="studio">เปิดดู</button></li>
          <li><strong>เลือกสไตล์ UGC → สร้างบท</strong> แก้ไขได้ทุกฉาก แล้วกด "⏺ สร้างไฟล์คลิปพรีวิว" (ฟรี)</li>
          <li><strong>บันทึก / ดาวน์โหลด</strong> คลิปไปโพสต์ TikTok เอง หรือ "⏰ Auto-Post" เมื่อเชื่อม Facebook แล้ว</li>
          <li><strong>สินค้าของฉัน</strong> ดึงสินค้าจริงจาก Shopee <button class="btn btn-ghost btn-sm" data-onb-go="products">เปิดดู</button></li>
        </ol>
        <p class="v8-muted v8-small">ทุกขั้นมีแถบสถานะบอกชัดว่าเสร็จ / กำลังทำ / ล้มเหลว</p>` },
      { title: '🛟 ติดขัดตรงไหน ดู FAQ ได้เลย', html: `
        <p>เมนู <strong>ช่วยเหลือ & FAQ</strong> รวมคำถามที่พบบ่อยทุกฟีเจอร์ พร้อมคำตอบทีละขั้นตอนและช่องค้นหา</p>
        <p>พบบั๊กหรืออยากได้ฟีเจอร์ไหน แจ้งได้ที่เมนู <strong>เสนอไอเดีย / แจ้งปัญหา</strong> — ความเห็นของคุณช่วยกำหนดสิ่งที่จะทำใน Phase ถัดไป</p>
        <p class="v8-muted v8-small">ดูหน้านี้อีกครั้งได้ที่ปุ่ม "🧪 BETA ทดสอบ" ด้านบน หรือในหน้าช่วยเหลือ</p>` },
    ],
    hidden() { try { return localStorage.getItem(ONB_KEY) === '1'; } catch { return false; } },
    open(force) {
      if (!force && (this.hidden() || sessionStorage.getItem('aas_onb_seen') === '1')) return;
      this.i = 0; $('v8OnbNever').checked = this.hidden(); this.render(); $('v8Onboard').hidden = false;
      setTimeout(() => $('v8OnbNext')?.focus(), 50);
    },
    close() {
      try {
        if ($('v8OnbNever').checked) localStorage.setItem(ONB_KEY, '1'); else localStorage.removeItem(ONB_KEY);
        sessionStorage.setItem('aas_onb_seen', '1');
      } catch {}
      $('v8Onboard').hidden = true;
    },
    render() {
      const s = this.slides[this.i], last = this.i === this.slides.length - 1;
      $('v8OnbBody').innerHTML = `<h2 id="v8OnbTitle" class="v8-onb-title">${s.title}</h2><div class="v8-onb-content">${s.html}</div>`;
      $('v8OnbDots').innerHTML = this.slides.map((_, k) => `<span class="${k === this.i ? 'is-on' : ''}"></span>`).join('');
      $('v8OnbPrev').style.visibility = this.i ? 'visible' : 'hidden';
      $('v8OnbNext').textContent = last ? '🚀 เริ่มใช้งาน' : 'ถัดไป →';
      $('v8OnbBody').querySelectorAll('[data-onb-go]').forEach(b => b.addEventListener('click', () => { this.close(); AAS.switchTab(b.dataset.onbGo); }));
    },
    bind() {
      $('v8OnbNext')?.addEventListener('click', () => {
        if (this.i < this.slides.length - 1) { this.i += 1; this.render(); }
        else { this.close(); AAS.switchTab('studio'); }
      });
      $('v8OnbPrev')?.addEventListener('click', () => { if (this.i) { this.i -= 1; this.render(); } });
      $('v8OnbClose')?.addEventListener('click', () => this.close());
      $('v8Onboard')?.addEventListener('click', e => { if (e.target.id === 'v8Onboard') this.close(); });
      document.addEventListener('keydown', e => { if (e.key === 'Escape' && !$('v8Onboard').hidden) this.close(); });
      $('v8BetaChip')?.addEventListener('click', () => this.open(true));
      $('v8OnbReopen')?.addEventListener('click', () => this.open(true));
    },
  };
  async function refreshQueueBadge() {
    try { const q = await api('/api/my/queue'); const b = $('badge-queue-count'); if (b) b.textContent = q.filter(x => x.status !== 'cancelled').length; } catch {}
  }
  async function refreshConnectorBadge() {
    try { const d = await api('/api/connectors'); const b = $('badge-connectors-count'); if (b) b.textContent = d.channels.length; } catch {}
  }

  function roundRect(ctx, x, y, w, h, r) {
    ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
  }
  function wrap(ctx, text, maxW) {
    // Thai has no spaces: break by grapheme when needed.
    const out = []; let line = '';
    const seg = window.Intl && Intl.Segmenter ? [...new Intl.Segmenter('th', { granularity: 'word' }).segment(text)].map(s => s.segment) : [...text];
    for (const w of seg) {
      if (ctx.measureText(line + w).width > maxW && line) { out.push(line.trim()); line = w.trimStart(); }
      else line += w;
    }
    if (line.trim()) out.push(line.trim());
    return out;
  }
  async function copy(text) {
    if (!text) return toast('ไม่มีข้อความให้คัดลอก', 'error');
    try { await navigator.clipboard.writeText(text); toast('📋 คัดลอกแล้ว', 'success'); }
    catch { prompt('คัดลอกข้อความนี้:', text); }
  }

  // =========================================================== calendar honesty pills
  async function calendarPills() {
    const box = $('v8CalPlatformStatus'); if (!box) return;
    let chans = [];
    try { chans = (await api('/api/connectors')).channels.filter(c => c.has_token); } catch {}
    box.innerHTML = ['tiktok', 'shopee', 'facebook', 'instagram', 'line_oa'].map(pl => {
      const n = chans.filter(c => c.platform === pl).length;
      const label = pl === 'tiktok' || pl === 'shopee' ? 'ยังไม่เชื่อมต่อ (โพสต์เอง)' : n ? `เชื่อมแล้ว ${n}` : 'ยังไม่เชื่อมต่อ';
      return `<span class="v8-pill-status ${n ? 'is-on' : ''}" title="${PLATFORM_LABEL[pl]}">${PLATFORM_ICON[pl]} ${label}</span>`;
    }).join('');
  }

  // =========================================================== dashboard CTA
  function dashCta() {
    const dash = $('dash');
    if (!dash || $('v8DashCta')) return;
    dash.insertAdjacentHTML('afterbegin', `<div class="v8-dash-cta" id="v8DashCta">
      <div><strong>🚀 เริ่มสร้างคลิป TikTok แรกใน 4 ขั้นตอน</strong><div class="v8-small">มีสินค้าตัวอย่างและบทตัวอย่างให้ลองทันที — ไม่ต้องตั้งค่าอะไร</div></div>
      <button class="btn btn-primary" data-tab-go="studio">เริ่มเลย →</button></div>`);
    bindTabGo(dash);
  }

  // =========================================================== wiring
  function bindTabGo(root = document) {
    root.querySelectorAll('[data-tab-go]').forEach(b => { if (b._v8) return; b._v8 = 1; b.addEventListener('click', () => AAS.switchTab(b.dataset.tabGo)); });
    bindHelpLinks(root);
  }
  function bindHelpLinks(root = document) {
    root.querySelectorAll('[data-help-article]').forEach(b => { if (b._v8h) return; b._v8h = 1; b.addEventListener('click', () => Help.openArticle(b.dataset.helpArticle)); });
  }

  window.AASv8 = {
    productRows,
    radarShopeeCards: (items, q) => `<div style="margin:6px 0 8px;font-weight:700">🛒 สินค้าจริงจาก Shopee Affiliate (ราคา/ค่าคอมยืนยันจาก API) — "${esc(q)}"</div>` +
      (items.length ? `<div class="v8-product-grid">${items.map(it => Shopee.card(it, 'radar')).join('')}</div>` : stateBox('empty', 'ไม่พบสินค้าที่เข้าร่วม Affiliate สำหรับคำค้นนี้', null)),
    importItem: (i, s, toStudio) => Shopee.importItem(i, s, toStudio),
    shopeeStatus: () => Shopee.status(),
    async refreshProduct(id, btn) {
      if (btn) btn.disabled = true;
      try { const r = await api(`/api/my/products/${id}/refresh`, 'POST'); toast('🔄 ' + r.message, 'success'); AAS.reloadProducts(); }
      catch (e) { toast(e.message, 'error'); } finally { if (btn) btn.disabled = false; }
    },
    async deleteProduct(id) {
      if (!confirm('ลบสินค้านี้ (รวมบท/โปรเจกต์ที่ผูกไว้)?')) return;
      try { await api(`/api/my/products/${id}`, 'DELETE'); toast('ลบแล้ว'); AAS.reloadProducts(); Studio.boot = null; }
      catch (e) { toast(e.message, 'error'); }
    },
    openPublish: (id, cap) => Publish.open(id, cap),
    currentCaption: () => ($('v8Caption') ? $('v8Caption').value : ''),
    goConnectors: () => { $('v8PublishModal').hidden = true; AAS.switchTab('connectors'); },
    loadConnectors: () => Conn.load(),
    tiktokConnect() { TikTokConnect.open(); },
    tiktokPost(id) { TikTokPost.open(id); },
    closeTiktok() { TikTokPost.close(); },
    async oauth(platform, btn, returnTab = 'connectors') {
      btn.disabled = true; btn.textContent = 'กำลังเปิดหน้าล็อกอิน…';
      try { const r = await api(`/api/connectors/${platform}/start?return_tab=${returnTab}`, 'POST'); location.href = r.auth_url; }
      catch (e) { toast(e.message, 'error'); btn.disabled = false; btn.textContent = { facebook: 'Connect with Facebook', instagram: 'Connect with Instagram', tiktok: 'Continue with TikTok' }[platform] || 'เชื่อมต่อ'; }
    },
    async verify(id, btn) {
      btn.disabled = true; const t = btn.textContent; btn.textContent = 'กำลังตรวจ…';
      try {
        const r = await api(`/api/connectors/${id}/verify`, 'POST');
        const d = r.detail || {};
        toast(`✅ ${r.message}${d.followers != null ? ' · ผู้ติดตาม ' + Number(d.followers).toLocaleString() : ''}${d.basic_id ? ' · ' + d.basic_id : ''}`, 'success');
        Conn.load();
      } catch (e) { toast(e.message, 'error'); Conn.load(); }
      finally { btn.disabled = false; btn.textContent = t; }
    },
    async testPost(id, platform) {
      const broadcast = platform === 'line_broadcast';
      if (broadcast && !confirm('Broadcast ข้อความทดสอบหาเพื่อนทุกคนของ OA (นับโควต้า) ยืนยัน?')) return;
      const message = prompt('ข้อความทดสอบ (เว้นว่าง = ข้อความมาตรฐาน)', '✅ ทดสอบการเชื่อมต่อจาก Affiliate Auto Studio') ?? null;
      if (message === null) return;
      try {
        const r = await api(`/api/connectors/${id}/test-post`, 'POST', { message, line_mode: broadcast ? 'broadcast' : 'push', confirm_broadcast: broadcast });
        toast('✅ ' + r.message + (r.post_id ? ' · ' + r.post_id : ''), 'success'); Conn.loadLogs();
      } catch (e) { toast(e.message, 'error'); Conn.loadLogs(); }
    },
    async disconnect(id, name) {
      if (!confirm(`ตัดการเชื่อมต่อ "${name}"? (ควรถอนสิทธิ์แอปในการตั้งค่าของ Facebook/LINE ด้วย)`)) return;
      try { await api(`/api/connectors/${id}`, 'DELETE'); toast('ตัดการเชื่อมต่อแล้ว'); Conn.load(); } catch (e) { toast(e.message, 'error'); }
    },
    copy,
    loadHelp: () => Help.load(),
    openThread: id => Chat.openThread(id),
    openPay: () => Pay.open(),
    renderProducts,
    inlineEdit(btn) { inlineEdit(btn); },
    aiProduct(id) { AiProducts.open([id]); },
    closeAi() { AiProducts.close(); },
    toggleAiImage(id, on) { patchProduct(id, { use_ai_image: on }, on ? 'ใช้รูปที่ AI สร้าง' : 'กลับไปใช้รูปเดิม'); },
    async undoAi(id) {
      try { const r = await api(`/api/my/products/${id}/ai-undo`, 'POST'); toast(r.message, 'success'); AAS.reloadProducts(); }
      catch (e) { toast(e.message, 'error'); }
    },
    goKeys() { AAS.switchTab('keys'); setTimeout(() => document.querySelector('#keys [name=gemini], #keys input')?.focus(), 350); },
    editProduct(id) { EditProduct.open(id); },
    renameProduct(id, cur) { const t = (prompt('ชื่อสินค้าใหม่', cur) || '').trim(); if (t && t !== cur) patchProduct(id, { title: t }, 'เปลี่ยนชื่อแล้ว'); },
    editLink(id, cur) { const v = prompt('ลิงก์ affiliate (https://s.shopee.co.th/… หรือเว้นว่างเพื่อลบ)', cur); if (v === null) return; patchProduct(id, { offer_link: v.trim() }, v.trim() ? 'บันทึกลิงก์แล้ว' : 'ลบลิงก์แล้ว'); },
    toggleProduct(id, on) { patchProduct(id, { active: !!on }, on ? 'เปิดใช้งานสินค้า' : 'ปิดใช้งานสินค้า (จะไม่ขึ้นในหน้าสร้างคอนเทนต์)'); },
    toast: (m, t) => toast(m, t),
    askAbout() { AAS.switchTab('help'); },
    loadStudio: () => Studio.load(),
    openProject: id => Studio.openProject(id),
    async deleteProject(id) {
      if (!confirm('ลบโปรเจกต์นี้?')) return;
      try { await api(`/api/studio/projects/${id}`, 'DELETE'); if (Studio.project && Studio.project.id === id) { Studio.project = null; $('v8ScriptEditor').hidden = true; Studio.resetPreview(); Studio.renderClips(); } await Studio.load(); refreshQueueBadge(); }
      catch (e) { toast(e.message, 'error'); }
    },
    async showNotifications() {
      // Real, account-derived notifications only.
      const notes = [];
      try {
        const [u, b, q] = await Promise.all([api('/api/support/unread'), api('/api/studio/bootstrap'), api('/api/my/queue')]);
        if (u.unread) notes.push(`💬 มีข้อความซัพพอร์ตใหม่ ${u.unread} ข้อความ`);
        const running = b.projects.filter(p => p.status === 'clip_running').length;
        const failed = b.projects.filter(p => p.status === 'clip_failed').length;
        if (running) notes.push(`⏳ กำลังสร้างคลิป AI ${running} งาน`);
        if (failed) notes.push(`❌ คลิป AI ล้มเหลว ${failed} งาน (คืนเครดิตแล้ว)`);
        const waiting = q.filter(x => x.status === 'ready_manual').length;
        if (waiting) notes.push(`🎵 มีคลิปรอโพสต์เองใน TikTok ${waiting} รายการ`);
      } catch (e) { if (isAuthError(e)) return toast('เข้าสู่ระบบเพื่อดูการแจ้งเตือน'); }
      toast(notes.length ? notes.join('\n') : 'ยังไม่มีการแจ้งเตือนใหม่');
    },
    async cancelPost(id) {
      if (!confirm('ยกเลิกโพสต์ที่ตั้งเวลานี้? (โพสต์ที่ฝากคิวไว้ใน Facebook จะถูกลบด้วย)')) return;
      try { const r = await api(`/api/scheduled-posts/${id}`, 'DELETE'); toast(r.message); AutoPost.load(); } catch (e) { toast(e.message, 'error'); }
    },
    async retryPost(id) {
      try { await api(`/api/scheduled-posts/${id}/retry`, 'POST'); toast('ส่งใหม่แล้ว'); AutoPost.load(); } catch (e) { toast(e.message, 'error'); }
    },
    showClip: () => Studio.project && Studio.project.clip_url && Studio.showVideo(Studio.project.clip_url),
    studioWithProduct: id => Studio.open(id),
    async studioFromName(name) {
      name = String(name || '').trim();
      if (name.length < 3) return toast('ชื่อสินค้าต้องยาวอย่างน้อย 3 ตัวอักษร', 'error');
      try { const r = await api('/api/studio/quick-product', 'POST', { title: name.slice(0, 200), platform: 'other', url: '', source: 'manual' }); Studio.open(r.id); }
      catch (e) { toast(e.message, 'error'); }
    },
    async studioFromTitle(title, platform, url = '') {
      // Web leads are headlines: let the user trim them to a real product name first.
      const guess = String(title).replace(/\s+[-|–]\s+[^-|–]+$/, '').replace(/^\d+\s*(สุดยอด|อันดับ|รายการ)?\s*/, '').trim();
      const name = (prompt('ชื่อสินค้าที่จะใช้ทำบท (แก้ให้เหลือชื่อสินค้า)', guess || title) || '').trim();
      if (!name) return;
      if (name.length < 3) return toast('ชื่อสินค้าต้องยาวอย่างน้อย 3 ตัวอักษร', 'error');
      try { const r = await api('/api/studio/quick-product', 'POST', { title: name.slice(0, 200), platform: platform === 'shopee' ? 'shopee' : 'other', url: url || '', source: 'radar' }); Studio.open(r.id); }
      catch (e) { toast(e.message, 'error'); }
    },
  };

  document.addEventListener('aas:auth', () => {
    Profile.paint();
    // Login/logout changes who the chat belongs to: restart it cleanly.
    Chat.stop(); Studio.boot = null; Studio.project = null;
    if (document.querySelector('#help.active')) Help.load();
    if (document.querySelector('#studio.active')) Studio.load();
    if (document.querySelector('#connectors.active')) Conn.load();
    refreshConnectorBadge(); Unread.refresh();
  });

  document.addEventListener('aas:tab', e => {
    const t = e.detail;
    if (t === 'studio') Studio.load();
    if (t === 'connectors') Conn.load();
    if (t === 'help') Help.load();
    if (t === 'products') Shopee.status();
    if (t === 'calendar') calendarPills();
    if (t !== 'studio') { cancelAnimationFrame(Studio.raf); }
  });

  function init() {
    Shopee.bind(); Conn.bind(); Studio.bind(); AutoPost.bind(); Onboard.bind(); Profile.bind(); Pay.bind(); ImportFile.bind(); Fetch.bind();
    api('/api/beta/capacity').then(c => { if (!c.invite_only) $('regInviteCode')?.closest('.form-group')?.setAttribute('hidden', ''); }).catch(() => {});
    if (!new URLSearchParams(location.search).get('oauth')) setTimeout(() => Onboard.open(false), 700);
    document.querySelectorAll('[data-close]').forEach(b => b.addEventListener('click', () => { $(b.dataset.close).hidden = true; }));
    $('v8PublishSubmit')?.addEventListener('click', () => Publish.submit());
    $('v8HelpSearch')?.addEventListener('input', () => Help.loaded && Help.render());
    bindTabGo(document);
    dashCta();
    EditProduct.bind();
    AiProducts.bind();
    TikTokConnect.bind();
    $('v8TtClose')?.addEventListener('click', () => TikTokPost.close());
    $('v8TtModal')?.addEventListener('click', e => { if (e.target.id === 'v8TtModal') TikTokPost.close(); });
    document.addEventListener('keydown', e => { if (e.key !== 'Escape') return;
      if (!$('v8TtModal')?.hidden) TikTokPost.close();
      if (!$('v8TtConnect')?.hidden) TikTokConnect.close();
      if (!$('v8EditProduct')?.hidden) EditProduct.close();
      if (!$('v8Ai')?.hidden) AiProducts.close(); });
    const qs = new URLSearchParams(location.search);
    const tab = qs.get('tab');
    if (qs.get('oauth')) {
      const pl = PLATFORM_LABEL[qs.get('platform')] || qs.get('platform');
      if (qs.get('oauth') === 'success') toast(`✅ เชื่อมต่อ ${pl} สำเร็จ ${qs.get('count') || ''} บัญชี${qs.get('ig') && qs.get('ig') !== '0' ? ` (+ Instagram ${qs.get('ig')})` : ''}`, 'success');
      else toast(`❌ เชื่อมต่อ ${pl} ไม่สำเร็จ: ${qs.get('reason') || ''}`, 'error');
    }
    if (tab && document.getElementById(tab)) setTimeout(() => AAS.switchTab(tab), 300);
    if (qs.toString()) history.replaceState(null, '', location.pathname);
    setTimeout(() => { Unread.refresh(); refreshConnectorBadge(); refreshQueueBadge(); }, 1200);
    setInterval(() => { if (!Chat.ws) Unread.refresh(); }, 30000);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();

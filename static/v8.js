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

  function sourceChip(p) {
    const map = { shopee_affiliate_api: ['chip-success', 'Shopee API ✓'], manual: ['', 'กรอกเอง'], sample: ['', 'สินค้าตัวอย่าง'], radar: ['', 'จาก Radar'] };
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
        : c.platform === 'instagram'
          ? `<div class="v8-small v8-muted">${m.via === 'facebook' ? 'ผ่านเพจ ' + esc(m.page_name || '') : 'Instagram Login'}${c.token_expires_at ? ' · token หมดอายุ ' + esc(c.token_expires_at.slice(0, 10)) : ''}</div>`
          : `<div class="v8-small v8-muted">${esc(m.category || '')} · Page ID ${esc(c.account_id)}</div>`;
      return `<div class="v8-chan">
        <div class="v8-chan-head">${imgTag(m.picture || '', c.account_name, 'v8-avatar')}<div style="flex:1;min-width:0"><strong>${esc(c.account_name)}</strong>${extra}</div>${status}</div>
        <div class="v8-chan-actions">
          <button class="btn btn-ghost btn-sm" onclick="AASv8.verify(${c.id}, this)">📡 ตรวจสอบ</button>
          <button class="btn btn-ghost btn-sm" onclick="AASv8.testPost(${c.id}, '${c.platform}')">📤 ทดสอบส่ง</button>
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
          ${head('facebook', 'Facebook Pages', 'ล็อกอินกับ Facebook → เลือกเพจ → โพสต์รูป+แคปชั่น+ลิงก์ได้จริง (เชื่อมได้หลายเพจ)')}
          ${cfg.facebook.ready ? '' : notReady('Meta App')}
          <div class="v8-chan-list">${by('facebook').map(c => this.chanRow(c)).join('') || '<div class="v8-empty">ยังไม่มีเพจที่เชื่อม</div>'}</div>
          <button class="btn btn-primary v8-fb-btn" ${cfg.facebook.ready ? '' : 'disabled'} onclick="AASv8.oauth('facebook', this)">Connect with Facebook</button>
        </div>
        <div class="mf-card v8-conn-card">
          ${head('instagram', 'Instagram (Business/Creator)', 'เชื่อมผ่านเพจ Facebook ที่ผูก IG ไว้ (อัตโนมัติ) หรือ Instagram Login โดยตรง')}
          ${cfg.instagram.ready ? '' : (cfg.instagram.via_facebook_ready ? '<div class="v8-muted v8-small">💡 เชื่อม Facebook Page ที่ผูก IG ไว้ ระบบจะเพิ่ม IG ให้อัตโนมัติ</div>' : notReady('Instagram App'))}
          <div class="v8-chan-list">${by('instagram').map(c => this.chanRow(c)).join('') || '<div class="v8-empty">ยังไม่มีบัญชี IG ที่เชื่อม</div>'}</div>
          <button class="btn btn-primary v8-ig-btn" ${cfg.instagram.ready ? '' : 'disabled'} onclick="AASv8.oauth('instagram', this)">Connect with Instagram</button>
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
      bindHelpLinks($('v8ConnectorCards'));
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
        ['meta_app_id', 'ig_app_id', 'public_base_url'].forEach(k => { f[k].value = d[k].value || ''; f[k].disabled = d[k].from_env; f[k].title = d[k].from_env ? 'ตั้งค่าจาก ENV' : ''; });
        ['meta_app_secret', 'ig_app_secret'].forEach(k => { f[k].placeholder = d[k].set ? '•••••• (ตั้งไว้แล้ว — เว้นว่าง = ไม่เปลี่ยน)' : 'ยังไม่ได้ตั้ง'; f[k].disabled = d[k].from_env; });
        const cfg = this.data.config;
        $('v8RedirectInfo').innerHTML = `<div class="v8-small">ใส่ใน Meta App → Facebook Login → Valid OAuth Redirect URIs:<br><code class="v8-code">${esc(cfg.facebook.redirect_uri)}</code> <button type="button" class="btn btn-ghost btn-sm" onclick="AASv8.copy(${jsArg(cfg.facebook.redirect_uri)})">คัดลอก</button></div>
          <div class="v8-small">Instagram Business login → Redirect URL:<br><code class="v8-code">${esc(cfg.instagram.redirect_uri)}</code> <button type="button" class="btn btn-ghost btn-sm" onclick="AASv8.copy(${jsArg(cfg.instagram.redirect_uri)})">คัดลอก</button></div>
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

  // =========================================================== HELP CENTER + CHAT

  // =========================================================== FAQ (replaces live chat)
  const FAQ_Q = {
    quickstart: 'เริ่มใช้งานครั้งแรกต้องทำอะไรบ้าง?',
    navigation: 'แต่ละเมนูใน Sidebar ใช้ทำอะไร?',
    studio: 'สร้างคลิป TikTok แบบ UGC ได้อย่างไร?',
    autopost: 'ตั้งเวลา Auto-Post ไป Facebook / Instagram / LINE ได้อย่างไร?',
    'shopee-credentials': 'จะขอ Shopee Affiliate AppID / Secret ได้จากที่ไหน?',
    'shopee-add-product': 'เพิ่มสินค้าจาก Shopee พร้อมรูป ราคา และค่าคอมได้อย่างไร?',
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
          const arts = d.articles.filter(a => a.id !== 'support-chat').map(a => ({ ...a, title: FAQ_Q[a.id] || a.title }));
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
    boot: null, productId: null, style: 'ugc_pov', project: null, img: null, playing: false, raf: 0, pollT: 0,
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
      $('v8Engine').innerHTML = `<div><strong>🎬 เอนจินวิดีโอ (Phase 1):</strong> ${esc(e.label)}</div>
        <div class="v8-small v8-muted">${esc(e.note)}</div>
        <div class="v8-engine-cost">ต้นทุนคลิป AI: <strong>${e.cost_credits} เครดิต</strong> · คงเหลือ <strong id="v8CreditsLeft">${this.boot.credits}</strong> เครดิต · คลิปพรีวิว UGC: <strong>ฟรี</strong></div>`;
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
      this.renderClips(); this.renderAi(); this.renderPlatforms(); this.paintSteps(); this.renderProjects(); AutoPost.render();
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
        toast('🎲 สุ่มบทใหม่แล้ว', 'success');
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
    async aiClip() {
      const e = this.boot.engine;
      if (!this.project) return toast('สร้างบทก่อน', 'error');
      if (e.cost_credits && !confirm(`สร้างคลิป AI ด้วย ${e.label}\nใช้ ${e.cost_credits} เครดิต (คงเหลือ ${this.boot.credits})\nถ้าล้มเหลว ระบบคืนเครดิตอัตโนมัติ\n\nยืนยัน?`)) return;
      if (this.dirty) { try { await this.saveScript(true); } catch { return; } }
      $('v8AiClip').disabled = true;
      try {
        const r = await api(`/api/studio/projects/${this.project.id}/ai-clip`, 'POST');
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



  // =========================================================== PROFILE MENU (top-right)
  const Profile = {
    paint() {
      const me = AAS.getMe() || {}, on = !!me.id;
      $('v8Profile').hidden = !on;
      const trig = $('authModalTriggerBtn'); if (trig) trig.hidden = on;
      if (!on) { this.close(); return; }
      const name = me.username || '-', ini = name.slice(0, 1).toUpperCase();
      $('v8PfAv').textContent = ini; $('v8PmAv').textContent = ini;
      $('v8PfName').textContent = name; $('v8PmName').textContent = name;
      $('v8PfRole').textContent = me.role === 'admin' ? 'ADMIN' : 'MEMBER';
      $('v8PmEmail').textContent = me.email || '';
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
          ${row('ชื่อผู้ใช้', esc(me.username))}${row('อีเมล', esc(me.email || '-'))}
          ${row('สถานะ', me.role === 'admin' ? '<span class="chip chip-success">ผู้ดูแลระบบ</span>' : '<span class="chip">สมาชิก Beta</span>')}
          ${row('เครดิตคงเหลือ', `⚡ ${Number(me.credits || 0).toLocaleString('th-TH')} เครดิต`)}
        </tbody></table>
        <p class="v8-muted v8-small">ต้องการเปลี่ยนรหัสผ่านหรือลบบัญชี แจ้งทีมงานที่เมนู "เสนอไอเดีย / แจ้งปัญหา" — ช่วง Beta ผู้ดูแลจะดำเนินการให้</p>
        <div class="v8-onb-nav"><button class="btn btn-secondary btn-sm" data-acc="topup">💳 เติมเงิน</button><button class="btn btn-ghost btn-sm" data-acc="logout">🚪 ออกจากระบบ</button></div>`;
        box.querySelector('[data-acc=topup]').addEventListener('click', () => { $('v8Account').hidden = true; AAS.openTopup(); });
        box.querySelector('[data-acc=logout]').addEventListener('click', () => AAS.logout());
      } catch (e) { box.innerHTML = stateBox('error', 'โหลดข้อมูลบัญชีไม่สำเร็จ: ' + e.message, null); }
    },
    act(k) {
      this.close();
      const me = AAS.getMe() || {};
      if (k === 'members') return me.role === 'admin' ? AAS.switchTab('users_mgmt') : this.account();
      if (k === 'topup') return AAS.openTopup();
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
    async oauth(platform, btn, returnTab = 'connectors') {
      btn.disabled = true; btn.textContent = 'กำลังเปิดหน้าล็อกอิน…';
      try { const r = await api(`/api/connectors/${platform}/start?return_tab=${returnTab}`, 'POST'); location.href = r.auth_url; }
      catch (e) { toast(e.message, 'error'); btn.disabled = false; btn.textContent = platform === 'facebook' ? 'Connect with Facebook' : 'Connect with Instagram'; }
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
    Shopee.bind(); Conn.bind(); Studio.bind(); AutoPost.bind(); Onboard.bind(); Profile.bind();
    if (!new URLSearchParams(location.search).get('oauth')) setTimeout(() => Onboard.open(false), 700);
    document.querySelectorAll('[data-close]').forEach(b => b.addEventListener('click', () => { $(b.dataset.close).hidden = true; }));
    $('v8PublishSubmit')?.addEventListener('click', () => Publish.submit());
    $('v8HelpSearch')?.addEventListener('input', () => Help.loaded && Help.render());
    bindTabGo(document);
    dashCta();
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

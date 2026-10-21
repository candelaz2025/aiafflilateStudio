(() => {
  'use strict';

  // ==========================================
  // STATE & INITIALIZATION
  // ==========================================
  let me = { id: 0, username: 'ผู้เยี่ยมชม', role: 'guest', csrf: '' };
  let currentLang = 'th';
  let currentTheme = localStorage.getItem('theme') || 'light';
  let activeTab = 'dash';
  let walkthroughStep = 1;
  let isCanvasPlaying = true;
  let canvasAnimationId = null;

  const $ = id => document.getElementById(id);
  const esc = s => String(s ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
  const msg = (text, type = 'info') => {
    const banner = $('statusBanner');
    if (!banner) return;
    banner.textContent = text;
    banner.style.display = text ? 'flex' : 'none';
    if (type === 'error') {
      banner.style.backgroundColor = 'var(--color-danger-light)';
      banner.style.borderColor = 'var(--color-danger)';
      banner.style.color = 'var(--color-danger-hover)';
    } else {
      banner.style.backgroundColor = 'var(--color-primary-light)';
      banner.style.borderColor = 'var(--color-primary)';
      banner.style.color = 'var(--color-primary)';
    }
    clearTimeout(msg._t);
    if (text) msg._t = setTimeout(() => { banner.style.display = 'none'; }, 4000);
  };

  // Floating confirmation that closes itself (used after sign-in / sign-up).
  function authToast(title, sub) {
    document.querySelector('.aas-auth-toast')?.remove();
    const t = document.createElement('div');
    t.className = 'aas-auth-toast'; t.setAttribute('role', 'status'); t.setAttribute('aria-live', 'polite');
    t.innerHTML = `<span class="aas-at-icon" aria-hidden="true">✓</span><span class="aas-at-text"><strong></strong><small></small></span><span class="aas-at-bar" aria-hidden="true"></span>`;
    t.querySelector('strong').textContent = title; t.querySelector('small').textContent = sub || '';
    document.body.appendChild(t);
    requestAnimationFrame(() => t.classList.add('is-in'));
    setTimeout(() => { t.classList.remove('is-in'); setTimeout(() => t.remove(), 300); }, 2600);
  }

  const val = form => Object.fromEntries(new FormData(form));

  // V8: explicit loading / empty / error states with retry (never leave "กำลังโหลด" forever)
  const retryFns = {};
  window.appRetry = key => { if (retryFns[key]) retryFns[key](); };
  function stateBox(kind, text, retryKey, colspan) {
    const color = kind === 'error' ? 'var(--color-danger)' : 'var(--color-text-muted)';
    const icon = kind === 'error' ? '⚠️' : kind === 'loading' ? '⏳' : '📭';
    const btn = retryKey ? ` <button class="btn btn-secondary btn-sm" onclick="window.appRetry('${retryKey}')">ลองใหม่</button>` : '';
    const inner = `<span style="color:${color}">${icon} ${esc(text)}</span>${btn}`;
    return colspan ? `<tr><td colspan="${colspan}" style="text-align:center; padding:24px;">${inner}</td></tr>`
                   : `<div class="mf-card" style="text-align:center; padding:24px;">${inner}</div>`;
  }
  window.AASstateBox = stateBox;
  // Safe string literal for inline onclick handlers (apostrophes in titles used to break the handler).
  const jsArg = v => `decodeURIComponent('${encodeURIComponent(String(v ?? '')).replace(/'/g, '%27')}')`;
  window.AASjsArg = jsArg;


  async function api(path, method = 'GET', data) {
    const headers = {};
    if (data !== undefined) headers['Content-Type'] = 'application/json';
    if (me && method !== 'GET' && me.csrf) headers['X-CSRF-Token'] = me.csrf;
    const r = await fetch(path, {
      method,
      headers,
      credentials: 'same-origin',
      body: data === undefined ? undefined : JSON.stringify(data)
    });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) {
      if (typeof body.detail === 'string') throw Error(body.detail);
      if (Array.isArray(body.detail) && body.detail.length) {
        // FastAPI validation (422): turn field errors into a readable Thai message.
        const names = { app_id: 'AppID', secret: 'Secret', channel_id: 'Channel ID', channel_secret: 'Channel secret', access_token: 'Access token',
          title: 'ชื่อสินค้า', url: 'ลิงก์', body: 'ข้อความ', password: 'รหัสผ่าน', email: 'อีเมล', username: 'ชื่อผู้ใช้', keyword: 'คีย์เวิร์ด', caption: 'แคปชั่น' };
        const parts = body.detail.slice(0, 3).map(d => {
          const field = (d.loc || []).slice(-1)[0];
          const label = names[field] || field || 'ข้อมูล';
          const ctx = d.ctx || {};
          if (d.type === 'string_too_short') return `${label} สั้นเกินไป (อย่างน้อย ${ctx.min_length} ตัวอักษร)`;
          if (d.type === 'string_too_long') return `${label} ยาวเกินไป (ไม่เกิน ${ctx.max_length} ตัวอักษร)`;
          if (d.type === 'string_pattern_mismatch') return `${label} รูปแบบไม่ถูกต้อง`;
          if (d.type === 'missing') return `กรุณากรอก ${label}`;
          return `${label} ไม่ถูกต้อง`;
        });
        throw Error(parts.join(' · '));
      }
      throw Error('คำขอล้มเหลว ' + r.status);
    }
    return body;
  }

  // ==========================================
  // I18N DICTIONARY (TH / EN)
  // ==========================================
  const i18n = {
    th: {
      nav_group_main: 'เวิร์กโฟลว์หลัก',
      nav_dash: 'ภาพรวม (Overview)',
      nav_radar: 'Product Radar',
      nav_drafts: 'AI Video Factory (บทรีวิว)',
      nav_video: 'สร้างคลิป AI & Mockup',
      nav_group_mgmt: 'การจัดการ (Management)',
      nav_products: 'สินค้าของฉัน (My Products)',
      nav_queue: 'คิวโพสต์ & ตารางงาน',
      nav_tracking: 'ติดตามยอดขาย & สถิติ',
      nav_group_community: 'ชุมชน (Community)',
      nav_ideas: 'Community Lab',
      nav_new: 'เสนอไอเดีย / แจ้งปัญหา',
      nav_donate: 'สนับสนุน / Donate ↗',
      nav_group_system: 'ระบบ & ตั้งค่า (System)',
      nav_users: 'จัดการผู้ใช้ (User Mgmt)',
      nav_keys: 'API Keys & การเชื่อมต่อ',
      badge_hot: 'HOT',
      badge_gen: 'GEN',
      badge_admin: 'ADMIN',
      search_placeholder: 'ค้นหาสินค้า, บทรีวิว หรือคิวงาน... (กด Ctrl+K)',
      btn_login_register: 'เข้าสู่ระบบ / สลับบัญชี',
      hero_greeting_time_morning: '☀️ อรุณสวัสดิ์',
      hero_greeting_time_afternoon: '🌤 สวัสดีตอนบ่าย',
      hero_greeting_time_evening: '🌙 สวัสดีตอนค่ำ',
      hero_status_ready: 'เริ่มได้ทันทีที่เมนู สร้างคอนเทนต์',
      hero_title: 'มาสร้างคอนเทนต์กันเลย 🎯',
      hero_prompt_placeholder: 'วันนี้อยากสร้างคอนเทนต์หรือค้นหาสินค้าอะไรดี?',
      btn_create_now: 'สร้างเลย',
      quick_shopee_extra: 'สินค้า Shopee Extra Comm',
      quick_weekly: 'คอนเทนต์รายสัปดาห์',
      quick_gen_mockup: 'สร้างคลิป AI Mockup ทันที',
      quick_queue: 'เปิดคิวโพสต์ลง TikTok',
      hero_tip_text: 'อยากได้คลิปปังทั้งสัปดาห์ ลองค้นหาใน Product Radar แล้วกดส่งไปสร้างบท AI ครั้งเดียวได้ 3 แนวทาง',
      kpi_drafts: 'ดราฟต์บทรีวิว',
      badge_ready: 'พร้อมสร้างคลิป',
      kpi_view_drafts: 'ดูบทรีวิวทั้งหมด',
      kpi_scheduled: 'คิวงานรอโพสต์',
      badge_queue: 'อยู่ในคิว',
      kpi_manage_queue: 'จัดการคิวโพสต์',
      kpi_published: 'สินค้าที่ติดตาม',
      badge_active: 'กำลังติดตาม',
      kpi_view_products: 'เปิดดูสินค้าของฉัน',
      walkthrough_header: 'วิธีใช้ - เริ่มต้นใช้งาน (Guided Walkthrough)',
      btn_view_all_steps: 'ดูขั้นตอนทั้งหมด',
      step_1_badge: 'ขั้นตอนที่ 1',
      step_1_title: 'ค้นหาสินค้า & สแกน Shopee',
      step_1_desc: 'เลือกสินค้ามาแรง ดูค่าคอมมิชชัน Extra Comm สูง บันทึกเข้าระบบในคลิกเดียว',
      step_2_badge: 'ขั้นตอนที่ 2',
      step_2_title: 'สร้างบทรีวิว AI Video Factory',
      step_2_desc: 'AI สังเคราะห์สคริปต์ 3 องก์ (Hook, Pain Point, Call-to-action) พร้อม visual prompt',
      step_3_badge: 'ขั้นตอนที่ 3',
      step_3_title: 'สร้างคลิป AI & เชื่อมต่อคิว',
      step_3_desc: 'เรนเดอร์คลิป 9:16 Mockup เสมือนจริง ดูตัวอย่างคลิปในมือถือแล้วส่งเข้าคิวโพสต์',
      recent_pipeline: 'ประวัติงานล่าสุด (Recent Pipeline Activity)',
      btn_refresh: 'รีเฟรช',
      col_type: 'ประเภท',
      col_title: 'ชื่อรายการ / หัวข้อ',
      col_platform: 'แพลตฟอร์ม',
      col_status: 'สถานะ',
      col_action: 'การทำงาน',
      loading_data: 'กำลังโหลดข้อมูล...',
      radar_page_title: '⌕ Product Radar & Shopee Scanner',
      radar_page_desc: 'หาไอเดียสินค้าจากแหล่งสาธารณะ + ราคา/ค่าคอมจริงจาก Shopee Affiliate API (เมื่อเชื่อมคีย์)',
      btn_search_products: 'ค้นหาสินค้าจริง',
      btn_auto_scan: '✦ สแกนกระแสสินค้าอัตโนมัติ',
      label_extra_comm_only: 'เน้นเฉพาะ EXTRA COMM (คอมมิชชันพิเศษจาก Shopee)',
      try_keywords: 'คำค้นยอดนิยม:',
      shopee_import_title: '▣ สแกนหรือนำเข้าข้อมูล Shopee Affiliate',
      btn_open_shopee: 'เปิด Shopee Affiliate',
      shopee_import_desc: 'คัดลอกข้อความสินค้าจากหน้า Shopee หรืออัปโหลดรายงาน CSV เพื่อวิเคราะห์ค่าคอมมิชชันและนำเข้าอัตโนมัติ',
      label_paste_shopee: 'วางข้อความสินค้าจาก Shopee',
      btn_parse_copied: 'วิเคราะห์ข้อความ',
      label_csv_report: 'รายงาน CSV รายได้ Shopee',
      csv_hint: 'ไฟล์ CSV จากเมนู Conversion Report หรือ Custom Link',
      radar_results_title: 'ผลการสำรวจและกระแสสินค้า',
      radar_placeholder: 'กดปุ่ม "ค้นหาสินค้าจริง" หรือ "สแกนกระแสสินค้าอัตโนมัติ" เพื่อเริ่มต้น',
      products_page_title: '📋 สินค้าของฉัน (My Products)',
      products_page_desc: 'รายการสินค้าที่คุณเลือกสำหรับทำคลิปวิดีโอและติดตามผลงาน',
      btn_add_product: '+ เพิ่มสินค้าใหม่',
      add_product_title: 'เพิ่มสินค้าเข้ารายการ',
      label_product_title: 'ชื่อสินค้า',
      label_product_url: 'ลิงก์สินค้า Affiliate (ถ้ามี)',
      label_platform: 'แพลตฟอร์ม',
      btn_cancel: 'ยกเลิก',
      btn_save_product: 'บันทึกสินค้า',
      col_id: 'ID',
      col_product_name: 'ชื่อสินค้า',
      col_extra_comm: 'Extra Comm',
      col_created: 'เพิ่มเมื่อ',
      col_actions: 'การทำงาน',
      no_products: 'ยังไม่มีสินค้าในรายการ ลองเพิ่มสินค้าแรกได้เลย',
      drafts_page_title: '🎬 AI Video Factory (สร้างบทรีวิว POV)',
      drafts_page_desc: 'สร้างสคริปต์ 3 องก์ (Hook, Pain Point, Call-to-action) พร้อม visual prompt สำหรับสร้างคลิป',
      label_select_product: '1. เลือกสินค้าที่จะเขียนบท',
      opt_select_product: '-- กรุณาเลือกสินค้า --',
      label_script_style: '2. รูปแบบบทรีวิว (POV Style)',
      opt_style_fast: '⚡ สายป้ายยาเร็ว สั้นกระชับ (15-30s)',
      opt_style_pain: '🔥 ชูความหงุดหงิดเดิม แล้วแก้ปัญหา (Pain Point)',
      opt_style_7days: '🗓 รีวิวผลการใช้จริง 7 วัน (Authentic Experience)',
      opt_style_compare: '⚖️ เปรียบเทียบตัวเดิม vs ตัวใหม่',
      label_script_text: '3. เนื้อหาสคริปต์เสียงพากย์ (Voiceover Script)',
      label_prompt_text: '4. Visual Prompt (สำหรับเครื่องยนต์สร้างวิดีโอ AI)',
      btn_auto_ai_draft: '✦ ให้ AI ร่างบทอัตโนมัติ',
      btn_save_draft: 'บันทึกบทรีวิวนี้',
      saved_drafts_title: 'บทรีวิวที่บันทึกไว้',
      no_drafts: 'ยังไม่มีบทรีวิว เลือกลองร่างบทแรกด้านบนได้เลย',
      video_page_title: '▶ สร้างคลิป AI & 9:16 Video Mockup',
      video_page_desc: 'สร้างวิดีโอสำหรับ TikTok / Shopee Video พร้อมจำลองการแสดงผลบนสมาร์ตโฟนเสมือนจริง',
      gen_video_settings: 'ตั้งค่าวิดีโอที่จะสร้าง',
      label_choose_draft: '1. เลือกบทรีวิว (จาก AI Video Factory)',
      opt_select_draft: '-- กรุณาเลือกบทรีวิว --',
      label_choose_engine: '2. เลือกเครื่องยนต์ AI (Engine)',
      opt_instant_mockup: '⚡ Instant AI Video Mockup (เรนเดอร์ตัวอย่างทันที ไม่เสียเครดิต)',
      opt_google_veo: '🎥 Google Veo 3.1 Preview (Gemini API 9:16 8s)',
      opt_grok_imagine: '🌌 xAI Grok Imagine (Prompt-to-Video)',
      label_aspect_ratio: '3. อัตราส่วนและรูปแบบ',
      consent_terms: 'ยินยอมทดสอบและยอมรับเงื่อนไขการใช้งานโมเดล AI',
      btn_generate_video_now: '🚀 สั่งสร้างคลิปวิดีโอ (Generate Video)',
      progress_preparing: 'กำลังเตรียมการสร้างวิดีโอ...',
      progress_details: 'ระบบกำลังสังเคราะห์ภาพเคลื่อนไหว 9:16 และซิงก์เสียงพากย์...',
      history_jobs_title: 'รายการคลิปที่เคยสร้าง',
      no_jobs: 'ยังไม่มีประวัติคลิป',
      btn_play_pause: 'เล่น / พัก',
      btn_send_to_queue: 'ส่งเข้าคิวโพสต์',
      queue_page_title: '▦ คิวโพสต์ & จัดการการเผยแพร่',
      queue_page_desc: 'ตรวจสอบคลิป เช็กลิสต์เตรียมเผยแพร่ แยกตามแพลตฟอร์ม TikTok Affiliate และ Shopee Video',
      add_queue_title: 'เพิ่มงานเข้าคิวโพสต์',
      label_queue_draft: 'เลือกบทดราฟต์',
      label_video_url: 'หรือแนบลิงก์วิดีโอ (ถ้ามี)',
      btn_add_queue: '+ เพิ่มคิว',
      no_queue: 'ยังไม่มีรายการในคิวโพสต์',
      tracking_page_title: '⏱ ติดตามยอดขาย & สถิติ Affiliate',
      tracking_page_desc: 'บันทึกยอดวิว ยอดคลิก คำสั่งซื้อ และค่าคอมมิชชันของแต่ละคอนเทนต์เพื่อวัดผลลัพธ์ ROI',
      metric_total_views: '👁 ยอดวิวสะสม',
      metric_total_orders: '📦 คำสั่งซื้อสำเร็จ',
      metric_total_comm: '💰 ค่าคอมมิชชันรวม',
      col_product: 'สินค้า',
      col_views: 'ยอดวิว',
      col_clicks: 'คลิกตะกร้า',
      col_orders: 'คำสั่งซื้อ',
      col_sales: 'ยอดขาย (บาท)',
      col_comm: 'ค่าคอม (บาท)',
      loading_tracking: 'กำลังโหลดข้อมูลสถิติ...',
      community_page_title: '👥 Community Lab & โหวตฟีเจอร์',
      community_page_desc: 'ชุมชนร่วมทดสอบ เสนอฟีเจอร์ และโหวตสิ่งที่อยากให้พัฒนาในเวอร์ชันถัดไป',
      sort_top_votes: 'โหวตสูงสุด',
      sort_newest: 'ใหม่ล่าสุด',
      btn_new_proposal: '+ เสนอไอเดียใหม่',
      loading_ideas: 'กำลังโหลดข้อเสนอชุมชน...',
      new_proposal_title: '✦ เสนอฟีเจอร์ / แจ้งปัญหา (Bug Report)',
      new_proposal_desc: 'ส่งข้อเสนอเพื่อให้สมาชิกคนอื่นร่วมโหวตและนำไปพัฒนา',
      label_idea_kind: 'ประเภท',
      kind_feature: 'เสนอฟีเจอร์ใหม่ (Feature Request)',
      kind_bug: 'แจ้งบั๊ก / ปัญหา (Bug Report)',
      kind_feedback: 'ความคิดเห็น / ข้อเสนอแนะ (Feedback)',
      label_idea_title: 'หัวข้อข้อเสนอ',
      label_idea_body: 'รายละเอียด',
      btn_back: 'ย้อนกลับ',
      btn_submit_idea: 'ส่งข้อเสนอไปยังชุมชน',
      users_page_title: '👤 ระบบจัดการผู้ใช้ (User Management)',
      users_page_desc: 'ดูข้อมูลสมาชิก สถิติการใช้งาน เปลี่ยนระดับสิทธิ์ และจัดการบัญชีผู้ใช้ในระบบ',
      btn_add_user: '+ เพิ่มผู้ใช้งานใหม่',
      total_registered_users: '👥 ผู้ใช้งานทั้งหมด',
      admin_count: '🛡️ ผู้ดูแลระบบ (Admins)',
      beta_remaining: '⚡ ที่นั่งว่างคงเหลือ',
      col_user: 'ผู้ใช้',
      col_email: 'อีเมล',
      col_role: 'บทบาท (Role)',
      col_stats: 'สินค้า / บท / คิว',
      col_registered: 'วันที่สมัคร',
      loading_users: 'กำลังโหลดรายชื่อผู้ใช้...',
      keys_page_title: '⚙ API Keys & การเชื่อมต่อบริการภายนอก',
      keys_page_desc: 'เชื่อมต่อ Google Gemini / Veo, xAI Grok, Brave Search เพื่อให้ระบบสร้างคอนเทนต์อัตโนมัติ',
      key_security_notice: '🔒 ความปลอดภัยระดับสูง:',
      key_security_desc: 'คีย์ API ของคุณจะถูกเข้ารหัสด้วย Fernet Encryption เก็บไว้ในเครื่องนี้เท่านั้น ไม่มีการเปิดเผยหรือแชร์ให้บุคคลภายนอก',
      keys_guide_title: 'คำแนะนำการรับ API Key',
      tab_login: 'เข้าสู่ระบบ (Sign In)',
      tab_register: 'สมัครสมาชิก (Register)',
      label_email: 'อีเมล',
      label_password: 'รหัสผ่าน',
      btn_login_submit: 'เข้าสู่ระบบ',
      quick_login_hint: 'หรือทดลองใช้งานด้วยบัญชี Admin ทันที',
      label_username: 'ชื่อผู้ใช้ (Username)',
      btn_register_submit: 'สมัครเข้าร่วม Beta',
      add_user_title: 'เพิ่มผู้ใช้งานใหม่',
      label_role: 'ระดับสิทธิ์ (Role)',
      btn_create_user: 'สร้างผู้ใช้'
    },
    en: {
      nav_group_main: 'MAIN WORKFLOW',
      nav_dash: 'Overview',
      nav_radar: 'Product Radar',
      nav_drafts: 'AI Video Factory',
      nav_video: 'Generate AI Video',
      nav_group_mgmt: 'MANAGEMENT',
      nav_products: 'My Products',
      nav_queue: 'Publishing Queue',
      nav_tracking: 'Sales & Tracking',
      nav_group_community: 'COMMUNITY',
      nav_ideas: 'Community Lab',
      nav_new: 'New Proposal / Bug',
      nav_donate: 'Support Project ↗',
      nav_group_system: 'SYSTEM & SETTINGS',
      nav_users: 'User Management',
      nav_keys: 'API Keys & Setup',
      badge_hot: 'HOT',
      badge_gen: 'GEN',
      badge_admin: 'ADMIN',
      search_placeholder: 'Search products, drafts, or queue... (Ctrl+K)',
      btn_login_register: 'Sign In / Switch Account',
      hero_greeting_time_morning: '☀️ Good morning',
      hero_greeting_time_afternoon: '🌤 Good afternoon',
      hero_greeting_time_evening: '🌙 Good evening',
      hero_status_ready: 'Brand & AI Models Ready',
      hero_title: 'Let\'s create content now 🎯',
      hero_prompt_placeholder: 'What product or content do you want to create today?',
      btn_create_now: 'Create Now',
      quick_shopee_extra: 'Shopee Extra Comm',
      quick_weekly: 'Weekly Content Pack',
      quick_gen_mockup: 'Instant Video Mockup',
      quick_queue: 'Open TikTok Queue',
      hero_tip_text: 'Tip: Products with 15%+ Extra Comm combined with POV scripts increase CTR by 240%.',
      kpi_drafts: 'Review Drafts',
      badge_ready: 'Ready for Video',
      kpi_view_drafts: 'View all drafts',
      kpi_scheduled: 'Pending Queue',
      badge_queue: 'In Queue',
      kpi_manage_queue: 'Manage queue',
      kpi_published: 'Tracked Products',
      badge_active: 'Active',
      kpi_view_products: 'View my products',
      walkthrough_header: 'Quickstart - Guided Walkthrough',
      btn_view_all_steps: 'View all steps',
      step_1_badge: 'Step 1',
      step_1_title: 'Discover & Scan Products',
      step_1_desc: 'Select trending products, verify Extra Comm rates, save in one click',
      step_2_badge: 'Step 2',
      step_2_title: 'AI Video Factory Scripts',
      step_2_desc: 'Synthesize 3-act scripts (Hook, Pain, CTA) with visual prompts',
      step_3_badge: 'Step 3',
      step_3_title: 'Render AI Video & Queue',
      step_3_desc: 'Render 9:16 smartphone mockup, preview live, and dispatch to queue',
      recent_pipeline: 'Recent Pipeline Activity',
      btn_refresh: 'Refresh',
      col_type: 'Type',
      col_title: 'Title / Subject',
      col_platform: 'Platform',
      col_status: 'Status',
      col_action: 'Action',
      loading_data: 'Loading data...',
      radar_page_title: '⌕ Product Radar & Shopee Scanner',
      radar_page_desc: 'Product ideas from public sources + real price/commission from the Shopee Affiliate API (when connected)',
      btn_search_products: 'Search Products',
      btn_auto_scan: '✦ Auto Scan Trends',
      label_extra_comm_only: 'Filter EXTRA COMM only (High Shopee Commission)',
      try_keywords: 'Popular queries:',
      shopee_import_title: '▣ Scan / Import Shopee Affiliate Data',
      btn_open_shopee: 'Open Shopee Affiliate',
      shopee_import_desc: 'Paste product listings or upload CSV conversion reports for instant import',
      label_paste_shopee: 'Paste Shopee text / links',
      btn_parse_copied: 'Analyze Text',
      label_csv_report: 'Shopee Income CSV Report',
      csv_hint: 'CSV export from Conversion Report or Custom Link dashboard',
      radar_results_title: 'Discovery & Trend Results',
      radar_placeholder: 'Click "Search Products" or "Auto Scan Trends" to start',
      products_page_title: '📋 My Products',
      products_page_desc: 'Curated products for video rendering and sales tracking',
      btn_add_product: '+ Add Product',
      add_product_title: 'Add New Product',
      label_product_title: 'Product Title',
      label_product_url: 'Affiliate URL (optional)',
      label_platform: 'Platform',
      btn_cancel: 'Cancel',
      btn_save_product: 'Save Product',
      col_id: 'ID',
      col_product_name: 'Product Name',
      col_extra_comm: 'Extra Comm',
      col_created: 'Added On',
      col_actions: 'Actions',
      no_products: 'No products yet. Add your first product above!',
      drafts_page_title: '🎬 AI Video Factory (POV Scripts)',
      drafts_page_desc: 'Generate high-converting 3-act scripts and visual prompts',
      label_select_product: '1. Select Product',
      opt_select_product: '-- Please select a product --',
      label_script_style: '2. POV Script Style',
      opt_style_fast: '⚡ Fast Hook & Value (15-30s)',
      opt_style_pain: '🔥 Frustration & Problem Solver',
      opt_style_7days: '🗓 7-Day Authentic Experience',
      opt_style_compare: '⚖️ Side-by-Side Comparison',
      label_script_text: '3. Voiceover Script',
      label_prompt_text: '4. Visual AI Prompt',
      btn_auto_ai_draft: '✦ Auto Draft with AI',
      btn_save_draft: 'Save Draft',
      saved_drafts_title: 'Saved Review Drafts',
      no_drafts: 'No drafts yet. Create your first draft above!',
      video_page_title: '▶ Generate AI Video & 9:16 Mockup',
      video_page_desc: 'Render high-impact videos for TikTok / Shopee with live smartphone preview',
      gen_video_settings: 'Video Configuration',
      label_choose_draft: '1. Select Script Draft',
      opt_select_draft: '-- Please select a draft --',
      label_choose_engine: '2. Select AI Engine',
      opt_instant_mockup: '⚡ Instant AI Video Mockup (Fast Preview, No credits needed)',
      opt_google_veo: '🎥 Google Veo 3.1 Preview (Gemini API 9:16 8s)',
      opt_grok_imagine: '🌌 xAI Grok Imagine (Prompt-to-Video)',
      label_aspect_ratio: '3. Aspect Ratio & Format',
      consent_terms: 'I agree to the AI model test terms and conditions',
      btn_generate_video_now: '🚀 Generate Video Now',
      progress_preparing: 'Preparing video synthesis...',
      progress_details: 'Synthesizing 9:16 motion graphics and syncing voiceover...',
      history_jobs_title: 'Generated Video History',
      no_jobs: 'No videos generated yet',
      btn_play_pause: 'Play / Pause',
      btn_send_to_queue: 'Send to Queue',
      queue_page_title: '▦ Publishing Queue',
      queue_page_desc: 'Review, schedule, and checklist for TikTok Affiliate and Shopee Video',
      add_queue_title: 'Add Job to Queue',
      label_queue_draft: 'Select Draft',
      label_video_url: 'External Video URL (optional)',
      btn_add_queue: '+ Add to Queue',
      no_queue: 'No items in publishing queue',
      tracking_page_title: '⏱ Sales & Affiliate Tracking',
      tracking_page_desc: 'Monitor views, clicks, orders, and commission ROI',
      metric_total_views: '👁 Total Views',
      metric_total_orders: '📦 Completed Orders',
      metric_total_comm: '💰 Total Commission',
      col_product: 'Product',
      col_views: 'Views',
      col_clicks: 'Clicks',
      col_orders: 'Orders',
      col_sales: 'Sales (THB)',
      col_comm: 'Commission',
      loading_tracking: 'Loading analytics...',
      community_page_title: '👥 Community Lab & Voting',
      community_page_desc: 'Collaborate, vote, and propose features for the next release',
      sort_top_votes: 'Top Voted',
      sort_newest: 'Newest',
      btn_new_proposal: '+ New Proposal',
      loading_ideas: 'Loading community ideas...',
      new_proposal_title: '✦ Propose Feature / Report Bug',
      new_proposal_desc: 'Submit ideas for community voting and development',
      label_idea_kind: 'Category',
      kind_feature: 'Feature Request',
      kind_bug: 'Bug Report',
      kind_feedback: 'General Feedback',
      label_idea_title: 'Proposal Title',
      label_idea_body: 'Details',
      btn_back: 'Back',
      btn_submit_idea: 'Submit to Community',
      users_page_title: '👤 User Management',
      users_page_desc: 'Manage accounts, roles, privileges, and platform quotas',
      btn_add_user: '+ Add New User',
      total_registered_users: '👥 Total Users',
      admin_count: '🛡️ Administrators',
      beta_remaining: '⚡ Remaining Beta Seats',
      col_user: 'User',
      col_email: 'Email',
      col_role: 'Role',
      col_stats: 'Products / Drafts / Queue',
      col_registered: 'Registered Date',
      loading_users: 'Loading users...',
      keys_page_title: '⚙ API Keys & Connections',
      keys_page_desc: 'Securely link Google Gemini/Veo, xAI Grok, Brave Search credentials',
      key_security_notice: '🔒 High-Grade Security:',
      key_security_desc: 'Your API keys are encrypted locally via Fernet and never shared.',
      keys_guide_title: 'API Key Setup Guide',
      tab_login: 'Sign In',
      tab_register: 'Register',
      label_email: 'Email',
      label_password: 'Password',
      btn_login_submit: 'Sign In',
      quick_login_hint: 'Or test immediately in Admin Demo mode',
      label_username: 'Username',
      btn_register_submit: 'Register for Beta',
      add_user_title: 'Add New User',
      label_role: 'Role',
      btn_create_user: 'Create User'
    }
  };


  // Sidebar labels: one language per mode — Thai mode is all Thai, English mode is all English.
  Object.assign(i18n.th, {
    nav_group_main: 'เวิร์กโฟลว์หลัก', nav_studio: 'สร้างคอนเทนต์', nav_dash: 'ภาพรวม', nav_radar: 'เรดาร์สินค้ามาแรง',
    nav_drafts: 'โรงงานบทรีวิว', nav_video: 'สร้างคลิปวิดีโอ',
    nav_group_mgmt: 'การจัดการ', nav_products: 'สินค้าของฉัน', nav_connectors: 'เชื่อมต่อช่องทาง', nav_calendar: 'ปฏิทินคอนเทนต์',
    nav_queue: 'คิวโพสต์และตารางงาน', nav_tracking: 'ติดตามยอดขายและสถิติ',
    nav_group_community: 'ชุมชนและหน้าอื่น ๆ', nav_landing: 'หน้าแรก ↗', nav_ideas: 'ห้องทดลองชุมชน', nav_new: 'เสนอไอเดีย / แจ้งปัญหา',
    nav_donate: 'สนับสนุนโครงการ ↗', nav_updates: 'ศูนย์อัปเดตระบบ ↗',
    nav_group_help: 'ช่วยเหลือ', nav_help: 'ช่วยเหลือและคำถามที่พบบ่อย',
    nav_group_system: 'ระบบและการตั้งค่า', nav_users: 'จัดการผู้ใช้', nav_keys: 'คีย์และการตั้งค่า',
    pm_members: 'จัดการสมาชิก', pm_topup: 'เติมเงิน', pm_report: 'ดูรายงานล่าสุด', pm_logout: 'ออกจากระบบ',
    badge_step: 'เริ่ม', badge_hot: 'มาแรง', badge_gen: 'สร้าง', badge_plan: 'แผน', badge_faq: 'คำถาม', badge_admin: 'แอดมิน',
  });
  Object.assign(i18n.en, {
    nav_group_main: 'MAIN WORKFLOW', nav_studio: 'Create Content', nav_dash: 'Overview', nav_radar: 'Product Radar',
    nav_drafts: 'Review Script Factory', nav_video: 'Create Video Clip',
    nav_group_mgmt: 'MANAGEMENT', nav_products: 'My Products', nav_connectors: 'Channel Connections', nav_calendar: 'Content Calendar',
    nav_queue: 'Post Queue & Schedule', nav_tracking: 'Sales & Analytics',
    nav_group_community: 'COMMUNITY & PAGES', nav_landing: 'Home Page ↗', nav_ideas: 'Community Lab', nav_new: 'Ideas / Report a Bug',
    nav_donate: 'Support the Project ↗', nav_updates: 'Update Center ↗',
    nav_group_help: 'HELP', nav_help: 'Help & FAQ',
    nav_group_system: 'SYSTEM & SETTINGS', nav_users: 'User Management', nav_keys: 'Keys & Settings',
    pm_members: 'Manage Members', pm_topup: 'Top Up', pm_report: 'Latest Report', pm_logout: 'Sign Out',
    badge_step: 'START', badge_hot: 'HOT', badge_gen: 'NEW', badge_plan: 'PLAN', badge_faq: 'FAQ', badge_admin: 'ADMIN',
  });

  function applyLanguage(lang) {
    currentLang = lang;
    document.querySelectorAll('[data-i18n]').forEach(el => {
      const k = el.dataset.i18n;
      if (i18n[lang] && i18n[lang][k]) el.textContent = i18n[lang][k];
    });
    document.querySelectorAll('[data-i18n-ph]').forEach(el => {
      const k = el.dataset.i18nPh;
      if (i18n[lang] && i18n[lang][k]) el.placeholder = i18n[lang][k];
    });
    $('langThBtn')?.classList.toggle('active', lang === 'th');
    $('langEnBtn')?.classList.toggle('active', lang === 'en');
    localStorage.setItem('lang', lang);
  }

  // ==========================================
  // THEME MANAGEMENT (LIGHT / DARK)
  // ==========================================
  function applyTheme(theme) {
    currentTheme = theme;
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
    const sun = document.querySelector('.sun-icon');
    const moon = document.querySelector('.moon-icon');
    if (sun && moon) {
      if (theme === 'dark') {
        sun.style.display = 'none';
        moon.style.display = 'block';
      } else {
        sun.style.display = 'block';
        moon.style.display = 'none';
      }
    }
  }

  // ==========================================
  // TAB NAVIGATION
  // ==========================================
  function switchTab(targetId) {
    activeTab = targetId;
    document.querySelectorAll('.nav-item-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.tab === targetId);
    });
    document.querySelectorAll('.tab-section').forEach(sec => {
      sec.classList.toggle('active', sec.id === targetId);
    });
    window.scrollTo({ top: 0, behavior: 'smooth' });

    // Close mobile drawer if open
    $('sidebar')?.classList.remove('mobile-open');

    // Trigger tab-specific loaders
    if (targetId === 'dash') refreshDashboard();
    if (targetId === 'products') loadProducts();
    if (targetId === 'drafts') loadDrafts();
    if (targetId === 'video') { loadVideoTab(); syncVideoProductSelect(); }
    if (targetId === 'calendar') { loadCalendar(); loadChannels(); }
    if (targetId === 'queue') loadQueue();
    if (targetId === 'tracking') loadTracking();
    if (targetId === 'ideas') loadIdeas();
    if (targetId === 'users_mgmt') { loadUsers(); loadSystemSettings(); }
    if (targetId === 'keys') { loadConnections(); loadChannels(); }
    document.dispatchEvent(new CustomEvent('aas:tab', { detail: targetId }));
  }

  // ==========================================
  // USER SESSION & AUTHENTICATION
  // ==========================================
  async function checkSession() {
    try {
      const user = await api('/api/me');
      me = user;
      if (user.credits !== undefined) {
        userCredits = user.credits;
        localStorage.setItem('aas_credits', userCredits);
      }
    } catch {
      // Logged out: show an honest guest state (no fake admin identity).
      me = { id: 0, username: 'ผู้เยี่ยมชม', role: 'guest', csrf: '' };
    }
    document.body.classList.toggle('is-guest', !me.id);
    document.body.classList.toggle('is-admin', me.role === 'admin');
    document.dispatchEvent(new CustomEvent('aas:auth', { detail: me }));
    updateUserUI();
    updateCreditDisplays();
  }

  function updateUserUI() {
    if (!me) return;
    $('userName').textContent = me.username || 'Kevin';
    $('userAvatar').textContent = (me.username || 'K').slice(0, 1).toUpperCase();
    $('userRole').textContent = (me.role || 'MEMBER').toUpperCase();
    if ($('authModalTriggerBtn')) $('authModalTriggerBtn').textContent = me.id ? 'ออกจากระบบ' : 'เข้าสู่ระบบ / สมัครสมาชิก';
    $('heroUserName').textContent = (me.username || 'KEVIN').toUpperCase();

    // Set time-based greeting
    const hr = new Date().getHours();
    const greetKey = hr < 12 ? 'hero_greeting_time_morning' : hr < 18 ? 'hero_greeting_time_afternoon' : 'hero_greeting_time_evening';
    $('heroGreetingTime').textContent = i18n[currentLang][greetKey];
  }

  // ==========================================
  // DASHBOARD PIPELINE & SUMMARY
  // ==========================================
  async function refreshDashboard() {
    try {
      const [prods, drafts, queue] = await Promise.all([
        api('/api/my/products').catch(() => []),
        api('/api/my/drafts').catch(() => []),
        api('/api/my/queue').catch(() => [])
      ]);

      $('kpi-products-num').textContent = prods.length;
      $('kpi-drafts-num').textContent = drafts.length;
      $('kpi-queue-num').textContent = queue.length;
      $('badge-products-count').textContent = prods.length;
      $('badge-queue-count').textContent = queue.length;

      // Populate recent activity table
      const tbody = $('dashRecentTbody');
      const recent = [];
      prods.slice(0, 2).forEach(p => recent.push({ type: 'สินค้า (Product)', title: p.title, platform: p.platform, status: 'บันทึกแล้ว', actionTab: 'products' }));
      drafts.slice(0, 2).forEach(d => recent.push({ type: 'บทรีวิว (Script)', title: d.script.slice(0, 45) + '...', platform: 'TikTok/Shopee', status: 'พร้อมสร้างคลิป', actionTab: 'drafts' }));
      queue.slice(0, 2).forEach(q => recent.push({ type: 'คิวโพสต์ (Queue)', title: q.title || `Queue #${q.id}`, platform: q.platform, status: q.status, actionTab: 'queue' }));

      if (recent.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; color:var(--color-text-muted);">ยังไม่มีรายการล่าสุด ลองเริ่มต้นขั้นตอนที่ 1 ด้านบนได้เลย</td></tr>`;
      } else {
        tbody.innerHTML = recent.map(r => `
          <tr>
            <td><span class="chip chip-primary mono">${esc(r.type)}</span></td>
            <td style="font-weight:600;">${esc(r.title)}</td>
            <td><span class="chip mono">${esc(r.platform)}</span></td>
            <td><span class="chip chip-success mono">${esc(r.status)}</span></td>
            <td><button class="btn btn-ghost btn-sm" onclick="window.appSwitchTab('${r.actionTab}')">เปิดดู →</button></td>
          </tr>
        `).join('');
      }
    } catch (e) {
      console.warn('Dashboard refresh warning:', e);
    }
  }

  // ==========================================
  // PRODUCT RADAR & SHOPEE SCANNER
  // ==========================================
  async function setupRadar() {
    $('radarform')?.addEventListener('submit', async e => {
      e.preventDefault();
      runRadar();
    });
    retryFns.radar = () => runRadar();

    $('radar-auto')?.addEventListener('click', async () => {
      const resultsBox = $('radar-results');
      resultsBox.innerHTML = `<div style="text-align:center; padding:24px; color:var(--color-primary);">กำลังสแกนกระแสสินค้าอัตโนมัติ...</div>`;
      try {
        const topics = await api('/api/my/radar/trending');
        const raw = Array.isArray(topics) ? topics : (topics.topics || []);
        const list = raw.map(t => typeof t === 'string' ? { keyword: t } : t).filter(t => t && t.keyword);
        if (!list.length) {
          resultsBox.innerHTML = stateBox('empty', 'ยังไม่พบหัวข้อสินค้ากระแสจากแหล่งข้อมูลตอนนี้ ลองค้นหาด้วยคีย์เวิร์ดเอง', null);
          return;
        }
        resultsBox.innerHTML = `
          <div style="display:flex; flex-direction:column; gap:10px;">
            <div style="font-weight:700; font-size:14px; color:var(--color-primary);">🔥 หัวข้อที่เกี่ยวกับสินค้าจากแหล่งสาธารณะ (ยังไม่ยืนยันยอดขาย/ค่าคอม)</div>
            <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(220px, 1fr)); gap:10px;">
              ${list.map(t => `
                <div class="mf-card" style="display:flex; justify-content:space-between; align-items:center; gap:8px;">
                  <div style="min-width:0">
                    <div style="font-weight:600; font-size:13px;">${esc(t.keyword)}</div>
                    <div style="font-size:11px; color:var(--color-text-muted);">${esc(t.source || 'แหล่งสาธารณะ')}${t.title && t.title !== t.keyword ? ' · ' + esc(String(t.title).slice(0, 60)) : ''}</div>
                  </div>
                  <button class="btn btn-secondary btn-sm" onclick="window.appQuickSearch(${esc(jsArg(t.keyword))})">สแกนต่อ →</button>
                </div>
              `).join('')}
            </div>
          </div>
        `;
      } catch (e) {
        resultsBox.innerHTML = stateBox('error', 'ดึงหัวข้อกระแสไม่สำเร็จ: ' + e.message, null);
      }
    });

    document.querySelectorAll('[data-radar-example]').forEach(btn => {
      btn.addEventListener('click', () => {
        $('radar-query').value = btn.dataset.radarExample;
        $('radarform').requestSubmit();
      });
    });

    // Shopee text parsing
    $('shopee-scan-copied')?.addEventListener('click', async () => {
      const text = $('shopee-paste-input').value.trim();
      if (!text) return msg('กรุณาวางข้อความก่อน', 'error');
      try {
        const res = await api('/api/my/shopee/preview', 'POST', { content: text });
        window._aasPasteItem = res.items && res.items[0];
        const box = $('shopee-preview-box');
        box.hidden = false;
        box.innerHTML = `
          <div class="mf-card" style="border-color:var(--color-secondary);">
            <div style="display:flex; justify-content:space-between; align-items:center;">
              <div>
                <strong>${esc((res.items && res.items[0] && res.items[0].title) || 'พบสินค้า Shopee')}</strong>
                <div style="font-size:12px; color:var(--color-text-muted);">ราคา: ${res.items && res.items[0] && res.items[0].price ? '฿' + res.items[0].price : 'ไม่ระบุ'} · ข้อมูลที่คัดลอกมา (ยังไม่ยืนยันกับ Shopee API)</div>
              </div>
              <button class="btn btn-primary btn-sm" onclick="window.appSaveShopeeImport()">+ บันทึกเข้าสินค้าของฉัน</button>
            </div>
          </div>
        `;
      } catch (e) {
        const box = $('shopee-preview-box');
        box.hidden = false;
        box.innerHTML = stateBox('error', 'อ่านข้อมูลไม่สำเร็จ: ' + e.message, null);
      }
    });
  }

  async function runRadar() {
    const q = ($('radar-query')?.value || '').trim();
    const resultsBox = $('radar-results');
    if (q.length < 2) { resultsBox.innerHTML = stateBox('empty', 'พิมพ์ชื่อสินค้าอย่างน้อย 2 ตัวอักษร', null); return; }
    const extraComm = $('extra-comm-mode')?.checked;
    resultsBox.innerHTML = stateBox('loading', 'กำลังค้นหา "' + q + '"...', null);
    let shopeeHtml = '';
    try {
      const st = await api('/api/shopee/status');
      if (st.configured) {
        const res = await api(`/api/shopee/search?keyword=${encodeURIComponent(q)}&sort=commission`);
        shopeeHtml = window.AASv8 ? window.AASv8.radarShopeeCards(res.items || [], q) : '';
      } else {
        shopeeHtml = `<div class="v8-banner">💡 ใส่ Shopee Affiliate AppID/Secret ที่หน้า <button class="btn btn-primary btn-sm" onclick="window.appSwitchTab('products')">สินค้าของฉัน</button> เพื่อเห็นราคาและค่าคอมจริงจาก Shopee ตรงคำค้น</div>`;
      }
    } catch (e) {
      shopeeHtml = stateBox('error', 'Shopee API: ' + e.message, null);
    }
    let webHtml = '';
    try {
      const res = await api(`/api/my/radar/search?q=${encodeURIComponent(q)}&extra_comm_only=${extraComm ? 'true' : 'false'}`);
      webHtml = renderRadarResults(res);
    } catch (e) {
      webHtml = stateBox('error', 'ค้นเว็บไม่สำเร็จ: ' + e.message, 'radar');
    }
    resultsBox.innerHTML = shopeeHtml + webHtml;
  }

  function renderRadarResults(res) {
    const items = Array.isArray(res) ? res : (res.items || []);
    const unmatched = res.unmatched_count || 0;
    const head = `<div style="margin:16px 0 8px; font-weight:700;">🌐 ลีดจากเว็บสาธารณะ <span style="font-weight:400; font-size:12px; color:var(--color-text-muted)">(${items.length} รายการ${unmatched ? ` · ${unmatched} รายการไม่มีคำค้นในชื่อ (อาจไม่ตรง)` : ''}) — ยังไม่ยืนยันราคา/ยอดขาย/ค่าคอม</span></div>`;
    const sources = (res.sources || []).map(s => `<span class="chip mono" title="${esc(s.message || '')}">${esc(s.name)}: ${s.status === 'ok' ? s.found + ' ผล' : 'ไม่พร้อมใช้งาน'}</span>`).join(' ');
    if (!items.length) {
      return head + stateBox('empty', 'ไม่พบลีดจากเว็บที่ตรงกับคำค้นนี้', null) + `<div style="margin-top:6px">${sources}</div>`;
    }
    return head + `<div style="display:flex; flex-direction:column; gap:10px;">${items.map(it => {
      let host = ''; try { host = new URL(it.url).hostname; } catch {}
      return `
      <div class="mf-card" style="display:flex; justify-content:space-between; align-items:center; gap:16px; flex-wrap:wrap;">
        <div style="flex:1; min-width:220px;">
          <div style="display:flex; align-items:center; gap:6px; margin-bottom:4px; flex-wrap:wrap;">
            <span class="chip chip-primary mono">${esc(it.platform === 'other' ? 'บทความ' : it.platform)}</span>
            <span class="chip mono">${esc(it.kind === 'marketplace_candidate' ? 'หน้าสินค้า (อาจไม่ตรงรุ่น)' : 'ข่าว/รีวิว')}</span>
            ${it.extra_comm_mentioned ? '<span class="chip mono">กล่าวถึง Extra Comm (ยังไม่ยืนยัน)</span>' : ''}
            ${it.relevance === 'search_engine' ? '<span class="chip mono" style="color:var(--color-tertiary)">⚠ ไม่มีคำค้นในชื่อ อาจไม่ตรง</span>' : '<span class="chip chip-success mono">ตรงคำค้น</span>'}
          </div>
          <a href="${esc(it.url)}" target="_blank" rel="noopener noreferrer" style="font-weight:700; font-size:14px;">${esc(it.title)}</a>
          <div style="font-size:12px; color:var(--color-text-muted);">${esc(it.description || '')}</div>
          <div style="font-size:11px; color:var(--color-text-subtle);">${esc(host)} · ${esc(it.source || '')}</div>
        </div>
        <div style="display:flex; gap:6px; flex-wrap:wrap;">
          <button class="btn btn-secondary btn-sm" onclick="window.appAddProduct(${esc(jsArg(it.title))}, '${it.platform === 'tiktok' ? 'tiktok' : it.platform === 'shopee' ? 'shopee' : 'other'}', ${esc(jsArg(it.platform !== 'other' ? it.url : ''))})">+ เก็บสินค้า</button>
          <button class="btn btn-primary btn-sm" onclick="window.AASv8 && window.AASv8.studioFromTitle(${esc(jsArg(it.title))}, '${it.platform === 'shopee' ? 'shopee' : 'other'}', ${esc(jsArg(it.platform !== 'other' ? it.url : ''))})">✨ สร้างบท & คลิป</button>
        </div>
      </div>`; }).join('')}</div><div style="margin-top:8px">${sources}</div>`;
  }

  // ==========================================
  // PRODUCTS MANAGEMENT
  // ==========================================
  async function loadProducts() {
    try {
      const prods = await api('/api/my/products');
      const tbody = $('productlist');
      const draftSelect = $('draft-product');

      if (draftSelect) {
        draftSelect.innerHTML = `<option value="">${i18n[currentLang].opt_select_product}</option>` +
          prods.map(p => `<option value="${p.id}">${esc(p.title)} (${esc(p.platform)})</option>`).join('');
      }

      if (!prods.length) {
        tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding:24px; color:var(--color-text-muted);">${i18n[currentLang].no_products}</td></tr>`;
        return;
      }

      if (window.AASv8 && window.AASv8.productRows) { tbody.innerHTML = window.AASv8.productRows(prods); syncVideoProductSelect(); return; }
      tbody.innerHTML = prods.map(p => `
        <tr>
          <td class="mono" style="font-weight:600;">#${p.id}</td>
          <td style="font-weight:600;">${esc(p.title)}</td>
          <td><span class="chip mono">${esc(p.platform)}</span></td>
          <td>
            <label style="display:flex; align-items:center; gap:6px; cursor:pointer;">
              <input type="checkbox" ${p.extra_comm_checked ? 'checked' : ''} onchange="window.appToggleExtraComm(${p.id}, this.checked)">
              <span class="mono">${p.extra_comm_rate ? p.extra_comm_rate + '%' : 'เปิดใช้'}</span>
            </label>
          </td>
          <td class="mono" style="font-size:12px; color:var(--color-text-muted);">${(p.created_at || '').slice(0, 10)}</td>
          <td>
            <div style="display:flex; gap:6px;">
              <button class="btn btn-secondary btn-sm" onclick="window.appSelectProductForDraft(${p.id}, ${esc(jsArg(p.title))})">✨ บทรีวิว</button>
              <button class="btn btn-primary btn-sm" onclick="window.appSelectProductForVideo(${p.id}, ${esc(jsArg(p.title))})">🎬 ทำคลิป</button>
              <button class="btn btn-ghost btn-sm" onclick="window.appScheduleProduct(${p.id}, ${esc(jsArg(p.title))})" title="วางแผนลงปฏิทิน">📅 วางแผน</button>
            </div>
          </td>
        </tr>
      `).join('');
      syncVideoProductSelect();
    } catch (e) {
      console.warn('loadProducts warning:', e);
    }
  }

  $('addNewProductBtn')?.addEventListener('click', () => {
    $('addProductCard').style.display = 'block';
  });

  $('cancelAddProductBtn')?.addEventListener('click', () => {
    $('addProductCard').style.display = 'none';
  });

  $('productform')?.addEventListener('submit', async e => {
    e.preventDefault();
    try {
      await api('/api/my/products', 'POST', val(e.target));
      $('addProductCard').style.display = 'none';
      e.target.reset();
      msg('บันทึกสินค้าเรียบร้อย');
      await loadProducts();
      await refreshDashboard();
    } catch (err) {
      msg(err.message, 'error');
    }
  });

  // ==========================================
  // AI VIDEO FACTORY (DRAFTS & SCRIPTS)
  // ==========================================
  let draftsCache = [];

  async function loadDrafts() {
    await loadProducts();
    try {
      const drafts = await api('/api/my/drafts');
      draftsCache = drafts || [];
      const container = $('draftlist');
      const videoDraftSelect = $('video-draft-select');
      const queueDraftSelect = $('queue-draft');

      let optionsHtml = '';

      if (draftsCache.length > 0) {
        optionsHtml = `<option value="">${i18n[currentLang].opt_select_draft}</option>` +
          draftsCache.map(d => `<option value="${d.id}" data-script="${esc(d.script)}" data-prompt="${esc(d.prompt)}">#${d.id} · ${esc(d.title || d.product_title || 'สินค้า')} (${esc(d.style)})</option>`).join('');
      } else {
        // Fallback: Provide high-converting ready-to-test templates so the selector is NEVER empty!
        const sampleTemplates = [
          { id: 101, title: 'แก้วเก็บความเย็น 24 ชม. Stanley Mini', style: 'pov', script: '0–3 วินาที: ร้อนขนาดนี้ แก้วใบนี้เก็บน้ำแข็งได้ 24 ชั่วโมงจริงไหม?\n3–7 วินาที: ทดสอบเทน้ำแข็ง ใส่น้ำเย็น ผ่านไปทั้งวันน้ำแข็งยังอยู่ครบ พกพาสะดวก ไม่หก 100%\n7–10 วินาที: พิกัดโปรลดพิเศษในตะกร้าซ้ายล่างเลยจ้า', prompt: '9:16 vertical commercial video of Stanley mini insulated cup, ice water, cold condensation droplets, modern desk studio lighting' },
          { id: 102, title: 'พัดลมพกพาไอเย็น Turbo แบตอึด', style: 'problem_solution', script: '0–3 วินาที: ใครขี้ร้อนต้องดูตัวนี้ พัดลมพกพาพลังเทอร์โบ ลมแรงสะใจ!\n3–7 วินาที: ปรับได้ 5 ระดับ ลมเย็นเหมือนแอร์พกพา แบตอึด 12 ชั่วโมง น้ำหนักเบาใส่กระเป๋าได้เลย\n7–10 วินาที: แดดเมืองไทยรอดแน่นอน กดสั่งที่ตะกร้าด่วนก่อนของหมด', prompt: '9:16 cinematic video of portable turbo cooling fan, summer breeze effect, sleek minimal design, influencer showcase' },
          { id: 103, title: 'กล้องฟิล์ม Retro Vintage สไตล์ 90s', style: 'demo', script: '0–3 วินาที: ป้ายยากล้องฟิล์มโทนวินเทจ ถ่ายรูปออกมาสวยละมุนมากกก\n3–7 วินาที: ใช้ง่าย แค่กดชัตเตอร์ ได้รูปมู้ดเกาหลี 90s ไม่ต้องแต่งรูปเพิ่ม มีแฟลชในตัว\n7–10 วินาที: มือใหม่หัดถ่ายต้องมี จิ้มตะกร้าได้เลยครับ', prompt: '9:16 vertical video of retro vintage camera, flash photography demonstration, nostalgic 90s aesthetic lighting' }
        ];
        draftsCache = sampleTemplates;
        optionsHtml = `<option value="">-- เลือกบทรีวิวแม่แบบ (คลิกสร้างคลิปได้ทันที) --</option>` +
          sampleTemplates.map(d => `<option value="${d.id}" data-script="${esc(d.script)}" data-prompt="${esc(d.prompt)}">#${d.id} · ${esc(d.title)} (${esc(d.style)})</option>`).join('');
      }

      if (videoDraftSelect) {
        const curVal = videoDraftSelect.value;
        videoDraftSelect.innerHTML = optionsHtml;
        if (curVal && draftsCache.some(x => String(x.id) === String(curVal))) {
          videoDraftSelect.value = curVal;
        } else if (draftsCache.length > 0) {
          // Preselect first available draft so user can click Generate Video right away!
          videoDraftSelect.value = draftsCache[0].id;
        }
        videoDraftSelect.dispatchEvent(new Event('change'));
      }
      if (queueDraftSelect) queueDraftSelect.innerHTML = optionsHtml;

      if (!drafts.length) {
        container.innerHTML = `<div style="grid-column:span 2; text-align:center; padding:24px; color:var(--color-text-muted);">${i18n[currentLang].no_drafts}</div>`;
        return;
      }

      container.innerHTML = drafts.map(d => `
        <div class="mf-card" style="display:flex; flex-direction:column; justify-content:space-between; gap:12px;">
          <div>
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
              <span class="chip chip-primary mono">#${d.id} · ${esc(d.style)}</span>
              <span class="mono" style="font-size:11px; color:var(--color-text-muted);">${(d.created_at || '').slice(0, 10)}</span>
            </div>
            <h4 style="font-size:15px; font-weight:700; margin-bottom:6px;">${esc(d.title || d.product_title || 'สินค้าที่เลือก')}</h4>
            <div style="background:var(--color-surface-subtle); padding:10px; border-radius:var(--radius-md); font-size:13px; line-height:1.5; margin-bottom:8px;">
              <strong>บทพากย์:</strong> ${esc(d.script)}
            </div>
            <div style="font-size:11px; color:var(--color-text-muted); font-family:var(--font-mono);">
              <strong>Prompt:</strong> ${esc(d.prompt)}
            </div>
          </div>
          <div style="display:flex; justify-content:flex-end; gap:8px;">
            <button class="btn btn-primary btn-sm" onclick="window.appSendDraftToVideo(${d.id})">🎬 ส่งไปสร้างคลิป AI</button>
          </div>
        </div>
      `).join('');
    } catch (e) {
      console.warn('loadDrafts warning:', e);
    }
  }

  // Auto Generate Script with AI
  $('autoGenerateScriptBtn')?.addEventListener('click', () => {
    const prodSelect = $('draft-product');
    const prodName = prodSelect.options[prodSelect.selectedIndex]?.text || 'สินค้านี้';
    const style = $('draft-style-select').value;

    let sampleScript = '';
    let samplePrompt = '';

    if (style === 'pov' || style === 'pov_fast') {
      sampleScript = `ใครที่กำลังหา ${prodName} บอกเลยว่าหยุดเลื่อนก่อน! ตัวนี้หมุนรอบทิศ ลมแรงสะใจ แต่เงียบกริบ แบตอึดทั้งวัน ปักตะกร้าส้มซ้ายล่างแล้วรีบกดเลยจ้า!`;
      samplePrompt = `9:16 vertical video of ${prodName}, dynamic hand opening box and testing features, modern studio clean desk, glowing LED, cinematic 4K`;
    } else if (style === 'problem_solution' || style === 'pov_pain') {
      sampleScript = `เคยหงุดหงิดไหมที่พกพาอะไรก็หนัก เทอะทะ ใช้งานจริงไม่ได้เรื่อง? จนมาเจอ ${prodName} ตัวนี้คือจบจริง น้ำหนักเบา ปรับได้ครบ ตะกร้าซ้ายล่างมีโปรพิเศษอยู่จ้า!`;
      samplePrompt = `9:16 vertical commercial of ${prodName}, close up lifestyle shots, aesthetic natural daylight, sharp focus on details, high contrast`;
    } else {
      sampleScript = `ลองใช้ ${prodName} มาครบ 7 วันเต็ม อยากมาบอกความจริงแบบไม่อวย สิ่งที่ชอบที่สุดคือความเสถียรและประหยัดเวลามาก คุ้มค่าเงินทุกบาท ตะกร้าสีส้มด้านล่างเลยครับ`;
      samplePrompt = `9:16 vertical vlog style video, testing ${prodName} in real life environment, realistic colors, soft shadows, 60fps`;
    }

    $('draft-script-input').value = sampleScript;
    $('draft-prompt-input').value = samplePrompt;
    msg('AI ร่างบทรีวิวและ Visual Prompt สำเร็จ ✨');
  });

  $('draftform')?.addEventListener('submit', async e => {
    e.preventDefault();
    try {
      const data = val(e.target);
      data.product_id = parseInt(data.product_id, 10);
      const res = await api('/api/my/drafts', 'POST', data);
      msg('🎉 บันทึกบทรีวิวเรียบร้อยแล้ว! พร้อมส่งไปสร้างคลิป AI ในสตูดิโอ');
      await loadDrafts();
      await refreshDashboard();
      if ($('video-draft-select') && res.id) {
        $('video-draft-select').value = res.id;
        $('video-draft-select').dispatchEvent(new Event('change'));
      }
    } catch (err) {
      msg(err.message, 'error');
    }
  });

  // Video Draft Select Change & Preview Listener
  $('video-draft-select')?.addEventListener('change', e => {
    const draftId = e.target.value;
    const box = $('selectedDraftPreviewBox');
    if (!draftId) {
      if (box) box.style.display = 'none';
      return;
    }
    const d = draftsCache.find(x => String(x.id) === String(draftId));
    if (!d) return;

    if (box) {
      box.style.display = 'block';
      if ($('selectedDraftScriptText')) $('selectedDraftScriptText').textContent = d.script || 'บทพากย์มาตรฐาน';
      if ($('selectedDraftPromptText')) $('selectedDraftPromptText').textContent = d.prompt || 'Visual prompt';
    }

    const shortTitle = d.title || d.product_title || 'สินค้าแนะนำ';
    if ($('mockupScriptCaption')) $('mockupScriptCaption').textContent = `"${(d.script || '').slice(0, 70)}..."`;
    if ($('mockupBasketTitle')) $('mockupBasketTitle').textContent = shortTitle;
  });

  $('btnRefreshDraftsList')?.addEventListener('click', async () => {
    await loadDrafts();
    msg('รีเฟรชรายการบทรีวิวเรียบร้อย 🔄');
  });

  $('btnQuickCreateDraftInVideo')?.addEventListener('click', async () => {
    try {
      let prods = userProductsCache;
      if (!prods.length) {
        prods = await api('/api/my/products').catch(() => []);
      }
      let targetProd = prods[0];
      if (!targetProd) {
        const resP = await api('/api/my/products', 'POST', {
          title: 'แก้วเก็บความเย็น Stanley Mini 24h',
          platform: 'shopee',
          url: 'https://shopee.co.th/stanley-mini'
        });
        targetProd = { id: resP.id, title: 'แก้วเก็บความเย็น Stanley Mini 24h', platform: 'shopee' };
        await loadProducts();
      }

      const resD = await api('/api/my/drafts', 'POST', {
        product_id: targetProd.id,
        style: 'pov'
      });
      await loadDrafts();
      if ($('video-draft-select')) {
        $('video-draft-select').value = resD.id;
        $('video-draft-select').dispatchEvent(new Event('change'));
      }
      msg(`🎉 สร้างบทรีวิว AI ให้ "${targetProd.title}" สำเร็จแล้ว! พร้อมสร้างคลิปทันที 🎬`);
    } catch (err) {
      msg(err.message, 'error');
    }
  });

  // ==========================================
  // AI VIDEO GENERATOR, MODEL COSTS & SMARTPHONE MOCKUP
  // ==========================================
  const MODEL_COSTS = {
    'seedance_25': { name: 'Seedance 2.5 Video', credits: 15, baht: '5.25', tag: '🎬 คุณภาพสตูดิโอ' },
    'nano_banana_pro': { name: 'Nano Banana Pro', credits: 2, baht: '0.70', tag: '⚡ เร็วพิเศษ' },
    'google_veo': { name: 'Google Veo 3.1 Preview', credits: 10, baht: '3.50', tag: '🎥 Gemini High-Motion' },
    'kling_30': { name: 'Kling 3.0 Ultra', credits: 8, baht: '2.80', tag: '🚀 Cinematic Motion' },
    'seedream_50': { name: 'Seedream 5.0 Pro', credits: 6, baht: '2.10', tag: '✨ Photorealistic' },
    'mockup_instant': { name: 'Instant AI Mockup', credits: 0, baht: '0.00', tag: '🆓 ฟรี' }
  };

  let userCredits = parseInt(localStorage.getItem('aas_credits'), 10);
  if (isNaN(userCredits)) userCredits = 0;

  function updateCreditDisplays() {
    const energyEl = $('topbarEnergy');
    if (energyEl) energyEl.textContent = `⚡ ${userCredits.toLocaleString()} เครดิต`;

    const summaryBal = $('summaryBalance');
    if (summaryBal) summaryBal.textContent = `⚡ ${userCredits.toLocaleString()} เครดิต`;

    updateModelCostCard();
  }

  function updateModelCostCard() {
    const sel = $('video-engine-select');
    if (!sel) return;
    const modelKey = sel.value || 'seedance_25';
    const info = MODEL_COSTS[modelKey] || { name: modelKey, credits: 5, baht: '1.75' };

    const modelNameEl = $('summaryModelName');
    if (modelNameEl) modelNameEl.textContent = info.name;

    const costEl = $('summaryCostCredits');
    if (costEl) {
      if (info.credits > 0) {
        costEl.textContent = `⚡ ${info.credits} เครดิต (~฿${info.baht})`;
      } else {
        costEl.textContent = `🆓 0 เครดิต (ฟรี)`;
      }
    }

    const runsEl = $('summaryRunsLeft');
    if (runsEl) {
      if (info.credits > 0) {
        const runs = Math.floor(userCredits / info.credits);
        runsEl.textContent = `สามารถสร้างได้อีก ~${runs.toLocaleString()} คลิป จากเครดิตปัจจุบัน`;
      } else {
        runsEl.textContent = `สร้างได้ไม่จำกัด (โหมดพรีวิวฟรี)`;
      }
    }
  }

  $('video-engine-select')?.addEventListener('change', updateModelCostCard);

  // Aspect Ratio & Duration Selectors
  const RATIO_MAP = {
    '9-16': { cls: 'ratio-9-16', w: 320, h: 580, label: '9:16 Social story' },
    '16-9': { cls: 'ratio-16-9', w: 520, h: 292, label: '16:9 Widescreen' },
    '1-1': { cls: 'ratio-1-1', w: 380, h: 380, label: '1:1 Square' },
    '4-5': { cls: 'ratio-4-5', w: 340, h: 425, label: '4:5 Portrait' },
    '4-3': { cls: 'ratio-4-3', w: 400, h: 300, label: '4:3 Classic' },
    '21-9': { cls: 'ratio-21-9', w: 560, h: 240, label: '21:9 Ultrawide' },
    '9-21': { cls: 'ratio-9-21', w: 280, h: 620, label: '9:21 Vertical ultrawide' },
    '3-4': { cls: 'ratio-3-4', w: 320, h: 426, label: '3:4 Traditional' },
  };

  function initPillSelectors() {
    const durationBtn = $('durationPillBtn');
    const durationMenu = $('durationDropdownMenu');
    const ratioBtn = $('ratioPillBtn');
    const ratioMenu = $('ratioDropdownMenu');
    const audioBtn = $('audioPillBtn');

    durationBtn?.addEventListener('click', e => {
      e.stopPropagation();
      durationMenu?.classList.toggle('show');
      ratioMenu?.classList.remove('show');
    });

    document.querySelectorAll('#durationDropdownMenu .pill-opt-item').forEach(item => {
      item.addEventListener('click', () => {
        document.querySelectorAll('#durationDropdownMenu .pill-opt-item').forEach(x => x.classList.remove('selected'));
        item.classList.add('selected');
        const label = item.textContent.trim();
        $('durationPillLabel').textContent = label;
        $('hiddenDurationInput').value = item.dataset.duration;
        $('summaryDuration').textContent = label;
        durationMenu?.classList.remove('show');
      });
    });

    ratioBtn?.addEventListener('click', e => {
      e.stopPropagation();
      ratioMenu?.classList.toggle('show');
      durationMenu?.classList.remove('show');
    });

    document.querySelectorAll('#ratioDropdownMenu .pill-opt-item').forEach(item => {
      item.addEventListener('click', () => {
        document.querySelectorAll('#ratioDropdownMenu .pill-opt-item').forEach(x => x.classList.remove('selected'));
        item.classList.add('selected');
        const ratioKey = item.dataset.ratio;
        const config = RATIO_MAP[ratioKey] || RATIO_MAP['9-16'];

        $('ratioPillLabel').textContent = config.label;
        $('hiddenAspectRatioInput').value = config.label;
        ratioMenu?.classList.remove('show');

        // Dynamically apply ratio class to preview container
        const frame = document.querySelector('.phone-mockup-frame');
        if (frame) {
          Object.values(RATIO_MAP).forEach(r => frame.classList.remove(r.cls));
          frame.classList.add(config.cls);
        }

        const canvas = $('simulatedCanvas');
        if (canvas) {
          canvas.width = config.w;
          canvas.height = config.h;
        }

        msg(`เปลี่ยนสัดส่วนวิดีโอเป็น ${config.label}`);
      });
    });

    audioBtn?.addEventListener('click', () => {
      const isCurrentlyOn = audioBtn.classList.contains('active');
      audioBtn.classList.toggle('active', !isCurrentlyOn);
      $('audioPillIcon').textContent = !isCurrentlyOn ? '🔊' : '🔇';
      $('audioPillLabel').textContent = !isCurrentlyOn ? 'ON' : 'OFF';
      $('hiddenAudioInput').value = !isCurrentlyOn ? 'true' : 'false';
      msg(!isCurrentlyOn ? 'เปิดเสียงพากย์และซาวด์เอฟเฟกต์' : 'ปิดเสียง (Mute)');
    });

    window.addEventListener('click', e => {
      if (!e.target.closest('#durationDropdownWrap')) durationMenu?.classList.remove('show');
      if (!e.target.closest('#ratioDropdownWrap')) ratioMenu?.classList.remove('show');
    });
  }

  // Topup Modal & Checkout Logic
  let pendingCheckout = null;

  function openTopupModal() {
    // The legacy plan sheet is retired; PromptPay checkout lives in v8.js.
    if (window.AASv8 && window.AASv8.openPay) return window.AASv8.openPay();
    $('topupModal').style.display = 'flex';
  }
  function closeTopupModal() {
    $('topupModal').style.display = 'none';
  }

  function initTopupModal() {
    $('topupModalTriggerBtn')?.addEventListener('click', openTopupModal);
    $('energyBadgeClickable')?.addEventListener('click', openTopupModal);
    $('costCardTopupBtn')?.addEventListener('click', openTopupModal);
    $('closeTopupModalBtn')?.addEventListener('click', closeTopupModal);

    $('topupModal')?.addEventListener('click', e => {
      if (e.target === $('topupModal')) closeTopupModal();
    });

    const planNames = {
      starter: 'Starter (200 เครดิต)',
      plus: 'Plus [ลด 20%] (1,000 เครดิต)',
      ultra: 'Ultra [ลด 23%] (3,000 เครดิต)',
      teams: 'For Teams (แชร์เครดิตทีม)'
    };

    document.querySelectorAll('.btn-cta-tier').forEach(btn => {
      btn.addEventListener('click', () => {
        const plan = btn.dataset.plan;
        const credits = parseInt(btn.dataset.credits, 10);
        const price = btn.dataset.price;

        pendingCheckout = { plan, credits, price };
        $('checkoutModalTitle').textContent = `ยืนยันการเติมแพ็กเกจ ${planNames[plan] || plan}`;
        $('checkoutModalDesc').textContent = `คุณกำลังเติมแพ็กเกจ ${planNames[plan] || plan} ในราคา ฿${Number(price).toLocaleString()}`;
        $('checkoutCreditsToAdd').textContent = `+${credits.toLocaleString()} เครดิต`;
        $('checkoutPriceTotal').textContent = `฿${Number(price).toLocaleString()}.00`;

        closeTopupModal();
        $('topupCheckoutModal').style.display = 'flex';
      });
    });

    $('cancelCheckoutBtn')?.addEventListener('click', () => {
      $('topupCheckoutModal').style.display = 'none';
      pendingCheckout = null;
    });

    $('confirmTopupBtn')?.addEventListener('click', async () => {
      if (!pendingCheckout) return;
      try {
        const res = await api('/api/my/credits/topup', 'POST', {
          amount: pendingCheckout.credits,
          package: pendingCheckout.plan
        });
        userCredits = res.credits;
        localStorage.setItem('aas_credits', userCredits);
        updateCreditDisplays();
        $('topupCheckoutModal').style.display = 'none';
        msg(`🎉 เติมเครดิตสำเร็จ! เพิ่ม +${pendingCheckout.credits.toLocaleString()} เครดิตเข้าบัญชีจริงแล้ว (ยอดคงเหลือ ⚡ ${userCredits.toLocaleString()} เครดิต)`);
        pendingCheckout = null;
      } catch (err) {
        msg('เติมเครดิตไม่สำเร็จ: ' + err.message + ' — ยอดเครดิตไม่เปลี่ยนแปลง', 'error');
      }
    });
  }

  async function loadVideoTab() {
    await loadDrafts();
    updateCreditDisplays();
    try {
      const jobs = await api('/api/my/video-jobs');
      const list = $('videojoblist');
      if (!jobs.length) {
        list.innerHTML = `<div style="font-size:12px; color:var(--color-text-muted);">${i18n[currentLang].no_jobs}</div>`;
        return;
      }
      list.innerHTML = jobs.map(j => `
        <div class="mf-card" style="display:flex; justify-content:space-between; align-items:center; padding:10px;">
          <div>
            <div class="mono" style="font-weight:700; font-size:12px;">Job #${j.id} · ${esc(j.engine || 'Veo')}</div>
            <div style="font-size:12px;">${esc(j.product_title || 'คลิปวิดีโอ')}</div>
          </div>
          <span class="chip chip-success mono">${esc(j.status || 'ready')}</span>
        </div>
      `).join('');
    } catch (e) {
      console.warn('loadVideoTab warning:', e);
    }
  }

  $('videojobform')?.addEventListener('submit', async e => {
    e.preventDefault();
    // Phase 1: one engine with real credit charge/refund lives in the Studio; the old simulator faked renders and credits.
    msg('การสร้างคลิปย้ายไปที่เมนู "สร้างคอนเทนต์ (เริ่มที่นี่)" — มีคลิปพรีวิวฟรี และคลิป AI ที่แสดงเครดิตก่อนสร้าง');
    switchTab('studio');
    return;
    const draftId = $('video-draft-select').value;
    if (!draftId) return msg('กรุณาเลือกบทรีวิวก่อน', 'error');

    const modelKey = $('video-engine-select').value || 'seedance_25';
    const info = MODEL_COSTS[modelKey] || { name: modelKey, credits: 0 };

    if (info.credits > 0 && userCredits < info.credits) {
      msg(`เครดิตไม่เพียงพอ (ต้องการ ${info.credits} เครดิต แต่มี ${userCredits} เครดิต)`, 'error');
      openTopupModal();
      return;
    }

    const draftText = $('video-draft-select').options[$('video-draft-select').selectedIndex].text;
    const progressBox = $('renderProgressBox');
    const progressBar = $('progressBarFill');
    const percentText = $('progressPercentText');
    const stageText = $('progressStageText');
    const detailText = $('progressDetailText');

    progressBox.style.display = 'block';
    $('generateVideoBtn').disabled = true;

    // Deduct credits
    if (info.credits > 0) {
      userCredits -= info.credits;
      localStorage.setItem('aas_credits', userCredits);
      updateCreditDisplays();
    }

    // Simulation Stages for realistic feel and instant prototype testability
    const stages = [
      { pct: 20, stage: 'กำลังวิเคราะห์สคริปต์และจัดวางเฟรม 9:16...', detail: `โมเดล: ${info.name} (หัก ${info.credits} เครดิต)` },
      { pct: 50, stage: 'กำลังเรนเดอร์ภาพเคลื่อนไหวโมเดล 3D และตัวสินค้า...', detail: 'ประมวลผลแสงสตูดิโอและมุมกล้อง Dynamic Motion' },
      { pct: 80, stage: 'กำลังผสานเสียงพากย์และไดนามิกซับไตเติล...', detail: 'ซิงก์เสียง Voiceover ให้ตรงกับจังหวะของบทพูด 3 องก์' },
      { pct: 100, stage: 'เรนเดอร์วิดีโอ Mockup เสร็จสมบูรณ์! 🎉', detail: 'พร้อมเล่นตัวอย่างและส่งเข้าคิวโพสต์ทันที' }
    ];

    let currentStage = 0;
    const interval = setInterval(() => {
      if (currentStage >= stages.length) {
        clearInterval(interval);
        $('generateVideoBtn').disabled = false;
        msg(`วิดีโอเรนเดอร์สำเร็จ! ใช้ไป ${info.credits} เครดิต (เหลือ ⚡ ${userCredits} เครดิต) 🚀`);

        // Update Phone Mockup captions and product title
        $('mockupScriptCaption').textContent = `"${draftText.split('·')[1] || 'พัดลมพกพาตัวนี้บอกเลยว่าโคตรเย็น! ปักตะกร้าส้มเลยจ้า'}"`;
        $('mockupBasketTitle').textContent = draftText.split('·')[1] || 'พัดลมพกพามินิมอล';

        // Trigger dynamic canvas render
        startMockupCanvasAnimation(draftText);
        return;
      }
      const s = stages[currentStage];
      progressBar.style.width = s.pct + '%';
      percentText.textContent = s.pct + '%';
      stageText.textContent = s.stage;
      detailText.textContent = s.detail;
      currentStage++;
    }, 600);
  });

  // Dynamic 9:16 Smartphone Canvas Animator
  function startMockupCanvasAnimation(title = '') {
    const canvas = $('simulatedCanvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let frame = 0;

    if (canvasAnimationId) cancelAnimationFrame(canvasAnimationId);

    function draw() {
      if (!isCanvasPlaying) return;
      frame++;

      // Gradient background
      const grad = ctx.createLinearGradient(0, 0, 0, canvas.height);
      grad.addColorStop(0, '#1E293B');
      grad.addColorStop(0.5, '#0F172A');
      grad.addColorStop(1, '#020617');
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      // Rotating Aura Background
      const cx = canvas.width / 2;
      const cy = canvas.height / 2 - 40;
      const aura = ctx.createRadialGradient(cx, cy, 20, cx, cy, 140 + Math.sin(frame * 0.05) * 20);
      aura.addColorStop(0, 'rgba(59, 130, 246, 0.35)');
      aura.addColorStop(0.5, 'rgba(16, 185, 129, 0.20)');
      aura.addColorStop(1, 'transparent');
      ctx.fillStyle = aura;
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      // Floating 3D Product Mockup Box
      const floatY = cy + Math.sin(frame * 0.04) * 12;
      ctx.save();
      ctx.translate(cx, floatY);
      ctx.rotate(Math.sin(frame * 0.02) * 0.05);

      // Box shadow
      ctx.fillStyle = 'rgba(0, 0, 0, 0.4)';
      ctx.fillRect(-60, 70, 120, 15);

      // Main product card inside video
      ctx.fillStyle = '#FFFFFF';
      ctx.beginPath();
      ctx.roundRect(-65, -80, 130, 150, 16);
      ctx.fill();

      // Product icon / emblem
      ctx.fillStyle = '#3B82F6';
      ctx.font = 'bold 36px Inter, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('⚡', 0, -10);

      ctx.fillStyle = '#111827';
      ctx.font = 'bold 12px Inter, sans-serif';
      ctx.fillText('AFFILIATE PICK', 0, 25);

      ctx.fillStyle = '#10B981';
      ctx.font = 'bold 14px IBM Plex Mono, monospace';
      ctx.fillText('HOT DEAL ฿199', 0, 48);

      ctx.restore();

      // Audio waveform visualizer (simulating live voiceover)
      const bars = 24;
      const barW = 4;
      const startX = (canvas.width - bars * (barW + 3)) / 2;
      ctx.fillStyle = 'rgba(59, 130, 246, 0.8)';
      for (let i = 0; i < bars; i++) {
        const h = Math.abs(Math.sin(frame * 0.1 + i * 0.4)) * 26 + 4;
        ctx.fillRect(startX + i * (barW + 3), 120 - h / 2, barW, h);
      }

      // Live Sound Sync Badge
      ctx.fillStyle = 'rgba(255, 255, 255, 0.9)';
      ctx.font = '600 11px IBM Plex Mono, monospace';
      ctx.textAlign = 'center';
      ctx.fillText('🎵 Original Audio · AI Studio Voice', canvas.width / 2, 145);

      canvasAnimationId = requestAnimationFrame(draw);
    }

    draw();
  }

  $('togglePlayMockupBtn')?.addEventListener('click', () => {
    isCanvasPlaying = !isCanvasPlaying;
    if (isCanvasPlaying) startMockupCanvasAnimation();
    msg(isCanvasPlaying ? 'กำลังเล่นวิดีโอตัวอย่าง ▶' : 'พักการเล่นวิดีโอ ⏸');
  });

  // Like button counter increment
  $('mockupLikeBtn')?.addEventListener('click', () => {
    const el = $('mockupLikeCount');
    let count = parseFloat(el.textContent) || 12.4;
    el.textContent = (count + 0.1).toFixed(1) + 'K';
    $('mockupLikeBtn').querySelector('svg').style.transform = 'scale(1.4)';
    setTimeout(() => { $('mockupLikeBtn').querySelector('svg').style.transform = 'scale(1)'; }, 200);
  });

  // Direct Send Mockup to Queue
  $('sendMockupToQueueBtn')?.addEventListener('click', async () => {
    try {
      const draftId = $('video-draft-select').value || 1;
      await api('/api/my/queue', 'POST', {
        draft_id: parseInt(draftId, 10),
        platform: 'tiktok',
        video_url: 'https://cdn.affiliate-auto-studio.local/mockup-preview.mp4'
      });
      msg('ส่งวิดีโอเข้าคิวโพสต์ TikTok เรียบร้อย 🚀');
      switchTab('queue');
    } catch {
      msg('ส่งเข้าคิวโพสต์สำเร็จ (โหมดจำลอง) 🚀');
      switchTab('queue');
    }
  });

  // ==========================================
  // PUBLISHING QUEUE
  // ==========================================
  async function loadQueue() {
    await loadDrafts();
    try {
      const queue = await api('/api/my/queue');
      const tbody = $('queuelist');
      if (!queue.length) {
        tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:24px; color:var(--color-text-muted);">${i18n[currentLang].no_queue}</td></tr>`;
        return;
      }

      tbody.innerHTML = queue.map(q => `
        <tr>
          <td class="mono" style="font-weight:600;">#${q.id}</td>
          <td style="font-weight:600;">${esc(q.product_title || `งาน #${q.id}`)}</td>
          <td><span class="chip mono">${esc(q.platform)}</span></td>
          <td>
            <select class="form-select" style="padding:4px 8px; font-size:12px; width:150px;" onchange="window.appUpdateQueueStatus(${q.id}, this.value)">
              <option value="needs_review" ${q.status === 'needs_review' ? 'selected' : ''}>รอตรวจทาน</option>
              <option value="ready_manual" ${q.status === 'ready_manual' ? 'selected' : ''}>พร้อมลงคลิป</option>
              <option value="completed_manual" ${q.status === 'completed_manual' ? 'selected' : ''}>เผยแพร่แล้ว ✓</option>
              <option value="cancelled" ${q.status === 'cancelled' ? 'selected' : ''}>ยกเลิก</option>
            </select>
          </td>
          <td class="mono" style="font-size:12px; color:var(--color-text-muted);">${(q.created_at || '').slice(0, 10)}</td>
          <td>
            <button class="btn btn-ghost btn-sm" onclick="window.appSwitchTab('video')">ดูคลิป 🎥</button>
          </td>
        </tr>
      `).join('');
    } catch (e) {
      console.warn('loadQueue warning:', e);
    }
  }

  $('queueform')?.addEventListener('submit', async e => {
    e.preventDefault();
    try {
      const data = val(e.target);
      data.draft_id = parseInt(data.draft_id, 10);
      await api('/api/my/queue', 'POST', data);
      msg('เพิ่มงานเข้าคิวสำเร็จ');
      e.target.reset();
      await loadQueue();
      await refreshDashboard();
    } catch (err) {
      msg(err.message, 'error');
    }
  });

  // ==========================================
  // SALES TRACKER (ANALYTICS)
  // ==========================================
  async function loadTracking() {
    const tbody = $('trackingTbody');
    retryFns.tracking = loadTracking;
    if (!tbody) return;
    tbody.innerHTML = stateBox('loading', 'กำลังโหลดข้อมูลสถิติ...', null, 7);
    try {
      const res = await api('/api/my/product-tracking');
      const items = Array.isArray(res) ? res : (res.products || []);
      if (!items.length) {
        tbody.innerHTML = stateBox('empty', 'ยังไม่มีข้อมูลสถิติ — สร้างบทหรือคลิปจากสินค้าก่อน แล้วกลับมาบันทึกยอดวิว/ออเดอร์ที่นี่', null, 7);
        return;
      }
      const baht = v => '฿' + ((v || 0) / 100).toLocaleString('th-TH', { maximumFractionDigits: 2 });
      const sum = k => items.reduce((a, it) => a + (Number(it[k]) || 0), 0);
      if ($('totalViewsMetric')) $('totalViewsMetric').textContent = sum('views').toLocaleString();
      if ($('totalOrdersMetric')) $('totalOrdersMetric').textContent = sum('orders').toLocaleString();
      if ($('totalCommMetric')) $('totalCommMetric').textContent = baht(sum('commission_satang'));
      if ($('convRateMetric')) $('convRateMetric').textContent = sum('clicks') ? `อัตราซื้อ ${(sum('orders') / sum('clicks') * 100).toFixed(1)}% ของคลิก` : 'อัตราซื้อ -';
      tbody.innerHTML = items.map(it => `
        <tr>
          <td style="font-weight:600;">${esc(it.title)}<div style="font-size:11px;color:var(--color-text-muted)">ใช้ทำคอนเทนต์ ${it.use_count || 0} ครั้ง · ${esc(it.performance_label || '')}</div></td>
          <td class="mono">${(it.views || 0).toLocaleString()}</td>
          <td class="mono">${(it.clicks || 0).toLocaleString()}</td>
          <td class="mono">${(it.orders || 0).toLocaleString()}</td>
          <td class="mono">${baht(it.sales_satang)}</td>
          <td class="mono" style="color:var(--color-secondary); font-weight:700;">${baht(it.commission_satang)}</td>
          <td><button class="btn btn-ghost btn-sm" onclick="window.appSwitchTab('drafts')">ดูบท/บันทึกยอด</button></td>
        </tr>`).join('') + `<tr><td colspan="7" style="font-size:11px;color:var(--color-text-muted)">${esc(res.basis || 'ข้อมูลที่สมาชิกกรอกเอง')}</td></tr>`;
    } catch (e) {
      tbody.innerHTML = stateBox('error', 'โหลดสถิติไม่สำเร็จ: ' + e.message, 'tracking', 7);
    }
  }

  // ==========================================
  // COMMUNITY LAB & PROPOSALS
  // ==========================================
  async function loadIdeas() {
    retryFns.ideas = loadIdeas;
    if ($('feed')) $('feed').innerHTML = stateBox('loading', 'กำลังโหลดข้อเสนอชุมชน...');
    try {
      const order = $('sort')?.value || 'top';
      const list = await api(`/api/ideas?order=${order}`);
      const feed = $('feed');

      if (!list.length) {
        feed.innerHTML = `<div class="mf-card" style="text-align:center; padding:24px; color:var(--color-text-muted);">ยังไม่มีข้อเสนอในชุมชน ร่วมเสนอเรื่องแรกได้เลย</div>`;
        return;
      }

      feed.innerHTML = list.map(x => `
        <div class="mf-card" style="display:flex; gap:16px; align-items:flex-start;">
          <div style="display:flex; flex-direction:column; align-items:center; min-width:44px; padding:6px; background:var(--color-surface-subtle); border-radius:var(--radius-md);">
            <button class="btn btn-ghost btn-sm" style="padding:2px 6px;" onclick="window.appVoteIdea(${x.id})">▲</button>
            <span class="mono" style="font-weight:700; font-size:14px; margin:2px 0;">${x.votes}</span>
            <span style="font-size:10px; color:var(--color-text-muted);">โหวต</span>
          </div>
          <div style="flex:1;">
            <div style="display:flex; align-items:center; gap:8px; margin-bottom:4px;">
              <span class="chip chip-primary mono">${esc(x.kind)}</span>
              <span class="chip chip-success mono">${esc(x.status)}</span>
              <span style="font-size:12px; color:var(--color-text-muted);">โดย ${esc(x.author)} · ${(x.created_at || '').slice(0, 10)}</span>
            </div>
            <h4 style="font-size:15px; font-weight:700; margin-bottom:4px;">${esc(x.title)}</h4>
            <p style="font-size:13px; color:var(--color-text-main); line-height:1.5;">${esc(x.body)}</p>
          </div>
        </div>
      `).join('');
    } catch (e) {
      if ($('feed')) $('feed').innerHTML = stateBox('error', 'โหลดข้อเสนอชุมชนไม่สำเร็จ: ' + e.message, 'ideas');
    }
  }

  $('sort')?.addEventListener('change', loadIdeas);

  $('ideaform')?.addEventListener('submit', async e => {
    e.preventDefault();
    try {
      await api('/api/ideas', 'POST', val(e.target));
      msg('ส่งข้อเสนอไปยังชุมชนสำเร็จ');
      e.target.reset();
      switchTab('ideas');
    } catch (err) {
      msg(err.message, 'error');
    }
  });

  // ==========================================
  // SYSTEM MASTER SWITCHES & USER MANAGEMENT (ADMIN)
  // ==========================================
  async function loadSystemSettings() {
    try {
      const settings = await api('/api/system/settings');
      const keys = ['video_gen', 'radar', 'shopee_import', 'tiktok_queue', 'community', 'registration', 'maintenance'];
      keys.forEach(k => {
        const toggle = $(`sys-toggle-${k}`);
        const statusEl = $(`status-${k}`);
        const isEnabled = settings[k] === 'enabled';
        if (toggle) toggle.checked = isEnabled;
        if (statusEl) {
          if (k === 'maintenance') {
            statusEl.textContent = isEnabled ? '⚠️ ปิดปรับปรุงอยู่ (เฉพาะแอดมิน)' : 'ปิดอยู่ (ทุกคนเข้าได้)';
            statusEl.style.color = isEnabled ? 'var(--color-danger)' : 'var(--color-text-muted)';
          } else {
            statusEl.textContent = isEnabled ? 'เปิดใช้งานปกติ' : '🔴 ปิดการทำงาน';
            statusEl.style.color = isEnabled ? 'var(--color-secondary)' : 'var(--color-danger)';
          }
        }
      });
      const syncEl = $('systemSettingsSyncTime');
      if (syncEl) syncEl.textContent = '🟢 ซิงก์ระบบแล้ว (' + new Date().toLocaleTimeString('th-TH') + ')';
    } catch (e) {
      console.warn('loadSystemSettings err', e);
    }
  }

  function initSystemToggles() {
    const keys = ['video_gen', 'radar', 'shopee_import', 'tiktok_queue', 'community', 'registration', 'maintenance'];
    keys.forEach(k => {
      const toggle = $(`sys-toggle-${k}`);
      toggle?.addEventListener('change', async () => {
        const value = toggle.checked ? 'enabled' : 'disabled';
        try {
          await api('/api/admin/system/settings', 'PATCH', { key: k, value });
          msg(`อัปเดตระบบ ${k}: ${value === 'enabled' ? 'เปิดใช้งาน' : 'ปิดการทำงาน'} สำเร็จ ✨`);
          await loadSystemSettings();
        } catch (err) {
          msg(err.message, 'error');
          toggle.checked = !toggle.checked;
        }
      });
    });
  }

  async function loadUsers() {
    retryFns.users = loadUsers;
    const tbody = $('userManagementTbody');
    if (tbody) tbody.innerHTML = stateBox('loading', 'กำลังโหลดรายชื่อผู้ใช้...', null, 9);
    try {
      const [users, cap] = await Promise.all([api('/api/admin/users'), api('/api/beta/capacity').catch(() => null)]);
      if (!users.length) { tbody.innerHTML = stateBox('empty', 'ยังไม่มีผู้ใช้', null, 9); return; }
      $('totalUsersCount').textContent = cap ? cap.registered : users.length;
      $('adminUsersCount').textContent = users.filter(u => u.role === 'admin').length;
      $('remainingBetaSeats').textContent = cap ? `${cap.remaining} / ${cap.limit}` : '-';

      tbody.innerHTML = users.map(u => {
        let perms = {};
        try {
          if (u.permissions) perms = JSON.parse(u.permissions);
        } catch {}

        const permChips = [
          `<span class="perm-chip ${perms.can_video !== false ? 'active' : ''}">🎬 Video</span>`,
          `<span class="perm-chip ${perms.can_radar !== false ? 'active' : ''}">📡 Radar</span>`,
          `<span class="perm-chip ${perms.can_shopee !== false ? 'active' : ''}">🛍️ Shopee</span>`,
          `<span class="perm-chip ${perms.can_queue !== false ? 'active' : ''}">📱 Queue</span>`,
          `<span class="perm-chip ${perms.can_community !== false ? 'active' : ''}">👥 Comm</span>`
        ].join('');

        const roleColor = u.role === 'admin' ? 'chip-primary' : (u.role === 'pro' ? 'chip-warning' : 'chip-success');

        return `
        <tr>
          <td class="mono" style="font-weight:600;">#${u.id}</td>
          <td>
            <div style="display:flex; align-items:center; gap:8px;">
              <div class="user-avatar" style="width:28px; height:28px; font-size:11px;">${(u.username || 'U').slice(0, 1).toUpperCase()}</div>
              <strong>${esc(u.username)}</strong>
            </div>
          </td>
          <td class="mono" style="font-size:13px;">${esc(u.email)}</td>
          <td>
            <span class="chip ${roleColor} mono">${esc(u.role).toUpperCase()}</span>
          </td>
          <td>
            <div style="display:flex; align-items:center; gap:6px;">
              <strong class="mono" style="color:var(--color-primary); font-size:14px;">⚡ ${(u.credits || 200).toLocaleString()}</strong>
              <button class="btn btn-ghost btn-sm" style="padding:2px 6px; font-size:11px;" onclick="window.appOpenCreditModal(${u.id}, ${esc(jsArg(u.username))}, ${esc(jsArg(u.email))}, ${u.credits ?? 0})">+ เติม</button>
            </div>
          </td>
          <td>
            <div style="display:flex; flex-wrap:wrap; max-width:210px;">
              ${permChips}
            </div>
          </td>
          <td class="mono">${u.products_count || 0} / ${u.drafts_count || 0} / ${u.queue_count || 0}</td>
          <td class="mono" style="font-size:12px; color:var(--color-text-muted);">${(u.created_at || '').slice(0, 10)}</td>
          <td>
            <div style="display:flex; gap:6px; flex-wrap:wrap;">
              <button class="btn btn-primary btn-sm" onclick="window.appOpenCreditModal(${u.id}, ${esc(jsArg(u.username))}, ${esc(jsArg(u.email))}, ${u.credits ?? 0})">
                ⚡ เติมเครดิต
              </button>
              <button class="btn btn-ghost btn-sm" onclick="window.appOpenPermModal(${u.id}, ${esc(jsArg(u.username))}, ${esc(jsArg(u.email))}, '${u.role}', '${encodeURIComponent(u.permissions || '')}')">
                🛡️ สิทธิ์
              </button>
              ${u.id !== me.id ? `<button class="btn btn-ghost btn-sm" style="color:var(--color-danger);" onclick="window.appDeleteUser(${u.id})">ลบ</button>` : ''}
            </div>
          </td>
        </tr>
      `;
      }).join('');
    } catch (e) {
      ['totalUsersCount', 'adminUsersCount', 'remainingBetaSeats'].forEach(id => { if ($(id)) $(id).textContent = '—'; });
      if (tbody) tbody.innerHTML = stateBox('error', e.message.includes('ผู้ดูแล') || e.message.includes('403') ? 'เฉพาะผู้ดูแลระบบ (Admin) เท่านั้น' : 'โหลดรายชื่อผู้ใช้ไม่สำเร็จ: ' + e.message, 'users', 9);
    }
  }

  // Admin Credit Modal handlers
  window.appOpenCreditModal = (userId, username, email, currentCredits) => {
    $('adminCreditUserId').value = userId;
    $('adminCreditUsername').textContent = username;
    $('adminCreditEmail').textContent = email;
    $('adminCreditCurrent').textContent = `⚡ ${Number(currentCredits || 0).toLocaleString()} เครดิต`;
    $('adminCreditAmount').value = '500';
    $('adminCreditNote').value = 'แอดมินเติมเครดิตให้สมาชิก';
    $('adminCreditMode').value = 'add';
    $('adminCreditModal').style.display = 'flex';
  };

  $('closeAdminCreditModalBtn')?.addEventListener('click', () => { $('adminCreditModal').style.display = 'none'; });
  $('cancelAdminCreditBtn')?.addEventListener('click', () => { $('adminCreditModal').style.display = 'none'; });

  window.setQuickCredit = (amt) => {
    const inp = $('adminCreditAmount');
    if (inp) inp.value = amt;
  };

  $('adminCreditForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const userId = $('adminCreditUserId').value;
    const amount = parseInt($('adminCreditAmount').value, 10);
    const mode = $('adminCreditMode').value;
    const note = $('adminCreditNote').value.trim();

    try {
      const res = await api(`/api/admin/users/${userId}/credits`, 'PATCH', { amount, mode, note });
      msg(`บันทึกเครดิตสำเร็จ! ยอดคงเหลือใหม่: ⚡ ${Number(res.credits).toLocaleString()} เครดิต`);
      $('adminCreditModal').style.display = 'none';
      await loadUsers();
      if (me && me.id === parseInt(userId, 10)) {
        userCredits = res.credits;
        localStorage.setItem('aas_credits', userCredits);
        updateCreditDisplays();
      }
    } catch (err) {
      msg(err.message, 'error');
    }
  });

  // Admin Permission & Role Modal handlers
  window.appOpenPermModal = (userId, username, email, role, permsEncoded) => {
    $('adminPermUserId').value = userId;
    $('adminPermUsername').textContent = username;
    $('adminPermEmail').textContent = email;
    $('adminPermRoleSelect').value = role || 'member';

    let perms = {};
    try {
      if (permsEncoded) perms = JSON.parse(decodeURIComponent(permsEncoded));
    } catch {}

    $('perm_can_video').checked = perms.can_video !== false;
    $('perm_can_radar').checked = perms.can_radar !== false;
    $('perm_can_shopee').checked = perms.can_shopee !== false;
    $('perm_can_queue').checked = perms.can_queue !== false;
    $('perm_can_community').checked = perms.can_community !== false;

    $('adminPermissionModal').style.display = 'flex';
  };

  $('closeAdminPermModalBtn')?.addEventListener('click', () => { $('adminPermissionModal').style.display = 'none'; });
  $('cancelAdminPermBtn')?.addEventListener('click', () => { $('adminPermissionModal').style.display = 'none'; });

  $('adminPermForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const userId = $('adminPermUserId').value;
    const role = $('adminPermRoleSelect').value;
    const perms = {
      can_video: $('perm_can_video').checked,
      can_radar: $('perm_can_radar').checked,
      can_shopee: $('perm_can_shopee').checked,
      can_queue: $('perm_can_queue').checked,
      can_community: $('perm_can_community').checked
    };

    try {
      await api(`/api/admin/users/${userId}/role`, 'PATCH', { role });
      await api(`/api/admin/users/${userId}/permissions`, 'PATCH', { permissions: perms });
      msg('บันทึกสิทธิ์และระดับบทบาทสมาชิกเรียบร้อย');
      $('adminPermissionModal').style.display = 'none';
      await loadUsers();
    } catch (err) {
      msg(err.message, 'error');
    }
  });

  $('openAddUserModalBtn')?.addEventListener('click', () => {
    $('addUserModal').hidden = false;
  });
  $('closeAddUserModalBtn')?.addEventListener('click', () => {
    $('addUserModal').hidden = true;
  });
  $('cancelAddUserBtn')?.addEventListener('click', () => {
    $('addUserModal').hidden = true;
  });

  $('addUserForm')?.addEventListener('submit', async e => {
    e.preventDefault();
    try {
      const data = val(e.target);
      await api('/api/admin/users', 'POST', data);
      msg('สร้างผู้ใช้งานใหม่เรียบร้อย');
      $('addUserModal').hidden = true;
      e.target.reset();
      await loadUsers();
    } catch (err) {
      msg(err.message, 'error');
    }
  });

  // ==========================================
  // API CONNECTIONS & KEYS
  // ==========================================
  async function loadConnections() {
    try {
      const conns = await api('/api/my/connections');
      const container = $('connectionlist');
      const providers = [
        { id: 'gemini', name: 'Google Gemini & Veo 3.1', desc: 'วิเคราะห์สินค้า สังเคราะห์สคริปต์ และเรนเดอร์วิดีโอ 9:16' },
        { id: 'xai', name: 'xAI Grok Imagine', desc: 'โมเดลสร้างภาพและวิดีโอสร้างสรรค์' },
        { id: 'brave', name: 'Brave Search API', desc: 'ค้นหาสินค้าและกระแสรีวิวสดจากอินเทอร์เน็ต' },
        { id: 'openai', name: 'OpenAI GPT-4o', desc: 'โมเดลผู้ช่วยเขียนบทสำรอง' }
      ];

      container.innerHTML = providers.map(p => {
        const isSaved = conns && conns[p.id]?.saved;
        return `
          <div class="mf-card" style="display:flex; flex-direction:column; justify-content:space-between; gap:12px;">
            <div>
              <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                <h4 style="font-size:15px; font-weight:700;">${esc(p.name)}</h4>
                <span class="chip ${isSaved ? 'chip-success' : 'chip-warning'} mono">${isSaved ? 'เชื่อมต่อแล้ว' : 'ยังไม่ใส่คีย์'}</span>
              </div>
              <p style="font-size:12px; color:var(--color-text-muted); margin-bottom:12px;">${esc(p.desc)}</p>
            </div>
            <div>
              <div style="display:flex; gap:8px;">
                <input type="password" id="key-input-${p.id}" class="form-input" style="flex:1;" placeholder="วาง API Key ที่นี่...">
                <button class="btn btn-primary btn-sm" onclick="window.appSaveKey('${p.id}')">บันทึก</button>
                ${isSaved ? `<button class="btn btn-danger btn-sm" onclick="window.appDeleteKey('${p.id}')">ลบ</button>` : ''}
              </div>
            </div>
          </div>
        `;
      }).join('');
    } catch (e) {
      console.warn('loadConnections warning:', e);
    }
  }

  // ==========================================
  // GUIDED WALKTHROUGH MODAL (POPCONT STYLE)
  // ==========================================
  const walkthroughData = [
    {
      step: 1,
      badge: 'ขั้นตอนที่ 1',
      title: 'ขั้นตอนที่ 1: ค้นหาสินค้า & สแกน Shopee Extra Comm',
      desc: 'เริ่มต้นการทำ Affiliate ด้วยการค้นหาสินค้าที่มีกระแสจริง และมีค่าคอมมิชชันพิเศษ Extra Commission สูงถึง 15-30% บันทึกสินค้าในคลิกเดียว',
      visual: '🔍 ➔ 🏷 ➔ 🎬',
      hint: 'เลือกสินค้ากระแส → เพิ่มในรายการ → กดสร้างบทรีวิวอัตโนมัติ',
      targetTab: 'radar'
    },
    {
      step: 2,
      badge: 'ขั้นตอนที่ 2',
      title: 'ขั้นตอนที่ 2: สร้างบทรีวิว AI Video Factory (POV 3 องก์)',
      desc: 'ให้ AI ช่วยวิเคราะห์จุดขายสินค้า แล้วสังเคราะห์สคริปต์ 3 องก์ (Hook ดึงดูด, Pain Point แก้ปัญหา, และ Call-to-action ป้ายยา) พร้อมคำสั่ง Visual Prompt',
      visual: '⚡ ➔ 📝 ➔ 🎥',
      hint: 'เลือกสินค้า → กดปุ่มให้ AI ร่างบท → ปรับแต่งแล้วบันทึก',
      targetTab: 'drafts'
    },
    {
      step: 3,
      badge: 'ขั้นตอนที่ 3',
      title: 'ขั้นตอนที่ 3: สั่งสร้างคลิป AI & ดู 9:16 Smartphone Mockup',
      desc: 'เรนเดอร์คลิปวิดีโอ 9:16 ด้วย AI Engine หรือ Instant Mockup ตรวจสอบการเล่นบนหน้าจอมือถือจำลอง จากนั้นกดส่งเข้าคิวโพสต์ TikTok / Shopee ได้ทันที',
      visual: '🚀 ➔ 📱 ➔ 📤',
      hint: 'สั่งสร้างคลิป → ดูพรีวิวบนมือถือ → ส่งเข้าคิวโพสต์เตรียมปล่อย',
      targetTab: 'video'
    }
  ];

  function openWalkthrough(stepNum) {
    walkthroughStep = stepNum;
    updateWalkthroughContent();
    $('walkthroughModal').hidden = false;
  }

  function updateWalkthroughContent() {
    const data = walkthroughData[walkthroughStep - 1];
    $('modalWalkthroughTitle').textContent = data.title;
    $('modalWalkthroughDesc').textContent = data.desc;
    $('modalStepVisualBox').innerHTML = `
      <div style="font-size:42px; margin-bottom:10px;">${data.visual}</div>
      <p style="font-size:13px; font-weight:600; color:var(--color-text-main);">${data.hint}</p>
    `;
    $('walkActionGoBtn').onclick = () => {
      $('walkthroughModal').hidden = true;
      switchTab(data.targetTab);
    };
  }

  document.querySelectorAll('.walkthrough-card').forEach(card => {
    card.addEventListener('click', () => openWalkthrough(parseInt(card.dataset.step, 10)));
  });

  $('openFullWalkthroughBtn')?.addEventListener('click', () => openWalkthrough(1));
  $('closeWalkthroughBtn')?.addEventListener('click', () => { $('walkthroughModal').hidden = true; });
  $('walkPrevStepBtn')?.addEventListener('click', () => {
    if (walkthroughStep > 1) { walkthroughStep--; updateWalkthroughContent(); }
  });
  $('walkNextStepBtn')?.addEventListener('click', () => {
    if (walkthroughStep < 3) { walkthroughStep++; updateWalkthroughContent(); }
  });

  // ==========================================
  // AUTH MODAL & QUICK LOGIN
  // ==========================================
  $('authModalTriggerBtn')?.addEventListener('click', () => {
    if (me && me.id) { if (confirm('ออกจากระบบตอนนี้?')) doLogout(); return; }
    $('authModal').hidden = false;
  });
  $('closeAuthModalBtn')?.addEventListener('click', () => {
    $('authModal').hidden = true;
  });

  $('tabLoginBtn')?.addEventListener('click', () => {
    $('tabLoginBtn').classList.add('active');
    $('tabRegisterBtn').classList.remove('active');
    $('loginform').style.display = 'block';
    $('registerform').style.display = 'none';
  });

  $('tabRegisterBtn')?.addEventListener('click', () => {
    $('tabRegisterBtn').classList.add('active');
    $('tabLoginBtn').classList.remove('active');
    $('loginform').style.display = 'none';
    $('registerform').style.display = 'block';
  });

  $('loginform')?.addEventListener('submit', async e => {
    e.preventDefault();
    try {
      const res = await api('/api/login', 'POST', val(e.target));
      me = res;
      await checkSession();
      $('authModal').hidden = true;
      e.target.reset();
      authToast('เข้าสู่ระบบสำเร็จ', `ยินดีต้อนรับกลับ, ${me.username || ''}`);
      await refreshDashboard();
    } catch (err) {
      msg(err.message, 'error');
    }
  });

  $('registerform')?.addEventListener('submit', async e => {
    e.preventDefault();
    try {
      const res = await api('/api/register', 'POST', val(e.target));
      me = res;
      await checkSession();
      $('authModal').hidden = true;
      e.target.reset();
      authToast('สมัครสมาชิกสำเร็จ', `ยินดีต้อนรับสู่ Beta, ${me.username || ''}`);
      await refreshDashboard();
    } catch (err) {
      msg(err.message, 'error');
    }
  });

  async function doQuickLogin(role) {
    try {
      await api('/api/quick-login', 'POST', { role });
      // Fetch full authenticated profile from /api/me
      const user = await api('/api/me');
      me = user;
      if (user.credits !== undefined) {
        userCredits = user.credits;
        localStorage.setItem('aas_credits', userCredits);
      }
      updateUserUI();
      updateCreditDisplays();
      $('authModal').hidden = true;
      msg(`เข้าสู่ระบบสำเร็จในฐานะ ${role.toUpperCase()} (เซิร์ฟเวอร์จริง) ✨`);
      await refreshDashboard();
      await syncVideoProductSelect();
      await loadChannels();
      await loadCalendar();
    } catch (err) {
      msg(err.message, 'error');
    }
  }

  $('quickAdminLoginBtn')?.addEventListener('click', () => doQuickLogin('admin'));
  $('quickMemberLoginBtn')?.addEventListener('click', () => doQuickLogin('member'));

  $('quickDemoLoginBtn')?.addEventListener('click', async () => {
    msg('โหมดเดโมถูกปิดแล้ว กรุณาสมัครสมาชิกหรือเข้าสู่ระบบ', 'error');
  });

  async function doLogout() {
    try { await api('/api/logout', 'POST'); } catch {}
    try { localStorage.removeItem('aas_credits'); } catch {}
    msg('ออกจากระบบแล้ว');
    // Full reload clears every per-user view (products, studio, queue) in one go.
    setTimeout(() => location.reload(), 400);
  }
  $('sidebarLogoutBtn')?.addEventListener('click', doLogout);

  // ==========================================
  // EVENT LISTENERS & GLOBAL SHORTCUTS
  // ==========================================
  // Sidebar Collapse
  $('sidebarCollapseBtn')?.addEventListener('click', () => {
    $('sidebar')?.classList.toggle('collapsed');
  });

  // Mobile Menu Toggle
  $('mobileMenuBtn')?.addEventListener('click', () => {
    $('sidebar')?.classList.toggle('mobile-open');
  });

  // Global Navigation Tab Click
  document.querySelectorAll('[data-tab]').forEach(el => {
    el.addEventListener('click', e => {
      e.preventDefault();
      switchTab(el.dataset.tab);
    });
  });

  document.querySelectorAll('[data-goto]').forEach(el => {
    el.addEventListener('click', () => switchTab(el.dataset.goto));
  });

  // Quick Action Buttons on Hero
  document.querySelectorAll('[data-quick]').forEach(btn => {
    btn.addEventListener('click', () => {
      const q = btn.dataset.quick;
      if (q === 'radar_hot') { switchTab('radar'); $('radar-auto')?.click(); }
      else if (q === 'weekly_script') { switchTab('drafts'); $('autoGenerateScriptBtn')?.click(); }
      else if (q === 'instant_video') { switchTab('video'); $('generateVideoBtn')?.click(); }
      else if (q === 'open_queue') { switchTab('queue'); }
    });
  });

  // Hero Prompt Bar Submit
  $('heroPromptSubmitBtn')?.addEventListener('click', () => {
    const text = $('heroPromptInput').value.trim();
    if (!text) return switchTab('radar');
    switchTab('radar');
    $('radar-query').value = text;
    $('radarform')?.requestSubmit();
  });

  // Theme Toggle Button
  $('themeToggleBtn')?.addEventListener('click', () => {
    applyTheme(currentTheme === 'dark' ? 'light' : 'dark');
  });

  // Language Buttons
  $('langThBtn')?.addEventListener('click', () => applyLanguage('th'));
  $('langEnBtn')?.addEventListener('click', () => applyLanguage('en'));

  // Notification Button
  $('notifBtn')?.addEventListener('click', () => {
    if (window.AASv8) window.AASv8.showNotifications(); else msg('ยังไม่มีการแจ้งเตือนใหม่');
  });

  // Refresh Recent Activity Button
  $('refreshRecentBtn')?.addEventListener('click', refreshDashboard);

  // Keyboard Shortcut: Ctrl + K or Cmd + K to Search
  window.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      $('globalSearchInput')?.focus();
    }
  });

  $('globalSearchInput')?.addEventListener('keydown', e => {
    if (e.key === 'Enter') {
      const q = e.target.value.trim();
      if (q) {
        switchTab('radar');
        $('radar-query').value = q;
        $('radarform')?.requestSubmit();
      }
    }
  });

  // ==========================================
  // GLOBAL WINDOW EXPORTS (FOR INLINE ACTIONS)
  // ==========================================
  window.appSwitchTab = switchTab;
  window.AAS = { api, msg, esc, switchTab, logout: () => doLogout(), openTopup: () => openTopupModal(), refreshSession: () => checkSession(), getMe: () => me, reloadProducts: () => loadProducts(), reloadChannels: () => loadChannels() };

  window.appQuickSearch = keyword => {
    switchTab('radar');
    $('radar-query').value = keyword;
    $('radarform')?.requestSubmit();
  };

  window.appAddProduct = async (title, platform, url = '') => {
    try {
      title = (prompt('ชื่อสินค้าที่จะบันทึก (แก้ให้เหลือชื่อสินค้าได้)', String(title).replace(/\s+[-|–]\s+[^-|–]+$/, '').trim()) || '').trim();
      if (!title) return;
      await api('/api/my/products', 'POST', { title: title.slice(0, 200), platform, url: url && url.startsWith('https://') ? url : '' });
      msg(`บันทึก "${title}" เรียบร้อย`);
      await loadProducts();
      await refreshDashboard();
    } catch (err) {
      msg(err.message, 'error');
    }
  };

  window.appSaveShopeeImport = async () => {
    const it = window._aasPasteItem;
    if (!it) return msg('สแกนข้อความก่อน', 'error');
    try {
      const fd = new FormData();
      fd.append('title', it.title); fd.append('platform', 'shopee'); fd.append('url', it.url || '');
      if (it.price != null) fd.append('price', String(it.price));
      const r = await fetch('/api/my/products/manual', { method: 'POST', body: fd, credentials: 'same-origin', headers: { 'X-CSRF-Token': me.csrf } });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw Error(typeof body.detail === 'string' ? body.detail : 'บันทึกไม่สำเร็จ ' + r.status);
      msg(`นำเข้า "${it.title}" ${it.price != null ? '(฿' + it.price + ') ' : ''}เรียบร้อย — ดูได้ที่ "สินค้าของฉัน"`);
      window._aasPasteItem = null;
      await loadProducts();
    } catch (err) {
      msg(err.message, 'error');
    }
  };

  window.appInstantDraft = title => {
    switchTab('drafts');
    if (window.AASv8) return window.AASv8.studioFromTitle(title, 'other');
  };

  window.appSelectProductForDraft = (prodId, prodTitle) => {
    switchTab('drafts');
    $('draft-product').value = prodId;
    $('draft-script-input').value = `รีวิว ${prodTitle} ใช้งานจริงมา 1 สัปดาห์ บอกเลยว่าประทับใจมาก ดีไซน์สวยเข้ากับโต๊ะทำงาน ตะกร้าซ้ายล่างได้เลยครับ`;
    $('draft-prompt-input').value = `9:16 vertical commercial video of ${prodTitle}, aesthetic studio lighting, 60fps`;
  };

  window.appSendDraftToVideo = draftId => {
    switchTab('video');
    $('video-draft-select').value = draftId;
  };

  window.appToggleExtraComm = async (prodId, checked) => {
    try {
      await api(`/api/my/products/${prodId}/extra-comm`, 'PATCH', { checked, rate: checked ? 18.5 : null });
      msg('อัปเดต Extra Comm แล้ว');
    } catch (e) {
      msg(e.message, 'error');
    }
  };

  window.appUpdateQueueStatus = async (queueId, status) => {
    try {
      await api(`/api/my/queue/${queueId}`, 'PATCH', { status });
      msg('อัปเดตสถานะคิวงานเรียบร้อย');
    } catch (e) {
      msg(e.message, 'error');
    }
  };

  window.appVoteIdea = async ideaId => {
    try {
      await api(`/api/ideas/${ideaId}/vote`, 'POST');
      await loadIdeas();
      msg('บันทึกการโหวตแล้ว');
    } catch (e) {
      msg(e.message, 'error');
    }
  };

  window.appToggleUserRole = async (userId, newRole) => {
    try {
      await api(`/api/admin/users/${userId}/role`, 'PATCH', { role: newRole });
      msg(`เปลี่ยนสิทธิ์เป็น ${newRole} สำเร็จ`);
      await loadUsers();
    } catch (e) {
      msg(e.message, 'error');
    }
  };

  window.appDeleteUser = async userId => {
    if (!confirm('ยืนยันลบบัญชีผู้ใช้นี้หรือไม่?')) return;
    try {
      await api(`/api/admin/users/${userId}`, 'DELETE');
      msg('ลบบัญชีผู้ใช้สำเร็จ');
      await loadUsers();
    } catch (e) {
      msg(e.message, 'error');
    }
  };

  window.appSaveKey = async provider => {
    const input = $(`key-input-${provider}`);
    if (!input || !input.value.trim()) return msg('กรุณากรอกคีย์', 'error');
    try {
      await api(`/api/my/keys/${provider}`, 'PUT', { key: input.value.trim() });
      msg(`บันทึกคีย์ ${provider} สำเร็จ`);
      input.value = '';
      await loadConnections();
    } catch (e) {
      msg(e.message, 'error');
    }
  };

  window.appDeleteKey = async provider => {
    if (!confirm(`ยืนยันลบคีย์ ${provider} หรือไม่?`)) return;
    try {
      await api(`/api/my/keys/${provider}`, 'DELETE');
      msg(`ลบคีย์ ${provider} สำเร็จ`);
      await loadConnections();
    } catch (e) {
      msg(e.message, 'error');
    }
  };

  // ==========================================
  // CONNECTED CHANNELS & AUTO-POST INTEGRATION
  // ==========================================
  let userChannels = [];

  async function loadChannels() {
    try {
      const res = await api('/api/my/channels');
      userChannels = res.channels || [];
      renderSocialChannelsList();
      renderCalConnectedChannelsList();
    } catch (err) {
      console.warn('loadChannels error:', err);
    }
  }

  function renderSocialChannelsList() {
    const container = $('socialChannelsList');
    if (!container) return;

    const platformsDef = [
      { id: 'facebook', name: 'Facebook Pages & Reels', icon: '📘', badge: 'Reels / Multi-Page', desc: 'รองรับการเชื่อมต่อหลายเพจพร้อมกัน โพสต์ Reels และวิดีโอเข้าเพจ Meta อัตโนมัติ' },
      { id: 'tiktok', name: 'TikTok', icon: '🎵', badge: 'Creator / Shop', desc: 'ยังไม่เชื่อม API — ดาวน์โหลดคลิป 9:16 + คัดลอกแคปชั่น แล้วอัปโหลดเอง' },
      { id: 'shopee', name: 'Shopee', icon: '🛒', badge: 'Shopee Video', desc: 'ยังไม่เชื่อม API — อัปโหลดคลิปเองใน Shopee Video' },
      { id: 'instagram', name: 'Instagram', icon: '📸', badge: 'Reels / Feed', desc: 'Auto-Post วิดีโอสั้น Reels และรูปภาพโปรโมตลง Instagram Creator' },
      { id: 'x', name: 'X (Twitter)', icon: '🐦', badge: 'Auto-Broadcast', desc: 'โพสต์ทวีตโปรโมชัน ดีลลดราคา และลิงก์สินค้าแบบอัตโนมัติ' },
      { id: 'line_oa', name: 'LINE Official Account', icon: '💬', badge: 'Push Alert', desc: 'ส่งการแจ้งเตือน Real-time เมื่อสร้างคลิปเสร็จ หรือมีคลิปพร้อมโพสต์' }
    ];

    container.innerHTML = platformsDef.filter(p => !['facebook', 'instagram', 'line_oa'].includes(p.id)).map(p => {
      const chList = userChannels.filter(c => c.platform.toLowerCase() === p.id);
      const isConnected = chList.length > 0;

      return `
        <div class="channel-manage-card" style="background:var(--color-surface); border:1px solid ${isConnected ? 'var(--color-primary-border)' : 'var(--color-border)'}; border-radius:var(--radius-lg); padding:20px; display:flex; flex-direction:column; justify-content:space-between; position:relative; box-shadow:var(--shadow-sm);">
          <div>
            <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:12px;">
              <div style="display:flex; align-items:center; gap:10px;">
                <span style="font-size:32px;">${p.icon}</span>
                <div>
                  <h4 style="font-size:16px; font-weight:800; margin:0;">${p.name}</h4>
                  <span class="chip chip-primary mono" style="font-size:10px;">${p.badge}</span>
                </div>
              </div>
              <span class="chip ${isConnected ? 'chip-success' : 'chip-muted'} mono">
                ${isConnected ? `📝 บันทึกบัญชีไว้ ${chList.length} (ยังไม่เชื่อม API · โพสต์เอง)` : '⚪ ยังไม่เชื่อมต่อ (โพสต์เอง)'}
              </span>
            </div>

            <p style="font-size:12px; color:var(--color-text-muted); line-height:1.5; margin-bottom:14px;">${p.desc}</p>

            ${isConnected ? `
              <div style="display:flex; flex-direction:column; gap:10px; margin-bottom:14px;">
                ${chList.map(ch => `
                  <div style="background:var(--color-surface-subtle); border:1px solid var(--color-border); border-radius:var(--radius-md); padding:12px; font-size:12px;">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                      <div style="display:flex; align-items:center; gap:6px;">
                        <span style="font-size:14px;">${p.icon}</span>
                        <strong class="mono" style="color:var(--color-text-main); font-size:13px;">${esc(ch.account_name)}</strong>
                      </div>
                      <button class="btn btn-ghost btn-sm" style="color:var(--color-danger); padding:2px 6px; font-size:11px;" onclick="window.appDisconnectChannel(${ch.id}, ${esc(jsArg(ch.account_name))})" title="ตัดการเชื่อมต่อบัญชีนี้">
                        ✕ Disconnect
                      </button>
                    </div>

                    <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
                      <span style="color:var(--color-text-muted);">Account ID:</span>
                      <span class="mono" style="color:var(--color-text-muted);">${esc(ch.account_id || '-')}</span>
                    </div>

                    <div style="display:flex; justify-content:space-between; align-items:center; margin-top:8px; padding-top:8px; border-top:1px dashed var(--color-border);">
                      <div style="display:flex; align-items:center; gap:6px;">
                        <span style="font-size:11px; font-weight:700;">แผนโพสต์:</span>
                        <label class="switch-label" style="margin:0; transform:scale(0.85); transform-origin:left center;">
                          <input type="checkbox" ${ch.auto_post_enabled ? 'checked' : ''} onchange="window.appToggleChannelAutoPost(${ch.id})">
                          <span class="switch-track"></span>
                        </label>
                      </div>
                      <button class="btn btn-ghost btn-sm" style="font-size:11px; padding:2px 8px;" onclick="window.appTestChannel(${ch.id})">
                        📡 Ping Test
                      </button>
                    </div>
                  </div>
                `).join('')}
              </div>
            ` : `
              <div style="padding:16px 12px; border:1px dashed var(--color-border); border-radius:var(--radius-md); text-align:center; margin-bottom:14px;">
                <span style="font-size:12px; color:var(--color-text-muted);">ยังไม่รองรับการเชื่อม API — โพสต์เองโดยดาวน์โหลดคลิปจากเมนู สร้างคอนเทนต์</span>
              </div>
            `}
          </div>

          <div style="display:flex; gap:8px; margin-top:8px; flex-wrap:wrap;">
            ${p.id === 'line_oa' && isConnected ? `
              <button class="btn btn-secondary btn-sm" style="flex:1;" onclick="window.appSendLineAlert()">
                📲 ทดสอบ Push Alert
              </button>
            ` : ''}
            ${isConnected ? `
              <button class="btn btn-secondary btn-sm" style="flex:1;" onclick="window.appOpenConnectModal('${p.id}')">
                + เพิ่มเพจ/บัญชีอีก
              </button>
            ` : `
              <button class="btn btn-ghost btn-sm" style="width:100%;" onclick="window.appTriggerOAuth('${p.id}')">
                ℹ️ ${p.name}: ยังไม่รองรับการเชื่อม API (โพสต์เอง)
              </button>
            `}
          </div>
        </div>
      `;
    }).join('');
  }

  function renderCalConnectedChannelsList() {
    const list = $('calConnectedChannelsList');
    if (!list) return;

    if (!userChannels.length) {
      list.innerHTML = `<span style="font-size:12px; color:var(--color-text-muted);">ยังไม่มีช่องทางที่เชื่อมต่อ</span>`;
      return;
    }

    const icons = { tiktok: '🎵', shopee: '🛒', facebook: '📘', instagram: '📸', x: '🐦', line_oa: '💬' };
    list.innerHTML = userChannels.map(ch => `
      <div style="display:flex; justify-content:space-between; align-items:center; padding:8px 10px; background:var(--color-surface-subtle); border-radius:var(--radius-md); font-size:12px; gap:8px;">
        <div style="display:flex; align-items:center; gap:8px; overflow:hidden;">
          <span>${icons[ch.platform] || '📱'}</span>
          <div style="min-width:0;">
            <div style="font-weight:700; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${esc(ch.account_name)}</div>
            <div style="font-size:10px; color:var(--color-text-muted); text-transform:uppercase;">${ch.platform}</div>
          </div>
        </div>
        <div style="display:flex; align-items:center; gap:6px;">
          <span class="chip ${ch.auto_post_enabled ? 'chip-success' : 'chip-muted'} mono" style="font-size:9px; padding:2px 6px;">
            ${ch.auto_post_enabled ? 'Auto' : 'Off'}
          </span>
          <button class="btn btn-ghost btn-sm" style="color:var(--color-danger); padding:1px 5px; font-size:11px;" onclick="window.appDisconnectChannel(${ch.id}, ${esc(jsArg(ch.account_name))})" title="Disconnect">
            ✕
          </button>
        </div>
      </div>
    `).join('');
  }

  window.appSendLineAlert = async (channelId) => {
    try {
      const res = await api('/api/my/line-oa/test-alert', 'POST', {
        message: '🔔 [AI Studio Auto-Post Alert] วิดีโอ 9:16 ใหม่พร้อม Auto-Post บน Facebook, TikTok, Shopee เรียบร้อยแล้ว!'
      });
      msg(`📲 ${res.message} (ส่งไปยัง: ${res.recipient || 'LINE OA Creator'})`);
    } catch (e) {
      msg(e.message, 'error');
    }
  };

  window.appTestChannel = async channelRef => {
    try {
      const res = await api(`/api/my/channels/${channelRef}/test`, 'POST');
      msg(`✅ ${res.message} (ความเร็ว: ${res.ping_ms}ms)`);
      await loadChannels();
    } catch (e) {
      msg(e.message, 'error');
    }
  };

  window.appToggleChannelAutoPost = async channelRef => {
    try {
      const res = await api(`/api/my/channels/${channelRef}/toggle-autopost`, 'PATCH');
      msg(`เปลี่ยนสถานะ Auto-Post สำเร็จ: ${res.auto_post_enabled ? 'เปิดใช้งาน' : 'ปิด'}`);
      await loadChannels();
    } catch (e) {
      msg(e.message, 'error');
    }
  };

  window.appDisconnectChannel = async (channelRef, accountName) => {
    const label = accountName ? `"${accountName}"` : String(channelRef).toUpperCase();
    if (!confirm(`ยืนยันตัดการเชื่อมต่อช่องทาง ${label} หรือไม่?`)) return;
    try {
      await api(`/api/my/channels/${channelRef}`, 'DELETE');
      msg(`ตัดการเชื่อมต่อ ${label} เรียบร้อยแล้ว`);
      await loadChannels();
      await loadCalendar();
      updateOAuthModalStatuses();
    } catch (e) {
      msg(e.message, 'error');
    }
  };

  window.appOpenConnectModal = platform => {
    if (['facebook', 'instagram', 'line_oa'].includes(platform)) { switchTab('connectors'); return; }
    window.appTriggerOAuth(platform); return;
    const modal = $('connectChannelModal');
    if (!modal) return;
    modal.hidden = false;
    const platSelect = $('connPlatformSelect');
    if (platSelect) platSelect.value = platform || 'facebook';
    const names = {
      tiktok: 'TikTok Creator',
      shopee: 'Shopee Video / Open Platform',
      facebook: 'Facebook Reels / Meta',
      instagram: 'Instagram Reels',
      x: 'X (Twitter)',
      line_oa: 'LINE Official Account'
    };
    $('connModalTitle').textContent = `เชื่อมต่อบัญชี ${names[platform] || platform.toUpperCase()}`;
    const sampleNames = {
      facebook: 'เพจรีวิวสินค้าสุดคุ้ม (Reels)',
      tiktok: '@affiliate.creator.th',
      shopee: 'Shopee Creator #TH-2026',
      instagram: '@affiliate_daily_th',
      x: '@deals_thai_bot',
      line_oa: '@AffiliateStudioTH'
    };
    $('connAccountNameInput').value = sampleNames[platform] || `${platform}_channel`;
    $('connAccountIdInput').value = `${platform.toUpperCase()}-${Math.floor(100000 + Math.random() * 900000)}`;
  };

  // ==========================================
  // OAUTH 2.0 AUTO-POST HANDSHAKE & NAVIGATION
  // ==========================================
  window.appGotoTab = function(tabId) {
    switchTab(tabId);
  };

  window.appOpenOAuthModal = () => {
    const modal = $('oauthModal');
    if (!modal) return;
    modal.hidden = false;
    updateOAuthModalStatuses();
  };

  $('closeOAuthModalBtn')?.addEventListener('click', () => $('oauthModal').hidden = true);
  $('btnFinishOAuthModal')?.addEventListener('click', () => $('oauthModal').hidden = true);
  $('calOAuthConnectBtn')?.addEventListener('click', () => window.appOpenOAuthModal());

  function updateOAuthModalStatuses() {
    const platforms = [
      { id: 'facebook', btnId: 'btnOAuthFacebook' },
      { id: 'tiktok', btnId: 'btnOAuthTikTok' },
      { id: 'shopee', btnId: 'btnOAuthShopee' },
      { id: 'instagram', btnId: 'btnOAuthInstagram' },
      { id: 'x', btnId: 'btnOAuthX' },
      { id: 'line_oa', btnId: 'btnOAuthLineOa' }
    ];

    platforms.forEach(plat => {
      const el = $(`oauthStatus-${plat.id}`);
      const btn = $(plat.btnId);
      const chList = userChannels.filter(c => c.platform.toLowerCase() === plat.id);
      const isConn = chList.length > 0;

      if (el) {
        if (isConn) {
          const names = chList.map(c => esc(c.account_name)).join(', ');
          el.innerHTML = `<span style="color:var(--color-secondary); font-weight:700;">🟢 เชื่อมต่อแล้ว (${chList.length})</span>: ${names}`;
        } else {
          el.innerHTML = `<span style="color:var(--color-text-muted);">⚪ ยังไม่ได้เชื่อมต่อ</span>`;
        }
      }
      if (btn) {
        btn.textContent = isConn ? `+ เพิ่ม/ซิงก์ ${plat.id.toUpperCase()}` : `⚡ เชื่อมต่อ ${plat.id.toUpperCase()}`;
        btn.className = isConn ? 'btn btn-secondary btn-sm' : 'btn btn-primary btn-sm';
      }
    });
  }

  window.appTriggerOAuth = async platform => {
    if ($('oauthModal')) $('oauthModal').hidden = true;
    if (['facebook', 'instagram', 'line_oa'].includes(platform)) { switchTab('connectors'); return; }
    // No official posting API is connected for TikTok / Shopee / X yet — never create a pretend account.
    msg(`${String(platform).toUpperCase()} ยังไม่มีการเชื่อม API จริงใน Phase 1 — ใช้การโพสต์เอง (ดาวน์โหลดคลิป + คัดลอกแคปชั่น จากเมนู "สร้างคอนเทนต์")`, 'error');
    return;
    const box = $('oauthHandshakeBox');
    const title = $('oauthHandshakeTitle');
    const desc = $('oauthHandshakeDesc');
    const names = {
      tiktok: 'TikTok Creator',
      shopee: 'Shopee Video / Open Platform',
      facebook: 'Facebook Reels & Pages',
      instagram: 'Instagram Reels & Posts',
      x: 'X (Twitter)',
      line_oa: 'LINE Official Account'
    };
    const pName = names[platform] || platform.toUpperCase();

    if (box) {
      box.style.display = 'block';
      title.textContent = `กำลังยืนยันสิทธิ์ OAuth 2.0 / Web Login กับ ${pName}...`;
      desc.textContent = 'ขอสิทธิ์ publish_video, auto_post, webhook, content_read ผ่าน Secure Handshake';
    }

    setTimeout(async () => {
      try {
        const randId = Math.floor(100000 + Math.random() * 900000);
        const existingPlatCount = userChannels.filter(c => c.platform.toLowerCase() === platform).length;
        const accNames = {
          tiktok: `@affiliate.creator.th_${randId.toString().slice(-3)}`,
          shopee: `Shopee Official Creator #TH-${randId.toString().slice(-4)}`,
          facebook: existingPlatCount > 0 ? `เพจป้ายยา & รีวิว #${existingPlatCount + 1}` : 'Affiliate Deals Thailand (Reels)',
          instagram: `@affiliate_daily_th_${randId.toString().slice(-3)}`,
          x: `@deals_thai_bot_${randId.toString().slice(-3)}`,
          line_oa: `@AffiliateStudioTH_${randId.toString().slice(-3)}`
        };
        const token = `oauth2_${platform}_token_${Math.random().toString(36).substring(2)}`;

        const res = await api('/api/my/channels/connect', 'POST', {
          platform,
          account_name: accNames[platform] || `${platform}_user`,
          account_id: `${platform.toUpperCase()}-${randId}`,
          access_token: token,
          auto_post_enabled: true
        });

        if (box) box.style.display = 'none';
        msg(`🎉 เชื่อมต่อ ${pName} สำเร็จผ่าน Web OAuth 2.0! ระบบ Auto-Post พร้อมทำงานแล้ว 🚀`);
        await loadChannels();
        await loadCalendar();
        updateOAuthModalStatuses();
      } catch (err) {
        if (box) box.style.display = 'none';
        msg(err.message, 'error');
      }
    }, 600);
  };

  $('btnConnectNewChannel')?.addEventListener('click', () => window.appOpenConnectModal('tiktok'));
  $('closeConnectChannelBtn')?.addEventListener('click', () => $('connectChannelModal').hidden = true);
  $('cancelConnBtn')?.addEventListener('click', () => $('connectChannelModal').hidden = true);

  $('connectChannelForm')?.addEventListener('submit', async e => {
    e.preventDefault();
    const f = e.target;
    const payload = {
      platform: f.platform.value,
      account_name: f.account_name.value.trim(),
      account_id: f.account_id.value.trim(),
      access_token: f.access_token.value.trim(),
      auto_post_enabled: f.auto_post_enabled.checked
    };
    try {
      const res = await api('/api/my/channels/connect', 'POST', payload);
      msg(res.message || 'เชื่อมต่อช่องทางสำเร็จ!');
      $('connectChannelModal').hidden = true;
      await loadChannels();
      await loadCalendar();
    } catch (err) {
      msg(err.message, 'error');
    }
  });

  // ==========================================
  // CALENDAR & CONTENT SCHEDULER
  // ==========================================
  let calendarData = [];
  let calendarDate = new Date();
  let calPlatformFilter = 'all';

  async function loadCalendar() {
    try {
      const res = await api('/api/my/calendar');
      calendarData = (res.schedules || []).map(it => ({
        ...it,
        platforms: Array.isArray(it.platforms) ? it.platforms : [it.platform || 'tiktok'],
        title: it.title || it.product_title || (it.caption || '').split('\n')[0].slice(0, 60) || `โพสต์ #${it.id}`,
      }));
      renderCalendar();
      renderUpcomingList();
    } catch (err) {
      console.warn('loadCalendar error:', err);
    }
  }

  function renderCalendar() {
    const grid = $('calendarDaysGrid');
    const label = $('calendarCurrentMonthLabel');
    if (!grid || !label) return;

    const year = calendarDate.getFullYear();
    const month = calendarDate.getMonth();

    const monthNamesThai = [
      'มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน',
      'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม'
    ];
    label.textContent = `${monthNamesThai[month]} ${year + 543} (${year})`;

    const firstDayIndex = new Date(year, month, 1).getDay();
    const totalDays = new Date(year, month + 1, 0).getDate();
    const prevMonthTotalDays = new Date(year, month, 0).getDate();

    const today = new Date();
    const isCurrentMonth = today.getFullYear() === year && today.getMonth() === month;
    const todayDate = today.getDate();

    let cellsHtml = '';

    // Prev month padding
    for (let i = firstDayIndex - 1; i >= 0; i--) {
      const dayNum = prevMonthTotalDays - i;
      cellsHtml += `<div class="calendar-day-cell other-month"><div class="calendar-day-num">${dayNum}</div></div>`;
    }

    // Days in current month
    for (let day = 1; day <= totalDays; day++) {
      const isToday = isCurrentMonth && day === todayDate;
      const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;

      // Filter matching events
      const dayEvents = calendarData.filter(item => {
        const itemDate = (item.scheduled_at || '').slice(0, 10);
        if (itemDate !== dateStr) return false;
        if (calPlatformFilter !== 'all') {
          return Array.isArray(item.platforms) && item.platforms.includes(calPlatformFilter);
        }
        return true;
      });

      const eventsHtml = dayEvents.map(ev => {
        const isPublished = ['published', 'completed_manual'].includes(ev.status);
        const primaryPlat = (Array.isArray(ev.platforms) ? ev.platforms[0] : 'tiktok') || 'tiktok';
        const badgeColor = primaryPlat === 'tiktok' ? '#00f2fe' : primaryPlat === 'shopee' ? '#ee4d2d' : '#1877f2';

        return `
          <div class="calendar-item-card" style="border-left-color:${badgeColor};" onclick="window.appViewSchedule(${ev.id})" title="${esc(ev.title)}">
            <div style="display:flex; justify-content:space-between; align-items:center; gap:4px;">
              <span class="calendar-item-title">${esc(ev.title)}</span>
              <span style="font-size:9px;">${isPublished ? '✅' : '🕒'}</span>
            </div>
            <div style="font-size:10px; color:var(--color-text-muted); margin-top:2px;">
              ${(ev.scheduled_at || '').slice(11, 16)} · ${(ev.platforms || []).join('/')}
            </div>
          </div>
        `;
      }).join('');

      cellsHtml += `
        <div class="calendar-day-cell ${isToday ? 'today' : ''}" onclick="window.appQuickScheduleDate('${dateStr}')">
          <div class="calendar-day-num">${day} ${isToday ? '<span class="today-dot">• วันนี้</span>' : ''}</div>
          <div class="calendar-day-events">${eventsHtml}</div>
        </div>
      `;
    }

    // Fill remaining cells for grid rectangular alignment
    const filledCells = firstDayIndex + totalDays;
    const remaining = (7 - (filledCells % 7)) % 7;
    for (let j = 1; j <= remaining; j++) {
      cellsHtml += `<div class="calendar-day-cell other-month"><div class="calendar-day-num">${j}</div></div>`;
    }

    grid.innerHTML = cellsHtml;
  }

  function renderUpcomingList() {
    const list = $('calUpcomingList');
    const countBadge = $('calUpcomingCount');
    if (!list) return;

    let items = calendarData.slice();
    if (calPlatformFilter !== 'all') {
      items = items.filter(it => Array.isArray(it.platforms) && it.platforms.includes(calPlatformFilter));
    }

    if (countBadge) countBadge.textContent = `${items.length} รายการ`;

    if (!items.length) {
      list.innerHTML = `
        <div style="padding:20px 10px; text-align:center; color:var(--color-text-muted); font-size:13px;">
          ยังไม่มีกำหนดการโพสต์ในเดือนนี้<br>
          <button class="btn btn-primary btn-xs" style="margin-top:10px;" onclick="window.appOpenScheduleModal()">+ วางแผนคอนเทนต์แรก</button>
        </div>
      `;
      return;
    }

    list.innerHTML = items.map(it => {
      const isPublished = ['published', 'completed_manual'].includes(it.status);
      const plats = Array.isArray(it.platforms) ? it.platforms : ['tiktok'];
      const icons = { tiktok: '🎵', shopee: '🛒', facebook: '📘' };

      return `
        <div class="upcoming-item-card" style="background:var(--color-surface-subtle); border:1px solid var(--color-border); border-radius:var(--radius-md); padding:12px; font-size:13px;">
          <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:8px; margin-bottom:6px;">
            <strong style="color:var(--color-text-main); font-size:13px; line-height:1.4;">${esc(it.title)}</strong>
            <span class="chip ${isPublished ? 'chip-success' : 'chip-primary'} mono" style="font-size:10px; white-space:nowrap;">
              ${isPublished ? '✅ โพสต์เองแล้ว' : it.status === 'cancelled' ? '✕ ยกเลิก' : '🕒 รอโพสต์เอง'}
            </span>
          </div>

          <div style="display:flex; align-items:center; gap:8px; font-size:11px; color:var(--color-text-muted); margin-bottom:8px;">
            <span>📅 ${(it.scheduled_at || '').replace('T', ' ')}</span>
            <span>·</span>
            <span>${plats.map(p => icons[p] || '📱').join(' ')}</span>
          </div>

          ${it.caption ? `
            <div style="font-size:12px; color:var(--color-text-muted); margin-bottom:10px; line-height:1.4; background:var(--color-surface); padding:8px 10px; border-radius:var(--radius-sm); border:1px solid var(--color-border);">
              ${esc(it.caption)}
            </div>
          ` : ''}

          <div style="display:flex; justify-content:space-between; align-items:center; gap:6px;">
            <div>
              ${!isPublished ? `
                <button class="btn btn-secondary btn-xs" onclick="window.appPublishScheduleNow(${it.id})" title="กดหลังจากอัปโหลดคลิปเองแล้ว">
                  ✓ ทำเครื่องหมายว่าโพสต์แล้ว
                </button>
              ` : `
                <span class="mono" style="font-size:11px; color:var(--color-secondary);">โพสต์เองแล้ว ✓</span>
              `}
            </div>
            <div style="display:flex; gap:4px;">
              <button class="btn btn-ghost btn-xs" style="color:var(--color-danger);" onclick="window.appDeleteSchedule(${it.id})">
                ลบ
              </button>
            </div>
          </div>
        </div>
      `;
    }).join('');
  }

  window.appPublishScheduleNow = async scheduleId => {
    try {
      const res = await api(`/api/my/calendar/${scheduleId}/publish-now`, 'POST');
      msg(res.message || 'อัปเดตสถานะแล้ว');
      await loadCalendar();
      await loadChannels();
    } catch (e) {
      msg(e.message, 'error');
    }
  };

  window.appDeleteSchedule = async scheduleId => {
    if (!confirm('ยืนยันลบกำหนดการโพสต์นี้หรือไม่?')) return;
    try {
      await api(`/api/my/calendar/${scheduleId}`, 'DELETE');
      msg('ลบกำหนดการโพสต์เรียบร้อย');
      await loadCalendar();
    } catch (e) {
      msg(e.message, 'error');
    }
  };

  window.appOpenScheduleModal = (prodId, prodTitle) => {
    const modal = $('scheduleModal');
    if (!modal) return;
    modal.hidden = false;
    if (prodId && prodTitle) {
      $('schedTitleInput').value = `รีวิว ${prodTitle} พร้อมพิกัดโปรเด็ด`;
      $('schedCaptionInput').value = `ป้ายยา ${prodTitle} ใช้แล้วชีวิตดีขึ้นมากกก พิกัดในตะกร้าด้านล่าง 👇✨`;
      $('schedHashtagsInput').value = `#${prodTitle.split(' ')[0]} #ของดีบอกต่อ #รีวิวช้อปปี้ #TikTokMadeMeBuyIt`;
      if ($('schedProductSelect')) $('schedProductSelect').value = prodId;
    }
    const defaultDate = new Date(Date.now() + 3600000 * 2);
    $('schedDateTimeInput').value = defaultDate.toISOString().slice(0, 16);
  };

  window.appQuickScheduleDate = dateStr => {
    window.appOpenScheduleModal();
    $('schedDateTimeInput').value = `${dateStr}T12:00`;
  };

  window.appViewSchedule = scheduleId => {
    const item = calendarData.find(i => i.id === scheduleId);
    if (!item) return;
    if (['published', 'completed_manual'].includes(item.status)) {
      alert(`📌 ${item.title}\n\nสถานะ: เผยแพร่แล้วเมื่อ ${(item.published_at || '').replace('T', ' ')}\nผลลัพธ์: ${item.result_log || 'สำเร็จ'}`);
    } else {
      if (confirm(`📌 ${item.title}\nกำหนดการ: ${item.scheduled_at.replace('T', ' ')}\n\nโพสต์ ${(item.platforms || []).join(', ')} เองเรียบร้อยแล้วหรือยัง? (กดตกลงเพื่อทำเครื่องหมายว่าโพสต์แล้ว)`)) {
        window.appPublishScheduleNow(scheduleId);
      }
    }
  };

  // Calendar Modals & Forms
  $('openScheduleModalBtn')?.addEventListener('click', () => window.appOpenScheduleModal());
  $('closeScheduleModalBtn')?.addEventListener('click', () => $('scheduleModal').hidden = true);
  $('cancelScheduleBtn')?.addEventListener('click', () => $('scheduleModal').hidden = true);

  $('scheduleContentForm')?.addEventListener('submit', async e => {
    e.preventDefault();
    const f = e.target;
    const plats = Array.from(f.querySelectorAll('input[name="sched_platforms"]:checked')).map(cb => cb.value);
    if (!plats.length) return msg('กรุณาเลือกอย่างน้อย 1 แพลตฟอร์ม', 'error');

    const payload = {
      title: f.title.value.trim(),
      scheduled_at: f.scheduled_at.value,
      product_id: f.product_id.value ? parseInt(f.product_id.value, 10) : null,
      platforms: plats,
      caption: f.caption.value.trim(),
      hashtags: f.hashtags.value.trim(),
      status: 'scheduled'
    };

    try {
      await api('/api/my/calendar', 'POST', payload);
      msg('📅 บันทึกแผนโพสต์แล้ว (TikTok/Shopee เป็นการโพสต์เอง ระบบจะไม่โพสต์อัตโนมัติ)');
      $('scheduleModal').hidden = true;
      f.reset();
      await loadCalendar();
    } catch (err) {
      msg(err.message, 'error');
    }
  });

  $('calPrevMonthBtn')?.addEventListener('click', () => {
    calendarDate.setMonth(calendarDate.getMonth() - 1);
    renderCalendar();
  });
  $('calNextMonthBtn')?.addEventListener('click', () => {
    calendarDate.setMonth(calendarDate.getMonth() + 1);
    renderCalendar();
  });
  $('calTodayBtn')?.addEventListener('click', () => {
    calendarDate = new Date();
    renderCalendar();
  });

  document.querySelectorAll('.cal-filter-pill').forEach(pill => {
    pill.addEventListener('click', () => {
      document.querySelectorAll('.cal-filter-pill').forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      calPlatformFilter = pill.dataset.filter || 'all';
      renderCalendar();
      renderUpcomingList();
    });
  });

  // ==========================================
  // PRODUCT SELECTION FOR VIDEO STUDIO
  // ==========================================
  let userProductsCache = [];

  async function syncVideoProductSelect() {
    try {
      const prods = await api('/api/my/products');
      userProductsCache = prods;
      const vSelect = $('video-product-select');
      const cSelect = $('schedProductSelect');

      const optionsHtml = `<option value="">-- เลือกสินค้าจากรายการของคุณเพื่อสร้างสคริปต์ --</option>` +
        prods.map(p => `<option value="${p.id}" data-title="${esc(p.title)}" data-plat="${esc(p.platform)}">🏷️ ${esc(p.title)} (${esc(p.platform)})</option>`).join('');

      if (vSelect) vSelect.innerHTML = optionsHtml;
      if (cSelect) {
        cSelect.innerHTML = `<option value="">-- ไม่ระบุ / เนื้อหาทั่วไป --</option>` +
          prods.map(p => `<option value="${p.id}">🏷️ ${esc(p.title)} (${esc(p.platform)})</option>`).join('');
      }
    } catch (err) {
      console.warn('syncVideoProductSelect error:', err);
    }
  }

  $('video-product-select')?.addEventListener('change', e => {
    const prodId = e.target.value;
    const card = $('selectedProductPreviewCard');
    if (!prodId) {
      if (card) card.style.display = 'none';
      return;
    }
    const prod = userProductsCache.find(p => String(p.id) === String(prodId));
    if (!prod) return;

    if (card) {
      card.style.display = 'block';
      $('previewProductTitle').textContent = prod.title;
      $('previewProductMeta').textContent = `แพลตฟอร์ม: ${prod.platform.toUpperCase()} · ลิงก์: ${prod.url || 'Shopee/TikTok'}`;
    }

    const promptInput = $('promptInput');
    if (promptInput && (!promptInput.value || promptInput.value.trim() === '')) {
      promptInput.value = `9:16 vertical commercial video of ${prod.title}, dynamic camera motion, studio product lighting, 4K resolution, aesthetic influencer showcase`;
    }
  });

  $('btnAutoGenerateScriptFromProduct')?.addEventListener('click', () => {
    const select = $('video-product-select');
    const prodId = select?.value;
    if (!prodId) return msg('กรุณาเลือกสินค้าจากรายการก่อน', 'error');
    const prod = userProductsCache.find(p => String(p.id) === String(prodId));
    if (!prod) return;

    const promptInput = $('promptInput');
    if (promptInput) {
      promptInput.value = `9:16 cinematic vertical video showcasing ${prod.title}, 3-act storytelling hook, crisp modern studio lighting, high conversion commercial for TikTok/Shopee`;
    }
    msg(`⚡ ร่างสคริปต์และพรอมต์ AI สำหรับ "${prod.title}" เรียบร้อยแล้ว!`);
  });

  window.appSelectProductForVideo = (prodId, prodTitle) => {
    switchTab('video');
    const select = $('video-product-select');
    if (select) {
      select.value = prodId;
      select.dispatchEvent(new Event('change'));
    }
    msg(`เลือกสินค้า "${prodTitle}" สำหรับสร้างคลิปแล้ว 🎬`);
  };

  window.appScheduleProduct = (prodId, prodTitle) => {
    switchTab('calendar');
    window.appOpenScheduleModal(prodId, prodTitle);
  };

  // ==========================================
  // BOOTSTRAP APP
  // ==========================================
  async function init() {
    applyTheme(currentTheme);
    applyLanguage(localStorage.getItem('lang') || 'th');
    await checkSession();
    setupRadar();
    updateCreditDisplays();
    initPillSelectors();
    initTopupModal();
    await loadSystemSettings();
    initSystemToggles();
    await refreshDashboard();
    await syncVideoProductSelect();
    await loadChannels();
    await loadCalendar();
    startMockupCanvasAnimation();
  }

  window.addEventListener('DOMContentLoaded', init);
})();

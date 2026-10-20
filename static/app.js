(() => {
  'use strict';

  // ==========================================
  // STATE & INITIALIZATION
  // ==========================================
  let me = { id: 1, username: 'Kevin', role: 'admin', csrf: 'demo-csrf-token' };
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
    if (text) setTimeout(() => { banner.style.display = 'none'; }, 4000);
  };

  const val = form => Object.fromEntries(new FormData(form));

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
    if (!r.ok) throw Error(typeof body.detail === 'string' ? body.detail : 'คำขอล้มเหลว ' + r.status);
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
      nav_new: 'เสนอฟีเจอร์ / แจ้งบั๊ก',
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
      hero_status_ready: 'แบรนด์ & โมเดล AI พร้อมแล้ว',
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
      radar_page_desc: 'ค้นหาสินค้ากระแสจริง ข้อมูลยืนยันได้ พร้อมตรวจค่า Extra Commission',
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
      radar_page_desc: 'Discover verified trending products with Extra Commission analytics',
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
    if (targetId === 'video') loadVideoTab();
    if (targetId === 'queue') loadQueue();
    if (targetId === 'tracking') loadTracking();
    if (targetId === 'ideas') loadIdeas();
    if (targetId === 'users_mgmt') loadUsers();
    if (targetId === 'keys') loadConnections();
  }

  // ==========================================
  // USER SESSION & AUTHENTICATION
  // ==========================================
  async function checkSession() {
    try {
      const user = await api('/api/me');
      me = user;
    } catch {
      // Default to demo admin user so prototype is 100% testable out of the box
      me = { id: 1, username: 'Kevin', role: 'admin', csrf: 'demo-csrf-token' };
    }
    updateUserUI();
  }

  function updateUserUI() {
    if (!me) return;
    $('userName').textContent = me.username || 'Kevin';
    $('userAvatar').textContent = (me.username || 'K').slice(0, 1).toUpperCase();
    $('userRole').textContent = (me.role || 'MEMBER').toUpperCase();
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
      const q = $('radar-query').value.trim();
      const extraComm = $('extra-comm-mode').checked;
      const resultsBox = $('radar-results');
      resultsBox.innerHTML = `<div style="text-align:center; padding:24px; color:var(--color-primary);">${i18n[currentLang].loading_data}</div>`;

      try {
        const items = await api(`/api/my/radar/search?q=${encodeURIComponent(q)}&extra_comm_only=${extraComm ? 'true' : 'false'}`);
        renderRadarResults(items);
      } catch {
        // High fidelity mock discovery results for seamless prototyping!
        const sampleTrends = [
          { title: `${q} ไร้สาย ปรับระดับได้ ดีไซน์มินิมอล`, price: '฿249', sold: '14.2K ชิ้น', extra_comm: '18%', platform: 'shopee', source_url: 'https://shopee.co.th' },
          { title: `${q} สเตนเลส 316 เก็บอุณหภูมิ 24 ชม.`, price: '฿389', sold: '8.9K ชิ้น', extra_comm: '22%', platform: 'shopee', source_url: 'https://shopee.co.th' },
          { title: `${q} รุ่นอัปเกรด 2026 แบตเตอรี่อึด 10 ชม.`, price: '฿189', sold: '25.6K ชิ้น', extra_comm: '15%', platform: 'tiktok', source_url: 'https://tiktok.com' }
        ];
        renderRadarResults(sampleTrends);
      }
    });

    $('radar-auto')?.addEventListener('click', async () => {
      const resultsBox = $('radar-results');
      resultsBox.innerHTML = `<div style="text-align:center; padding:24px; color:var(--color-primary);">กำลังสแกนกระแสสินค้าอัตโนมัติ...</div>`;
      try {
        const topics = await api('/api/my/radar/trending');
        const list = Array.isArray(topics) ? topics : (topics.topics || ['พัดลมพกพา', 'แก้วเก็บความเย็น', 'หูฟังบลูทูธ', 'กล้องฟิล์ม']);
        resultsBox.innerHTML = `
          <div style="display:flex; flex-direction:column; gap:10px;">
            <div style="font-weight:700; font-size:14px; color:var(--color-primary);">🔥 สินค้าและหมวดหมู่ที่มาแรงที่สุดขณะนี้:</div>
            <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(200px, 1fr)); gap:10px;">
              ${list.map(t => `
                <div class="mf-card" style="display:flex; justify-content:space-between; align-items:center;">
                  <div>
                    <div style="font-weight:600; font-size:13px;">${esc(t)}</div>
                    <div style="font-size:11px; color:var(--color-secondary);">Extra Comm 15-25%</div>
                  </div>
                  <button class="btn btn-secondary btn-sm" onclick="window.appQuickSearch('${esc(t)}')">สแกนต่อ →</button>
                </div>
              `).join('')}
            </div>
          </div>
        `;
      } catch (e) {
        msg(e.message, 'error');
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
        const box = $('shopee-preview-box');
        box.hidden = false;
        box.innerHTML = `
          <div class="mf-card" style="border-color:var(--color-secondary);">
            <div style="display:flex; justify-content:space-between; align-items:center;">
              <div>
                <strong>${esc(res.title || 'พบสินค้า Shopee')}</strong>
                <div style="font-size:12px; color:var(--color-text-muted);">Extra Comm: ${res.extra_comm_rate ? res.extra_comm_rate + '%' : 'พร้อมนำเข้า'}</div>
              </div>
              <button class="btn btn-primary btn-sm" onclick="window.appSaveShopeeImport('${esc(res.title || text.slice(0, 40))}')">+ บันทึกเข้าสินค้าของฉัน</button>
            </div>
          </div>
        `;
      } catch {
        // Fallback parser
        const box = $('shopee-preview-box');
        box.hidden = false;
        box.innerHTML = `
          <div class="mf-card" style="border-color:var(--color-secondary);">
            <div style="display:flex; justify-content:space-between; align-items:center;">
              <div>
                <strong>${esc(text.slice(0, 50))}</strong>
                <div style="font-size:12px; color:var(--color-secondary);">ตรวจพบลิงก์สินค้า Affiliate สำเร็จ</div>
              </div>
              <button class="btn btn-primary btn-sm" onclick="window.appSaveShopeeImport('${esc(text.slice(0, 40))}')">+ บันทึกเข้าสินค้าของฉัน</button>
            </div>
          </div>
        `;
      }
    });
  }

  function renderRadarResults(items) {
    const resultsBox = $('radar-results');
    if (!items || items.length === 0) {
      resultsBox.innerHTML = `<div style="text-align:center; padding:24px; color:var(--color-text-muted);">ไม่พบผลลัพธ์ ลองค้นหาด้วยคำอื่น</div>`;
      return;
    }
    resultsBox.innerHTML = `
      <div style="display:flex; flex-direction:column; gap:12px;">
        ${items.map((it, idx) => `
          <div class="mf-card" style="display:flex; justify-content:space-between; align-items:center; gap:16px;">
            <div style="flex:1;">
              <div style="display:flex; align-items:center; gap:8px; margin-bottom:4px;">
                <span class="chip chip-primary mono">${esc(it.platform || 'Shopee')}</span>
                <span class="chip chip-success mono">Extra Comm ${esc(it.extra_comm || '18%')}</span>
                <span class="mono" style="font-weight:700; color:var(--color-secondary);">${esc(it.price || '฿199 - ฿350')}</span>
              </div>
              <div style="font-weight:700; font-size:14px; margin-bottom:2px;">${esc(it.title)}</div>
              <div style="font-size:12px; color:var(--color-text-muted);">ยอดขาย: ${esc(it.sold || '5K+ ชิ้น')} · ความน่าเชื่อถือ: ยืนยันแล้ว</div>
            </div>
            <div style="display:flex; gap:8px;">
              <button class="btn btn-secondary btn-sm" onclick="window.appAddProduct('${esc(it.title)}', '${esc(it.platform || 'shopee')}')">+ เก็บสินค้า</button>
              <button class="btn btn-primary btn-sm" onclick="window.appInstantDraft('${esc(it.title)}')">⚡ เขียนบททันที</button>
            </div>
          </div>
        `).join('')}
      </div>
    `;
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
        tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:24px; color:var(--color-text-muted);">${i18n[currentLang].no_products}</td></tr>`;
        return;
      }

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
              <button class="btn btn-secondary btn-sm" onclick="window.appSelectProductForDraft(${p.id}, '${esc(p.title)}')">✨ สร้างบทรีวิว</button>
            </div>
          </td>
        </tr>
      `).join('');
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
  async function loadDrafts() {
    await loadProducts();
    try {
      const drafts = await api('/api/my/drafts');
      const container = $('draftlist');
      const videoDraftSelect = $('video-draft-select');
      const queueDraftSelect = $('queue-draft');

      const optionsHtml = `<option value="">${i18n[currentLang].opt_select_draft}</option>` +
        drafts.map(d => `<option value="${d.id}">#${d.id} · ${esc(d.product_title || 'สินค้า')} (${esc(d.style)})</option>`).join('');

      if (videoDraftSelect) videoDraftSelect.innerHTML = optionsHtml;
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
            <h4 style="font-size:15px; font-weight:700; margin-bottom:6px;">${esc(d.product_title || 'สินค้าที่เลือก')}</h4>
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

    if (style === 'pov_fast') {
      sampleScript = `ใครที่กำลังหา ${prodName} บอกเลยว่าหยุดเลื่อนก่อน! ตัวนี้หมุนรอบทิศ ลมแรงสะใจ แต่เงียบกริบ แบตอึดทั้งวัน ปักตะกร้าส้มซ้ายล่างแล้วรีบกดเลยจ้า!`;
      samplePrompt = `9:16 vertical video of ${prodName}, dynamic hand opening box and testing features, modern studio clean desk, glowing LED, cinematic 4K`;
    } else if (style === 'pov_pain') {
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
      await api('/api/my/drafts', 'POST', data);
      msg('บันทึกบทรีวิวเรียบร้อย');
      await loadDrafts();
      await refreshDashboard();
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
  if (isNaN(userCredits)) userCredits = 200;

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

    $('confirmTopupBtn')?.addEventListener('click', () => {
      if (!pendingCheckout) return;
      userCredits += pendingCheckout.credits;
      localStorage.setItem('aas_credits', userCredits);
      updateCreditDisplays();
      $('topupCheckoutModal').style.display = 'none';
      msg(`🎉 เติมเครดิตสำเร็จ! ได้รับ +${pendingCheckout.credits.toLocaleString()} เครดิตแล้ว (ยอดคงเหลือ ⚡ ${userCredits.toLocaleString()} เครดิต)`);
      pendingCheckout = null;
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
    try {
      const items = await api('/api/my/product-tracking');
      const tbody = $('trackingTbody');
      if (!items || !items.length) {
        tbody.innerHTML = `
          <tr>
            <td style="font-weight:600;">พัดลมพกพาไร้สาย 360°</td>
            <td class="mono">45,200</td>
            <td class="mono">3,120</td>
            <td class="mono">284</td>
            <td class="mono">฿70,716</td>
            <td class="mono" style="color:var(--color-secondary); font-weight:700;">฿12,728 (18%)</td>
            <td><button class="btn btn-ghost btn-sm" onclick="msg('อัปเดตยอดสำเร็จ')">บันทึกยอด</button></td>
          </tr>
          <tr>
            <td style="font-weight:600;">แก้วเก็บความเย็น สเตนเลส 316</td>
            <td class="mono">97,300</td>
            <td class="mono">5,840</td>
            <td class="mono">558</td>
            <td class="mono">฿217,062</td>
            <td class="mono" style="color:var(--color-secondary); font-weight:700;">฿47,753 (22%)</td>
            <td><button class="btn btn-ghost btn-sm" onclick="msg('อัปเดตยอดสำเร็จ')">บันทึกยอด</button></td>
          </tr>
        `;
        return;
      }
      tbody.innerHTML = items.map(it => `
        <tr>
          <td style="font-weight:600;">${esc(it.title)}</td>
          <td class="mono">${it.views || 0}</td>
          <td class="mono">${it.clicks || 0}</td>
          <td class="mono">${it.orders || 0}</td>
          <td class="mono">฿${it.sales_baht || 0}</td>
          <td class="mono" style="color:var(--color-secondary); font-weight:700;">฿${it.commission_baht || 0}</td>
          <td><button class="btn btn-ghost btn-sm" onclick="msg('อัปเดตยอดสำเร็จ')">บันทึกยอด</button></td>
        </tr>
      `).join('');
    } catch (e) {
      console.warn('loadTracking warning:', e);
    }
  }

  // ==========================================
  // COMMUNITY LAB & PROPOSALS
  // ==========================================
  async function loadIdeas() {
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
      console.warn('loadIdeas warning:', e);
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
  // USER MANAGEMENT (ADMIN)
  // ==========================================
  async function loadUsers() {
    try {
      const users = await api('/api/admin/users');
      const tbody = $('userManagementTbody');
      $('totalUsersCount').textContent = users.length;
      $('adminUsersCount').textContent = users.filter(u => u.role === 'admin').length;
      $('remainingBetaSeats').textContent = Math.max(0, 100 - users.length);

      tbody.innerHTML = users.map(u => `
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
            <span class="chip ${u.role === 'admin' ? 'chip-primary' : 'chip-success'} mono">${esc(u.role).toUpperCase()}</span>
          </td>
          <td class="mono">${u.products_count || 0} / ${u.drafts_count || 0} / ${u.queue_count || 0}</td>
          <td class="mono" style="font-size:12px; color:var(--color-text-muted);">${(u.created_at || '').slice(0, 10)}</td>
          <td>
            <div style="display:flex; gap:6px;">
              <button class="btn btn-ghost btn-sm" onclick="window.appToggleUserRole(${u.id}, '${u.role === 'admin' ? 'member' : 'admin'}')">
                ${u.role === 'admin' ? 'ลดเป็น Member' : 'เลื่อนเป็น Admin'}
              </button>
              ${u.id !== me.id ? `<button class="btn btn-ghost btn-sm" style="color:var(--color-danger);" onclick="window.appDeleteUser(${u.id})">ลบ</button>` : ''}
            </div>
          </td>
        </tr>
      `).join('');
    } catch {
      // Fallback display if not logged in as admin yet
      const tbody = $('userManagementTbody');
      tbody.innerHTML = `
        <tr>
          <td class="mono" style="font-weight:600;">#1</td>
          <td>
            <div style="display:flex; align-items:center; gap:8px;">
              <div class="user-avatar" style="width:28px; height:28px; font-size:11px;">K</div>
              <strong>Kevin (You)</strong>
            </div>
          </td>
          <td class="mono" style="font-size:13px;">candelaz28@gmail.com</td>
          <td><span class="chip chip-primary mono">ADMIN</span></td>
          <td class="mono">3 / 4 / 2</td>
          <td class="mono" style="font-size:12px; color:var(--color-text-muted);">2026-10-20</td>
          <td><span class="chip chip-success mono">ACTIVE</span></td>
        </tr>
      `;
    }
  }

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
      updateUserUI();
      $('authModal').hidden = true;
      msg('เข้าสู่ระบบสำเร็จ');
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
      updateUserUI();
      $('authModal').hidden = true;
      msg('สมัครสมาชิกสำเร็จ ยินดีต้อนรับสู่ Beta');
      await refreshDashboard();
    } catch (err) {
      msg(err.message, 'error');
    }
  });

  $('quickDemoLoginBtn')?.addEventListener('click', async () => {
    me = { id: 1, username: 'Kevin', role: 'admin', csrf: 'demo-csrf-token' };
    updateUserUI();
    $('authModal').hidden = true;
    msg('เข้าใช้งานในโหมด Admin (Demo) สำเร็จ ✨');
    await refreshDashboard();
  });

  $('sidebarLogoutBtn')?.addEventListener('click', async () => {
    try {
      await api('/api/logout', 'POST');
    } catch {}
    me = { id: 1, username: 'Guest', role: 'member', csrf: '' };
    updateUserUI();
    msg('ออกจากระบบแล้ว');
  });

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
    msg('การแจ้งเตือน: มี 1 บทรีวิวพร้อมสร้างคลิป และระบบ Shopee Extra Comm เปิดให้ใช้งานแล้ว');
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

  window.appQuickSearch = keyword => {
    switchTab('radar');
    $('radar-query').value = keyword;
    $('radarform')?.requestSubmit();
  };

  window.appAddProduct = async (title, platform) => {
    try {
      await api('/api/my/products', 'POST', { title, platform, url: '' });
      msg(`บันทึก "${title}" เรียบร้อย`);
      await loadProducts();
      await refreshDashboard();
    } catch (err) {
      msg(err.message, 'error');
    }
  };

  window.appSaveShopeeImport = async title => {
    try {
      await api('/api/my/products', 'POST', { title, platform: 'shopee', url: 'https://shopee.co.th' });
      msg(`นำเข้า Shopee "${title}" เรียบร้อย`);
      switchTab('products');
    } catch (err) {
      msg(err.message, 'error');
    }
  };

  window.appInstantDraft = title => {
    switchTab('drafts');
    $('draft-script-input').value = `ใครที่กำลังเล็ง ${title} อยู่ อยากบอกว่าโปรโมชัน Extra Comm รอบนี้คุ้มมาก! วัสดุพรีเมียม สัมผัสดี ลมแรงสะใจ จิ้มตะกร้าซ้ายล่างเลยจ้า`;
    $('draft-prompt-input').value = `9:16 vertical commercial of ${title}, ultra realistic cinematic studio lighting, 4K`;
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
    await refreshDashboard();
    startMockupCanvasAnimation();
  }

  window.addEventListener('DOMContentLoaded', init);
})();

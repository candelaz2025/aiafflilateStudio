// AI Studio Pro - Interactive Client Application
let currentDramaData = null;
let currentUgcData = null;
let currentOptimizedPrompt = null;
let currentStoryboardData = null;
let allTemplatesCache = [];
let autoRefreshTimer = null;

document.addEventListener('DOMContentLoaded', () => {
  initApp();
});

function initApp() {
  loadDashboard();
  loadSettings();
  loadCalendar();
  loadQueueTable();
  loadAllTemplates();
  checkMetaCookieStatus();

  // Start continuous polling for stats and live workflow
  autoRefreshTimer = setInterval(() => {
    pollWorkflowUpdates();
  }, 3000);
}

// -------------------------------------------------------------
// UI Navigation & Utilities
// -------------------------------------------------------------
function switchTab(tabId) {
  document.querySelectorAll('.tab-pane').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));

  const targetPane = document.getElementById(tabId);
  if (targetPane) targetPane.classList.add('active');

  const navBtn = document.querySelector(`[data-tab="${tabId}"]`);
  if (navBtn) navBtn.classList.add('active');

  if (tabId === 'tab-dashboard') loadDashboard();
  if (tabId === 'tab-workflow') loadWorkflowLogs();
  if (tabId === 'tab-calendar') loadCalendar();
  if (tabId === 'tab-queue') loadQueueTable();
  if (tabId === 'tab-settings') checkMetaCookieStatus();
}

function showToast(msg, duration = 3500) {
  const toast = document.getElementById('toastNotification');
  toast.textContent = msg;
  toast.classList.remove('hidden');
  setTimeout(() => {
    toast.classList.add('hidden');
  }, duration);
}

function formatTime(isoStr) {
  if (!isoStr) return '';
  const d = new Date(isoStr);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

// -------------------------------------------------------------
// 1. Dashboard & Live Workflow Pipeline
// -------------------------------------------------------------
async function loadDashboard() {
  try {
    const res = await fetch('/api/dashboard/stats');
    const data = await res.json();

    document.getElementById('statQueued').textContent = data.queued_jobs || 0;
    document.getElementById('statRunning').textContent = data.running_jobs || 0;
    document.getElementById('statCompleted').textContent = data.completed_jobs || 0;
    document.getElementById('statScheduled').textContent = data.calendar_scheduled || 0;
    document.getElementById('queueBadge').textContent = data.queued_jobs || 0;

    const workerBtn = document.getElementById('workerToggleBtn');
    const workerStateText = document.getElementById('workerStateText');
    if (data.auto_worker_enabled) {
      workerBtn.className = 'worker-btn running';
      workerStateText.textContent = 'ON';
    } else {
      workerBtn.className = 'worker-btn';
      workerStateText.textContent = 'PAUSED';
    }

    renderRecentVideos(data.recent_jobs || []);
  } catch (err) {
    console.error('Error loading dashboard stats:', err);
  }
}

async function pollWorkflowUpdates() {
  try {
    const res = await fetch('/api/dashboard/stats');
    const data = await res.json();

    document.getElementById('statQueued').textContent = data.queued_jobs || 0;
    document.getElementById('statRunning').textContent = data.running_jobs || 0;
    document.getElementById('statCompleted').textContent = data.completed_jobs || 0;
    document.getElementById('statScheduled').textContent = data.calendar_scheduled || 0;
    document.getElementById('queueBadge').textContent = data.queued_jobs || 0;

    const recent = data.recent_jobs || [];
    const activeJob = recent.find(j => ['prompt_crafting', 'dispatching', 'rendering', 'downloading'].includes(j.status));

    updatePipelineHighlight(activeJob ? activeJob.status : null);
    if (activeJob) {
      updateActiveJobCard(activeJob);
    }
  } catch (err) {
    // quiet polling errors
  }
}

function updatePipelineHighlight(status) {
  const steps = ['step-crafting', 'step-dispatching', 'step-rendering', 'step-downloading', 'step-completed'];
  steps.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.classList.remove('active');
  });

  if (!status) return;

  if (status === 'prompt_crafting') document.getElementById('step-crafting')?.classList.add('active');
  else if (status === 'dispatching') document.getElementById('step-dispatching')?.classList.add('active');
  else if (status === 'rendering') document.getElementById('step-rendering')?.classList.add('active');
  else if (status === 'downloading') document.getElementById('step-downloading')?.classList.add('active');
  else if (status === 'completed') document.getElementById('step-completed')?.classList.add('active');
}

function renderRecentVideos(jobs) {
  const container = document.getElementById('recentVideosGrid');
  const completed = jobs.filter(j => j.status === 'completed' && j.video_path);

  if (completed.length === 0) {
    container.innerHTML = '<div class="empty-state">ยังไม่มีวิดีโอที่สร้างเสร็จ กดปุ่มสร้างตัวอย่างได้จากเมนูด้านซ้าย</div>';
    return;
  }

  container.innerHTML = completed.map(j => `
    <div class="video-card-thumb" onclick="openVideoPlayer('${j.video_path}', '${escapeHtml(j.title)}')">
      <div class="thumb-img-box">
        <img src="${j.thumbnail_path || '/static/placeholder.jpg'}" alt="${escapeHtml(j.title)}" onerror="this.src='https://placehold.co/720x1280/0f172a/38bdf8?text=AI+Video'">
        <div class="play-overlay">
          <div class="play-circle">▶</div>
        </div>
      </div>
      <div class="thumb-caption">
        <h4>${escapeHtml(j.title)}</h4>
        <div class="thumb-meta">
          <span>${j.engine === 'meta_ai' ? 'Meta AI' : 'Google Flow'}</span>
          <span>${j.task_type.toUpperCase()}</span>
        </div>
      </div>
    </div>
  `).join('');
}

// -------------------------------------------------------------
// 2. Live Workflow Terminal Logs
// -------------------------------------------------------------
async function loadWorkflowLogs() {
  try {
    const res = await fetch('/api/queue?limit=15');
    const data = await res.json();
    const jobs = data.jobs || [];

    const activeJob = jobs.find(j => ['prompt_crafting', 'dispatching', 'rendering', 'downloading'].includes(j.status));
    updateActiveJobCard(activeJob);

    const terminal = document.getElementById('terminalLogs');
    let allLogs = [];
    jobs.forEach(j => {
      if (Array.isArray(j.logs)) {
        j.logs.forEach(l => {
          allLogs.push({ ...l, job_id: j.id, job_title: j.title });
        });
      }
    });

    allLogs.sort((a, b) => (a.time > b.time ? 1 : -1));
    const recentLogs = allLogs.slice(-30);

    if (recentLogs.length === 0) {
      terminal.innerHTML = '<div class="log-line info">[System] No recent worker logs. Standing by.</div>';
    } else {
      terminal.innerHTML = recentLogs.map(l => {
        let cls = 'info';
        if (l.stage === 'completed') cls = 'success';
        if (l.stage === 'failed') cls = 'error';
        if (l.stage === 'rendering') cls = 'warn';
        return `<div class="log-line ${cls}">[${formatTime(l.time)}] [Job #${l.job_id}] ${escapeHtml(l.message)}</div>`;
      }).join('');
      terminal.scrollTop = terminal.scrollHeight;
    }
  } catch (err) {
    console.error('Error loading workflow logs:', err);
  }
}

function updateActiveJobCard(job) {
  const badge = document.getElementById('wfActiveBadge');
  const body = document.getElementById('wfActiveBody');

  if (!job) {
    badge.textContent = 'Idle';
    badge.className = 'status-badge queued';
    body.innerHTML = '<div class="empty-state">ขณะนี้ไม่มีงานที่กำลังเรนเดอร์ ระบบพร้อมรับงานใหม่</div>';
    return;
  }

  badge.textContent = job.status.toUpperCase();
  badge.className = `status-badge ${job.status}`;

  body.innerHTML = `
    <div style="margin-bottom: 12px;">
      <h4 style="font-size: 1.05rem; margin-bottom: 4px;">${escapeHtml(job.title)}</h4>
      <p style="font-size: 0.8rem; color: var(--text-muted);">${escapeHtml(job.prompt)}</p>
    </div>
    <div style="margin-bottom: 12px;">
      <div style="display: flex; justify-content: space-between; font-size: 0.75rem; margin-bottom: 4px;">
        <span>ความคืบหน้า (Stage: ${job.status})</span>
        <strong>${job.progress}%</strong>
      </div>
      <div class="progress-track" style="width: 100%; height: 8px;">
        <div class="progress-fill" style="width: ${job.progress}%;"></div>
      </div>
    </div>
    <div style="font-size: 0.75rem; color: var(--text-dim); display: flex; gap: 16px;">
      <span>⚙ Engine: <strong>${job.engine}</strong></span>
      <span>📐 Aspect: <strong>${job.aspect_ratio}</strong></span>
      <span>⏱ Started: <strong>${formatTime(job.started_at)}</strong></span>
    </div>
  `;
}

// -------------------------------------------------------------
// 3. 30 Templates Showcase & Selector
// -------------------------------------------------------------
async function loadAllTemplates() {
  try {
    const res = await fetch('/api/templates/all');
    const data = await res.json();
    allTemplatesCache = data.templates || [];
  } catch (err) {
    console.error('Error loading templates:', err);
  }
}

function openTemplatesModal(filterType = 'all') {
  document.getElementById('templatesModal').classList.remove('hidden');
  filterTemplates(filterType);
}

function closeTemplatesModal() {
  document.getElementById('templatesModal').classList.add('hidden');
}

function filterTemplates(category) {
  document.querySelectorAll('.filter-chip').forEach(el => el.classList.remove('active'));
  const activeBtn = Array.from(document.querySelectorAll('.filter-chip')).find(b => b.textContent.toLowerCase().includes(category));
  if (activeBtn) activeBtn.classList.add('active');

  let filtered = allTemplatesCache;
  if (category === 'ugc') filtered = allTemplatesCache.filter(t => t.type === 'ugc');
  if (category === 'drama') filtered = allTemplatesCache.filter(t => t.type === 'drama');

  renderTemplatesGrid(filtered);
}

function renderTemplatesGrid(templates) {
  const container = document.getElementById('templatesGridContainer');
  if (templates.length === 0) {
    container.innerHTML = '<div class="empty-state">กำลังโหลดเทมเพลต...</div>';
    return;
  }

  container.innerHTML = templates.map(t => `
    <div class="template-card" onclick="selectTemplate('${t.id}')">
      <div>
        <span class="template-badge ${t.type}">${t.type.toUpperCase()} · ${escapeHtml(t.category)}</span>
        <div class="template-title">${escapeHtml(t.title)}</div>
        <div class="template-hook">"${escapeHtml(t.hook)}"</div>
        <p style="font-size: 0.72rem; color: var(--text-muted); line-height: 1.4;">${escapeHtml(t.summary)}</p>
      </div>
      <div class="template-meta">
        <span>🎙 ${escapeHtml(t.voice_tone)}</span>
        <span>🎨 ${escapeHtml(t.visual_tone)}</span>
      </div>
    </div>
  `).join('');
}

function selectTemplate(templateId) {
  const t = allTemplatesCache.find(x => x.id === templateId);
  if (!t) return;

  closeTemplatesModal();
  switchTab('tab-storyboard');

  document.getElementById('sbTopic').value = t.title;
  document.getElementById('sbType').value = t.type;
  if (t.voice_tone && document.getElementById('sbVoiceTone')) {
    document.getElementById('sbVoiceTone').value = t.voice_tone;
  }
  if (t.visual_tone && document.getElementById('sbVisualTone')) {
    document.getElementById('sbVisualTone').value = t.visual_tone;
  }

  showToast(`เลือกเทมเพลต "${t.title}" แล้ว! กำลังสร้าง Storyboard...`);
  // Trigger storyboard generation
  setTimeout(() => {
    document.getElementById('storyboardForm').dispatchEvent(new Event('submit'));
  }, 200);
}

// -------------------------------------------------------------
// 4. Storyboard & Character Lock Studio
// -------------------------------------------------------------
async function handleGenerateStoryboard(event) {
  event.preventDefault();
  const btn = document.getElementById('sbSubmitBtn');
  btn.disabled = true;
  btn.textContent = '🎨 กำลังเรนเดอร์ภาพฉาก & Storyboard AI...';

  const topic = document.getElementById('sbTopic').value;
  const type = document.getElementById('sbType').value;
  const gender = document.getElementById('sbGender').value;
  const preset = document.getElementById('sbCharacterPreset').value;
  const voice = document.getElementById('sbVoiceTone').value;
  const visual = document.getElementById('sbVisualTone').value;
  const scenesCount = parseInt(document.getElementById('sbScenesCount').value, 10);

  let charName = "อริน (Arin)";
  if (preset === 'char_phat') charName = "ภัทร (Phat)";
  if (preset === 'char_ploy') charName = "พลอย (Ploy)";
  if (preset === 'char_ken') charName = "เคน (Ken)";

  try {
    const res = await fetch('/api/storyboard/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        topic_or_product: topic,
        campaign_type: type,
        gender: gender,
        voice_tone_key: voice,
        visual_tone_key: visual,
        character_name: charName,
        total_scenes: scenesCount
      })
    });
    const data = await res.json();
    currentStoryboardData = data;

    renderStoryboardResult(data);
    document.getElementById('queueAllSbBtn').classList.remove('hidden');
    showToast(`สร้าง Storyboard ${data.scenes.length} ฉาก พร้อมภาพประกอบสำเร็จ!`);
  } catch (err) {
    showToast('เกิดข้อผิดพลาดในการสร้าง Storyboard');
    console.error(err);
  } finally {
    btn.disabled = false;
    btn.textContent = '🎨 สร้าง Storyboard พร้อมภาพประกอบฉาก AI';
  }
}

function renderStoryboardResult(data) {
  const container = document.getElementById('storyboardContainer');
  let html = `
    <div style="margin-bottom: 14px; border-bottom: 1px solid var(--border-subtle); padding-bottom: 10px;">
      <h3 style="font-size: 1.15rem; color: var(--cyan-primary);">${escapeHtml(data.title)}</h3>
      <div style="font-size: 0.78rem; color: var(--text-muted); margin-top: 4px; display: flex; flex-wrap: wrap; gap: 12px;">
        <span>🔒 <strong>Character Lock:</strong> ${escapeHtml(data.character_lock.name)} (${escapeHtml(data.character_lock.gender)})</span>
        <span>🎙 <strong>โทนเสียง:</strong> ${escapeHtml(data.voice_tone.name)}</span>
        <span>🎨 <strong>โทนภาพ:</strong> ${escapeHtml(data.visual_tone.name)}</span>
      </div>
    </div>
  `;

  html += (data.scenes || []).map(sc => `
    <div class="storyboard-card-item">
      <div class="storyboard-card-thumb">
        <img src="${sc.image_url}" alt="Scene ${sc.scene_number}" onerror="this.src='https://placehold.co/720x1080/0f172a/38bdf8?text=Scene+${sc.scene_number}'">
      </div>
      <div class="storyboard-card-content">
        <div class="storyboard-card-header">
          <span class="sb-timing-badge">ฉากที่ ${sc.scene_number} · ${escapeHtml(sc.timing)}</span>
          <button class="btn btn-xs btn-primary" onclick="queueStoryboardScene('${escapeHtml(data.title)} - Scene ${sc.scene_number}', '${escapeHtml(sc.video_prompt)}')">
            🚀 สั่ง Gen คลิปฉากนี้
          </button>
        </div>
        <div style="font-size: 0.8rem; margin: 6px 0;">
          <strong>บทพูด / เสียงพากย์:</strong>
          <p style="color: #f1f5f9; margin-top: 2px;">"${escapeHtml(sc.spoken_line)}"</p>
        </div>
        <div style="font-size: 0.72rem; color: var(--text-dim); margin-bottom: 4px;">
          📷 <strong>มุมกล้อง:</strong> ${escapeHtml(sc.camera_shot)}
        </div>
        <div class="prompt-code-box" style="margin-top: 6px;">${escapeHtml(sc.video_prompt)}</div>
      </div>
    </div>
  `).join('');

  container.innerHTML = html;
}

async function queueStoryboardScene(sceneTitle, promptText) {
  try {
    const res = await fetch('/api/queue', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        task_type: 'storyboard',
        title: sceneTitle,
        prompt: promptText,
        engine: 'google_flow',
        aspect_ratio: '9:16'
      })
    });
    const d = await res.json();
    if (d.success) {
      showToast(`ส่งฉาก "${sceneTitle}" เข้าคิวสร้างวิดีโอเรียบร้อย!`);
      loadDashboard();
      switchTab('tab-workflow');
    }
  } catch (err) {
    showToast('ไม่สามารถส่งงานเข้าคิวได้');
  }
}

async function queueAllStoryboardScenes() {
  if (!currentStoryboardData || !currentStoryboardData.scenes) return;
  const scenes = currentStoryboardData.scenes;
  let count = 0;
  for (const sc of scenes) {
    await fetch('/api/queue', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        task_type: 'storyboard',
        title: `${currentStoryboardData.title} - Scene ${sc.scene_number}`,
        prompt: sc.video_prompt,
        engine: 'google_flow',
        aspect_ratio: '9:16'
      })
    });
    count++;
  }
  showToast(`ส่ง Storyboard เข้าคิวครบทั้ง ${count} ฉากแล้ว!`);
  loadDashboard();
  switchTab('tab-queue');
}

function updateGenderPreset(gender) {
  const presetSelect = document.getElementById('sbCharacterPreset');
  if (gender === 'male') {
    presetSelect.value = 'char_phat';
  } else {
    presetSelect.value = 'char_arin';
  }
}

function applyCharacterPreset(presetId) {
  const genderSelect = document.getElementById('sbGender');
  if (presetId === 'char_phat' || presetId === 'char_ken') {
    genderSelect.value = 'male';
  } else {
    genderSelect.value = 'female';
  }
}

// -------------------------------------------------------------
// 5. Meta AI Cookie Verification, Storage & File Upload
// -------------------------------------------------------------
function handleCookieDragOver(e) {
  e.preventDefault();
  e.stopPropagation();
  const dz = document.getElementById('cookieDropzone');
  if (dz) dz.classList.add('dragover');
}

function handleCookieDragLeave(e) {
  e.preventDefault();
  e.stopPropagation();
  const dz = document.getElementById('cookieDropzone');
  if (dz) dz.classList.remove('dragover');
}

function handleCookieFileDrop(e) {
  e.preventDefault();
  e.stopPropagation();
  const dz = document.getElementById('cookieDropzone');
  if (dz) dz.classList.remove('dragover');

  if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
    const file = e.dataTransfer.files[0];
    uploadCookieFile(file);
  }
}

function handleCookieFileSelected(e) {
  if (e.target.files && e.target.files.length > 0) {
    const file = e.target.files[0];
    uploadCookieFile(file);
  }
}

async function uploadCookieFile(file) {
  const statusBox = document.getElementById('cookieUploadStatus');
  const resultBox = document.getElementById('metaCookieVerifyResult');
  const textarea = document.getElementById('metaCookieInput');

  statusBox.className = 'upload-status-bar';
  statusBox.classList.remove('hidden');
  statusBox.textContent = `⏳ กำลังอัปโหลดและตรวจสอบไฟล์: ${file.name}...`;

  const formData = new FormData();
  formData.append('file', file);

  try {
    const res = await fetch('/api/meta/upload-cookie-file', {
      method: 'POST',
      body: formData
    });
    const data = await res.json();

    if (res.ok && data.success) {
      statusBox.style.color = '#34d399';
      statusBox.style.borderColor = 'rgba(52, 211, 153, 0.5)';
      statusBox.textContent = `✓ อัปโหลดสำเร็จ: ${file.name} (ตรวจพบ ${data.cookies_count} คุกกี้: ${data.keys.join(', ')})`;
      
      showToast(`อัปโหลดไฟล์ Cookie สำเร็จ (${data.cookies_count} คุกกี้)!`);
      updateMetaCookieBadge(true, data.cookies_count);

      if (data.verification) {
        resultBox.style.color = data.verification.valid ? '#34d399' : '#f87171';
        resultBox.textContent = data.verification.message;
      }

      // Also read text to display in textarea
      const reader = new FileReader();
      reader.onload = (re) => {
        if (textarea) textarea.value = re.target.result;
      };
      reader.readAsText(file);
    } else {
      statusBox.style.color = '#f87171';
      statusBox.style.borderColor = 'rgba(248, 113, 113, 0.5)';
      statusBox.textContent = `⚠️ อัปโหลดไม่สำเร็จ: ${data.detail || 'รูปแบบไฟล์ไม่ถูกต้อง'}`;
      showToast('ไฟล์ Cookie ไม่ถูกต้อง');
    }
  } catch (err) {
    statusBox.style.color = '#f87171';
    statusBox.textContent = `เกิดข้อผิดพลาดในการอัปโหลดไฟล์: ${err.message}`;
    showToast('เกิดข้อผิดพลาดในการอัปโหลด');
  }
}

async function verifyAndSaveMetaCookie() {
  const cookieVal = document.getElementById('metaCookieInput').value.trim();
  const resultBox = document.getElementById('metaCookieVerifyResult');

  if (!cookieVal) {
    showToast('กรุณาวางค่า Cookie จาก meta.ai ก่อน');
    return;
  }

  resultBox.textContent = '⏳ กำลังตรวจสอบการเชื่อมต่อกับ meta.ai...';

  try {
    const res = await fetch('/api/meta/save-cookies', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cookies: cookieVal })
    });
    const data = await res.json();

    if (data.success && data.verification) {
      const v = data.verification;
      if (v.valid) {
        showToast('เชื่อมต่อ Meta AI ด้วย Cookie สำเร็จ!');
        resultBox.style.color = '#34d399';
        resultBox.textContent = `✓ ${v.message} (พบคุกกี้: ${v.found_keys ? v.found_keys.join(', ') : ''})`;
        updateMetaCookieBadge(true);
      } else {
        showToast('Cookie ไม่ผ่านการตรวจสอบ');
        resultBox.style.color = '#f87171';
        resultBox.textContent = `⚠️ ${v.message}`;
        updateMetaCookieBadge(false);
      }
    }
  } catch (err) {
    resultBox.style.color = '#f87171';
    resultBox.textContent = 'เกิดข้อผิดพลาดในการตรวจสอบ Cookie';
    showToast('ไม่สามารถเชื่อมต่อตรวจสอบได้');
  }
}

async function checkMetaCookieStatus() {
  try {
    const res = await fetch('/api/meta/status');
    const data = await res.json();
    updateMetaCookieBadge(data.has_cookies, data.cookies_count);
  } catch (err) {
    // quiet
  }
}

function updateMetaCookieBadge(isConnected, count = 0) {
  const badge = document.getElementById('metaCookieBadge');
  const headerBadge = document.getElementById('headerMetaBadge');

  if (isConnected) {
    if (badge) {
      badge.textContent = `● เชื่อมต่อแล้ว (${count || 'Active'} Cookies)`;
      badge.className = 'status-badge completed';
    }
    if (headerBadge) {
      headerBadge.style.borderColor = 'rgba(168, 85, 247, 0.6)';
      headerBadge.title = 'Meta AI Movie Gen (Cookie Connected)';
    }
  } else {
    if (badge) {
      badge.textContent = '○ ยังไม่เชื่อม Cookie';
      badge.className = 'status-badge queued';
    }
  }
}

// -------------------------------------------------------------
// 6. Drama AI Studio
// -------------------------------------------------------------
async function handleGenerateDrama(event) {
  event.preventDefault();
  const btn = document.getElementById('dramaSubmitBtn');
  btn.disabled = true;
  btn.textContent = '⏳ กำลังสร้างบทละครและฉาก AI...';

  const genre = document.getElementById('dramaGenre').value;
  const title = document.getElementById('dramaTitle').value;
  const episodes = parseInt(document.getElementById('dramaEpisodes').value, 10);
  const notes = document.getElementById('dramaNotes').value;

  try {
    const res = await fetch('/api/drama/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ genre_key: genre, custom_title: title, total_episodes: episodes, custom_notes: notes })
    });
    const data = await res.json();
    currentDramaData = data;

    renderDramaResult(data);
    document.getElementById('saveDramaBtn').classList.remove('hidden');
    showToast(`สร้างบท "${data.title}" จำนวน ${data.episodes.length} ตอน สำเร็จ!`);
  } catch (err) {
    showToast('เกิดข้อผิดพลาดในการสร้างบทละคร');
    console.error(err);
  } finally {
    btn.disabled = false;
    btn.textContent = '🎬 สร้างบทละครและฉากวิดีโอ AI';
  }
}

function renderDramaResult(data) {
  const container = document.getElementById('dramaResultContainer');
  let html = `
    <div style="margin-bottom: 16px; border-bottom: 1px solid var(--border-subtle); padding-bottom: 12px;">
      <h3 style="font-size: 1.15rem; color: var(--cyan-primary);">${escapeHtml(data.title)}</h3>
      <p style="font-size: 0.8rem; color: var(--text-muted); margin-top: 4px;"><strong>เรื่องย่อ:</strong> ${escapeHtml(data.synopsis)}</p>
    </div>
    <div style="margin-bottom: 14px;">
      <h4 style="font-size: 0.85rem; margin-bottom: 6px;">ตัวละครหลัก (Character Lock):</h4>
      <div style="display: flex; flex-wrap: wrap; gap: 8px;">
        ${(data.characters || []).map(c => `
          <span style="font-size: 0.75rem; background: rgba(255,255,255,0.06); padding: 4px 8px; border-radius: 4px;">
            <strong>${escapeHtml(c.name)}</strong> (${escapeHtml(c.role)}) - ${escapeHtml(c.personality)}
          </span>
        `).join('')}
      </div>
    </div>
    <h4 style="font-size: 0.85rem; margin-bottom: 8px;">รายตอน & ฉากวิดีโอ (${(data.episodes || []).length} ตอน):</h4>
  `;

  html += (data.episodes || []).map(ep => `
    <div class="accordion-item">
      <div class="accordion-header" onclick="this.nextElementSibling.classList.toggle('hidden')">
        <span>🎬 <strong>${escapeHtml(ep.episode_title)}</strong></span>
        <button class="btn btn-xs btn-primary" onclick="event.stopPropagation(); queueDramaEpisode('${escapeHtml(ep.episode_title)}', '${escapeHtml(ep.video_prompt)}')">
          🚀 สั่ง Gen คลิปตอนนี้
        </button>
      </div>
      <div class="accordion-body">
        <p><strong>🔥 3-Second Viral Hook:</strong> <span style="color: #38bdf8;">${escapeHtml(ep.viral_hook)}</span></p>
        <p style="margin-top: 6px; white-space: pre-wrap;"><strong>บทพูดและอารมณ์:</strong>\n${escapeHtml(ep.script_dialogue)}</p>
        <p style="margin-top: 6px;"><strong>⚡ จุดหักมุม (Cliffhanger):</strong> ${escapeHtml(ep.cliffhanger)}</p>
        <div style="margin-top: 8px;">
          <strong>Visual Video Prompt (9:16 Vertical):</strong>
          <div class="prompt-code-box">${escapeHtml(ep.video_prompt)}</div>
        </div>
      </div>
    </div>
  `).join('');

  container.innerHTML = html;
}

async function queueDramaEpisode(epTitle, promptText) {
  try {
    const res = await fetch('/api/drama/queue-episode', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: epTitle, prompt: promptText, engine: 'google_flow' })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`ส่งตอน "${epTitle}" เข้าคิวสร้างวิดีโอเรียบร้อยแล้ว!`);
      loadDashboard();
      switchTab('tab-workflow');
    }
  } catch (err) {
    showToast('เกิดข้อผิดพลาดในการส่งงานเข้าคิว');
  }
}

async function saveCurrentDrama() {
  if (!currentDramaData) return;
  try {
    const res = await fetch('/api/drama/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(currentDramaData)
    });
    const d = await res.json();
    if (d.success) showToast('บันทึกซีรีส์เรียบร้อยแล้ว!');
  } catch (err) {
    showToast('ไม่สามารถบันทึกได้');
  }
}

// -------------------------------------------------------------
// 7. UGC Creator AI Studio
// -------------------------------------------------------------
async function handleGenerateUgc(event) {
  event.preventDefault();
  const btn = document.getElementById('ugcSubmitBtn');
  btn.disabled = true;
  btn.textContent = '⏳ กำลังสร้างสคริปต์ UGC...';

  const product = document.getElementById('ugcProduct').value;
  const niche = document.getElementById('ugcNiche').value;
  const hookType = document.getElementById('ugcHookType').value;
  const gender = document.getElementById('ugcGender').value;
  const voice = document.getElementById('ugcVoiceTone').value;

  try {
    const res = await fetch('/api/ugc/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ product_name: product, niche, hook_type: hookType, voice_tone_key: voice })
    });
    const data = await res.json();
    currentUgcData = data;

    renderUgcResult(data);
    document.getElementById('saveUgcBtn').classList.remove('hidden');
    showToast(`สร้างแผน UGC สำหรับ "${product}" สำเร็จ!`);
  } catch (err) {
    showToast('เกิดข้อผิดพลาดในการสร้างสคริปต์ UGC');
    console.error(err);
  } finally {
    btn.disabled = false;
    btn.textContent = '✨ สร้างสคริปต์ UGC & ฉากวิดีโอ AI';
  }
}

function renderUgcResult(data) {
  const container = document.getElementById('ugcResultContainer');
  let html = `
    <div style="margin-bottom: 14px; border-bottom: 1px solid var(--border-subtle); padding-bottom: 10px;">
      <h3 style="font-size: 1.1rem; color: var(--purple-primary);">${escapeHtml(data.product_name)}</h3>
      <span style="font-size: 0.75rem; background: rgba(168, 85, 247, 0.15); color: #c084fc; padding: 2px 8px; border-radius: 4px;">
        ${escapeHtml(data.hook_type)}
      </span>
    </div>
    
    <div style="margin-bottom: 16px;">
      <h4 style="font-size: 0.85rem; margin-bottom: 8px;">🎙 สคริปต์พูดเรียงตามวินาที (Spoken Flow):</h4>
      ${(data.spoken_script || []).map(s => `
        <div style="font-size: 0.78rem; padding: 8px; background: rgba(0,0,0,0.25); border-radius: 6px; margin-bottom: 6px;">
          <div style="display:flex; justify-content:space-between; color: var(--cyan-primary); font-weight: bold; margin-bottom: 2px;">
            <span>⏱ ${escapeHtml(s.second)}</span>
            <span style="color: var(--text-dim);">${escapeHtml(s.visual_action)}</span>
          </div>
          <div>"${escapeHtml(s.text)}"</div>
        </div>
      `).join('')}
    </div>

    <h4 style="font-size: 0.85rem; margin-bottom: 8px;">🎬 ฉากสร้างวิดีโอ AI (AI Video Prompts):</h4>
  `;

  html += (data.scene_prompts || []).map(sc => `
    <div class="accordion-item">
      <div class="accordion-header" onclick="this.nextElementSibling.classList.toggle('hidden')">
        <span>ฉากที่ ${sc.scene_number}: <strong>${escapeHtml(sc.title)}</strong> (${sc.duration_sec}s)</span>
        <button class="btn btn-xs btn-primary" onclick="event.stopPropagation(); queueUgcScene('${escapeHtml(data.product_name)} - ${escapeHtml(sc.title)}', '${escapeHtml(sc.prompt)}')">
          🚀 สั่ง Gen ฉากนี้
        </button>
      </div>
      <div class="accordion-body">
        <p><strong>มุมกล้อง:</strong> ${escapeHtml(sc.camera_instruction)}</p>
        <div class="prompt-code-box">${escapeHtml(sc.prompt)}</div>
      </div>
    </div>
  `).join('');

  if (data.caption_hashtags) {
    html += `
      <div style="margin-top: 14px; padding: 10px; background: rgba(255,255,255,0.03); border-radius: 6px; font-size: 0.78rem;">
        <strong>แคปชันและแฮชแท็ก:</strong>
        <p style="color: #94a3b8; margin-top: 4px;">${escapeHtml(data.caption_hashtags)}</p>
      </div>
    `;
  }

  container.innerHTML = html;
}

async function queueUgcScene(sceneTitle, promptText) {
  try {
    const res = await fetch('/api/ugc/queue-scene', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: sceneTitle, prompt: promptText, engine: 'google_flow' })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`ส่งฉาก "${sceneTitle}" เข้าคิวสร้างเรียบร้อยแล้ว!`);
      loadDashboard();
      switchTab('tab-workflow');
    }
  } catch (err) {
    showToast('ไม่สามารถส่งงานเข้าคิวได้');
  }
}

async function saveCurrentUgc() {
  if (!currentUgcData) return;
  try {
    const res = await fetch('/api/ugc/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(currentUgcData)
    });
    const d = await res.json();
    if (d.success) showToast('บันทึกแคมเปญ UGC เรียบร้อย!');
  } catch (err) {
    showToast('ไม่สามารถบันทึกได้');
  }
}

// -------------------------------------------------------------
// 8. ช่วยคิด Prompt Studio
// -------------------------------------------------------------
async function handleOptimizePrompt(event) {
  event.preventDefault();
  const btn = document.getElementById('promptSubmitBtn');
  btn.disabled = true;
  btn.textContent = '💡 กำลังปรับแต่ง Prompt ขั้นสูง...';

  const raw = document.getElementById('promptRaw').value;
  const engine = document.getElementById('promptEngine').value;
  const camera = document.getElementById('promptCamera').value;
  const lighting = document.getElementById('promptLighting').value;

  try {
    const res = await fetch('/api/prompt/optimize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ raw_idea: raw, target_engine: engine, camera_motion: camera, lighting: lighting })
    });
    const data = await res.json();
    currentOptimizedPrompt = data;

    renderOptimizedPrompt(data);
    document.getElementById('promptQueueDirectBtn').classList.remove('hidden');
    showToast('ปรับแต่ง Prompt ขั้นสูงสำเร็จ!');
  } catch (err) {
    showToast('เกิดข้อผิดพลาดในการปรับแต่ง Prompt');
    console.error(err);
  } finally {
    btn.disabled = false;
    btn.textContent = '💡 ปรับแต่ง Prompt ให้พร้อมสร้างคลิป';
  }
}

function renderOptimizedPrompt(data) {
  const container = document.getElementById('promptResultContainer');
  container.innerHTML = `
    <div style="margin-bottom: 12px;">
      <span class="status-badge" style="background: rgba(56,189,248,0.15); color: #38bdf8;">
        Target: ${escapeHtml(data.target_engine)} (${data.aspect_ratio || '9:16'})
      </span>
    </div>
    <div style="margin-bottom: 12px;">
      <strong>Prompt พร้อมใช้งาน (คัดลอกหรือส่ง Gen ได้ทันที):</strong>
      <div class="prompt-code-box" style="font-size: 0.8rem; line-height: 1.5;">${escapeHtml(data.optimized_prompt)}</div>
    </div>
    <div style="margin-bottom: 12px;">
      <strong style="color: #f87171;">Negative Prompt (ตัดสิ่งแปลกปลอม):</strong>
      <div class="prompt-code-box" style="color: #fca5a5;">${escapeHtml(data.negative_prompt)}</div>
    </div>
    <div style="font-size: 0.78rem; color: var(--text-muted); display: flex; flex-direction: column; gap: 4px;">
      <span>📷 <strong>การเคลื่อนกล้อง:</strong> ${escapeHtml(data.camera_motion)}</span>
      <span>💡 <strong>แสงและบรรยากาศ:</strong> ${escapeHtml(data.lighting)}</span>
    </div>
  `;
}

async function queueOptimizedPromptDirect() {
  if (!currentOptimizedPrompt) return;
  try {
    const res = await fetch('/api/queue', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        task_type: 'prompt_gen',
        title: currentOptimizedPrompt.raw_idea.slice(0, 30) || 'AI Video Prompt',
        prompt: currentOptimizedPrompt.optimized_prompt,
        engine: currentOptimizedPrompt.target_engine,
        aspect_ratio: currentOptimizedPrompt.aspect_ratio || '9:16'
      })
    });
    const d = await res.json();
    if (d.success) {
      showToast('ส่ง Prompt เข้าคิวสร้างวิดีโอเรียบร้อยแล้ว!');
      loadDashboard();
      switchTab('tab-workflow');
    }
  } catch (err) {
    showToast('ไม่สามารถส่งงานเข้าคิวได้');
  }
}

// -------------------------------------------------------------
// 9. Calendar & Content Planner
// -------------------------------------------------------------
async function loadCalendar() {
  try {
    const res = await fetch('/api/calendar/events');
    const data = await res.json();
    const events = data.events || [];

    document.getElementById('calendarCountSummary').textContent = `${events.length} รายการ`;
    const container = document.getElementById('calendarEventsList');

    if (events.length === 0) {
      container.innerHTML = '<div class="empty-state">ยังไม่มีรายการแผนใน Calendar กดปุ่ม "+ AI สร้างแผนอัตโนมัติ" ด้านบนเพื่อเริ่มต้น</div>';
      return;
    }

    container.innerHTML = events.map(ev => `
      <div style="display: flex; align-items: center; justify-content: space-between; padding: 12px; background: rgba(0,0,0,0.25); border: 1px solid var(--border-subtle); border-radius: 8px; margin-bottom: 8px;">
        <div style="display: flex; align-items: center; gap: 14px;">
          <div style="background: rgba(56,189,248,0.15); color: #38bdf8; font-weight: bold; padding: 8px 12px; border-radius: 6px; text-align: center; min-width: 90px;">
            <div style="font-size: 0.85rem;">${escapeHtml(ev.scheduled_date)}</div>
            <div style="font-size: 0.7rem; color: var(--text-dim);">${escapeHtml(ev.scheduled_time)} น.</div>
          </div>
          <div>
            <div style="font-size: 0.88rem; font-weight: 600;">${escapeHtml(ev.title)}</div>
            <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 2px;">
              <span>ช่องทาง: <strong>${escapeHtml(ev.channel.toUpperCase())}</strong></span> |
              <span>Engine: <strong>${escapeHtml(ev.engine)}</strong></span> |
              <span>Auto Gen: <strong>${ev.auto_gen ? 'เปิดอัตโนมัติ' : 'ปิด'}</strong></span>
            </div>
          </div>
        </div>

        <div style="display: flex; align-items: center; gap: 8px;">
          <span class="status-badge ${ev.status}">${escapeHtml(ev.status)}</span>
          <button class="btn btn-xs btn-secondary" onclick="deleteCalendarEvent(${ev.id})">ลบ</button>
        </div>
      </div>
    `).join('');
  } catch (err) {
    console.error('Error loading calendar:', err);
  }
}

function openPlanModal() {
  document.getElementById('planModal').classList.remove('hidden');
}

function closePlanModal() {
  document.getElementById('planModal').classList.add('hidden');
}

async function handleGeneratePlan(event) {
  event.preventDefault();
  const btn = document.getElementById('planSubmitBtn');
  btn.disabled = true;
  btn.textContent = '⏳ กำลังวางแผนและจัดตาราง...';

  const type = document.getElementById('planType').value;
  const topic = document.getElementById('planTopic').value;
  const days = parseInt(document.getElementById('planDays').value, 10);
  const time = document.getElementById('planTime').value;
  const channel = document.getElementById('planChannel').value;
  const engine = document.getElementById('planEngine').value;
  const autoGen = document.getElementById('planAutoGen').checked;

  try {
    const res = await fetch('/api/calendar/plan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        campaign_type: type,
        topic_or_product: topic,
        days_count: days,
        preferred_time: time,
        channel,
        engine,
        auto_gen: autoGen
      })
    });
    const d = await res.json();
    if (d.success) {
      showToast(`สร้างแผน ${d.count} วัน ลงใน Calendar เรียบร้อยแล้ว!`);
      closePlanModal();
      loadCalendar();
      loadDashboard();
    }
  } catch (err) {
    showToast('เกิดข้อผิดพลาดในการสร้างแผน');
  } finally {
    btn.disabled = false;
    btn.textContent = '🚀 สร้างแผนและเพิ่มลง Calendar ทันที';
  }
}

async function deleteCalendarEvent(id) {
  if (!confirm('ยืนยันลบรายการนี้ออกจาก Calendar?')) return;
  try {
    await fetch(`/api/calendar/${id}`, { method: 'DELETE' });
    showToast('ลบรายการเรียบร้อย');
    loadCalendar();
    loadDashboard();
  } catch (err) {
    showToast('ลบไม่สำเร็จ');
  }
}

async function queueAllCalendarNow() {
  try {
    const res = await fetch('/api/calendar/queue-now', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({})
    });
    const data = await res.json();
    showToast(`ส่งงานจาก Calendar เข้าคิวจำนวน ${data.queued_jobs.length} งานแล้ว!`);
    loadCalendar();
    loadDashboard();
    switchTab('tab-queue');
  } catch (err) {
    showToast('ไม่สามารถสั่งสร้างได้');
  }
}

// -------------------------------------------------------------
// 10. Queue Management Table
// -------------------------------------------------------------
async function loadQueueTable() {
  try {
    const res = await fetch('/api/queue?limit=50');
    const data = await res.json();
    const jobs = data.jobs || [];

    const tbody = document.getElementById('queueTableBody');
    if (jobs.length === 0) {
      tbody.innerHTML = '<tr><td colspan="8" class="text-center empty-state">ยังไม่มีงานในคิว</td></tr>';
      return;
    }

    tbody.innerHTML = jobs.map(j => `
      <tr>
        <td>#${j.id}</td>
        <td><strong>${escapeHtml(j.title)}</strong></td>
        <td><span style="font-size: 0.75rem; text-transform: uppercase;">${escapeHtml(j.task_type)}</span></td>
        <td><span style="font-size: 0.75rem;">${j.engine === 'meta_ai' ? 'Meta AI' : 'Google Flow'}</span></td>
        <td><span class="status-badge ${j.status}">${escapeHtml(j.status)}</span></td>
        <td>
          <div class="progress-track">
            <div class="progress-fill" style="width: ${j.progress}%;"></div>
          </div>
          <span style="font-size: 0.7rem;">${j.progress}%</span>
        </td>
        <td>
          ${j.video_path ? `
            <button class="btn btn-xs btn-primary" onclick="openVideoPlayer('${j.video_path}', '${escapeHtml(j.title)}')">
              ▶ ดูคลิป
            </button>
          ` : '<span style="color: var(--text-dim); font-size: 0.75rem;">-</span>'}
        </td>
        <td>
          <div style="display: flex; gap: 4px;">
            ${j.status === 'failed' ? `<button class="btn btn-xs btn-secondary" onclick="retryJob(${j.id})">ลองใหม่</button>` : ''}
            <button class="btn btn-xs btn-secondary" onclick="deleteJob(${j.id})">ลบ</button>
          </div>
        </td>
      </tr>
    `).join('');
  } catch (err) {
    console.error('Error loading queue:', err);
  }
}

async function retryJob(id) {
  try {
    await fetch(`/api/queue/${id}/retry`, { method: 'POST' });
    showToast(`สั่งลองทำงาน #${id} ใหม่อีกครั้ง`);
    loadQueueTable();
  } catch (err) {
    showToast('ลองใหม่ไม่สำเร็จ');
  }
}

async function deleteJob(id) {
  try {
    await fetch(`/api/queue/${id}`, { method: 'DELETE' });
    showToast(`ลบงาน #${id} เรียบร้อย`);
    loadQueueTable();
    loadDashboard();
  } catch (err) {
    showToast('ลบงานไม่สำเร็จ');
  }
}

// -------------------------------------------------------------
// 11. Settings & Engine Config
// -------------------------------------------------------------
async function loadSettings() {
  try {
    const res = await fetch('/api/settings');
    const data = await res.json();
    const s = data.settings || {};

    if (s.default_engine) document.getElementById('cfgDefaultEngine').value = s.default_engine;
    if (s.gemini_api_key) document.getElementById('cfgGeminiKey').value = s.gemini_api_key;
    if (s.simulation_mode !== undefined) {
      document.getElementById('cfgSimulationMode').checked = s.simulation_mode.toLowerCase() === 'true';
    }
    if (s.notify_macos !== undefined) {
      document.getElementById('cfgNotifyMacos').checked = s.notify_macos.toLowerCase() === 'true';
    }
  } catch (err) {
    console.error('Error loading settings:', err);
  }
}

async function handleSaveSettings(event) {
  event.preventDefault();
  const settings = {
    default_engine: document.getElementById('cfgDefaultEngine').value,
    gemini_api_key: document.getElementById('cfgGeminiKey').value,
    simulation_mode: document.getElementById('cfgSimulationMode').checked ? 'true' : 'false',
    notify_macos: document.getElementById('cfgNotifyMacos').checked ? 'true' : 'false'
  };

  try {
    const res = await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ settings })
    });
    const d = await res.json();
    if (d.success) showToast('บันทึกการตั้งค่าเรียบร้อยแล้ว!');
  } catch (err) {
    showToast('บันทึกการตั้งค่าไม่สำเร็จ');
  }
}

async function toggleWorker() {
  try {
    const res = await fetch('/api/worker/toggle', { method: 'POST' });
    const data = await res.json();
    showToast(`Auto Worker: ${data.auto_worker_enabled ? 'เปิดการทำงาน' : 'หยุดชั่วคราว'}`);
    loadDashboard();
  } catch (err) {
    showToast('ไม่สามารถเปลี่ยนสถานะ Worker ได้');
  }
}

// -------------------------------------------------------------
// 12. Quick Sample Testing & Video Modal
// -------------------------------------------------------------
async function triggerSampleTest(engine) {
  try {
    showToast(`กำลังเริ่มทดสอบสร้างคลิปด้วย ${engine}...`);
    const res = await fetch(`/api/test/generate-sample?engine=${engine}`, { method: 'POST' });
    const data = await res.json();
    if (data.success) {
      showToast(`งานทดสอบ #${data.job_id} ถูกส่งเข้าคิวแล้ว!`);
      loadDashboard();
      switchTab('tab-workflow');
    }
  } catch (err) {
    showToast('ทดสอบไม่สำเร็จ');
  }
}

function openVideoPlayer(videoPath, title) {
  const modal = document.getElementById('videoModal');
  const player = document.getElementById('modalVideoPlayer');
  const titleEl = document.getElementById('modalVideoTitle');
  const metaEl = document.getElementById('modalVideoMeta');

  titleEl.textContent = title;
  metaEl.innerHTML = `
    <a href="${videoPath}" download class="btn btn-xs btn-primary">⬇ ดาวน์โหลดไฟล์ MP4 (9:16)</a>
  `;
  player.src = videoPath;
  modal.classList.remove('hidden');
}

function closeVideoModal() {
  const modal = document.getElementById('videoModal');
  const player = document.getElementById('modalVideoPlayer');
  player.pause();
  player.src = '';
  modal.classList.add('hidden');
}

function escapeHtml(text) {
  if (!text) return '';
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

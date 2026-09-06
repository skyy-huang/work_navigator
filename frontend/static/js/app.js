/* ════════════════════════════════════════════════════════════════
   职航 · 前端应用脚本 v0.2
   工作台聚合 / 简历创建 / 岗位智能匹配 / 一键投递（后端 REST API）
   ════════════════════════════════════════════════════════════════ */
'use strict';

(function () {
  const VIEWS = ['workbench', 'assistant', 'resume', 'interview', 'opportunities'];
  const DEFAULT_VIEW = 'workbench';
  const INDUSTRY_LOGO_CLASS = {
    '互联网': 'logo-int',
    '金融': 'logo-fin',
    '快消': 'logo-fmcg',
    '制造': 'logo-mfg',
    '咨询': 'logo-cons',
    '央国企': 'logo-soe',
  };
  const FAV_KEY = 'zhihang_favs';

  const state = {
    me: null,
    dash: null,
    jobs: [],
    applications: [],
    appliedIds: new Set(),
    favs: new Set(JSON.parse(localStorage.getItem(FAV_KEY) || '[]')),
    industryFilter: '全部',
    jobQuery: '',
    currentModalJob: null,
    skills: [],
  };

  const $ = (id) => document.getElementById(id);

  function esc(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function firstChar(text) {
    const s = String(text || '').trim();
    return s ? s[0] : '企';
  }

  /* ── Toast ── */
  const toastEl = $('toast');
  let toastTimer = null;
  function showToast(message, duration) {
    if (!toastEl) return;
    toastEl.textContent = message;
    toastEl.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toastEl.classList.remove('show'), duration || 2400);
  }

  /* ── API ── */
  async function api(path, options) {
    const res = await fetch(path, options);
    let data = {};
    try { data = await res.json(); } catch (err) { /* 无响应体 */ }
    if (!res.ok) {
      const detail = (data && data.detail) || ('请求失败 (' + res.status + ')');
      throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
    }
    return data;
  }

  /* ═══════════════════════════════════════════════
     hash 路由
  ═══════════════════════════════════════════════ */
  function viewFromHash() {
    const key = location.hash.replace(/^#\/?/, '');
    return VIEWS.indexOf(key) !== -1 ? key : DEFAULT_VIEW;
  }

  function activateView(name) {
    VIEWS.forEach((view) => {
      const section = $('view-' + view);
      const link = document.querySelector('.nav-link[data-view="' + view + '"]');
      if (!section) return;
      const active = view === name;
      section.classList.toggle('is-active', active);
      if (link) {
        link.classList.toggle('is-active', active);
        if (active) link.setAttribute('aria-current', 'page');
        else link.removeAttribute('aria-current');
      }
    });
    const mainEl = document.querySelector('.main');
    if (mainEl) mainEl.scrollTop = 0;
  }

  window.addEventListener('hashchange', () => activateView(viewFromHash()));

  function greetingByHour() {
    const hour = new Date().getHours();
    if (hour < 6) return '夜深了';
    if (hour < 11) return '早上好';
    if (hour < 14) return '中午好';
    if (hour < 18) return '下午好';
    return '晚上好';
  }

  function renderTopbar() {
    const profile = state.me && state.me.profile;
    if (!profile) return;
    $('userName').textContent = profile.name;
    $('userAvatar').textContent = firstChar(profile.name);
    $('userMeta').textContent = profile.grade + ' · ' + profile.major;
  }

  function renderWorkbench() {
    const dash = state.dash;
    const profile = dash.profile;
    const stats = dash.stats;
    const name = profile ? profile.name : '同学';
    $('wbGreeting').textContent = greetingByHour() + '，' + name + ' 👋';

    if (!dash.has_resume) {
      $('wbSub').textContent = '迈出第一步：创建简历后，我们就能为你推荐合适的机会';
      $('wbResumeShortcut').textContent = '📄 创建简历';
      $('resumeCta').classList.remove('hidden');
    } else {
      $('wbSub').textContent = '已投递 ' + stats.applications + ' 个岗位 · 面试中 ' + stats.in_interview +
        ' · 获得 Offer ' + stats.offers + ' 个';
      $('resumeCta').classList.add('hidden');
    }

    const p = dash.progress;
    $('wbProgressSummary').textContent = '已完成 ' + p.done_count + ' / ' + p.total + ' 步';
    $('wbProgress').innerHTML = p.steps.map((step, index) => {
      const marker = step.state === 'done'
        ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>'
        : esc(index + 1);
      return '<li class="step ' + (step.state === 'done' ? 'is-done' : '') +
        (step.state === 'current' ? ' is-current' : '') + '">' +
        '<span class="step-marker">' + marker + '</span>' +
        '<p class="step-name">' + esc(step.label) + '</p>' +
        '<p class="step-sub">' + esc(step.desc) + '</p></li>';
    }).join('');

    const taskList = $('wbTasks');
    if (!dash.tasks || !dash.tasks.length) {
      taskList.innerHTML = '<p class="loading-hint">暂无任务，一切顺利 🎉</p>';
    } else {
      const chipColor = { '简历': 'chip-tag', '投递': 'chip-job', '笔试': 'chip-code', '面试': 'chip-ok' };
      taskList.innerHTML = dash.tasks.map((task) => (
        '<li class="task-item">' +
        '<span class="task-dot task-open"></span>' +
        '<p>' + esc(task.title) + '</p>' +
        '<span class="chip ' + (chipColor[task.chip] || 'chip-soft') + '">' + esc(task.chip) + '</span>' +
        '<a class="text-btn" href="' + esc(task.link) + '">' + esc(task.cta) + '</a>' +
        '</li>'
      )).join('');
    }

    const jobList = $('wbJobs');
    if (!dash.recommended || !dash.recommended.length) {
      jobList.innerHTML = '<p class="loading-hint">' +
        (dash.has_resume ? '暂时没有推荐，去机会速览看看全部岗位' : '创建简历后自动推荐') + '</p>';
    } else {
      jobList.innerHTML = dash.recommended.map((item) => {
        const job = item.job;
        return '<li class="mini-job">' +
          '<span class="mini-logo" style="background:var(--primary)">' + esc(firstChar(job.company)) + '</span>' +
          '<p class="mini-job-main"><b>' + esc(job.company + ' · ' + job.title) + '</b>' +
          '<i>' + esc(job.city + ' · ' + job.type) + '</i></p>' +
          '<span class="chip chip-match">匹配 ' + item.match.score + '%</span></li>';
      }).join('');
    }

    renderApplications();
  }

  function renderApplications() {
    const apps = state.applications;
    $('wbAppSummary').textContent = apps.length ? '共 ' + apps.length + ' 条' : '暂无投递';
    const list = $('wbAppList');
    if (!apps.length) {
      list.innerHTML = '<p class="loading-hint">还没有投递记录，去机会速览找找合适岗位吧。</p>';
      return;
    }
    list.innerHTML = apps.map((app) => {
      const job = app.job;
      const isOffer = app.status_order >= 4;
      return '<li class="app-row">' +
        '<div class="app-row-main"><b>' + esc(job.company + ' · ' + job.title) + '</b>' +
        '<i><span class="app-time">' + esc(app.applied_at) + '</span> · ' + esc(job.city) + '</i></div>' +
        '<span class="app-status st-' + app.status_order + '">' + esc(app.status) + '</span>' +
        '<div class="app-actions">' +
        (!isOffer ? '<button class="btn btn-ghost btn-sm" data-app-action="advance" data-id="' + esc(app.id) + '">演示推进</button>' : '') +
        '<button class="btn btn-ghost btn-sm" data-app-action="withdraw" data-id="' + esc(app.id) + '">撤回</button>' +
        '</div></li>';
    }).join('');
  }

  async function refreshAll() {
    try {
      state.me = await api('/api/me');
      state.dash = await api('/api/dashboard');
      state.applications = (await api('/api/applications')).applications;
      state.appliedIds = new Set(state.applications.map((app) => app.job.id));
      renderTopbar();
      renderWorkbench();
    } catch (err) {
      console.error(err);
      showToast('数据加载失败：' + err.message, 3200);
    }
  }

  /* ═══════════════════════════════════════════════
     机会速览（岗位 + 智能匹配 + 投递）
  ═══════════════════════════════════════════════ */
  function renderIndustryPills(industries) {
    const wrap = $('industryPills');
    wrap.innerHTML = industries.map((industry) =>
      '<button class="filter-pill ' + (state.industryFilter === industry ? 'is-on' : '') +
      '" type="button" data-industry="' + esc(industry) + '">' + esc(industry) + '</button>'
    ).join('');
  }

  function matchBarHtml(match) {
    if (!match) {
      return '<div class="job-no-match">创建简历后展示匹配度 · <a href="#/resume">去创建</a></div>';
    }
    const width = Math.max(6, match.score);
    return '<div class="match-line"><i><em style="width:' + width + '%"></em></i>' +
      '<span>' + match.score + '% 匹配</span></div>';
  }

  function jobCardHtml(job) {
    const applied = state.appliedIds.has(job.id);
    const faved = state.favs.has(job.id);
    const match = job.match;
    const logoClass = INDUSTRY_LOGO_CLASS[job.industry] || 'logo-int';
    const tags = (job.tags || []).slice(0, 3).map((tag) => '<span class="tag tag-bk">' + esc(tag) + '</span>').join('');
    return '<article class="job-card card ' + (applied ? 'is-applied' : '') + '" data-job-id="' + esc(job.id) + '">' +
      '<div class="job-head">' +
      '<span class="job-logo ' + logoClass + '">' + esc(firstChar(job.company)) + '</span>' +
      '<div class="job-title"><b>' + esc(job.title) + '</b><i>' + esc(job.company + ' · ' + job.city + ' · ' + job.type) + '</i></div>' +
      '<button class="fav-btn ' + (faved ? 'is-on' : '') + '" type="button" data-fav data-id="' + esc(job.id) + '" aria-label="收藏">' + (faved ? '♥' : '♡') + '</button>' +
      '</div>' +
      '<p class="job-pay">' + esc(job.pay) + '</p>' +
      '<p class="job-tags">' + tags + '</p>' +
      matchBarHtml(match) +
      '<div class="job-foot">' +
      '<button class="btn btn-ghost btn-sm" type="button" data-act="detail" data-id="' + esc(job.id) + '">查看详情</button>' +
      (applied
        ? '<button class="btn btn-primary btn-sm" type="button" disabled>已投递 ✓</button>'
        : '<button class="btn btn-primary btn-sm" type="button" data-act="apply" data-id="' + esc(job.id) + '">去投递</button>') +
      '</div></article>';
  }

  function renderJobGrid() {
    const grid = $('jobGrid');
    const empty = $('jobEmpty');
    if (!state.jobs.length) {
      grid.innerHTML = '';
      empty.textContent = '没有符合条件的岗位，换个筛选或搜索词试试';
      empty.style.display = '';
      return;
    }
    empty.style.display = 'none';
    grid.innerHTML = state.jobs.map(jobCardHtml).join('');
  }

  async function loadJobs() {
    try {
      const query = new URLSearchParams();
      if (state.industryFilter && state.industryFilter !== '全部') query.set('industry', state.industryFilter);
      if (state.jobQuery) query.set('q', state.jobQuery);
      const data = await api('/api/jobs?' + query.toString());
      state.jobs = data.jobs;
      renderIndustryPills(data.industries);
      renderJobGrid();
      renderRecStrip();
    } catch (err) {
      console.error(err);
      $('jobGrid').innerHTML = '<p class="loading-hint">岗位加载失败：' + esc(err.message) + '</p>';
    }
  }

  async function renderRecStrip() {
    const listEl = $('recList');
    if (!state.me || !state.me.has_resume) {
      listEl.innerHTML = '<div class="rec-item" style="cursor:default;flex:1;min-width:0;border-style:dashed">' +
        '<b>创建简历后自动推荐</b><i>按 技能 / 方向 / 行业 / 城市 计算匹配度</i></div>';
      return;
    }
    try {
      const data = await api('/api/recommendations?limit=4');
      if (!data.items.length) {
        listEl.innerHTML = '<p class="loading-hint">暂无推荐</p>';
        return;
      }
      listEl.innerHTML = data.items.map((item) => {
        const job = item.job;
        const why = (item.match.matched_skills || []).slice(0, 3).join(' / ') || '方向匹配';
        return '<div class="rec-item" data-job-id="' + esc(job.id) + '" role="button">' +
          '<div class="rec-item-top"><b>' + esc(job.company + ' · ' + job.title) + '</b>' +
          '<span class="rec-score">' + item.match.score + '%</span></div>' +
          '<i>' + esc(job.city + ' · ' + job.pay) + '</i>' +
          '<span class="mini-why">命中：' + esc(why) + '</span></div>';
      }).join('');
    } catch (err) {
      listEl.innerHTML = '<p class="loading-hint">' + esc(err.message) + '</p>';
    }
  }

  function findJob(id) {
    return state.jobs.find((job) => job.id === id) || null;
  }

  async function doApply(jobId) {
    try {
      const job = findJob(jobId);
      await api('/api/applications', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ job_id: jobId }),
      });
      showToast('已投递「' + (job ? job.company : '') + '」，去工作台查看进度');
      state.appliedIds.add(jobId);
      renderJobGrid();
      closeModal();
      await refreshAll();
    } catch (err) {
      if (/已投递/.test(err.message)) {
        showToast('该岗位已在投递记录中', 2600);
      } else {
        showToast('投递失败：' + err.message, 3200);
      }
      await refreshAll();
    }
  }

  async function advanceApplication(id) {
    try {
      const next = await api('/api/applications/' + encodeURIComponent(id) + '/advance', { method: 'POST' });
      showToast('演示推进：状态更新为「' + next.status + '」');
      await refreshAll();
    } catch (err) {
      showToast(err.message, 3000);
    }
  }

  async function withdrawApplication(id) {
    try {
      await api('/api/applications/' + encodeURIComponent(id), { method: 'DELETE' });
      showToast('已撤回该投递');
      await refreshAll();
      renderJobGrid();
    } catch (err) {
      showToast(err.message, 3000);
    }
  }

  function toggleFav(jobId) {
    if (state.favs.has(jobId)) state.favs.delete(jobId);
    else state.favs.add(jobId);
    localStorage.setItem(FAV_KEY, JSON.stringify(Array.from(state.favs)));
    renderJobGrid();
  }

  /* ── 岗位详情弹层 ── */
  const modal = $('jobModal');

  function openModal(jobId) {
    const job = findJob(jobId);
    if (!job) return;
    state.currentModalJob = job;
    $('mLogo').className = 'job-logo ' + (INDUSTRY_LOGO_CLASS[job.industry] || 'logo-int');
    $('mLogo').textContent = firstChar(job.company);
    $('mTitle').textContent = job.title;
    $('mCompanyLine').textContent = job.company + ' · ' + job.city + ' · ' + job.type;
    $('mType').textContent = job.type;
    $('mIndustry').textContent = job.industry;
    $('mPay').textContent = job.pay;
    $('mTags').innerHTML = (job.tags || []).map((tag) => '<span class="tag tag-bk">' + esc(tag) + '</span>').join('');

    const detailJob = state.jobs.find((j) => j.id === jobId);
    $('mDesc').textContent = (detailJob && detailJob.description) || '岗位描述接入中';
    const reqs = (detailJob && detailJob.requirements) || [];
    $('mReqList').innerHTML = reqs.length
      ? reqs.map((req) => '<li>' + esc(req) + '</li>').join('')
      : '<li>任职要求接入中</li>';

    renderModalMatch(detailJob ? detailJob.match : null);
    const applied = state.appliedIds.has(jobId);
    const applyBtn = $('mApplyBtn');
    applyBtn.disabled = applied;
    applyBtn.textContent = applied ? '已投递 ✓' : '立即投递';
    const faved = state.favs.has(jobId);
    $('mFavBtn').textContent = faved ? '♥ 已收藏' : '♡ 收藏';
    modal.classList.remove('hidden');
  }

  function renderModalMatch(match) {
    const wrap = $('mMatch');
    if (!match) {
      wrap.innerHTML = '<p class="modal-empty">当前没有简历，无法计算匹配度。' +
        '创建简历后这里会展示技能命中与缺口。<a href="#/resume">去创建简历</a></p>';
      return;
    }
    const matched = (match.matched_skills || []).map((s) => '<span class="tag tag-es">✓ ' + esc(s) + '</span>').join('');
    const missing = (match.missing_skills || []).map((s) => '<span class="tag tag-bk">✗ ' + esc(s) + '</span>').join('');
    const reasons = [];
    if (match.direction_matched) reasons.push('方向与意向一致');
    if (match.industry_matched) reasons.push('行业与意向一致');
    if (match.city_matched) reasons.push('城市与意向一致');
    wrap.innerHTML =
      '<div class="match-hero"><span class="match-score-num">' + match.score + '%</span>' +
      '<div class="match-hero-text"><b>简历匹配度</b><p>' +
      (reasons.length ? reasons.join(' · ') : '基于技能重合度计算') + '</p></div></div>' +
      '<div class="match-chips">' +
      (matched ? '<div><span class="lb">技能命中</span>' + matched + '</div>' : '') +
      (missing
        ? '<div><span class="lb">技能缺口</span>' + missing + '</div>'
        : '<div><span class="lb">技能缺口</span><span class="coming-tag">无</span></div>') +
      '</div>';
  }

  function closeModal() {
    modal.classList.add('hidden');
    state.currentModalJob = null;
  }

  /* ═══════════════════════════════════════════════
     简历编辑器（创建 / 编辑 / 技能提取）
  ═══════════════════════════════════════════════ */
  const SAMPLE_RESUME = {
    full_name: '李同学',
    phone: '13800000000',
    email: 'li.tongxue@example.com',
    wechat: 'zhihang-demo',
    target_role: '后端开发实习生',
    target_direction: '后端',
    target_industry: '互联网',
    target_city: '杭州',
    self_intro: '计算机专业大三学生，熟悉 Java 与 Spring Boot 全栈开发，动手完成过秒杀系统与校园二手交易平台两个完整项目，注重工程规范与性能优化，目标拿下大厂后端实习。',
    education: [{ school: '示例大学', major: '计算机科学与技术', degree: '本科', period: '2023 - 2027' }],
    skills: ['Java', 'Spring Boot', 'MySQL', 'Redis', '分布式'],
    projects: [{
      name: '校园二手交易平台',
      period: '2025.03 - 2025.08',
      description: '负责订单与支付模块，使用 Spring Boot + MyBatis + MySQL 开发；用 Redis 缓存热点商品并做接口幂等，支撑 2000+ 日活。',
    }],
    internships: [{
      company: '某互联网创业公司',
      role: '后端开发实习生',
      period: '2026.06 - 2026.08',
      description: '参与用户增长后台接口开发与数据看板搭建，使用 SQL 分析留存漏斗并输出 3 条优化建议，被业务采纳。',
    }],
  };

  function eduRowHtml(data) {
    data = data || {};
    return '<div class="row-card">' +
      '<button class="row-remove" type="button" data-remove="edu" aria-label="删除">✕</button>' +
      '<div class="field-grid fg-2">' +
      '<label class="field"><span>学校</span><input data-k="school" value="' + esc(data.school) + '" placeholder="如：示例大学" maxlength="40" /></label>' +
      '<label class="field"><span>专业</span><input data-k="major" value="' + esc(data.major) + '" placeholder="如：计算机科学与技术" maxlength="40" /></label>' +
      '<label class="field"><span>学历</span><input data-k="degree" value="' + esc(data.degree) + '" placeholder="本科 / 硕士" maxlength="20" /></label>' +
      '<label class="field"><span>时间</span><input data-k="period" value="' + esc(data.period) + '" placeholder="2023 - 2027" maxlength="30" /></label>' +
      '</div></div>';
  }

  function projectRowHtml(data) {
    data = data || {};
    return '<div class="row-card">' +
      '<button class="row-remove" type="button" data-remove="project" aria-label="删除">✕</button>' +
      '<div class="field-grid fg-2">' +
      '<label class="field"><span>项目名称</span><input data-k="name" value="' + esc(data.name) + '" placeholder="如：校园二手交易平台" maxlength="60" /></label>' +
      '<label class="field"><span>时间</span><input data-k="period" value="' + esc(data.period) + '" placeholder="2025.03 - 2025.08" maxlength="30" /></label>' +
      '</div>' +
      '<label class="field"><span>描述（写清职责、技术栈与量化结果）</span>' +
      '<textarea rows="2" data-k="description" placeholder="用 Spring Boot + MySQL 开发…支撑 2000+ 日活">' + esc(data.description) + '</textarea></label>' +
      '</div>';
  }

  function internRowHtml(data) {
    data = data || {};
    return '<div class="row-card">' +
      '<button class="row-remove" type="button" data-remove="intern" aria-label="删除">✕</button>' +
      '<div class="field-grid fg-2">' +
      '<label class="field"><span>公司</span><input data-k="company" value="' + esc(data.company) + '" placeholder="公司/单位名称" maxlength="40" /></label>' +
      '<label class="field"><span>岗位</span><input data-k="role" value="' + esc(data.role) + '" placeholder="岗位名称" maxlength="40" /></label>' +
      '<label class="field"><span>时间</span><input data-k="period" value="' + esc(data.period) + '" placeholder="2026.06 - 2026.08" maxlength="30" /></label>' +
      '</div>' +
      '<label class="field"><span>工作内容（含量化结果）</span>' +
      '<textarea rows="2" data-k="description" placeholder="负责…，用 SQL 分析…输出 3 条优化建议">' + esc(data.description) + '</textarea></label>' +
      '</div>';
  }

  function blockRows(containerId, keys) {
    return Array.prototype.map.call($(containerId).querySelectorAll('.row-card'), (row) => {
      const item = {};
      keys.forEach((key) => {
        const input = row.querySelector('[data-k="' + key + '"]');
        item[key] = input ? input.value.trim() : '';
      });
      return item;
    }).filter((row) => Object.values(row).some(Boolean));
  }

  function collectResume() {
    const eduRows = Array.prototype.map.call($('eduList').querySelectorAll('.row-card'), (row) => {
      const get = (key) => (row.querySelector('[data-k="' + key + '"]') || {}).value || '';
      return { school: get('school').trim(), major: get('major').trim(), degree: get('degree').trim(), period: get('period').trim() };
    }).filter((row) => row.school || row.major || row.degree);

    return {
      full_name: $('fName').value.trim(),
      phone: $('fPhone').value.trim(),
      email: $('fEmail').value.trim(),
      wechat: $('fWechat').value.trim(),
      target_role: $('fRole').value.trim(),
      target_direction: $('fDirection').value,
      target_industry: $('fIndustry').value,
      target_city: $('fCity').value.trim(),
      self_intro: $('fIntro').value.trim(),
      education: eduRows,
      projects: blockRows('projList', ['name', 'period', 'description']),
      internships: blockRows('interList', ['company', 'role', 'period', 'description']),
      skills: state.skills.slice(),
    };
  }

  function refreshCompleteness() {
    const resume = collectResume();
    const criteria = [
      { id: 'okRole', ok: !!resume.target_role },
      { id: 'okEdu', ok: resume.education.length > 0 },
      { id: 'okProj', ok: resume.projects.length > 0 },
      { id: 'okInter', ok: resume.internships.length > 0 },
      { id: 'okSkill', ok: resume.skills.length >= 3 },
    ];
    criteria.forEach((criterion) => { $(criterion.id).textContent = criterion.ok ? '1' : '0'; });
    $('resumeComplete').textContent = criteria.filter((c) => c.ok).length * 20 + '%';
  }

  function renderSkillTags() {
    $('skillTags').innerHTML = state.skills.map((skill, index) =>
      '<span class="tag-x">' + esc(skill) +
      '<button type="button" data-remove-skill="' + index + '" aria-label="移除">✕</button></span>'
    ).join('');
  }

  function addSkill(value) {
    const name = value.trim();
    if (!name) return;
    if (state.skills.indexOf(name) !== -1) {
      showToast('该技能已添加', 1600);
      return;
    }
    if (state.skills.length >= 30) {
      showToast('技能标签最多 30 个', 1800);
      return;
    }
    state.skills.push(name);
    $('skillInput').value = '';
    renderSkillTags();
    refreshCompleteness();
  }

  function fillFormWith(resume) {
    resume = resume || {};
    const profile = state.me && state.me.profile;
    $('fName').value = resume.full_name || (profile && profile.name) || '';
    $('fPhone').value = resume.phone || '';
    $('fEmail').value = resume.email || '';
    $('fWechat').value = resume.wechat || '';
    $('fRole').value = resume.target_role || '';
    $('fDirection').value = resume.target_direction || '';
    $('fIndustry').value = resume.target_industry || '';
    $('fCity').value = resume.target_city || '';
    $('fIntro').value = resume.self_intro || '';
    state.skills = (resume.skills || []).slice();
    renderSkillTags();
    $('eduList').innerHTML = (resume.education && resume.education.length ? resume.education : [{}]).map(eduRowHtml).join('');
    $('projList').innerHTML = (resume.projects || []).map(projectRowHtml).join('');
    $('interList').innerHTML = (resume.internships || []).map(internRowHtml).join('');
    refreshCompleteness();
  }

  async function saveResume() {
    const resume = collectResume();
    if (!resume.target_role && !resume.self_intro && !resume.education.length &&
        !resume.projects.length && !resume.internships.length) {
      showToast('请至少填写求职意向、个人简介或一段经历', 3000);
      return;
    }
    const saveBtn = $('resumeSaveBtn');
    saveBtn.disabled = true;
    saveBtn.textContent = '保存中…';
    try {
      const data = await api('/api/resume', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(resume),
      });
      const skillsHtml = (data.resume_skills || []).map((skill) => '<span class="tag-x">' + esc(skill) + '</span>').join('');
      $('previewSkills').innerHTML = skillsHtml || '<p class="empty-hint">未识别到技能，可在描述中补充技术栈</p>';
      showToast('简历已保存，技能已更新，去机会速览看匹配结果');
      await refreshAll();
    } catch (err) {
      showToast('保存失败：' + err.message, 3200);
    } finally {
      saveBtn.disabled = false;
      saveBtn.textContent = '保存简历';
    }
  }

  /* ═══════════════════════════════════════════════
     简历上传解析 / AI 润色 / 导出
  ═══════════════════════════════════════════════ */
  const uploadModal = $('uploadModal');
  const polishModal = $('polishModal');
  let parsedResume = null;
  let polishChanges = [];

  function closeUploadModal() {
    uploadModal.classList.add('hidden');
    parsedResume = null;
  }

  function closePolishModal() {
    polishModal.classList.add('hidden');
    polishChanges = [];
  }

  function openUploadModal(filename) {
    $('uploadFileName').textContent = filename;
    $('uploadWarnings').innerHTML = '';
    $('uploadStats').innerHTML = '<p class="loading-hint">正在解析文件…</p>';
    $('uploadPreview').textContent = '';
    $('uploadApplyBtn').disabled = true;
    uploadModal.classList.remove('hidden');
  }

  function renderUploadResult(data) {
    const resume = data.resume || {};
    const profile = state.me && state.me.profile;
    $('uploadFileName').textContent = data.filename + ' · 解析完成';
    const warnings = data.warnings || [];
    $('uploadWarnings').innerHTML = warnings.length
      ? warnings.map((warn) => '<div class="warn-chip">⚠ ' + esc(warn) + '</div>').join('')
      : '';
    const stats = [
      ['姓名', resume.full_name || (profile && profile.name) || '未识别'],
      ['求职意向', resume.target_role || '未识别'],
      ['教育经历', (resume.education || []).length + ' 条'],
      ['项目经历', (resume.projects || []).length + ' 条'],
      ['实习经历', (resume.internships || []).length + ' 条'],
      ['技能标签', (resume.skills || []).length + ' 个'],
    ];
    $('uploadStats').innerHTML = stats.map((item) =>
      '<span class="parse-stat"><i>' + esc(item[0]) + '</i><b>' + esc(item[1]) + '</b></span>'
    ).join('');
    $('uploadPreview').textContent = data.preview || '未提取到可预览文本';
    parsedResume = resume;
    $('uploadApplyBtn').disabled = false;
  }

  async function handleResumeFile(file) {
    if (!file) return;
    openUploadModal(file.name);
    try {
      const form = new FormData();
      form.append('file', file);
      const data = await api('/api/resume/parse', { method: 'POST', body: form });
      renderUploadResult(data);
    } catch (err) {
      closeUploadModal();
      showToast('解析失败：' + err.message, 3600);
    }
  }

  function polishTitle(change) {
    const match = String(change.key || '').match(/^(project|intern)-(\d+)$/);
    if (change.key === 'intro') return '个人简介';
    if (!match) return '文字描述';
    const current = collectResume();
    const list = match[1] === 'project' ? current.projects : current.internships;
    const item = list[Number(match[2])] || {};
    const label = match[1] === 'project'
      ? (item.name || '项目经历')
      : ((item.company ? item.company + ' · ' : '') + (item.role || '实习经历'));
    return match[1] === 'project' ? '项目经历 · ' + label : '实习经历 · ' + label;
  }

  function polishItemHtml(change, index) {
    return '<article class="polish-item">' +
      '<div class="polish-top">' +
      '<label class="polish-toggle"><input type="checkbox" data-polish-toggle="' + index + '" checked /><span>采用</span></label>' +
      '<b>' + esc(polishTitle(change)) + '</b>' +
      '</div>' +
      '<p class="polish-reason">' + esc(change.reason || '让表达更专业') + '</p>' +
      '<div class="polish-compare">' +
      '<div class="polish-col"><span class="polish-col-label">原文</span><p>' + esc(change.original) + '</p></div>' +
      '<div class="polish-col"><span class="polish-col-label">润色后（可编辑）</span>' +
      '<textarea rows="4" data-polish-text="' + index + '">' + esc(change.polished) + '</textarea></div>' +
      '</div></article>';
  }

  function renderPolishResult(data) {
    polishChanges = data.changes || [];
    $('polishSource').textContent = data.source === 'deepseek' ? 'DeepSeek' : '离线引擎';
    $('polishNote').textContent = data.note || '';
    if (!polishChanges.length) {
      $('polishList').innerHTML = '<p class="loading-hint">' + esc(data.note || '暂无建议') + '</p>';
      $('polishApplyBtn').disabled = true;
      return;
    }
    $('polishList').innerHTML = polishChanges.map(polishItemHtml).join('');
    updatePolishApplyState();
  }

  function updatePolishApplyState() {
    const count = Array.prototype.filter.call(
      $('polishList').querySelectorAll('[data-polish-toggle]'),
      (box) => box.checked,
    ).length;
    const btn = $('polishApplyBtn');
    btn.disabled = count === 0;
    btn.textContent = count ? '应用所选 ' + count + ' 条并保存' : '应用所选并保存';
  }

  async function polishCurrentResume() {
    const resume = collectResume();
    if (!resume.self_intro && !resume.projects.length && !resume.internships.length) {
      showToast('请先补充自我介绍或项目 / 实习描述', 3000);
      return;
    }
    const btn = $('resumePolishBtn');
    btn.disabled = true;
    btn.textContent = '润色中…';
    $('polishSource').textContent = '生成中…';
    $('polishNote').textContent = '正在分析当前简历内容…';
    $('polishList').innerHTML = '<p class="loading-hint">AI 正在润色，通常需要几秒钟…</p>';
    $('polishApplyBtn').disabled = true;
    polishModal.classList.remove('hidden');
    try {
      const data = await api('/api/resume/polish', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(resume),
      });
      renderPolishResult(data);
    } catch (err) {
      $('polishList').innerHTML = '<p class="loading-hint">润色失败：' + esc(err.message) + '</p>';
      $('polishSource').textContent = '失败';
    } finally {
      btn.disabled = false;
      btn.textContent = 'AI 润色';
    }
  }

  function applyPolishValue(change, value) {
    if (change.key === 'intro') {
      $('fIntro').value = value;
      return;
    }
    const match = String(change.key || '').match(/^(project|intern)-(\d+)$/);
    if (!match) return;
    const containerId = match[1] === 'project' ? 'projList' : 'interList';
    const row = $(containerId).querySelectorAll('.row-card')[Number(match[2])];
    if (!row) return;
    const textarea = row.querySelector('[data-k="description"]');
    if (textarea) textarea.value = value;
  }

  async function applySelectedPolish() {
    const rows = $('polishList').querySelectorAll('.polish-item');
    rows.forEach((row) => {
      const index = Number(row.querySelector('[data-polish-toggle]').getAttribute('data-polish-toggle'));
      if (!row.querySelector('[data-polish-toggle]').checked) return;
      const change = polishChanges[index];
      const value = row.querySelector('[data-polish-text]').value.trim();
      if (change && value) applyPolishValue(change, value);
    });
    closePolishModal();
    await saveResume();
  }

  async function exportResume(format) {
    const resume = collectResume();
    if (!resume.target_role && !resume.self_intro && !resume.education.length &&
        !resume.projects.length && !resume.internships.length) {
      showToast('请先填写简历内容，再导出', 3000);
      return;
    }
    const trigger = document.querySelector('[data-export="' + format + '"]');
    const originalText = trigger ? trigger.textContent : '';
    if (trigger) {
      trigger.disabled = true;
      trigger.textContent = '正在导出…';
    }
    try {
      const res = await fetch('/api/resume/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ format: format, resume: resume }),
      });
      if (!res.ok) {
        let detail = '导出失败 (' + res.status + ')';
        try {
          const data = await res.json();
          if (data && data.detail) detail = data.detail;
        } catch (err) { /* ignore */ }
        throw new Error(detail);
      }
      const blob = await res.blob();
      const name = resume.full_name || (state.me && state.me.profile && state.me.profile.name) || '我的简历';
      const ext = format === 'pdf' ? 'pdf' : 'docx';
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = name + '-简历.' + ext;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 4000);
      showToast('简历已导出为 .' + ext);
    } catch (err) {
      showToast(err.message, 3600);
    } finally {
      if (trigger) {
        trigger.disabled = false;
        trigger.textContent = originalText || ('导出 ' + format.toUpperCase());
      }
      $('resumeExportDrop').classList.add('hidden');
    }
  }

  /* ═══════════════════════════════════════════════
     AI 求职助手（占位对话）
  ═══════════════════════════════════════════════ */
  const chatMessages = $('chatMessages');
  const chatInput = $('chatInput');
  const chatSend = $('chatSend');

  function scrollChatToBottom() {
    if (chatMessages) chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  function welcomeText() {
    return '你好，我是你的求职搭子「小航」👋\n\n' +
      '目前职航已打通：简历创建 → 岗位智能匹配 → 一键投递。\n' +
      '我（AI 问答 / 简历改写 / 模拟面试）将在后续版本接入，你可以先发条消息体验占位对话。';
  }

  function pushMessage(kind, text) {
    if (!chatMessages) return;
    const wrap = document.createElement('div');
    wrap.className = 'msg ' + (kind === 'user' ? 'msg-me' : 'msg-bot');
    const body = document.createElement('div');
    body.className = 'msg-body';
    body.textContent = text;
    wrap.appendChild(body);
    chatMessages.appendChild(wrap);
    scrollChatToBottom();
  }

  function sendMessage(rawText) {
    const text = (rawText || '').trim();
    if (!text || !chatInput) return;
    pushMessage('user', text);
    chatInput.value = '';
    chatInput.style.height = 'auto';
    chatSend.disabled = true;
    const preview = text.length > 36 ? text.slice(0, 36) + '…' : text;
    setTimeout(() => {
      pushMessage('bot', '已收到：' + preview + '\n\n这是框架占位回复。正式接入后，小航会结合你的简历与投递进度给出针对性建议（简历诊断 / 模拟面试 / 真题解析等）。');
    }, 600);
  }

  /* ═══════════════════════════════════════════════
     事件绑定与启动
  ═══════════════════════════════════════════════ */
  function bindStaticEvents() {
    document.addEventListener('click', (event) => {
      const trigger = event.target.closest('[data-toast]');
      if (trigger) showToast(trigger.getAttribute('data-toast'));
    });

    $('jobGrid').addEventListener('click', async (event) => {
      const favBtn = event.target.closest('[data-fav]');
      if (favBtn) { event.stopPropagation(); toggleFav(favBtn.getAttribute('data-id')); return; }
      const action = event.target.closest('[data-act]');
      if (!action) return;
      const id = action.getAttribute('data-id');
      if (action.getAttribute('data-act') === 'detail') openModal(id);
      if (action.getAttribute('data-act') === 'apply') await doApply(id);
    });

    $('recList').addEventListener('click', (event) => {
      const item = event.target.closest('.rec-item[data-job-id]');
      if (item) openModal(item.getAttribute('data-job-id'));
    });

    $('industryPills').addEventListener('click', (event) => {
      const pill = event.target.closest('[data-industry]');
      if (!pill) return;
      state.industryFilter = pill.getAttribute('data-industry');
      loadJobs();
    });

    const searchInput = $('jobSearch');
    $('jobSearchBtn').addEventListener('click', () => {
      state.jobQuery = searchInput.value.trim();
      loadJobs();
    });
    searchInput.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        state.jobQuery = searchInput.value.trim();
        loadJobs();
      }
    });

    $('mCloseBtn').addEventListener('click', closeModal);
    modal.addEventListener('click', (event) => {
      if (event.target === modal) closeModal();
    });
    $('mApplyBtn').addEventListener('click', async () => {
      if (state.currentModalJob) await doApply(state.currentModalJob.id);
    });
    $('mFavBtn').addEventListener('click', () => {
      if (!state.currentModalJob) return;
      toggleFav(state.currentModalJob.id);
      const faved = state.favs.has(state.currentModalJob.id);
      $('mFavBtn').textContent = faved ? '♥ 已收藏' : '♡ 收藏';
    });

    $('wbAppList').addEventListener('click', (event) => {
      const button = event.target.closest('[data-app-action]');
      if (!button) return;
      const id = button.getAttribute('data-id');
      if (button.getAttribute('data-app-action') === 'advance') advanceApplication(id);
      if (button.getAttribute('data-app-action') === 'withdraw') {
        if (window.confirm('确定撤回这条投递吗？')) withdrawApplication(id);
      }
    });

    $('wbTaskRefresh').addEventListener('click', async () => {
      showToast('任务已刷新');
      await refreshAll();
    });

    $('resumeSaveBtn').addEventListener('click', saveResume);
    $('resumeSampleBtn').addEventListener('click', () => {
      if (state.me && state.me.has_resume && !window.confirm('用示例数据覆盖当前简历草稿吗？')) return;
      fillFormWith(SAMPLE_RESUME);
      showToast('已填入示例，点击保存即可生效');
    });
    $('resumeUploadBtn').addEventListener('click', () => $('resumeUploadInput').click());
    $('resumeUploadInput').addEventListener('change', (event) => {
      handleResumeFile(event.target.files && event.target.files[0]);
      event.target.value = '';
    });
    $('uploadCloseBtn').addEventListener('click', closeUploadModal);
    $('uploadCancelBtn').addEventListener('click', closeUploadModal);
    $('uploadApplyBtn').addEventListener('click', () => {
      if (!parsedResume) return;
      fillFormWith(parsedResume);
      closeUploadModal();
      showToast('解析内容已应用到编辑器，请核对后保存');
    });
    uploadModal.addEventListener('click', (event) => {
      if (event.target === uploadModal) closeUploadModal();
    });

    $('resumePolishBtn').addEventListener('click', polishCurrentResume);
    $('polishCloseBtn').addEventListener('click', closePolishModal);
    $('polishCancelBtn').addEventListener('click', closePolishModal);
    $('polishApplyBtn').addEventListener('click', applySelectedPolish);
    polishModal.addEventListener('click', (event) => {
      if (event.target === polishModal) closePolishModal();
    });
    $('polishList').addEventListener('change', updatePolishApplyState);

    const exportBtn = $('resumeExportBtn');
    const exportDrop = $('resumeExportDrop');
    exportBtn.addEventListener('click', (event) => {
      event.stopPropagation();
      exportDrop.classList.toggle('hidden');
    });
    document.addEventListener('click', () => exportDrop.classList.add('hidden'));
    exportDrop.querySelectorAll('[data-export]').forEach((item) => {
      item.addEventListener('click', () => exportResume(item.getAttribute('data-export')));
    });

    const skillInput = $('skillInput');
    $('skillAddBtn').addEventListener('click', () => addSkill(skillInput.value));
    skillInput.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') { event.preventDefault(); addSkill(skillInput.value); }
    });
    document.addEventListener('click', (event) => {
      const remover = event.target.closest('[data-remove-skill]');
      if (remover) {
        state.skills.splice(Number(remover.getAttribute('data-remove-skill')), 1);
        renderSkillTags();
        refreshCompleteness();
      }
    });

    const adders = {
      edu: () => eduRowHtml(),
      project: () => projectRowHtml(),
      intern: () => internRowHtml(),
    };
    document.addEventListener('click', (event) => {
      const addBtn = event.target.closest('[data-add]');
      if (addBtn) {
        const key = addBtn.getAttribute('data-add');
        const targetId = { edu: 'eduList', project: 'projList', intern: 'interList' }[key];
        const container = $(targetId);
        if (container) container.insertAdjacentHTML('beforeend', adders[key]());
        refreshCompleteness();
        return;
      }
      const removeBtn = event.target.closest('[data-remove]');
      if (removeBtn) {
        const row = removeBtn.closest('.row-card');
        if (row) row.remove();
        refreshCompleteness();
      }
    });

    ['fRole', 'fDirection', 'fIndustry', 'fCity', 'fIntro'].forEach((id) => {
      $(id).addEventListener('input', refreshCompleteness);
    });
    ['eduList', 'projList', 'interList'].forEach((id) => {
      $(id).addEventListener('input', refreshCompleteness);
    });

    chatSend.addEventListener('click', () => sendMessage(chatInput.value));
    chatInput.addEventListener('input', () => {
      chatInput.style.height = 'auto';
      chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + 'px';
      chatSend.disabled = !chatInput.value.trim();
    });
    chatInput.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage(chatInput.value);
      }
    });
    document.querySelectorAll('.suggest-chip').forEach((chip) => {
      chip.addEventListener('click', () => sendMessage(chip.getAttribute('data-suggest')));
    });
    const clearChatBtn = document.querySelector('[data-action="clear-chat"]');
    if (clearChatBtn) {
      clearChatBtn.addEventListener('click', () => {
        chatMessages.innerHTML = '';
        pushMessage('bot', welcomeText());
        chatInput.focus();
      });
    }
  }

  async function boot() {
    bindStaticEvents();
    pushMessage('bot', welcomeText());
    activateView(viewFromHash());
    await refreshAll();
    await loadJobs();
    fillFormWith(state.me && state.me.resume ? state.me.resume : {});
  }

  document.addEventListener('DOMContentLoaded', boot);
})();

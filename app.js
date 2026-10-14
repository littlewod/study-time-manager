(() => {
  'use strict';

  const STORAGE_KEY = 'study_hub_progress_v2';
  const WEEKDAYS = ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六'];
  const initialToday = localDate(new Date());
  const state = {
    plan: window.STUDY_PLAN || null,
    progress: loadLocalProgress(),
    online: false,
    today: initialToday,
    selectedDate: initialToday,
    unfinishedOnly: false,
    pendingTaskIds: new Set(),
    errorTaskIds: new Set(),
    timer: {
      totalSec: 25 * 60,
      remainingSec: 25 * 60,
      running: false,
      endsAt: null,
      startedAt: null,
      taskId: null,
      taskTitle: null
    }
  };
  const el = id => document.getElementById(id);

  function localDate(date) {
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
  }

  function dateFromIso(value) {
    const [year, month, day] = value.split('-').map(Number);
    return new Date(year, month - 1, day);
  }

  function formatDateLabel(value, withYear = false) {
    const date = dateFromIso(value);
    const prefix = withYear ? `${date.getFullYear()}年` : '';
    return `${prefix}${date.getMonth() + 1}月${date.getDate()}日 ${WEEKDAYS[date.getDay()]}`;
  }

  function loadLocalProgress() {
    try {
      const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null');
      if (parsed && Array.isArray(parsed.completedTaskIds)) return normalizeProgress(parsed);
    } catch (_) {}
    return normalizeProgress({});
  }

  function normalizeProgress(value) {
    return {
      schemaVersion: 2,
      updatedAt: value?.updatedAt || null,
      completedTaskIds: Array.isArray(value?.completedTaskIds) ? value.completedTaskIds : [],
      notes: value?.notes && typeof value.notes === 'object' ? value.notes : {},
      focusSessions: Array.isArray(value?.focusSessions) ? value.focusSessions : []
    };
  }

  function saveLocalProgress() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state.progress));
  }

  async function api(path, options = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 2200);
    try {
      const response = await fetch(path, {
        ...options,
        signal: controller.signal,
        headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }
      });
      const body = await response.json().catch(() => null);
      if (!response.ok) throw new Error(body?.detail || `请求失败：${response.status}`);
      return body.data ?? body;
    } finally {
      clearTimeout(timeout);
    }
  }

  async function connect() {
    if (location.protocol === 'file:') {
      setOnline(false);
      return;
    }
    try {
      const pendingSessions = state.progress.focusSessions.filter(session => session.pendingSync);
      await api('/health');
      const [plan, progress] = await Promise.all([api('/api/v1/plan'), api('/api/v1/progress')]);
      state.plan = plan;
      state.progress = normalizeProgress(progress);
      for (let index = 0; index < pendingSessions.length; index += 1) {
        const session = pendingSessions[index];
        try {
          state.progress = normalizeProgress(await api('/api/v1/focus-sessions', {
            method: 'POST',
            body: JSON.stringify({
              taskId: session.taskId,
              date: session.date,
              startedAt: session.startedAt,
              endedAt: session.endedAt,
              durationSec: session.durationSec
            })
          }));
        } catch (error) {
          state.progress.focusSessions.push(...pendingSessions.slice(index));
          saveLocalProgress();
          throw error;
        }
      }
      saveLocalProgress();
      setOnline(true);
    } catch (_) {
      setOnline(false);
    }
  }

  function setOnline(online) {
    state.online = online;
    const pill = el('syncPill');
    pill.className = `sync-pill ${online ? 'online' : 'offline'}`;
    pill.textContent = online ? '桌面卡片已同步' : '离线本地模式';
  }

  function taskDone(taskId) {
    return state.progress.completedTaskIds.includes(taskId);
  }

  function allTaskIds() {
    return new Set((state.plan?.days || []).flatMap(day => day.tasks.map(task => task.id)));
  }

  function todayFocusSessions() {
    return state.progress.focusSessions.filter(session => session.date === state.today);
  }

  function focusedSecondsToday() {
    return todayFocusSessions().reduce((sum, session) => sum + Number(session.durationSec || 0), 0);
  }

  async function toggleTask(taskId, done) {
    if (state.pendingTaskIds.has(taskId)) return;
    const before = [...state.progress.completedTaskIds];
    const completed = new Set(before);
    done ? completed.add(taskId) : completed.delete(taskId);
    state.progress.completedTaskIds = [...completed].sort();
    state.progress.updatedAt = new Date().toISOString();
    state.pendingTaskIds.add(taskId);
    state.errorTaskIds.delete(taskId);
    saveLocalProgress();
    render();

    if (!state.online) {
      state.pendingTaskIds.delete(taskId);
      render();
      toast('已保存到当前浏览器');
      return;
    }

    try {
      state.progress = await api(`/api/v1/tasks/${encodeURIComponent(taskId)}`, {
        method: 'PATCH',
        body: JSON.stringify({ done })
      });
      state.pendingTaskIds.delete(taskId);
      saveLocalProgress();
      render();
      toast(done ? '完成一项，继续保持' : '已恢复为待完成');
    } catch (error) {
      state.progress.completedTaskIds = before;
      state.pendingTaskIds.delete(taskId);
      state.errorTaskIds.add(taskId);
      saveLocalProgress();
      setOnline(false);
      render();
      toast(error.message || '同步失败，已恢复原状态', true);
    }
  }

  function timerTask() {
    const day = selectedDay();
    return day?.tasks.find(task => !taskDone(task.id)) || null;
  }

  function formatTimer(seconds) {
    const safe = Math.max(0, Math.ceil(seconds));
    return `${String(Math.floor(safe / 60)).padStart(2, '0')}:${String(safe % 60).padStart(2, '0')}`;
  }

  function renderFocusTimer() {
    const timer = state.timer;
    const task = timer.taskTitle ? { title: timer.taskTitle } : timerTask();
    el('timerDisplay').textContent = formatTimer(timer.remainingSec);
    el('timerToggleButton').textContent = timer.running
      ? '暂停'
      : timer.remainingSec < timer.totalSec ? '继续专注' : '开始专注';
    el('timerFinishButton').disabled = timer.remainingSec >= timer.totalSec;
    el('focusTaskText').textContent = task
      ? `当前任务：${task.title}`
      : '当前日期没有待完成任务，可进行自由专注';
    document.querySelectorAll('[data-focus-minutes]').forEach(button => {
      const seconds = Number(button.dataset.focusMinutes) * 60;
      button.classList.toggle('active', seconds === timer.totalSec);
      button.disabled = timer.running || timer.remainingSec < timer.totalSec;
    });
    document.title = timer.running
      ? `${formatTimer(timer.remainingSec)} · 研途专注中`
      : '研途 · 学习时间管理';
  }

  function renderFocusSummary() {
    const sessions = todayFocusSessions();
    const focusedMinutes = Math.round(focusedSecondsToday() / 60);
    const todayPlan = state.plan?.days?.find(day => day.date === state.today);
    const plannedMinutes = todayPlan?.totalMinutes || 0;
    const ratio = plannedMinutes ? Math.round(focusedMinutes / plannedMinutes * 100) : 0;
    el('focusedMinutes').textContent = String(focusedMinutes);
    el('focusSessionCount').textContent = String(sessions.length);
    el('planActualRatio').textContent = `${ratio}%`;
  }

  function setFocusDuration(minutes) {
    if (state.timer.running || state.timer.remainingSec < state.timer.totalSec) return;
    state.timer.totalSec = minutes * 60;
    state.timer.remainingSec = minutes * 60;
    renderFocusTimer();
  }

  function toggleFocusTimer() {
    const timer = state.timer;
    if (timer.running) {
      timer.remainingSec = Math.max(0, Math.ceil((timer.endsAt - Date.now()) / 1000));
      timer.running = false;
      timer.endsAt = null;
      renderFocusTimer();
      return;
    }

    if (!timer.startedAt) {
      const task = timerTask();
      timer.startedAt = new Date().toISOString();
      timer.taskId = task?.id || null;
      timer.taskTitle = task?.title || null;
    }
    timer.running = true;
    timer.endsAt = Date.now() + timer.remainingSec * 1000;
    renderFocusTimer();
  }

  function resetFocusTimer() {
    state.timer.running = false;
    state.timer.remainingSec = state.timer.totalSec;
    state.timer.endsAt = null;
    state.timer.startedAt = null;
    state.timer.taskId = null;
    state.timer.taskTitle = null;
    renderFocusTimer();
  }

  async function saveFocusSession(session) {
    if (state.online) {
      try {
        state.progress = normalizeProgress(await api('/api/v1/focus-sessions', {
          method: 'POST',
          body: JSON.stringify(session)
        }));
        saveLocalProgress();
        renderFocusSummary();
        return;
      } catch (_) {
        setOnline(false);
      }
    }

    state.progress.focusSessions.push({
      ...session,
      id: `local-${Date.now()}`,
      pendingSync: true
    });
    state.progress.updatedAt = new Date().toISOString();
    saveLocalProgress();
    renderFocusSummary();
  }

  async function finishFocusTimer(completed = false) {
    const timer = state.timer;
    if (timer.running) {
      timer.remainingSec = Math.max(0, Math.ceil((timer.endsAt - Date.now()) / 1000));
      timer.running = false;
    }
    const durationSec = completed ? timer.totalSec : timer.totalSec - timer.remainingSec;
    if (durationSec < 60) {
      toast('专注满1分钟后才会记录');
      renderFocusTimer();
      return;
    }

    const endedAt = new Date();
    await saveFocusSession({
      taskId: timer.taskId,
      date: localDate(endedAt),
      startedAt: timer.startedAt || new Date(endedAt.getTime() - durationSec * 1000).toISOString(),
      endedAt: endedAt.toISOString(),
      durationSec
    });
    toast(completed ? '本轮专注完成，已记录' : `已记录 ${Math.round(durationSec / 60)} 分钟专注`);
    resetFocusTimer();
  }

  function tickFocusTimer() {
    const timer = state.timer;
    if (!timer.running) return;
    timer.remainingSec = Math.max(0, Math.ceil((timer.endsAt - Date.now()) / 1000));
    renderFocusTimer();
    if (timer.remainingSec === 0) {
      timer.running = false;
      finishFocusTimer(true);
    }
  }

  function percent(done, total) {
    return total ? Math.round(done / total * 100) : 0;
  }

  function selectedDay() {
    return state.plan?.days?.find(day => day.date === state.selectedDate) || null;
  }

  function currentWeek() {
    if (!state.plan) return null;
    return state.plan.weeks.find(week => week.start <= state.selectedDate && state.selectedDate <= week.end)
      || state.plan.weeks.find(week => week.start === state.plan.meta.planStart)
      || null;
  }

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>'"]/g, char => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
    })[char]);
  }

  function taskRow(task) {
    const done = taskDone(task.id);
    const pending = state.pendingTaskIds.has(task.id);
    const failed = state.errorTaskIds.has(task.id);
    const source = task.source
      ? `<p>来源：<a class="source-link" href="${escapeHtml(task.source.url)}" target="_blank" rel="noreferrer">${escapeHtml(task.source.label)} <span aria-hidden="true">↗</span></a></p>`
      : '';
    const inputId = `task-${task.id}`;
    return `<article class="task-row${done ? ' done' : ''}${pending ? ' syncing' : ''}${failed ? ' sync-error' : ''}" data-task-row="${escapeHtml(task.id)}">
      <label class="task-check-label" for="${escapeHtml(inputId)}">
        <input id="${escapeHtml(inputId)}" type="checkbox" data-task-id="${escapeHtml(task.id)}" ${done ? 'checked' : ''} ${pending ? 'disabled' : ''} aria-label="${done ? '取消完成' : '标记完成'}：${escapeHtml(task.title)}">
      </label>
      <p class="task-title">${escapeHtml(task.title)}</p>
      <span class="task-minutes">${task.durationMin} 分钟</span>
      <details class="task-detail">
        <summary>做法与完成标准</summary>
        <p>${escapeHtml(task.details)}</p>
        <p class="acceptance"><strong>完成标准：</strong>${escapeHtml(task.acceptance)}</p>
        ${source}
      </details>
    </article>`;
  }

  function taskGroup(category, tasks) {
    const visibleTasks = state.unfinishedOnly ? tasks.filter(task => !taskDone(task.id)) : tasks;
    if (!visibleTasks.length) return '';
    const done = tasks.filter(task => taskDone(task.id)).length;
    const pct = percent(done, tasks.length);
    return `<section class="task-group" data-category="${escapeHtml(category)}">
      <header class="task-group-header">
        <span class="category-dot" aria-hidden="true"></span>
        <h3>${escapeHtml(category)}</h3>
        <div class="group-progress" aria-label="${escapeHtml(category)}完成 ${done}/${tasks.length}">
          <span>${tasks.length - done} 项待完成</span>
          <span class="group-bar" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}"><i style="width:${pct}%"></i></span>
        </div>
      </header>
      <div class="task-list">${visibleTasks.map(taskRow).join('')}</div>
    </section>`;
  }

  function renderToday() {
    const day = selectedDay();
    const root = el('todayTasks');
    el('selectedDateLabel').textContent = formatDateLabel(state.selectedDate, true);
    el('backTodayButton').hidden = state.selectedDate === state.today;

    if (!day) {
      const beforePlan = state.selectedDate < state.plan.meta.planStart;
      el('todayFocus').textContent = beforePlan ? '当前计划尚未开始' : '当前计划周期已经结束';
      el('todayBudget').textContent = beforePlan ? `计划将于 ${state.plan.meta.planStart} 开始。` : '请进入“路线”查看下一阶段，或更新计划数据。';
      el('todayPercent').textContent = '—';
      el('todayCount').textContent = '无任务';
      el('remainingTasks').textContent = '0';
      el('remainingMinutes').textContent = '0';
      el('nextTaskText').textContent = '暂无';
      el('todayOrb').style.setProperty('--progress', '0deg');
      el('todayOrb').setAttribute('aria-valuenow', '0');
      el('continueButton').disabled = true;
      root.innerHTML = `<div class="empty-state">${beforePlan ? '现在可以先检查资料与环境，计划开始后会自动显示每日任务。' : '这一阶段已经完成。请用真实完成率生成下一阶段计划。'}</div>`;
      return;
    }

    const incomplete = day.tasks.filter(task => !taskDone(task.id));
    const done = day.tasks.length - incomplete.length;
    const pct = percent(done, day.tasks.length);
    const remainingMinutes = incomplete.reduce((sum, task) => sum + task.durationMin, 0);
    const nextTask = incomplete[0];
    el('todayFocus').textContent = day.focus;
    el('todayBudget').textContent = `${day.dayType === 'light' ? '轻量日' : '正常学习日'} · 计划 ${day.totalMinutes} 分钟`;
    el('todayPercent').textContent = `${pct}%`;
    el('todayCount').textContent = `${done}/${day.tasks.length}`;
    el('remainingTasks').textContent = String(incomplete.length);
    el('remainingMinutes').textContent = String(remainingMinutes);
    el('nextTaskText').textContent = nextTask ? `${nextTask.category} · ${nextTask.title}` : '今日任务已完成';
    el('todayOrb').style.setProperty('--progress', `${pct * 3.6}deg`);
    el('todayOrb').setAttribute('aria-valuenow', String(pct));
    el('continueButton').disabled = !nextTask;
    el('continueButton').textContent = nextTask ? '继续下一项' : '今日已完成';
    el('riskNotice').textContent = state.plan.meta.riskRules?.[0] || '根据真实完成率与专注时长调整任务量。';

    const groups = new Map();
    day.tasks.forEach(task => {
      if (!groups.has(task.category)) groups.set(task.category, []);
      groups.get(task.category).push(task);
    });
    const html = [...groups.entries()].map(([category, tasks]) => taskGroup(category, tasks)).join('');
    root.innerHTML = html || '<div class="empty-state">筛选条件下没有待完成任务。今天的任务已全部完成。</div>';
  }

  function renderWeek() {
    const week = currentWeek();
    if (!week) return;
    const days = state.plan.days.filter(day => week.start <= day.date && day.date <= week.end);
    const tasks = days.flatMap(day => day.tasks);
    const done = tasks.filter(task => taskDone(task.id)).length;
    const weekPct = percent(done, tasks.length);
    el('weekRange').textContent = `${formatDateLabel(week.start)} — ${formatDateLabel(week.end)}`;
    el('weekTitle').textContent = week.title;
    el('weekMetric').textContent = `${weekPct}%`;
    el('weekDoneCount').textContent = `${done}/${tasks.length} 项`;
    el('weekGoals').innerHTML = week.goals.map(goal => `<li>${escapeHtml(goal)}</li>`).join('');
    el('weekMilestone').textContent = `验收标准：${week.milestone}`;
    el('weekDays').innerHTML = days.map(day => {
      const dayDone = day.tasks.filter(task => taskDone(task.id)).length;
      const pct = percent(dayDone, day.tasks.length);
      const date = dateFromIso(day.date);
      return `<button type="button" class="day-card${day.date === state.today ? ' today' : ''}${day.date === state.selectedDate ? ' selected' : ''}" data-day-date="${day.date}" aria-label="查看 ${formatDateLabel(day.date)} 的任务">
        <header><h3>${date.getMonth() + 1}/${date.getDate()}<span class="weekday">${WEEKDAYS[date.getDay()]}</span></h3><strong>${pct}%</strong></header>
        <p>${escapeHtml(day.focus)}</p>
        <div class="mini-bar" role="progressbar" aria-label="当天完成进度" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}"><i style="width:${pct}%"></i></div>
        <footer>${dayDone}/${day.tasks.length} 项 · ${day.totalMinutes} 分钟</footer>
      </button>`;
    }).join('');
  }

  function renderRoadmap() {
    el('courseStatus').textContent = state.plan.meta.professionalCourseStatus || '用真实完成率和专注时长持续校准学习计划。';
    const reference = state.plan.evidence?.[0];
    el('officialCatalog').hidden = !reference;
    if (reference) {
      el('officialCatalog').href = reference.url;
      el('officialCatalog').firstChild.textContent = `${reference.label} `;
    }
    el('roadmapList').innerHTML = (state.plan.roadmap || []).map((item, index) => `<article class="roadmap-card">
      <time>阶段 ${String(index + 1).padStart(2, '0')} · ${escapeHtml(item.start)} — ${escapeHtml(item.end)}</time>
      <h3>${escapeHtml(item.title)}</h3>
      <p>${escapeHtml(item.detail)}</p>
    </article>`).join('');
  }

  function bindDynamicEvents() {
    document.querySelectorAll('[data-task-id]').forEach(input => {
      input.addEventListener('change', event => toggleTask(event.currentTarget.dataset.taskId, event.currentTarget.checked));
    });
    document.querySelectorAll('[data-day-date]').forEach(button => {
      button.addEventListener('click', () => {
        state.selectedDate = button.dataset.dayDate;
        switchView('today');
        render();
        window.scrollTo({ top: 0, behavior: 'smooth' });
      });
    });
  }

  function updateClock() {
    const now = new Date();
    el('clockText').textContent = now.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false });
    el('dateText').textContent = formatDateLabel(localDate(now));
  }

  function render() {
    if (!state.plan) return;
    updateClock();
    el('planChip').textContent = state.plan.meta.title || '学习计划';
    renderToday();
    renderWeek();
    renderRoadmap();
    renderFocusTimer();
    renderFocusSummary();
    bindDynamicEvents();
  }

  function switchView(view) {
    document.querySelectorAll('.tab').forEach(tab => {
      const active = tab.dataset.view === view;
      tab.classList.toggle('active', active);
      tab.setAttribute('aria-selected', String(active));
      tab.tabIndex = active ? 0 : -1;
    });
    ['today', 'week', 'roadmap'].forEach(name => {
      el(`${name}View`).hidden = name !== view;
    });
  }

  function toast(message, error = false) {
    const node = el('toast');
    node.textContent = message;
    node.className = `toast show${error ? ' error' : ''}`;
    node.setAttribute('role', error ? 'alert' : 'status');
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => { node.className = 'toast'; }, error ? 5200 : 2400);
  }

  function exportProgress() {
    const bundle = { schemaVersion: 2, exportedAt: new Date().toISOString(), planId: state.plan.meta.id, progress: state.progress };
    const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: 'application/json' });
    const anchor = document.createElement('a');
    anchor.href = URL.createObjectURL(blob);
    anchor.download = `学习进度_${state.today}.json`;
    anchor.click();
    URL.revokeObjectURL(anchor.href);
  }

  async function importProgress(file) {
    try {
      const parsed = JSON.parse(await file.text());
      const incoming = parsed.progress || parsed;
      if (!Array.isArray(incoming.completedTaskIds)) throw new Error('文件中没有有效的打卡数据。');
      const valid = allTaskIds();
      state.progress = normalizeProgress({
        schemaVersion: 2,
        updatedAt: new Date().toISOString(),
        completedTaskIds: [...new Set(incoming.completedTaskIds.filter(id => valid.has(id)))].sort(),
        notes: incoming.notes && typeof incoming.notes === 'object' ? incoming.notes : {},
        focusSessions: Array.isArray(incoming.focusSessions) ? incoming.focusSessions : []
      });
      saveLocalProgress();
      if (state.online) {
        state.progress = normalizeProgress(await api('/api/v1/progress', {
          method: 'PUT',
          body: JSON.stringify(state.progress)
        }));
      }
      render();
      toast('进度导入成功');
    } catch (error) {
      toast(error.message || '导入失败', true);
    }
  }

  async function poll() {
    if (state.online) {
      try {
        const progress = normalizeProgress(await api('/api/v1/progress'));
        const hasPendingSessions = state.progress.focusSessions.some(session => session.pendingSync);
        if (!hasPendingSessions && JSON.stringify(progress) !== JSON.stringify(state.progress)) {
          state.progress = progress;
          saveLocalProgress();
          render();
        }
      } catch (_) {
        setOnline(false);
      }
    } else if (location.protocol !== 'file:') {
      await connect();
      render();
    }
  }

  document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => switchView(tab.dataset.view));
    tab.addEventListener('keydown', event => {
      if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
      const tabs = [...document.querySelectorAll('.tab')];
      const direction = event.key === 'ArrowRight' ? 1 : -1;
      const next = tabs[(tabs.indexOf(tab) + direction + tabs.length) % tabs.length];
      next.focus();
      switchView(next.dataset.view);
    });
  });
  el('refreshButton').addEventListener('click', async () => {
    await connect();
    render();
    toast(state.online ? '计划与进度已刷新' : '当前为离线模式');
  });
  el('continueButton').addEventListener('click', () => {
    const next = document.querySelector('.task-row:not(.done)');
    if (next) {
      next.scrollIntoView({ behavior: 'smooth', block: 'center' });
      next.querySelector('input')?.focus({ preventScroll: true });
    }
  });
  el('backTodayButton').addEventListener('click', () => {
    state.selectedDate = state.today;
    render();
  });
  el('unfinishedOnly').addEventListener('change', event => {
    state.unfinishedOnly = event.currentTarget.checked;
    renderToday();
    bindDynamicEvents();
  });
  el('exportButton').addEventListener('click', exportProgress);
  el('importButton').addEventListener('click', () => el('importFile').click());
  el('importFile').addEventListener('change', event => {
    const file = event.target.files[0];
    if (file) importProgress(file);
    event.target.value = '';
  });
  document.querySelectorAll('[data-focus-minutes]').forEach(button => {
    button.addEventListener('click', () => setFocusDuration(Number(button.dataset.focusMinutes)));
  });
  el('timerToggleButton').addEventListener('click', toggleFocusTimer);
  el('timerFinishButton').addEventListener('click', () => finishFocusTimer(false));
  el('timerResetButton').addEventListener('click', resetFocusTimer);

  (async function init() {
    el('loadingView').setAttribute('aria-busy', 'true');
    await connect();
    if (!state.plan) {
      el('loadingView').removeAttribute('aria-busy');
      el('loadingView').innerHTML = '<div class="empty-state">未找到学习计划。请先运行桌面学习卡，它会自动创建示例计划。</div>';
      return;
    }
    el('loadingView').removeAttribute('aria-busy');
    el('loadingView').hidden = true;
    switchView('today');
    render();
    setInterval(poll, 5000);
    setInterval(tickFocusTimer, 250);
    setInterval(() => {
      const previousToday = state.today;
      const nextToday = localDate(new Date());
      if (nextToday !== previousToday) {
        state.today = nextToday;
        if (state.selectedDate === previousToday) state.selectedDate = nextToday;
        render();
      } else {
        updateClock();
      }
    }, 1000);
    if ('serviceWorker' in navigator && location.protocol.startsWith('http')) {
      navigator.serviceWorker.register('sw.js').catch(() => {});
    }
  })();
})();

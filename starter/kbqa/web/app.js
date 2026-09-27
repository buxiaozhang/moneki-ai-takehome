/* 经营看板 · 问答调试台
 *
 * 两条链路：
 *   - 发送问题 → POST /api/chat/stream（SSE），实时把规划/检索/工具/提示词画到右栏。
 *   - 刷新或点历史 → GET /api/trace/{trace_id}，用同一套渲染函数重放留档。
 * 两者走同一个 renderTrace 逻辑，所以"实时看到的"和"回看留档"不会长得不一样。
 */

'use strict';

const $ = (id) => document.getElementById(id);

const state = {
  health: null,
  catalog: null,
  streaming: false,
  currentSource: null, // 当前 SSE 连接，切换会话时用来收尾
  dash: null,          // 最近一次看板数据
  charts: [],          // 当前活着的图表句柄，切换筛选前要销毁
  drillStore: null,    // 图表联动选中的门店
  drillDate: null,     // 选中的日期
};

/* ---------- 工具 ---------- */

function esc(text) {
  return String(text == null ? '' : text)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function fmtNum(value, digits = 2) {
  if (value === null || value === undefined) return '—';
  const num = Number(value);
  if (!isFinite(num)) return '—';
  return num.toLocaleString('zh-CN', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function fmtMs(ms) {
  if (ms === null || ms === undefined) return '';
  return ms >= 1000 ? (ms / 1000).toFixed(2) + 's' : Math.round(ms) + 'ms';
}

async function getJSON(url, options) {
  const response = await fetch(url, options);
  const text = await response.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = { raw: text }; }
  if (!response.ok) throw new Error((data && data.error) || ('HTTP ' + response.status));
  return data;
}

/* ---------- 顶部状态 ---------- */

async function loadHealth() {
  try {
    const health = await getJSON('/api/health');
    state.health = health;
    const llm = health.llm || {};
    const live = health.llm_mode === 'live';

    $('health-dot').className = 'dot ' + (live ? 'ok' : 'bad');
    $('status').textContent = live
      ? `live · ${llm.model || '?'} · 文档 ${health.kb_docs} · 有效行 ${health.valid_sales_rows}`
      : `mock（未配 Key） · 文档 ${health.kb_docs} · 有效行 ${health.valid_sales_rows}`;

    // mock 时把"缺哪几个变量、怎么修"直接摆在顶栏下面，
    // 省得看着 mock 到处找原因（服务端只在启动时读一次配置，改了要重启）。
    const banner = $('llm-banner');
    if (live) {
      banner.hidden = true;
    } else {
      banner.hidden = false;
      const missing = (llm.missing || []).join('、') || '（未知）';
      banner.innerHTML =
        `<strong>当前是 mock 模式，问答走模板而不是真实模型。</strong><br>` +
        `缺少：<code>${esc(missing)}</code><br>` +
        `${esc(llm.hint || '')}` +
        (llm.dotenv
          ? `<br>已读到 <code>${esc(llm.dotenv)}</code>` +
            (llm.api_key_set === false ? '，但里面的 KEY 是空的' : '')
          : '');
    }
  } catch (error) {
    $('health-dot').className = 'dot bad';
    $('status').textContent = '服务不可用：' + error.message;
  }
}

async function loadCatalog() {
  const catalog = await getJSON('/api/debug/catalog');
  state.catalog = catalog;
  catalog.stores.forEach((store) => {
    const option = document.createElement('option');
    option.value = store.store_id;
    option.textContent = `${store.store_id} ${store.store_name}`;
    $('d-store').appendChild(option);
  });
  catalog.products.forEach((product) => {
    const option = document.createElement('option');
    option.value = product.product_id;
    option.textContent = `${product.product_id} ${product.product_name}`;
    $('d-product').appendChild(option);
  });
  if (catalog.data_period && catalog.data_period.start) {
    $('d-start').value = catalog.data_period.start;
    $('d-end').value = catalog.data_period.end;
    buildQuickRanges(catalog.data_period);
  }
}

/** 常用区间快捷键：整段 / 最近 7 天 / 按月。 */
function buildQuickRanges(period) {
  const box = $('dash-quick');
  const ranges = [['全部', period.start, period.end]];
  const end = new Date(period.end + 'T00:00:00');
  const weekAgo = new Date(end);
  weekAgo.setDate(weekAgo.getDate() - 6);
  ranges.push(['最近 7 天', weekAgo.toISOString().slice(0, 10), period.end]);
  // 数据里出现过的月份，各来一个。
  const months = new Set();
  const cursor = new Date(period.start + 'T00:00:00');
  const last = new Date(period.end + 'T00:00:00');
  while (cursor <= last) {
    months.add(cursor.toISOString().slice(0, 7));
    cursor.setMonth(cursor.getMonth() + 1);
  }
  Array.from(months).forEach((month) => {
    const [year, mon] = month.split('-').map(Number);
    const first = `${month}-01`;
    const lastDay = new Date(year, mon, 0).getDate();
    ranges.push([`${mon} 月`, first, `${month}-${String(lastDay).padStart(2, '0')}`]);
  });

  box.innerHTML = '';
  ranges.forEach(([label, start, end2]) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'chip';
    button.textContent = label;
    button.addEventListener('click', () => {
      $('d-start').value = start;
      $('d-end').value = end2;
      loadDashboard();
    });
    box.appendChild(button);
  });
}

/* ---------- 对话 ---------- */

function addUserMessage(text) {
  const wrap = document.createElement('div');
  wrap.className = 'msg msg-user';
  wrap.innerHTML = `<div class="bubble">${esc(text)}</div>`;
  $('messages').appendChild(wrap);
  scrollMessages();
}

function addAIMessage() {
  const wrap = document.createElement('div');
  wrap.className = 'msg msg-ai';
  wrap.innerHTML = `
    <div class="bubble streaming"></div>
    <div class="msg-meta"></div>
    <div class="extras"></div>`;
  $('messages').appendChild(wrap);
  scrollMessages();
  return wrap;
}

function scrollMessages() {
  const box = $('messages');
  box.scrollTop = box.scrollHeight;
}

/** 把一次响应的 payload 画进气泡（流式结束时与历史回放共用）。 */
function renderAnswer(wrap, payload) {
  const bubble = wrap.querySelector('.bubble');
  bubble.classList.remove('streaming');
  bubble.textContent = payload.answer || '（空回答）';

  const meta = wrap.querySelector('.msg-meta');
  meta.innerHTML = '';
  const type = payload.answer_type || 'unknown';
  meta.insertAdjacentHTML('beforeend', `<span class="badge ${esc(type)}">${esc(type)}</span>`);
  if (payload.trace_id) {
    meta.insertAdjacentHTML('beforeend', `<span class="badge">${esc(payload.trace_id)}</span>`);
  }
  if (payload.elapsed_ms) {
    meta.insertAdjacentHTML('beforeend', `<span class="badge">${fmtMs(payload.elapsed_ms)}</span>`);
  }

  const extras = wrap.querySelector('.extras');
  extras.innerHTML = '';

  (payload.citations || []).forEach((citation) => {
    const node = document.createElement('details');
    node.className = 'citation';
    node.innerHTML =
      `<summary>引用 <span class="cite-link">${esc(citation.doc_id)}</span></summary>
       <pre class="quote">${esc(citation.quote)}</pre>`;
    node.querySelector('.cite-link').addEventListener('click', (event) => {
      event.preventDefault();
      openDoc(citation.doc_id, citation.quote);
    });
    extras.appendChild(node);
  });

  (payload.data_evidence || []).forEach((item) => {
    const node = document.createElement('details');
    node.className = 'evidence';
    const label = item.tool ? `data_evidence · ${item.tool}` : 'data_evidence · sql';
    node.innerHTML = `<summary>${esc(label)}</summary>
      <pre>${esc(JSON.stringify(item, null, 2))}</pre>`;
    extras.appendChild(node);
  });

  scrollMessages();
}

/* ---------- 追踪渲染 ---------- */

const STEP_LABELS = {
  plan: '规划',
  search: '检索',
  tool: '工具调用',
  tool_arguments_invalid: '工具参数解析失败',
  answer_mock: '模板作答',
  answer_live: '模型作答',
  answer_live_failed: '模型作答失败',
  number_check_failed: '数字校验失败',
  response: '返回',
};

function stepTitle(step) {
  if (step.step === 'tool') {
    const tool = (step.detail && step.detail.tool) || '?';
    return `工具调用 · ${tool}`;
  }
  return STEP_LABELS[step.step] || step.step;
}

function stepBody(step) {
  const detail = step.detail || {};
  if (step.step === 'plan') {
    const lines = [];
    if (detail.intent) lines.push(`intent: ${detail.intent}`);
    if (detail.kind) lines.push(`kind: ${detail.kind}`);
    if (detail.search_query) lines.push(`检索词: ${detail.search_query}`);
    if (detail.window) lines.push(`区间: ${detail.window[0]} ~ ${detail.window[1]}`);
    if (detail.store_id) lines.push(`门店: ${detail.store_id}`);
    if (detail.product_id) lines.push(`商品: ${detail.product_id}`);
    if (detail.standalone_question) lines.push(`完整问题: ${detail.standalone_question}`);
    return lines.join('\n');
  }
  if (step.step === 'search') {
    const lines = [];
    if (detail.query) lines.push(`检索词: ${detail.query}`);
    if (detail.coverage !== undefined) lines.push(`覆盖率: ${detail.coverage}`);
    if (detail.expansions && detail.expansions.length) {
      lines.push(`别名扩展: ${detail.expansions.slice(0, 6).join('、')}`);
    }
    // 命中与过滤明细由 renderHits / renderFiltered 单独画，这里不重复。
    return lines.join('\n');
  }
  if (step.step === 'tool' || step.step === 'tool_arguments_invalid') {
    return JSON.stringify(detail.params || detail, null, 2);
  }
  if (step.step === 'response') {
    return `answer_type: ${detail.answer_type || '?'}` +
      (detail.notes && detail.notes.length ? `\nnotes: ${detail.notes.join('；')}` : '');
  }
  return Object.keys(detail).length ? JSON.stringify(detail, null, 2) : '';
}

/**
 * 检索结果画成"分数条 + 是否采纳"，比一串 score= 数字好读得多。
 * 补位片段（padded）不成作答依据，单独灰掉。
 */
function renderHits(detail) {
  const hits = detail.hits || [];
  if (!hits.length) return '';
  const max = Math.max(...hits.map((hit) => Number(hit.score) || 0), 0.0001);
  const rows = hits.map((hit, index) => {
    const pct = Math.max(2, (Number(hit.score) || 0) / max * 100);
    const cls = hit.padded ? 'hit padded' : 'hit';
    return `<div class="${cls}">
      <span class="hit-rank">${index + 1}</span>
      <span class="hit-doc cite-link" data-doc="${esc(hit.doc_id)}">${esc(hit.doc_id)}</span>
      <span class="hit-chunk">${esc(hit.chunk_id || '')}</span>
      <span class="hit-bar"><i style="width:${pct.toFixed(1)}%"></i></span>
      <span class="hit-score">${Number(hit.score).toFixed(3)}</span>
      ${hit.padded ? '<span class="hit-flag">补位</span>' : ''}
    </div>`;
  }).join('');
  return `<div class="hits">${rows}</div>`;
}

function renderFiltered(detail) {
  const filtered = detail.filtered || [];
  if (!filtered.length) return '';
  return `<div class="filtered"><div class="filtered-head">被过滤 ${filtered.length} 份</div>` +
    filtered.map((item) =>
      `<div class="filtered-row"><span class="cite-link" data-doc="${esc(item.doc_id)}">${esc(item.doc_id)}</span>
        <span class="filtered-reason">${esc(item.reason)}</span></div>`).join('') + '</div>';
}

function appendStep(step) {
  const box = $('trace');
  if (box.querySelector('.empty')) box.innerHTML = '';
  state.traceSteps = state.traceSteps || [];
  state.traceSteps.push(step);

  const node = document.createElement('div');
  node.className = 'step';
  node.dataset.step = step.step || '';
  const body = stepBody(step);
  let extra = '';
  if (step.step === 'search') extra = renderHits(step.detail || {}) + renderFiltered(step.detail || {});
  node.innerHTML = `
    <div class="step-head">
      <span class="step-name">${esc(stepTitle(step))}</span>
      <span class="step-ms">${fmtMs(step.took_ms)}</span>
    </div>
    ${body ? `<div class="step-detail">${esc(body)}</div>` : ''}
    ${extra}`;
  node.querySelectorAll('.cite-link').forEach((link) => {
    link.addEventListener('click', () => openDoc(link.dataset.doc));
  });
  box.appendChild(node);
  box.scrollTop = box.scrollHeight;
  return node;
}

function appendLLM(call) {
  const box = $('trace');
  if (box.querySelector('.empty')) box.innerHTML = '';
  const node = document.createElement('div');
  node.className = 'step' + (call.error ? ' error' : ' done');
  const lines = [];
  lines.push(`model: ${call.model || '?'}`);
  lines.push(`endpoint: ${call.endpoint || '?'}`);
  if (call.finish_reason) lines.push(`finish_reason: ${call.finish_reason}`);
  if (call.tool_calls && call.tool_calls.length) lines.push(`tool_calls: ${call.tool_calls.join('、')}`);
  if (call.has_reasoning) lines.push('reasoning_content: 有（不展示给用户）');
  if (call.content_chars !== undefined) lines.push(`content: ${call.content_chars} 字`);
  if (call.error) lines.push(`错误: ${call.error}`);
  node.innerHTML = `
    <div class="step-head">
      <span class="step-name">模型调用</span>
      <span class="step-ms">${fmtMs(call.took_ms)}</span>
    </div>
    <div class="step-detail">${esc(lines.join('\n'))}</div>
    ${call.prompt ? `<details class="citation"><summary>发给模型的请求</summary>
        <pre>${esc(call.prompt)}</pre></details>` : ''}
    ${call.raw_content ? `<details class="citation"><summary>模型原始输出</summary>
        <pre>${esc(call.raw_content)}</pre></details>` : ''}`;
  box.appendChild(node);
  box.scrollTop = box.scrollHeight;
}

function appendError(event) {
  const box = $('trace');
  if (box.querySelector('.empty')) box.innerHTML = '';
  const node = document.createElement('div');
  node.className = 'step error';
  node.innerHTML = `
    <div class="step-head"><span class="step-name">错误 · ${esc(event.where || '')}</span></div>
    <div class="step-detail">${esc((event.error_type || '') + ': ' + (event.message || ''))}</div>`;
  box.appendChild(node);
  box.scrollTop = box.scrollHeight;
}

function resetTrace(traceId) {
  $('trace').innerHTML = '<div class="empty">处理中…</div>';
  $('trace-id-label').textContent = traceId || '—';
  $('trace-summary').hidden = true;
  $('trace-summary').innerHTML = '';
  state.traceSteps = [];
}

/**
 * 顶部耗时条：把各步骤画成横向条形，一眼看出时间花在哪。
 *
 * `took_ms` 是各步骤自己的耗时，不是串行时间轴上的绝对位置 —— trace 里没有
 * 记录步骤起止时刻，所以这里画的是"相对占比"而不是甘特图。标题也照实写，
 * 免得看的人以为是严格的时间轴。
 */
function renderTraceSummary(steps, totalMs) {
  const box = $('trace-summary');
  const timed = (steps || []).filter((step) => Number(step.took_ms) > 0);
  const sum = timed.reduce((acc, step) => acc + Number(step.took_ms), 0);
  if (!timed.length) { box.hidden = true; return; }

  const bars = timed.map((step) => {
    const pct = sum ? (Number(step.took_ms) / sum) * 100 : 0;
    return `<div class="gantt-row">
      <span class="gantt-name">${esc(stepTitle(step))}</span>
      <span class="gantt-track"><i class="gantt-bar" style="width:${pct.toFixed(1)}%"></i></span>
      <span class="gantt-ms">${fmtMs(step.took_ms)}</span>
    </div>`;
  }).join('');

  box.hidden = false;
  box.innerHTML =
    `<div class="gantt-head">耗时构成 <span class="muted">各步骤耗时之和 ${fmtMs(sum)}` +
    (totalMs ? ` · 端到端 ${fmtMs(totalMs)}` : '') + `</span></div>` + bars;
}

/** 用留档重放一遍（历史点击）。 */
function renderTraceFromStore(trace) {
  resetTrace(trace.trace_id);
  (trace.steps || []).forEach(appendStep);
  (trace.llm_calls || []).forEach(appendLLM);
  (trace.errors || []).forEach((item) =>
    appendError({ where: item.where, error_type: item.type, message: item.message }));
  renderTraceSummary(state.traceSteps, trace.total_ms);
  $('trace-id-label').textContent = `${trace.trace_id} · 共 ${fmtMs(trace.total_ms)}`;
}

/* ---------- 发送 ---------- */

async function sendQuestion(question) {
  if (!question.trim() || state.streaming) return;
  const sessionId = $('session-id').value.trim() || 'debug-1';
  const useStream = $('use-stream').checked;

  addUserMessage(question);
  const wrap = addAIMessage();
  const bubble = wrap.querySelector('.bubble');
  $('send').disabled = true;
  state.streaming = true;

  const started = performance.now();
  let payload = null;

  try {
    if (useStream) {
      payload = await sendStreaming(sessionId, question, bubble);
    } else {
      payload = await getJSON('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, question }),
      });
      resetTrace(payload.trace_id);
      const trace = await getJSON('/api/trace/' + encodeURIComponent(payload.trace_id));
      renderTraceFromStore(trace);
    }
  } catch (error) {
    bubble.classList.remove('streaming');
    bubble.textContent = '请求失败：' + error.message;
    appendError({ where: 'frontend', error_type: 'Error', message: error.message });
    finishSend();
    return;
  }

  payload.elapsed_ms = Math.round(performance.now() - started);
  renderAnswer(wrap, payload);
  finishSend();
  loadHistory();
}

async function sendStreaming(sessionId, question, bubble) {
  const response = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, question }),
  });
  if (!response.ok || !response.body) {
    throw new Error('HTTP ' + response.status);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';
  let payload = null;

  resetTrace(null);

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE 以空行分帧；注释行（: keep-alive）直接跳过。
    let boundary;
    while ((boundary = buffer.indexOf('\n\n')) !== -1) {
      const frame = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const parsed = parseFrame(frame);
      if (!parsed) continue;

      if (parsed.event === 'step') {
        appendStep(parsed.data);
      } else if (parsed.event === 'llm') {
        appendLLM(parsed.data);
      } else if (parsed.event === 'error') {
        appendError(parsed.data);
      } else if (parsed.event === 'start') {
        $('trace-id-label').textContent = parsed.data.trace_id;
      } else if (parsed.event === 'final') {
        payload = parsed.data.payload;
        renderTraceSummary(state.traceSteps, null);
      }
    }
  }

  if (!payload) throw new Error('流结束但没有收到最终结果');
  // 流式过程中先把答案显示出来，逐字出现的观感留到有 delta 时再用。
  bubble.textContent = payload.answer || '';
  return payload;
}

function parseFrame(frame) {
  let event = 'message';
  const dataLines = [];
  for (const line of frame.split('\n')) {
    if (line.startsWith(':')) continue;
    if (line.startsWith('event:')) event = line.slice(6).trim();
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
  }
  if (!dataLines.length) return null;
  try {
    return { event, data: JSON.parse(dataLines.join('\n')) };
  } catch {
    return null;
  }
}

function finishSend() {
  state.streaming = false;
  $('send').disabled = false;
}

/* ---------- 历史 ---------- */

async function loadHistory() {
  try {
    const data = await getJSON('/api/traces?limit=30');
    const box = $('history');
    if (!data.traces.length) {
      box.innerHTML = '<div class="empty">暂无记录</div>';
      return;
    }
    box.innerHTML = '';
    data.traces.forEach((trace) => {
      const node = document.createElement('div');
      node.className = 'history-item';
      node.innerHTML = `
        <div class="history-q">${esc(trace.question || '（空）')}</div>
        <div class="history-m">${esc(trace.answer_type || '?')} · ${fmtMs(trace.total_ms)} ·
          ${trace.llm_calls} 次模型调用${trace.errors ? ' · ' + trace.errors + ' 个错误' : ''}</div>`;
      node.addEventListener('click', async () => {
        const full = await getJSON('/api/trace/' + encodeURIComponent(trace.trace_id));
        renderTraceFromStore(full);
      });
      box.appendChild(node);
    });
  } catch { /* 历史只是辅助，失败不影响主流程 */ }
}

/* ---------- 索引 ---------- */

async function loadIndex() {
  const data = await getJSON('/api/debug/index');
  $('index-meta').textContent =
    `${data.doc_count} 份文档 / ${data.chunk_count} 个片段 · key ${data.index_key}`;

  const warnings = $('index-warnings');
  warnings.innerHTML = '';
  if (data.warnings && data.warnings.length) {
    const box = document.createElement('div');
    box.className = 'warn-box';
    box.textContent = '装载告警：\n' + data.warnings.join('\n');
    warnings.appendChild(box);
  }

  const tbody = $('index-table').querySelector('tbody');
  tbody.innerHTML = '';
  const expected = data.doc_count + (data.warnings || []).length;
  data.docs.forEach((doc) => {
    const row = document.createElement('tr');
    const stale = doc.status === '已废止';
    if (stale) row.className = 'dim';
    row.innerHTML = `
      <td><span class="cite-link">${esc(doc.doc_id)}</span></td>
      <td>${esc(doc.title || '')}</td>
      <td>${esc(doc.type || '')}</td>
      <td>${esc(doc.status || '')}</td>
      <td>${esc(doc.effective_from || '—')}</td>
      <td>${esc(doc.superseded_by || '—')}</td>
      <td class="num">${doc.chunks}</td>
      <td class="num">${doc.chars}</td>
      <td>${esc(doc.format || '')}</td>`;
    row.querySelector('.cite-link').addEventListener('click', () => openDoc(doc.doc_id));
    tbody.appendChild(row);
  });
  $('index-meta').textContent += `（含告警跳过 ${expected - data.doc_count} 个文件）`;
}

/* ---------- 经营看板 ---------- */

const SEVERITY_LABELS = { high: '高', warn: '注意', info: '提示' };
const SEVERITY_ORDER = { high: 0, warn: 1, info: 2 };

function destroyCharts() {
  state.charts.forEach((chart) => chart.destroy());
  state.charts = [];
}

function dashParams(extra) {
  const params = new URLSearchParams({
    start: $('d-start').value,
    end: $('d-end').value,
    top_limit: $('d-top').value || '10',
  });
  if ($('d-store').value) params.set('store_id', $('d-store').value);
  if ($('d-product').value) params.set('product_id', $('d-product').value);
  Object.entries(extra || {}).forEach(([key, value]) => params.set(key, value));
  return params;
}

async function loadDashboard(event) {
  if (event) event.preventDefault();
  destroyCharts();
  state.drillStore = null;
  state.drillDate = null;

  const data = await getJSON('/api/ui/dashboard?' + dashParams());
  state.dash = data;

  const scope = [
    `$($('d-store').value || '全部门店')`,
    `$($('d-product').value || '全部商品')`,
    `${data.start} ~ ${data.end}`,
  ].join(' · ');
  $('dash-meta').textContent = scope;

  renderCards(data);
  renderAlerts(data);
  renderTrend(data);
  renderStoreCompare(data);
  renderTopProducts(data);
  renderQualityMini(data);
  renderDailyTable(data);
}

function renderCards(data) {
  const summary = data.summary || {};
  const counts = data.anomaly_counts || {};
  const flagged = (counts.high || 0) + (counts.warn || 0);
  const items = [
    ['净营业额', fmtNum(summary.net_revenue) + ' 元', 'ok'],
    ['退款金额', fmtNum(summary.refund_amount) + ' 元', summary.refund_amount > 0 ? 'warn' : ''],
    ['有效订单数', String(summary.orders ?? '—'), ''],
    ['客单价', summary.aov === null || summary.aov === undefined ? 'null' : fmtNum(summary.aov) + ' 元', ''],
    ['销量', String(summary.qty ?? '—'), ''],
    ['异常日', flagged ? `${flagged} 天` : '无', flagged ? 'warn' : 'ok'],
  ];
  $('dash-cards').innerHTML = items.map(([label, value, cls]) =>
    `<div class="card ${cls}"><div class="label">${label}</div><div class="value">${esc(value)}</div></div>`
  ).join('');
}

function renderAlerts(data) {
  const box = $('dash-alerts');
  const items = [];
  (data.period_warnings || []).forEach((w) => items.push({ ...w, date: null }));
  (data.anomalies || []).forEach((a) => items.push(a));

  if (!items.length) {
    box.innerHTML = `<div class="alert-box ok">未发现异常：所选区间内没有零营业额、显著低于均值或环比骤降的日子。</div>`;
    return;
  }

  items.sort((a, b) => (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9)
    || String(a.date || '').localeCompare(String(b.date || '')));

  const params = data.anomaly_params || {};
  box.innerHTML =
    `<div class="alert-head">异常预警 <span class="muted">规则：零营业额 · 连续 ${2} 天以上零营业额 · ` +
    `低于均值 − ${params.z ?? 2}σ · 环比降幅 ≥ ${Math.round((params.drop_ratio ?? 0.5) * 100)}%</span></div>` +
    `<div class="alert-list">` + items.map((item) => {
      const date = item.date ? (item.end_date && item.end_date !== item.date
        ? `${item.date} ~ ${item.end_date}` : item.date) : '';
      return `<div class="alert alert-${esc(item.severity)}">
        <span class="alert-tag">${esc(SEVERITY_LABELS[item.severity] || item.severity)}</span>
        <span class="alert-label">${esc(item.label)}</span>
        ${date ? `<button class="alert-date cite-link" data-date="${esc(item.date)}">${esc(date)}</button>` : ''}
        <span class="alert-detail">${esc(item.detail)}</span>
      </div>`;
    }).join('') + '</div>';

  box.querySelectorAll('.alert-date').forEach((button) => {
    button.addEventListener('click', () => {
      state.drillDate = button.dataset.date;
      renderTrend(state.dash);
      highlightDaily(state.drillDate);
    });
  });
}

function renderTrend(data) {
  const old = state.charts.find((chart) => chart.id === 'trend');
  if (old) { old.destroy(); state.charts = state.charts.filter((c) => c !== old); }
  const container = $('trend-chart');
  container.innerHTML = '';
  const chart = window.Charts.renderTrendChart(container, data.days, {
    selectedDate: state.drillDate,
    onSelect(day) {
      state.drillDate = day ? day.date : null;
      highlightDaily(state.drillDate);
      const meta = $('daily-meta');
      meta.textContent = day ? `已选中 ${day.date}` : '—';
    },
  });
  chart.id = 'trend';
  state.charts.push(chart);

  const counts = data.anomaly_counts || {};
  $('trend-title').textContent =
    `营业额趋势（${data.days.length} 天${counts.high ? ` · ${counts.high} 天高优先级异常` : ''}）`;
  $('trend-legend').innerHTML =
    `<span class="lg"><i class="sw sw-bar"></i>净营业额</span>` +
    `<span class="lg"><i class="sw sw-high"></i>高优先级异常</span>` +
    `<span class="lg"><i class="sw sw-warn"></i>注意</span>` +
    `<span class="lg"><i class="sw sw-zero"></i>零营业额</span>`;
}

function renderStoreCompare(data) {
  const old = state.charts.find((chart) => chart.id === 'store');
  if (old) { old.destroy(); state.charts = state.charts.filter((c) => c !== old); }
  const container = $('store-chart');
  container.innerHTML = '';

  // 已经选了某家门店时，`by_store` 为空，改用该店的逐日数据画支付构成。
  if (!data.by_store || !data.by_store.length) {
    const rows = Object.entries(data.payments || {}).map(([label, info]) => ({
      label, value: info.net_revenue, sub: `${info.orders} 单`,
      extra: `订单占比 ${(info.share_orders * 100).toFixed(1)}%`,
    }));
    $('store-hint').textContent = '该门店的支付方式构成';
    const chart = window.Charts.renderBarChart(container, rows, { valueLabel: '净营业额' });
    chart.id = 'store';
    state.charts.push(chart);
    return;
  }

  $('store-hint').textContent = '点击某家门店下钻';
  const items = data.by_store.map((store) => ({
    id: store.store_id,
    label: `${store.store_id} ${store.store_name}`,
    sub: `${store.orders} 单 · 客单价 ${store.aov === null ? '—' : store.aov}`,
    value: store.net_revenue,
  }));
  const chart = window.Charts.renderBarChart(container, items, {
    valueLabel: '净营业额',
    selectedId: state.drillStore,
    onSelect(id) {
      state.drillStore = id;
      if (id) {
        $('d-store').value = id;
        loadDashboard();
      }
    },
  });
  chart.id = 'store';
  state.charts.push(chart);
}

function renderTopProducts(data) {
  const rows = data.top_products || [];
  const total = Number((data.summary || {}).net_revenue) || 0;
  const tbody = $('top-table').querySelector('tbody');
  tbody.innerHTML = '';
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="7" class="empty">没有数据</td></tr>';
    return;
  }
  const max = Math.max(...rows.map((row) => Number(row.net_revenue) || 0), 1);
  rows.forEach((row, index) => {
    const share = total ? (Number(row.net_revenue) / total) * 100 : 0;
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td class="num">${index + 1}</td>
      <td>${esc(row.product_name || row.product_id)}</td>
      <td>${esc(row.product_category || '')}</td>
      <td class="num">${fmtNum(row.net_revenue)}</td>
      <td class="num">${row.qty}</td>
      <td class="num">${row.orders}</td>
      <td class="share-cell">
        <span class="share-bar" style="width:${(Number(row.net_revenue) / max * 100).toFixed(1)}%"></span>
        <span class="share-text">${share.toFixed(1)}%</span>
      </td>`;
    tbody.appendChild(tr);
  });
  $('top-title').textContent = `Top ${rows.length} 商品`;
}

function renderQualityMini(data) {
  const report = data.data_quality || {};
  const removed = report.removed || {};
  const rows = Object.entries(removed);
  const total = rows.reduce((sum, [, value]) => sum + (value || 0), 0);
  const rawRows = report.raw_rows ?? 0;

  let html = `<div class="quality-grid">` +
    [['原始行数', rawRows], ['保留行数', report.kept_rows ?? '—'],
     ['剔除合计', total], ['保留率', rawRows ? (report.kept_rows / rawRows * 100).toFixed(1) + '%' : '—']]
      .map(([label, value]) =>
        `<div class="mini"><div class="label">${label}</div><div class="value">${esc(value)}</div></div>`)
      .join('') + '</div>';

  html += '<div class="stack-bar">';
  rows.forEach(([key, value]) => {
    if (!value) return;
    const pct = total ? (value / total) * 100 : 0;
    html += `<span class="stack-seg" style="width:${pct.toFixed(2)}%" title="${esc(key)} ${value} 行"></span>`;
  });
  html += '</div><div class="stack-key">' + rows.filter(([, value]) => value).map(([key, value]) =>
    `<span class="lg"><i class="sw sw-seg"></i>${esc(REMOVAL_LABELS[key] || key)} ${value}</span>`
  ).join('') + '</div>';

  if (!total) {
    html += `<div class="warn-box">所有剔除计数都是 0 —— 清洗规则可能没有真正生效。</div>`;
  }
  $('dash-quality').innerHTML = html;
}

function renderDailyTable(data) {
  const tbody = $('dash-daily-table').querySelector('tbody');
  tbody.innerHTML = '';
  const days = data.days || [];
  if (!days.length) {
    tbody.innerHTML = '<tr><td colspan="6" class="empty">没有数据</td></tr>';
    return;
  }
  days.forEach((day) => {
    const tr = document.createElement('tr');
    tr.dataset.date = day.date;
    if (day.severity) tr.classList.add('row-' + day.severity);
    if (!day.orders) tr.classList.add('dim');
    const marks = (day.anomalies || []).map((a) =>
      `<span class="mini-tag tag-${esc(a.severity)}" title="${esc(a.detail)}">${esc(a.label)}</span>`
    ).join(' ');
    tr.innerHTML = `
      <td>${esc(day.date)}</td>
      <td class="num">${fmtNum(day.net_revenue)}</td>
      <td class="num">${day.orders}</td>
      <td class="num">${day.aov === null || day.aov === undefined ? 'null' : fmtNum(day.aov)}</td>
      <td class="num">${fmtNum(day.refund_amount ?? 0)}</td>
      <td>${marks || '<span class="muted">—</span>'}</td>`;
    tr.addEventListener('click', () => {
      state.drillDate = state.drillDate === day.date ? null : day.date;
      renderTrend(data);
      highlightDaily(state.drillDate);
      $('daily-meta').textContent = state.drillDate ? `已选中 ${state.drillDate}` : '—';
    });
    tbody.appendChild(tr);
  });
}

function highlightDaily(date) {
  const rows = $('dash-daily-table').querySelectorAll('tbody tr');
  rows.forEach((row) => row.classList.toggle('row-selected', !!date && row.dataset.date === date));
  if (date) {
    const target = $('dash-daily-table').querySelector(`tbody tr[data-date="${date}"]`);
    if (target) target.scrollIntoView({ block: 'nearest' });
  }
}

/* ---------- 数据质量 ---------- */

const REMOVAL_LABELS = {
  '1_unparseable_date': '日期无法解析',
  '2_empty_amount': 'amount 为空',
  '3_qty_le_zero': 'qty ≤ 0',
  '4_store_not_in_stores': '门店脏外键',
  '5_product_not_in_products': '商品脏外键',
  '6_duplicate_row': '完全重复行',
  note_unparseable_amount: '金额解析失败（备注）',
};

async function loadQuality() {
  const data = await getJSON('/api/data_quality');
  const report = data.cleaning_report || {};
  const removed = report.removed || {};
  const box = $('quality-body');

  const cards = [
    ['原始行数', report.raw_rows, ''],
    ['保留行数', report.kept_rows, 'ok'],
    ['销售行', report.kept_sales_rows, ''],
    ['退款行', report.kept_refund_rows, ''],
  ];
  let html = '<div class="cards">' + cards.map(([label, value, cls]) =>
    `<div class="card ${cls}"><div class="label">${label}</div>
     <div class="value">${value === undefined ? '—' : value}</div></div>`
  ).join('') + '</div>';

  const removedTotal = Object.values(removed).reduce((sum, value) => sum + (value || 0), 0);
  html += '<h4>剔除明细</h4><table><thead><tr><th>原因</th><th>行数</th></tr></thead><tbody>';
  Object.entries(removed).forEach(([key, value]) => {
    html += `<tr${value ? '' : ' class="dim"'}><td>${esc(REMOVAL_LABELS[key] || key)}</td>
      <td class="num">${value || 0}</td></tr>`;
  });
  html += `<tr><td><strong>合计</strong></td><td class="num"><strong>${removedTotal}</strong></td></tr>`;
  html += '</tbody></table>';

  if (removedTotal === 0) {
    html += `<div class="warn-box">所有剔除计数都是 0 —— 清洗规则可能没有真正生效（KB-001 §3 要求六类剔除，真实数据里每一类都有样本）。</div>`;
  }
  if (data.data_period) {
    html += `<p class="muted">数据区间：${esc(data.data_period.start)} ~ ${esc(data.data_period.end)}</p>`;
  }
  if (data.kb_warnings && data.kb_warnings.length) {
    html += `<div class="warn-box">知识库告警：\n${esc(data.kb_warnings.join('\n'))}</div>`;
  }
  box.innerHTML = html;
}

/* ---------- 文档抽屉 ---------- */

async function openDoc(docId, highlight) {
  const drawer = $('drawer');
  drawer.hidden = false;
  $('drawer-title').textContent = docId;
  $('drawer-body').innerHTML = '<div class="empty">加载中…</div>';
  try {
    const data = await getJSON('/api/debug/doc/' + encodeURIComponent(docId));
    const meta = data.meta || {};
    let html = `<p class="muted">${esc(meta.title || '')} · ${esc(meta.state || '')} ·
      生效 ${esc(meta.effective_from || '—')} · ${data.chunks.length} 个片段</p>`;
    if (highlight) {
      html += `<h4>引用的原文片段</h4><pre class="quote">${esc(highlight)}</pre>`;
    }
    html += '<h4>切块结果</h4>';
    data.chunks.forEach((chunk) => {
      html += `<div class="chunk"><div class="chunk-head">${esc(chunk.chunk_id)} ·
        ${chunk.chars} 字</div><pre>${esc(chunk.text)}</pre></div>`;
    });
    html += `<h4>全文</h4><pre>${esc(data.text)}</pre>`;
    $('drawer-body').innerHTML = html;
  } catch (error) {
    $('drawer-body').innerHTML = `<div class="warn-box">${esc(error.message)}</div>`;
  }
}

/* ---------- 导航与初始化 ---------- */

function switchView(name) {
  document.querySelectorAll('.tab').forEach((tab) =>
    tab.classList.toggle('active', tab.dataset.view === name));
  document.querySelectorAll('.view').forEach((view) =>
    view.classList.toggle('active', view.id === 'view-' + name));
  if (name === 'index') loadIndex();
  if (name === 'quality') loadQuality();
  // 看板切回来时重画一次：隐藏状态下容器宽度是 0，SVG 会按 0 宽画。
  if (name === 'dash') {
    if (!state.dash) loadDashboard();
    else state.charts.forEach((chart) => chart.redraw());
  }
}

function init() {
  $('tabs').addEventListener('click', (event) => {
    const tab = event.target.closest('.tab');
    if (tab) switchView(tab.dataset.view);
  });

  $('composer').addEventListener('submit', (event) => {
    event.preventDefault();
    const input = $('question');
    const question = input.value;
    input.value = '';
    sendQuestion(question);
  });

  $('question').addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      $('composer').requestSubmit();
    }
  });

  $('dash-form').addEventListener('submit', loadDashboard);
  $('drawer-close').addEventListener('click', () => { $('drawer').hidden = true; });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') $('drawer').hidden = true;
  });

  loadHealth();
  loadCatalog().then(() => loadDashboard()).catch(() => {});
  loadHistory();
  setInterval(loadHealth, 30000);
}

document.addEventListener('DOMContentLoaded', init);

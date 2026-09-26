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
  const stores = $('m-store');
  catalog.stores.forEach((store) => {
    const option = document.createElement('option');
    option.value = store.store_id;
    option.textContent = `${store.store_id} ${store.store_name}`;
    stores.appendChild(option);
  });
  const products = $('m-product');
  catalog.products.forEach((product) => {
    const option = document.createElement('option');
    option.value = product.product_id;
    option.textContent = `${product.product_id} ${product.product_name}`;
    products.appendChild(option);
  });
  if (catalog.data_period && catalog.data_period.start) {
    $('m-start').value = catalog.data_period.start;
    $('m-end').value = catalog.data_period.end;
  }
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
    if (detail.coverage !== undefined) lines.push(`覆盖率: ${detail.coverage}`);
    if (detail.expansions && detail.expansions.length) {
      lines.push(`别名扩展: ${detail.expansions.slice(0, 6).join('、')}`);
    }
    (detail.hits || []).forEach((hit, index) => {
      const padded = hit.padded ? '（补位，不作答）' : '';
      lines.push(`${index + 1}. ${hit.doc_id} ${hit.chunk_id} score=${hit.score}${padded}`);
    });
    if (detail.filtered && detail.filtered.length) {
      lines.push(`— 被过滤 ${detail.filtered.length} 份：`);
      detail.filtered.slice(0, 6).forEach((item) => {
        lines.push(`   ${item.doc_id}: ${item.reason}`);
      });
    }
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

function appendStep(step) {
  const box = $('trace');
  if (box.querySelector('.empty')) box.innerHTML = '';
  const node = document.createElement('div');
  node.className = 'step';
  node.dataset.step = step.step || '';
  const body = stepBody(step);
  node.innerHTML = `
    <div class="step-head">
      <span class="step-name">${esc(stepTitle(step))}</span>
      <span class="step-ms">${fmtMs(step.took_ms)}</span>
    </div>
    ${body ? `<div class="step-detail">${esc(body)}</div>` : ''}`;
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
}

/** 用留档重放一遍（历史点击）。 */
function renderTraceFromStore(trace) {
  resetTrace(trace.trace_id);
  (trace.steps || []).forEach(appendStep);
  (trace.llm_calls || []).forEach(appendLLM);
  (trace.errors || []).forEach((item) =>
    appendError({ where: item.where, error_type: item.type, message: item.message }));
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

/* ---------- 指标 ---------- */

async function loadMetrics(event) {
  if (event) event.preventDefault();
  const params = new URLSearchParams({
    start: $('m-start').value,
    end: $('m-end').value,
  });
  if ($('m-store').value) params.set('store_id', $('m-store').value);
  if ($('m-product').value) params.set('product_id', $('m-product').value);

  const summary = await getJSON('/api/metrics/summary?' + params);
  const cards = $('metric-cards');
  const items = [
    ['净营业额', fmtNum(summary.net_revenue) + ' 元', 'ok'],
    ['退款金额', fmtNum(summary.refund_amount) + ' 元', summary.refund_amount > 0 ? 'warn' : ''],
    ['有效订单数', String(summary.orders), ''],
    ['客单价', summary.aov === null ? 'null' : fmtNum(summary.aov) + ' 元', ''],
    ['销量', String(summary.qty), ''],
  ];
  cards.innerHTML = items.map(([label, value, cls]) =>
    `<div class="card ${cls}"><div class="label">${label}</div><div class="value">${esc(value)}</div></div>`
  ).join('');

  const daily = await getJSON('/api/metrics/daily?' + params);
  const tbody = $('daily-table').querySelector('tbody');
  tbody.innerHTML = '';
  daily.days.forEach((day) => {
    const row = document.createElement('tr');
    if (!day.orders) row.className = 'dim';
    row.innerHTML = `
      <td>${esc(day.date)}</td>
      <td class="num">${fmtNum(day.net_revenue)}</td>
      <td class="num">${day.orders}</td>
      <td class="num">${day.aov === null ? 'null' : fmtNum(day.aov)}</td>`;
    tbody.appendChild(row);
  });
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

  $('metrics-form').addEventListener('submit', loadMetrics);
  $('drawer-close').addEventListener('click', () => { $('drawer').hidden = true; });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') $('drawer').hidden = true;
  });

  loadHealth();
  loadCatalog().then(() => loadMetrics()).catch(() => {});
  loadHistory();
  setInterval(loadHealth, 30000);
}

document.addEventListener('DOMContentLoaded', init);

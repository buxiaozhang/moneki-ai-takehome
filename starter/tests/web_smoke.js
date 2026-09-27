/* 前端 DOM 冒烟测试（node + jsdom）。
 *
 * 为什么需要它：pytest 只能验证接口字段和静态文件取得到，**验证不了页面的 JS 会不会抛错**。
 * `$('x')` 取到 null、图表在容器宽度为 0 时画、点击联动的重画顺序 —— 这些只有把脚本
 * 真的放进 DOM 里跑一遍才看得见，而它们一旦出错整页就是白屏或空图，接口测试全绿。
 *
 * 用法：
 *     node tests/web_smoke.js
 * 需要能找到 jsdom。它会依次尝试：
 *   1) 环境变量 DOM_DIR 指向的目录；
 *   2) 常规 node_modules 解析；
 * 找不到就 **跳过** 并返回 0，不让缺依赖把测试卡死。
 */

'use strict';

const fs = require('fs');
const path = require('path');

const WEB_DIR = path.join(__dirname, '..', 'kbqa', 'web');

function loadJsdom() {
  const candidates = [];
  if (process.env.DOM_DIR) candidates.push(process.env.DOM_DIR);
  candidates.push(null); // 走常规解析
  for (const dir of candidates) {
    try {
      const target = dir ? path.join(dir, 'jsdom') : 'jsdom';
      return require(target);
    } catch { /* 试下一个 */ }
  }
  return null;
}

const jsdomModule = loadJsdom();
if (!jsdomModule) {
  console.log('  ⊘ 跳过：本机没装 jsdom（设 DOM_DIR 指向含 jsdom 的 node_modules 即可运行）');
  process.exit(0);
}
const { JSDOM } = jsdomModule;

/* ---------- 运行环境 ---------- */

/** 造一个装了必要桩的 JSDOM，并载入 charts.js / app.js。 */
function boot(fetchImpl, fixtureHtml) {
  const dom = new JSDOM(fixtureHtml || fs.readFileSync(path.join(WEB_DIR, 'index.html'), 'utf8'),
    { runScripts: 'outside-only', pretendToBeVisual: true });
  const { window } = dom;

  // jsdom 没有实现这些，图表与滚动会用到。
  window.ResizeObserver = class { observe() {} disconnect() {} };
  window.requestAnimationFrame = (fn) => setTimeout(fn, 0);
  window.cancelAnimationFrame = (id) => clearTimeout(id);
  // 布局引擎缺席：clientWidth 恒为 0，图表会按 0 宽画，所以给个固定宽度。
  Object.defineProperty(window.HTMLElement.prototype, 'clientWidth',
    { get() { return 760; }, configurable: true });
  window.HTMLElement.prototype.scrollIntoView = function () {};

  const errors = [];
  window.addEventListener('error', (e) => errors.push(String(e.message)));
  window.fetch = fetchImpl;

  window.eval(fs.readFileSync(path.join(WEB_DIR, 'charts.js'), 'utf8'));
  window.eval(fs.readFileSync(path.join(WEB_DIR, 'app.js'), 'utf8'));
  return { window, errors };
}

function jsonResponse(body) {
  return { ok: true, status: 200, text: async () => JSON.stringify(body) };
}

/** 造一份形状与真实接口一致的看板数据。 */
function dashboardFixture() {
  const closed = {
    kind: 'closed_run', severity: 'high', date: '2026-06-02', end_date: '2026-06-03',
    days: 2, label: '连续 2 天零营业额', detail: '停业',
  };
  return {
    start: '2026-06-01', end: '2026-06-30',
    summary: { net_revenue: 12345.0, refund_amount: 100.0, orders: 300, aov: 41.15, qty: 900 },
    days: [
      { date: '2026-06-01', net_revenue: 500, orders: 12, aov: 41.6, refund_amount: 0, anomalies: [], severity: null },
      { date: '2026-06-02', net_revenue: 0, orders: 0, aov: null, refund_amount: 0, anomalies: [closed], severity: 'high' },
      { date: '2026-06-03', net_revenue: 0, orders: 0, aov: null, refund_amount: 0, anomalies: [closed], severity: 'high' },
      { date: '2026-06-04', net_revenue: 620, orders: 15, aov: 41.3, refund_amount: 20, anomalies: [], severity: null },
    ],
    anomalies: [closed],
    anomaly_counts: { high: 1, warn: 0, info: 0 },
    period_warnings: [{ kind: 'refund_high', severity: 'warn', label: '退款占比偏高', detail: '退款 100 元' }],
    anomaly_params: { z: 2, drop_ratio: 0.5 },
    top_products: [{ product_id: 'P06', product_name: '牛肉poke', product_category: '主食', net_revenue: 900, qty: 20, orders: 18 }],
    by_store: [{ store_id: 'S01', store_name: 'A', net_revenue: 800, orders: 20, aov: 40 }],
    payments: { '微信': { orders: 10, net_revenue: 500, share_orders: 1 } },
    data_quality: { raw_rows: 18628, kept_rows: 18290, removed: { '1_unparseable_date': 8, '2_empty_amount': 150 } },
    data_period: { start: '2026-05-01', end: '2026-08-31' },
  };
}

function standardRoutes(overrides) {
  const dash = dashboardFixture();
  const table = {
    '/api/health': { llm_mode: 'mock', kb_docs: 35, valid_sales_rows: 18290, llm: { missing: ['LLM_API_KEY'], hint: 'h' } },
    '/api/debug/catalog': {
      stores: [{ store_id: 'S01', store_name: 'A' }, { store_id: 'S02', store_name: 'B' }],
      products: [{ product_id: 'P06', product_name: '牛肉poke' }],
      data_period: { start: '2026-05-01', end: '2026-08-31' },
    },
    '/api/traces': { traces: [] },
    '/api/ui/dashboard': dash,
    '/api/debug/index': {
      doc_count: 1, chunk_count: 2, index_key: 'k', warnings: ['w0'],
      docs: [{ doc_id: 'KB-001', title: 't', type: 'x', status: '现行', effective_from: '2026-01-01',
        superseded_by: null, chunks: 2, chars: 10, format: 'md' }],
    },
    '/api/data_quality': {
      cleaning_report: { raw_rows: 100, kept_rows: 90, kept_sales_rows: 80, kept_refund_rows: 10,
        removed: { '1_unparseable_date': 8, '2_empty_amount': 2 } },
      data_period: { start: '2026-05-01', end: '2026-08-31' }, kb_warnings: [],
    },
    '/api/debug/doc/KB-001': { meta: { title: 'T', state: '现行' }, chunks: [{ chunk_id: 'c1', chars: 3, text: 'abc' }], text: 'abc' },
  };
  return { ...table, ...(overrides || {}) };
}

/* ---------- 断言 ---------- */

let failures = 0;
function check(label, ok, extra) {
  if (!ok) failures += 1;
  console.log(`  ${ok ? 'OK ' : '✗  '} ${label}${extra !== undefined && extra !== '' ? ' — ' + extra : ''}`);
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/* ---------- 用例 ---------- */

async function caseDashboard() {
  console.log('\n【看板渲染】');
  const routes = standardRoutes();
  const { window, errors } = boot(async (url) => {
    const key = String(url).split('?')[0];
    const body = routes[key];
    if (body === undefined) throw new Error('未预料的请求 ' + url);
    return jsonResponse(body);
  });
  const doc = window.document;
  doc.dispatchEvent(new window.Event('DOMContentLoaded'));
  await sleep(300);

  check('无未捕获错误', errors.length === 0, errors.join(' | '));
  check('指标卡片 6 张', doc.querySelectorAll('#dash-cards .card').length === 6,
    doc.querySelectorAll('#dash-cards .card').length + ' 张');
  check('异常预警已渲染', doc.querySelectorAll('#dash-alerts .alert').length >= 2);
  check('趋势图 SVG 已生成', !!doc.querySelector('#trend-chart svg'));
  check('柱子数 = 天数', doc.querySelectorAll('#trend-chart rect.bar').length === 4);
  check('零营业额柱单独着色', doc.querySelectorAll('#trend-chart rect.bar-zero').length === 2);
  check('异常圆点已画', doc.querySelectorAll('#trend-chart circle.anomaly-dot').length === 2);
  check('门店对比图已生成', !!doc.querySelector('#store-chart svg'));
  check('Top 商品表已填充', doc.querySelectorAll('#top-table tbody tr').length === 1);
  check('数据质量面板 4 格', doc.querySelectorAll('#dash-quality .mini').length === 4);
  check('逐日表已填充', doc.querySelectorAll('#dash-daily-table tbody tr').length === 4);
  check('高优先级行有标记', doc.querySelectorAll('#dash-daily-table tr.row-high').length === 2);
  check('快捷区间按钮已生成', doc.querySelectorAll('#dash-quick .chip').length > 2);
  check('日期默认填入数据区间', doc.getElementById('d-start').value === '2026-05-01');

  // 图表 => 表格联动
  doc.querySelector('#trend-chart rect.bar').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(80);
  check('点柱子后选中对应行', doc.querySelectorAll('#dash-daily-table tr.row-selected').length === 1
    && doc.querySelector('#dash-daily-table tr.row-selected').dataset.date === '2026-06-01');

  // 表格 => 图表联动。点第 4 行（避开已被选中的第 1 行：同一行再点是"取消选中"）
  const rows = doc.querySelectorAll('#dash-daily-table tbody tr');
  rows[3].dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(80);
  check('点表格行高亮切换', doc.querySelector('#dash-daily-table tr.row-selected').dataset.date === '2026-06-04');
  check('趋势图同步选中', !!doc.querySelector('#trend-chart rect.bar-selected'));

  // 再点同一行取消
  rows[3].dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(80);
  check('再点同一行取消选中', doc.querySelectorAll('#dash-daily-table tr.row-selected').length === 0);

  // 预警里的日期按钮应能定位
  const link = doc.querySelector('#dash-alerts .alert-date');
  if (link) {
    link.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
    await sleep(80);
    check('点预警日期可定位到该日', doc.querySelectorAll('#dash-daily-table tr.row-selected').length === 1);
  }

  // 切页签再回来：隐藏时宽度为 0，必须重画
  doc.querySelector('.tab[data-view="chat"]').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  doc.querySelector('.tab[data-view="dash"]').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(150);
  check('切页签往返后趋势图仍在', !!doc.querySelector('#trend-chart svg'));
  check('全程无未捕获错误', errors.length === 0, errors.join(' | '));
}

async function caseTracePanel(fixturePath) {
  console.log('\n【追踪面板】');
  if (!fixturePath || !fs.existsSync(fixturePath)) {
    console.log('  ⊘ 跳过：没有传真实 trace 夹具（第 3 个参数指向 /api/trace 的 JSON）');
    return;
  }
  const fixture = JSON.parse(fs.readFileSync(fixturePath, 'utf8'));
  const routes = standardRoutes({ '/api/traces': { traces: [fixture.trace] } });
  routes['/api/trace/' + fixture.trace.trace_id] = fixture.trace;

  const { window, errors } = boot(async (url) => {
    const key = String(url).split('?')[0];
    const body = routes[key];
    if (body === undefined) throw new Error('未预料的请求 ' + url);
    return jsonResponse(body);
  });
  const doc = window.document;
  doc.dispatchEvent(new window.Event('DOMContentLoaded'));
  await sleep(250);

  const item = doc.querySelector('#history .history-item');
  check('历史列表已渲染', !!item);
  if (item) {
    item.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
    await sleep(250);
  }

  const steps = doc.querySelectorAll('#trace .step');
  check('追踪步骤已渲染', steps.length >= 5, steps.length + ' 步');
  check('耗时构成面板出现', doc.getElementById('trace-summary').hidden === false);
  check('耗时条已画', doc.querySelectorAll('#trace-summary .gantt-bar').length >= 4);

  const hits = doc.querySelectorAll('#trace .hits .hit');
  check('检索命中已可视化', hits.length >= 3, hits.length + ' 条');
  const bars = [...doc.querySelectorAll('#trace .hits .hit-bar i')].map((b) => parseFloat(b.style.width));
  check('每条命中都有分数条', bars.length === hits.length);
  check('分数条宽度递减', bars.every((w, i) => i === 0 || w <= bars[i - 1] + 0.01), bars.join(', '));
  check('工具调用已列出', [...steps].filter((s) => s.dataset.step === 'tool').length >= 1);
  check('命中片段可点开文档', !!doc.querySelector('#trace .hits .cite-link'));
  check('被过滤的文档已列出', doc.querySelectorAll('#trace .filtered-row').length >= 1);

  // 模型失败后「耗时构成」会和步骤叠在一起，所以它必须能折叠。
  // 注意：jsdom 不做布局，这里只能验"折叠逻辑对不对"，
  // "折起来之后不再重叠"由 test_dashboard.py 的 CSS 不变量守着。
  const summary = doc.getElementById('trace-summary');
  const ganttToggle = summary.querySelector('.gantt-head');
  check('耗时构成有折叠控件', ganttToggle && ganttToggle.tagName === 'BUTTON');
  check('折叠控件默认是展开的', summary.classList.contains('collapsed') === false
    && ganttToggle.getAttribute('aria-expanded') === 'true');
  check('展开时耗时条可见', summary.querySelectorAll('.gantt-body .gantt-row').length >= 4);

  ganttToggle.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(30);
  check('点击后收起', summary.classList.contains('collapsed') === true);
  check('收起后 aria-expanded=false', ganttToggle.getAttribute('aria-expanded') === 'false');

  ganttToggle.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(30);
  check('再点展开', summary.classList.contains('collapsed') === false);

  check('无未捕获错误', errors.length === 0, errors.join(' | '));
}

async function caseStreaming(fixturePath) {
  console.log('\n【流式问答】');
  if (!fixturePath || !fs.existsSync(fixturePath)) {
    console.log('  ⊘ 跳过：没有传真实 trace 夹具');
    return;
  }
  const fixture = JSON.parse(fs.readFileSync(fixturePath, 'utf8'));
  const routes = standardRoutes();
  const encoder = new TextEncoder();
  const frame = (event, data) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;

  const { window, errors } = boot(async (url) => {
    const key = String(url).split('?')[0];
    if (key === '/api/chat/stream') {
      const frames = [
        frame('start', { trace_id: 't-live-1' }),
        ...fixture.trace.steps.map((s) => frame('step', s)),
        frame('llm', { model: 'mock', endpoint: '/x', took_ms: 12, prompt: '{"messages":[]}', content_chars: 42, finish_reason: 'stop' }),
        frame('final', { payload: fixture.chat }),
      ];
      let index = 0;
      return {
        ok: true, status: 200,
        body: { getReader: () => ({ read: async () => (index < frames.length
          ? { value: encoder.encode(frames[index++]), done: false }
          : { value: undefined, done: true }) }) },
      };
    }
    const body = routes[key];
    if (body === undefined) throw new Error('未预料的请求 ' + url);
    return jsonResponse(body);
  });

  const doc = window.document;
  doc.dispatchEvent(new window.Event('DOMContentLoaded'));
  await sleep(200);
  doc.getElementById('question').value = fixture.trace.question;
  doc.getElementById('composer').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
  await sleep(600);

  check('用户气泡出现', doc.querySelectorAll('.msg-user').length === 1);
  check('AI 气泡已填充答案', (doc.querySelector('.msg-ai .bubble').textContent || '').length > 20);
  check('answer_type 徽章已渲染', !!doc.querySelector('.msg-ai .badge'));
  check('引用已渲染', doc.querySelectorAll('.msg-ai .citation').length >= 1);
  check('data_evidence 已渲染', doc.querySelectorAll('.msg-ai .evidence').length >= 1);
  check('追踪步骤已流式渲染', doc.querySelectorAll('#trace .step').length >= 5);
  check('耗时构成已出现', doc.getElementById('trace-summary').hidden === false);
  check('trace_id 已显示', doc.getElementById('trace-id-label').textContent === 't-live-1');
  check('发送按钮已恢复', doc.getElementById('send').disabled === false);
  check('无未捕获错误', errors.length === 0, errors.join(' | '));
}

async function caseOtherViews() {
  console.log('\n【索引 / 数据质量 / 抽屉】');
  const routes = standardRoutes();
  const { window, errors } = boot(async (url) => {
    const key = String(url).split('?')[0];
    const body = routes[key];
    if (body === undefined) throw new Error('未预料的请求 ' + url);
    return jsonResponse(body);
  });
  const doc = window.document;
  doc.dispatchEvent(new window.Event('DOMContentLoaded'));
  await sleep(200);

  doc.querySelector('.tab[data-view="index"]').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(200);
  check('索引表已填充', doc.querySelectorAll('#index-table tbody tr').length === 1);
  check('索引告警已显示', (doc.getElementById('index-warnings').textContent || '').includes('w0'));

  doc.querySelector('#index-table .cite-link').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(200);
  check('文档抽屉已打开', doc.getElementById('drawer').hidden === false);
  check('抽屉内容已加载', (doc.getElementById('drawer-body').textContent || '').includes('abc'));
  doc.getElementById('drawer-close').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  check('抽屉可关闭', doc.getElementById('drawer').hidden === true);

  doc.querySelector('.tab[data-view="quality"]').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(200);
  check('数据质量页已填充', (doc.getElementById('quality-body').textContent || '').includes('日期无法解析'));
  check('无未捕获错误', errors.length === 0, errors.join(' | '));
}

/**
 * 页面上不该出现「模板没插值」的痕迹。
 *
 * 踩过的坑：把 `$('d-store').value` 写进了反引号模板里。反引号里插值要写 `${...}`，
 * 写成 `$(` 就会把源码原样打到页面上，筛选摘要那一行于是显示成
 * `$($('d-store').value || '全部门店') · …`。
 * 这里把四个页签都渲染一遍，再扫所有可见文字。
 */
async function caseNoRawSourceLeak() {
  console.log('\n【渲染文字】');
  const routes = standardRoutes();
  const { window, errors } = boot(async (url) => {
    const key = String(url).split('?')[0];
    const body = routes[key];
    if (body === undefined) throw new Error('未预料的请求 ' + url);
    return jsonResponse(body);
  });
  const doc = window.document;
  doc.dispatchEvent(new window.Event('DOMContentLoaded'));
  await sleep(250);
  for (const tab of ['dash', 'chat', 'index', 'quality']) {
    const el = doc.querySelector(`.tab[data-view="${tab}"]`);
    if (el) {
      el.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
      await sleep(200);
    }
  }

  const text = doc.body.textContent || '';
  check('没有未插值的 $(' , !text.includes('$('), text.includes('$(') ? '页面上出现了 "$("' : '干净');
  check('没有裸露的 ${', !text.includes('${'), text.includes('${') ? '页面上出现了 "${"' : '干净');

  const meta = doc.getElementById('dash-meta').textContent || '';
  check('筛选摘要已渲染', meta.includes('·') && !meta.includes('$('), meta);
  check('筛选摘要含日期区间', /20\d\d-\d\d-\d\d ~ 20\d\d-\d\d-\d\d/.test(meta), meta);
  check('筛选摘要写了"全部门店/全部商品"', meta.includes('全部门店') && meta.includes('全部商品'), meta);
  check('无未捕获错误', errors.length === 0, errors.join(' | '));
}

/* ---------- 主流程 ---------- */

/**
 * 数字列的表头必须和它的单元格一样标成 .num（右对齐）。
 *
 * 不标的话会出现「表头在左、数字在右」：数字跑到列的右边缘，
 * 看上去就像属于右边那一列 —— 逐日明细的「净营业额」当初就是这样被误读的。
 * 这里按列比对 class，两侧不一致就报出是第几列、表头写的什么。
 */
async function caseTableAlignment() {
  console.log('\n【表格对齐】');
  const routes = standardRoutes();
  const { window, errors } = boot(async (url) => {
    const key = String(url).split('?')[0];
    const body = routes[key];
    if (body === undefined) throw new Error('未预料的请求 ' + url);
    return jsonResponse(body);
  });
  const doc = window.document;
  doc.dispatchEvent(new window.Event('DOMContentLoaded'));
  await sleep(250);

  // 每个页签点一遍，让所有表都填上数据。
  for (const tab of ['dash', 'index', 'quality']) {
    const el = doc.querySelector(`.tab[data-view="${tab}"]`);
    if (el) {
      el.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
      await sleep(250);
    }
  }

  const tables = [...doc.querySelectorAll('table')];
  check('页面上有表格', tables.length >= 3, tables.length + ' 个');

  let bad = 0;
  tables.forEach((table) => {
    const head = table.closest('.panel')?.querySelector('.panel-head span');
    const name = table.id || (head && head.textContent) || '无名表格';
    const ths = [...table.querySelectorAll('thead th')];
    const row = table.querySelector('tbody tr');
    if (!ths.length || !row || row.querySelector('.empty')) return;
    const tds = [...row.querySelectorAll('td')];
    if (tds.length !== ths.length) {
      bad += 1;
      check(`列数一致（${name}）`, false, `表头 ${ths.length} 列，数据 ${tds.length} 列`);
      return;
    }
    const mismatched = ths
      .map((th, i) => ({ th, i }))
      .filter(({ th, i }) => th.classList.contains('num') !== tds[i].classList.contains('num'));
    if (mismatched.length) bad += 1;
    check(
      `数字列表头对齐（${name}）`,
      mismatched.length === 0,
      mismatched.length
        ? '这些列不一致：' + mismatched.map(({ th, i }) => `第${i + 1}列「${th.textContent.trim()}」`).join('、')
        : `${ths.length} 列一致`
    );
  });
  check('所有表格对齐一致', bad === 0, bad ? bad + ' 个表格有问题' : '全部一致');
  check('无未捕获错误', errors.length === 0, errors.join(' | '));
}

/** 默认用仓库里那份真实夹具；也可以用第 2 个参数临时指向别的。 */
function defaultFixture() {
  const local = path.join(__dirname, 'fixtures', 'trace_sample.json');
  return fs.existsSync(local) ? local : null;
}

(async () => {
  const fixturePath = process.argv[2] || defaultFixture();
  console.log('前端 DOM 冒烟测试');
  await caseDashboard();
  await caseTracePanel(fixturePath);
  await caseStreaming(fixturePath);
  await caseTableAlignment();
  await caseNoRawSourceLeak();
  await caseOtherViews();
  console.log(failures ? `\n  ${failures} 项失败` : '\n  全部通过');
  process.exit(failures ? 1 : 0);
})();

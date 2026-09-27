/* 自绘 SVG 图表。
 *
 * 为什么不用 ECharts：实测这台机器访问 jsdelivr / unpkg 都失败，CDN 方案会让
 * 图表整块空掉，而且不会有任何提示。这里只用原生 DOM + SVG，离线可用。
 *
 * 三个图：折线/柱状趋势图（带异常标记）、横向条形对比图、环形占比图。
 * 都返回一个带 `destroy()` 的句柄，切换筛选时先销毁再重画，避免 resize 监听泄漏。
 */

'use strict';

const SVG_NS = 'http://www.w3.org/2000/svg';

/** 建一个 SVG 元素并设属性。 */
function svgEl(tag, attrs) {
  const node = document.createElementNS(SVG_NS, tag);
  Object.entries(attrs || {}).forEach(([key, value]) => {
    if (value !== null && value !== undefined) node.setAttribute(key, String(value));
  });
  return node;
}

/** 金额缩写：12345 → 1.2万。坐标轴上用，省地方。 */
function shortNum(value) {
  const num = Number(value) || 0;
  const abs = Math.abs(num);
  if (abs >= 10000) return (num / 10000).toFixed(abs >= 100000 ? 0 : 1) + '万';
  if (abs >= 1000) return (num / 1000).toFixed(abs >= 10000 ? 0 : 1) + 'k';
  return String(Math.round(num));
}

function niceCeil(value) {
  if (!(value > 0)) return 1;
  const exp = Math.floor(Math.log10(value));
  const base = Math.pow(10, exp);
  const norm = value / base;
  const step = norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10;
  return step * base;
}

/** 让容器跟着窗口变化重画。返回取消函数。 */
function autoResize(container, draw) {
  let frame = null;
  const run = () => {
    if (frame) cancelAnimationFrame(frame);
    frame = requestAnimationFrame(() => {
      frame = null;
      const width = container.clientWidth;
      if (width > 0) draw(width);
    });
  };
  const observer = new ResizeObserver(run);
  observer.observe(container);
  run();
  return () => observer.disconnect();
}

/** 悬停提示：一个跟着鼠标走的浮层，图表共用。 */
function makeTooltip(container) {
  const node = document.createElement('div');
  node.className = 'chart-tip';
  node.hidden = true;
  container.appendChild(node);
  return {
    show(event, html) {
      node.innerHTML = html;
      node.hidden = false;
      const box = container.getBoundingClientRect();
      let left = event.clientX - box.left + 12;
      const top = event.clientY - box.top + 12;
      if (left + node.offsetWidth > box.width) left = box.width - node.offsetWidth - 6;
      node.style.left = Math.max(4, left) + 'px';
      node.style.top = Math.max(4, top) + 'px';
    },
    hide() { node.hidden = true; },
    destroy() { node.remove(); },
  };
}

/* ---------- 趋势图 ---------- */

/**
 * 逐日趋势。柱子高度是净营业额，异常日描红并在顶部打标记。
 *
 * @param {HTMLElement} container
 * @param {Array} days      [{date, net_revenue, orders, aov, severity, anomalies}]
 * @param {Object} options  {onSelect(day), selectedDate}
 */
function renderTrendChart(container, days, options) {
  const opts = options || {};
  const tooltip = makeTooltip(container);
  let selected = opts.selectedDate || null;

  function draw(width) {
    container.querySelectorAll('svg').forEach((node) => node.remove());
    if (!days || !days.length) {
      container.insertAdjacentHTML('beforeend', '<div class="empty">没有数据</div>');
      return;
    }

    const height = 240;
    const pad = { top: 16, right: 12, bottom: 34, left: 46 };
    const innerW = Math.max(10, width - pad.left - pad.right);
    const innerH = height - pad.top - pad.bottom;
    const maxValue = niceCeil(Math.max(...days.map((d) => Number(d.net_revenue) || 0), 1));
    const slot = innerW / days.length;
    const barW = Math.max(2, Math.min(26, slot * 0.68));

    const svg = svgEl('svg', {
      width: '100%', height, viewBox: `0 0 ${width} ${height}`, role: 'img',
    });

    // 横向网格 + y 轴刻度
    for (let i = 0; i <= 4; i += 1) {
      const value = (maxValue / 4) * i;
      const y = pad.top + innerH - (innerH * i) / 4;
      svg.appendChild(svgEl('line', {
        x1: pad.left, x2: width - pad.right, y1: y, y2: y, class: 'grid-line',
      }));
      const label = svgEl('text', {
        x: pad.left - 6, y: y + 3, class: 'axis-text', 'text-anchor': 'end',
      });
      label.textContent = shortNum(value);
      svg.appendChild(label);
    }

    const step = Math.max(1, Math.ceil(days.length / 12));

    days.forEach((day, index) => {
      const value = Number(day.net_revenue) || 0;
      const barH = (value / maxValue) * innerH;
      const x = pad.left + slot * index + (slot - barW) / 2;
      const y = pad.top + innerH - barH;
      const isSelected = selected === day.date;

      const rect = svgEl('rect', {
        x, y: barH > 0 ? y : pad.top + innerH - 1,
        width: barW, height: Math.max(barH, value > 0 ? 1 : 2),
        rx: Math.min(3, barW / 3),
        class: 'bar' + (day.severity ? ' bar-' + day.severity : '') + (isSelected ? ' bar-selected' : ''),
      });
      if (value <= 0) rect.setAttribute('class', 'bar bar-zero' + (isSelected ? ' bar-selected' : ''));
      rect.addEventListener('mousemove', (event) => {
        const items = (day.anomalies || []).map((a) => `<div class="tip-warn">${a.label}</div>`).join('');
        tooltip.show(event,
          `<strong>${day.date}</strong><br>` +
          `净营业额 ${Number(value).toLocaleString('zh-CN')} 元<br>` +
          `订单 ${day.orders} 单` +
          (day.aov === null || day.aov === undefined ? '' : `<br>客单价 ${day.aov} 元`) +
          items);
      });
      rect.addEventListener('mouseleave', () => tooltip.hide());
      rect.addEventListener('click', () => {
        selected = selected === day.date ? null : day.date;
        if (opts.onSelect) opts.onSelect(selected ? day : null);
        draw(width);
      });
      svg.appendChild(rect);

      // 异常标记：柱子顶端一个圆点，零营业额的日子贴在基线上。
      if (day.severity) {
        svg.appendChild(svgEl('circle', {
          cx: x + barW / 2,
          cy: value > 0 ? y - 5 : pad.top + innerH - 6,
          r: 3.2,
          class: 'anomaly-dot anomaly-' + day.severity,
        }));
      }

      if (index % step === 0 || index === days.length - 1) {
        const label = svgEl('text', {
          x: x + barW / 2, y: height - 14, class: 'axis-text', 'text-anchor': 'middle',
        });
        label.textContent = day.date.slice(5);
        svg.appendChild(label);
      }
    });

    svg.appendChild(svgEl('line', {
      x1: pad.left, x2: width - pad.right,
      y1: pad.top + innerH, y2: pad.top + innerH, class: 'axis-line',
    }));

    container.appendChild(svg);
  }

  const stop = autoResize(container, draw);
  return {
    destroy() { stop(); tooltip.destroy(); container.innerHTML = ''; },
    redraw() { draw(container.clientWidth || 600); },
  };
}

/* ---------- 横向条形图 ---------- */

/**
 * 门店 / 商品对比。横向条 + 数值，点击回调用在下钻。
 *
 * @param {Array} items   [{label, sub, value}]
 * @param {Object} options {onSelect(id, item), valueLabel}
 */
function renderBarChart(container, items, options) {
  const opts = options || {};
  const tooltip = makeTooltip(container);
  let selected = opts.selectedId || null;

  function draw(width) {
    container.querySelectorAll('svg').forEach((node) => node.remove());
    if (!items || !items.length) {
      container.insertAdjacentHTML('beforeend', '<div class="empty">没有数据</div>');
      return;
    }
    const rowH = 30;
    const height = items.length * rowH + 12;
    const labelW = Math.min(150, Math.max(88, width * 0.34));
    const valueW = 78;
    const innerW = Math.max(20, width - labelW - valueW - 14);
    const max = Math.max(...items.map((item) => Number(item.value) || 0), 1);

    const svg = svgEl('svg', { width: '100%', height, viewBox: `0 0 ${width} ${height}`, role: 'img' });

    items.forEach((item, index) => {
      const value = Number(item.value) || 0;
      const y = index * rowH + 6;
      const barW = (value / max) * innerW;
      const isSelected = selected === item.id;

      const label = svgEl('text', {
        x: labelW - 8, y: y + rowH / 2 - 1, class: 'axis-text bar-label', 'text-anchor': 'end',
      });
      label.textContent = item.label;
      svg.appendChild(label);

      if (item.sub) {
        const sub = svgEl('text', {
          x: labelW - 8, y: y + rowH / 2 + 10, class: 'axis-text bar-sub', 'text-anchor': 'end',
        });
        sub.textContent = item.sub;
        svg.appendChild(sub);
      }

      svg.appendChild(svgEl('rect', {
        x: labelW, y: y + 4, width: innerW, height: rowH - 12, rx: 4, class: 'bar-track',
      }));

      const bar = svgEl('rect', {
        x: labelW, y: y + 4, width: Math.max(barW, value > 0 ? 2 : 0), height: rowH - 12, rx: 4,
        class: 'bar-fill' + (isSelected ? ' bar-selected' : ''),
        tabindex: '0',
      });
      bar.addEventListener('mousemove', (event) => {
        tooltip.show(event,
          `<strong>${item.label}</strong><br>${opts.valueLabel || '数值'} ` +
          `${Number(value).toLocaleString('zh-CN')}${item.extra ? '<br>' + item.extra : ''}`);
      });
      bar.addEventListener('mouseleave', () => tooltip.hide());
      bar.addEventListener('click', () => {
        selected = selected === item.id ? null : item.id;
        if (opts.onSelect) opts.onSelect(selected, item);
        draw(width);
      });
      svg.appendChild(bar);

      const valueText = svgEl('text', {
        x: labelW + innerW + 8, y: y + rowH / 2 + 1, class: 'axis-text bar-value',
      });
      valueText.textContent = shortNum(value);
      svg.appendChild(valueText);
    });

    container.appendChild(svg);
  }

  const stop = autoResize(container, draw);
  return {
    destroy() { stop(); tooltip.destroy(); container.innerHTML = ''; },
    redraw() { draw(container.clientWidth || 600); },
  };
}

/* ---------- 环形图 ---------- */

/**
 * 占比环形图（支付方式构成）。
 *
 * @param {Array} items [{label, value, share}]
 */
function renderDonutChart(container, items, options) {
  const opts = options || {};
  const tooltip = makeTooltip(container);
  const palette = ['#4c8dff', '#35c98a', '#f5a623', '#e5574a', '#9b6cf2', '#28b8c8'];

  function draw(width) {
    container.querySelectorAll('svg').forEach((node) => node.remove());
    const rows = (items || []).filter((item) => (Number(item.value) || 0) > 0);
    if (!rows.length) {
      container.insertAdjacentHTML('beforeend', '<div class="empty">没有数据</div>');
      return;
    }
    const height = 200;
    const size = Math.min(height, width * 0.5);
    const radius = size / 2 - 6;
    const cx = size / 2 + 4;
    const cy = height / 2;
    const total = rows.reduce((sum, item) => sum + (Number(item.value) || 0), 0) || 1;

    const svg = svgEl('svg', { width: '100%', height, viewBox: `0 0 ${width} ${height}`, role: 'img' });
    let angle = -Math.PI / 2;

    rows.forEach((item, index) => {
      const value = Number(item.value) || 0;
      const sweep = (value / total) * Math.PI * 2;
      const end = angle + sweep;
      const large = sweep > Math.PI ? 1 : 0;
      const x1 = cx + radius * Math.cos(angle);
      const y1 = cy + radius * Math.sin(angle);
      const x2 = cx + radius * Math.cos(end);
      const y2 = cy + radius * Math.sin(end);

      const path = svgEl('path', {
        d: `M ${cx} ${cy} L ${x1} ${y1} A ${radius} ${radius} 0 ${large} 1 ${x2} ${y2} Z`,
        fill: palette[index % palette.length],
        class: 'donut-slice',
      });
      path.addEventListener('mousemove', (event) => {
        tooltip.show(event, `<strong>${item.label}</strong><br>${value.toLocaleString('zh-CN')}` +
          `<br>占比 ${(value / total * 100).toFixed(1)}%`);
      });
      path.addEventListener('mouseleave', () => tooltip.hide());
      svg.appendChild(path);
      angle = end;

      // 右侧图例
      const ly = 16 + index * 20;
      if (ly < height - 6) {
        svg.appendChild(svgEl('rect', {
          x: size + 16, y: ly, width: 10, height: 10, rx: 2, fill: palette[index % palette.length],
        }));
        const text = svgEl('text', { x: size + 32, y: ly + 9, class: 'axis-text' });
        text.textContent = `${item.label} ${(value / total * 100).toFixed(1)}%`;
        svg.appendChild(text);
      }
    });

    container.appendChild(svg);
  }

  const stop = autoResize(container, draw);
  return {
    destroy() { stop(); tooltip.destroy(); container.innerHTML = ''; },
    redraw() { draw(container.clientWidth || 600); },
  };
}

window.Charts = { renderTrendChart, renderBarChart, renderDonutChart };

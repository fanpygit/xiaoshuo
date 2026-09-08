const $ = (id) => document.getElementById(id);

let lastMarkdown = '';
let lastName = '小说大纲';

/* ---------- 极简 Markdown 渲染 ---------- */
function escapeHtml(s) {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function inline(text) {
  return escapeHtml(text)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*]+)\*/g, '<em>$1</em>');
}

function renderMarkdown(md) {
  const lines = String(md || '').replace(/\r\n/g, '\n').split('\n');
  let html = '';
  let inCode = false;
  let codeBuf = [];
  let listType = null;

  const closeList = () => {
    if (listType) { html += `</${listType}>`; listType = null; }
  };

  for (const line of lines) {
    if (line.trim().startsWith('```')) {
      if (inCode) {
        html += '<pre><code>' + escapeHtml(codeBuf.join('\n')) + '</code></pre>';
        codeBuf = [];
        inCode = false;
      } else {
        closeList();
        inCode = true;
      }
      continue;
    }
    if (inCode) { codeBuf.push(line); continue; }

    const t = line.trim();
    if (!t) { closeList(); continue; }

    const h = t.match(/^(#{1,4})\s+(.*)$/);
    if (h) {
      closeList();
      const level = Math.min(h[1].length + 1, 4);
      html += `<h${level}>${inline(h[2])}</h${level}>`;
      continue;
    }

    if (/^(-{3,}|\*{3,})$/.test(t)) {
      closeList();
      html += '<hr>';
      continue;
    }

    if (/^[-*+]\s+/.test(t)) {
      if (listType !== 'ul') { closeList(); html += '<ul>'; listType = 'ul'; }
      html += '<li>' + inline(t.replace(/^[-*+]\s+/, '')) + '</li>';
      continue;
    }

    if (/^\d+[.)]\s+/.test(t)) {
      if (listType !== 'ol') { closeList(); html += '<ol>'; listType = 'ol'; }
      html += '<li>' + inline(t.replace(/^\d+[.)]\s+/, '')) + '</li>';
      continue;
    }

    if (/^>\s?/.test(t)) {
      closeList();
      html += '<blockquote>' + inline(t.replace(/^>\s?/, '')) + '</blockquote>';
      continue;
    }

    closeList();
    html += '<p>' + inline(t) + '</p>';
  }

  closeList();
  return html;
}

/* ---------- 状态与提示 ---------- */
function setStatus(msg, isError = true) {
  const el = $('status');
  el.textContent = msg;
  el.style.color = isError ? '#d64545' : '#18a058';
}

/* ---------- 配置 ---------- */
async function loadConfig() {
  try {
    const resp = await fetch('/api/config');
    const data = await resp.json();
    if (data.base_url) $('base-url').value = data.base_url;
    if (data.model) {
      const sel = $('model');
      let found = false;
      for (const opt of sel.options) {
        if (opt.value === data.model) { found = true; break; }
      }
      if (!found) {
        const opt = document.createElement('option');
        opt.value = data.model;
        opt.textContent = data.model;
        sel.appendChild(opt);
      }
      sel.value = data.model;
    }
    if (data.save_dir) $('save-dir').value = data.save_dir;
    if (data.thinking) $('thinking').value = data.thinking;
    if (data.api_key_set) {
      $('api-key').value = '';
      $('api-key').placeholder = '已保存（' + data.api_key + '），留空则沿用';
    }
  } catch (e) {
    console.error('读取配置失败', e);
  }
}

$('save-config').addEventListener('click', async () => {
  const btn = $('save-config');
  btn.disabled = true;
  try {
    const resp = await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        base_url: $('base-url').value,
        model: $('model').value,
        api_key: $('api-key').value,
        save_dir: $('save-dir').value,
        thinking: $('thinking').value,
      }),
    });
    const data = await resp.json();
    if (!resp.ok) {
      $('config-hint').textContent = data.error || '保存失败';
      $('config-hint').style.color = '#d64545';
    } else {
      $('config-hint').textContent = '已保存 ✓';
      $('config-hint').style.color = '#18a058';
      if (data.api_key_set) {
        $('api-key').value = '';
        $('api-key').placeholder = '已保存，留空则沿用';
      }
    }
  } catch (e) {
    $('config-hint').textContent = '保存失败：' + e.message;
    $('config-hint').style.color = '#d64545';
  } finally {
    btn.disabled = false;
  }
});

function configPayload() {
  return {
    base_url: $('base-url').value.trim(),
    model: $('model').value.trim(),
    api_key: $('api-key').value.trim(),
    thinking: $('thinking').value,
  };
}

/* ---------- 标签切换 ---------- */
function switchTab(name) {
  document.querySelectorAll('.tab').forEach((t) => {
    t.classList.toggle('active', t.dataset.tab === name);
  });
  document.querySelectorAll('.tab-panel').forEach((p) => {
    p.classList.toggle('active', p.id === 'panel-' + name);
  });
  // 切到对应标签时刷新下拉列表，确保能看到新生成的小说/章节正文
  if (name === 'coherence') loadCoherenceNovels();
  if (name === 'polish') loadPolishNovels();
  if (name === 'refine') loadRefineNovels();
  if (name === 'insert') loadInsertSummaries();
}

document.querySelectorAll('.tab').forEach((t) => {
  t.addEventListener('click', () => switchTab(t.dataset.tab));
});

/* ---------- 结果展示 ---------- */
function showResult(markdown, name) {
  lastMarkdown = markdown;
  lastName = name || '小说大纲';
  $('result').innerHTML = renderMarkdown(markdown);
  $('result-panel').hidden = false;
  $('result-panel').classList.add('show');
  const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' });
  $('download').href = URL.createObjectURL(blob);
  $('download').download = lastName + '.md';
  $('result-panel').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

/* ---------- 通用请求 ---------- */
async function postJson(url, payload, btn, loadingText, name) {
  btn.disabled = true;
  const original = btn.textContent;
  btn.textContent = loadingText;
  setStatus('正在生成，请稍候…', false);
  try {
    const resp = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (!resp.ok) {
      setStatus(data.error || '操作失败');
      return null;
    }
    const content = data.content || data.outline || '';
    if (!content) { setStatus('返回内容为空'); return null; }
    showResult(content, name);
    setStatus('完成！', false);
    return data;
  } catch (e) {
    setStatus('请求失败：' + e.message);
    return null;
  } finally {
    btn.disabled = false;
    btn.textContent = original;
  }
}

/* ---------- 大纲生成 ---------- */
$('generate').addEventListener('click', async () => {
  const prompt = $('prompt').value.trim();
  if (!prompt) { setStatus('请先填写故事灵感 / 提示词'); return; }
  const data = await postJson('/api/generate', {
    ...configPayload(),
    prompt,
    novel_name: $('novel-name').value.trim(),
    genre: Array.from(document.querySelectorAll('#genre input[type="checkbox"]:checked')).map((c) => c.value),
    plot_tags: Array.from(document.querySelectorAll('#plot-tags input[type="checkbox"]:checked')).map((c) => c.value),
    length: $('length').value,
    chapters: $('chapters').value,
    pov: $('pov').value,
    tone: $('tone').value,
    extra: $('extra').value.trim(),
  }, $('generate'), '生成中…', '小说大纲');
  if (data && data.saved_path) {
    setStatus('已保存到：' + data.saved_path, false);
    loadNovels();
  }
});

/* ---------- 章节梗概 ---------- */
$('expand-chapters').addEventListener('click', async () => {
  const outline = $('chapters-outline').value.trim();
  if (!outline) { setStatus('请先粘贴小说大纲'); return; }
  const data = await postJson('/api/expand-chapters', {
    ...configPayload(),
    outline,
    novel_name: $('chapters-novel-name').value.trim(),
    chapters: $('chapters-count').value,
    words: $('chapters-words').value,
  }, $('expand-chapters'), '分批生成中…', '章节梗概');
  if (data && data.message) {
    setStatus(data.message, false);
  } else if (data && data.folder_path) {
    let msg = '已保存 ' + (data.chapter_count || 0) + ' 章到：' + data.folder_path;
    if (data.batch_count) msg += '（分 ' + data.batch_count + ' 批）';
    setStatus(msg, false);
  }
  loadSummaries();
});

/* ---------- 章节写作 ---------- */
$('write-chapter').addEventListener('click', async () => {
  const outline = $('writing-outline').value.trim();
  if (!outline) { setStatus('请先读取或填写故事梗概 / 大纲'); return; }
  let context = '';
  if (prevChapterContent) context += '【前章梗概】\n' + prevChapterContent;
  if (nextChapterContent) context += (context ? '\n\n' : '') + '【后章梗概】\n' + nextChapterContent;
  const data = await postJson('/api/write-chapter', {
    ...configPayload(),
    outline,
    context,
    novel_name: $('writing-novel-name').value.trim(),
    chapter: $('writing-chapter').value.replace(/\.md$/, '').trim(),
    words: $('writing-words').value,
    tone: $('writing-tone').value,
    pov: $('writing-pov').value,
    author: $('writing-author').value.trim(),
    style_sample: styleSample,
    requirement: $('writing-requirement').value.trim(),
    prev_content: $('writing-prev-content').value.trim(),
  }, $('write-chapter'), '写作中…', '章节正文');
  if (data && data.saved_path) {
    setStatus('已保存章节到：' + data.saved_path, false);
  }
});

/* ---------- 连贯性检查 ---------- */
let currentContentNovel = '';

let coherenceKind = 'summary';

async function loadCoherenceNovels() {
  let url;
  if (coherenceKind === 'summary') url = '/api/summaries';
  else if (coherenceKind === 'content') url = '/api/contents';
  else url = '/api/combined';
  try {
    const resp = await fetch(url);
    const data = await resp.json();
    const list = data.summaries || data.contents || data.combined || [];
    const sel = $('contents-select');
    sel.innerHTML = '<option value="">—— 选择小说 ——</option>';
    for (const name of list) {
      const opt = document.createElement('option');
      opt.value = name;
      opt.textContent = name;
      sel.appendChild(opt);
    }
  } catch (e) {
    console.error('加载小说列表失败', e);
  }
}

$('coherence-kind').addEventListener('change', () => {
  coherenceKind = $('coherence-kind').value;
  $('contents-select').innerHTML = '<option value="">—— 选择小说 ——</option>';
  $('coherence-chapters').innerHTML = '<p class="hint">请先读取章节列表</p>';
  loadCoherenceNovels();
});

$('load-contents').addEventListener('click', async () => {
  const name = $('contents-select').value;
  if (!name) { setStatus('请先选择小说'); return; }
  try {
    let base;
    if (coherenceKind === 'summary') base = '/api/summaries/';
    else if (coherenceKind === 'content') base = '/api/contents/';
    else base = '/api/combined/';
    const resp = await fetch(base + encodeURIComponent(name) + '/chapters');
    const data = await resp.json();
    if (!resp.ok) { setStatus(data.error || '读取失败'); return; }
    currentContentNovel = name;
    const box = $('coherence-chapters');
    box.innerHTML = '';
    for (const f of data.chapters) {
      const label = document.createElement('label');
      label.className = 'chip';
      const input = document.createElement('input');
      input.type = 'checkbox';
      input.name = 'coherence-chapter';
      input.value = f;
      const span = document.createElement('span');
      span.textContent = f.replace(/\.md$/, '');
      label.appendChild(input);
      label.appendChild(span);
      box.appendChild(label);
    }
    setStatus('已加载 ' + data.chapters.length + ' 章，请勾选要检查的章节', false);
  } catch (e) {
    setStatus('读取失败：' + e.message);
  }
});

let currentCoherenceChapters = [];

function parseIssues(md) {
  const lines = String(md || '').replace(/\r\n/g, '\n').split('\n');
  const issues = [];
  let inSection = false;
  for (const line of lines) {
    const t = line.trim();
    if (/^#{1,4}\s/.test(t)) {
      inSection = /发现的问题/.test(t) || /问题/.test(t);
      continue;
    }
    if (!inSection || !t) continue;
    if (/^(无|暂无|没有问题)/.test(t)) continue;
    let m = t.match(/^\d+[.、)]\s*(.*)$/);
    if (m && m[1].trim()) { issues.push(m[1].trim()); continue; }
    m = t.match(/^[-*+]\s+(.*)$/);
    if (m && m[1].trim()) { issues.push(m[1].trim()); continue; }
  }
  return issues;
}

function renderIssues(issues) {
  const box = $('coherence-issues');
  box.innerHTML = '';
  $('coherence-fix-panel').hidden = false;
  if (!issues.length) {
    box.innerHTML = '<p class="hint">未解析到编号问题（可能无问题或格式不同）</p>';
    return;
  }
  for (const issue of issues) {
    const label = document.createElement('label');
    label.className = 'chip';
    const input = document.createElement('input');
    input.type = 'checkbox';
    input.name = 'coherence-issue';
    input.value = issue;
    const span = document.createElement('span');
    span.textContent = issue;
    label.appendChild(input);
    label.appendChild(span);
    box.appendChild(label);
  }
}

$('check-coherence').addEventListener('click', async () => {
  const chapters = Array.from(document.querySelectorAll('input[name="coherence-chapter"]:checked')).map((c) => c.value);
  if (!chapters.length) { setStatus('请选择要检查的章节'); return; }
  currentCoherenceChapters = chapters;
  const data = await postJson('/api/check-coherence', {
    ...configPayload(),
    novel_name: currentContentNovel,
    chapters,
    kind: coherenceKind,
  }, $('check-coherence'), '检查中…', '连贯性检查');
  if (data && data.content) {
    renderIssues(parseIssues(data.content));
  }
});

$('fix-issues').addEventListener('click', async () => {
  const issues = Array.from(document.querySelectorAll('input[name="coherence-issue"]:checked')).map((c) => c.value);
  if (!issues.length) { setStatus('请勾选要修复的问题'); return; }
  const data = await postJson('/api/fix-coherence', {
    ...configPayload(),
    novel_name: currentContentNovel,
    chapters: currentCoherenceChapters,
    issues,
    kind: coherenceKind,
  }, $('fix-issues'), '修复中…', '修复结果');
  if (data && data.message) setStatus(data.message, false);
});

$('save-issues').addEventListener('click', async () => {
  const all = Array.from(document.querySelectorAll('input[name="coherence-issue"]')).map((c) => c.value);
  const checked = Array.from(document.querySelectorAll('input[name="coherence-issue"]:checked')).map((c) => c.value);
  const unchecked = all.filter((x) => !checked.includes(x));
  if (!unchecked.length) { setStatus('没有未选的问题'); return; }
  const data = await postJson('/api/save-issues', {
    ...configPayload(),
    novel_name: currentContentNovel,
    chapters: currentCoherenceChapters,
    issues: unchecked,
    kind: coherenceKind,
  }, $('save-issues'), '保存中…', '问题文档');
  if (data && data.message) setStatus(data.message, false);
});

/* ---------- 复制 / 导出 ---------- */
$('copy').addEventListener('click', async () => {
  if (!lastMarkdown) { setStatus('没有可复制的内容'); return; }
  try {
    await navigator.clipboard.writeText(lastMarkdown);
    setStatus('已复制 Markdown 到剪贴板', false);
  } catch (e) {
    setStatus('复制失败，请手动选中复制');
  }
});

$('export-word').addEventListener('click', async () => {
  if (!lastMarkdown) { setStatus('没有可导出的内容'); return; }
  const btn = $('export-word');
  btn.disabled = true;
  setStatus('正在生成 Word 文档…', false);
  try {
    const resp = await fetch('/api/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ outline: lastMarkdown, title: lastName }),
    });
    if (!resp.ok) {
      let msg = '导出失败';
      try { msg = (await resp.json()).error || msg; } catch (e) { /* ignore */ }
      setStatus(msg);
      return;
    }
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = lastName + '.docx';
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    setStatus('已导出 Word 文档', false);
  } catch (e) {
    setStatus('导出失败：' + e.message);
  } finally {
    btn.disabled = false;
  }
});

/* ---------- 小说文件读写 ---------- */
async function loadNovels() {
  try {
    const resp = await fetch('/api/novels');
    const data = await resp.json();
    const sel = $('novels-select');
    sel.innerHTML = '<option value="">—— 选择已保存的小说 ——</option>';
    for (const name of data.novels) {
      const opt = document.createElement('option');
      opt.value = name;
      opt.textContent = name;
      sel.appendChild(opt);
    }
  } catch (e) {
    console.error('加载小说列表失败', e);
  }
}

$('load-novel').addEventListener('click', async () => {
  const name = $('novels-select').value;
  if (!name) { setStatus('请先选择一个小说'); return; }
  try {
    const resp = await fetch('/api/novels/' + encodeURIComponent(name));
    const data = await resp.json();
    if (!resp.ok) { setStatus(data.error || '读取失败'); return; }
    $('chapters-outline').value = data.content;
    $('chapters-novel-name').value = name;
    setStatus('已读取大纲「' + name + '」', false);
  } catch (e) {
    setStatus('读取失败：' + e.message);
  }
});

$('outline-file').addEventListener('change', () => {
  const file = $('outline-file').files && $('outline-file').files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    $('chapters-outline').value = reader.result;
    const base = file.name.replace(/\.(md|txt|markdown)$/i, '');
    if (base) $('chapters-novel-name').value = base;
    const hint = $('outline-file-hint');
    hint.textContent = '已读取：' + file.name;
    hint.style.color = '#18a058';
    setStatus('已读取大纲文件「' + file.name + '」', false);
  };
  reader.onerror = () => setStatus('读取文件失败');
  reader.readAsText(file, 'utf-8');
});

$('extra-file').addEventListener('change', () => {
  const file = $('extra-file').files && $('extra-file').files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    $('extra').value = reader.result;
    const hint = $('extra-file-hint');
    hint.textContent = '已读取：' + file.name;
    hint.style.color = '#18a058';
  };
  reader.onerror = () => setStatus('读取文件失败');
  reader.readAsText(file, 'utf-8');
});

async function loadSummaries() {
  try {
    const resp = await fetch('/api/summaries');
    const data = await resp.json();
    const sel = $('summaries-select');
    sel.innerHTML = '<option value="">—— 选择已生成的章节梗概 ——</option>';
    for (const name of data.summaries) {
      const opt = document.createElement('option');
      opt.value = name;
      opt.textContent = name;
      sel.appendChild(opt);
    }
  } catch (e) {
    console.error('加载章节梗概列表失败', e);
  }
}

let currentNovel = '';
let prevChapterContent = '';
let nextChapterContent = '';
let chapterFiles = [];

async function loadChapterOptions(name) {
  try {
    const resp = await fetch('/api/summaries/' + encodeURIComponent(name) + '/chapters');
    const data = await resp.json();
    if (!resp.ok) return;
    chapterFiles = data.chapters;
    const fill = (selId, placeholder) => {
      const sel = $(selId);
      sel.innerHTML = '<option value="">' + placeholder + '</option>';
      for (const f of data.chapters) {
        const opt = document.createElement('option');
        opt.value = f;
        opt.textContent = f.replace(/\.md$/, '');
        sel.appendChild(opt);
      }
    };
    fill('prev-chapter-select', '—— 无 ——');
    fill('next-chapter-select', '—— 无 ——');
    fill('writing-chapter', '—— 选择目标章节 ——');
  } catch (e) {
    console.error('加载章节文件列表失败', e);
  }
}

async function loadChapterContent(name, fname) {
  if (!name || !fname) return '';
  try {
    const resp = await fetch('/api/summaries/' + encodeURIComponent(name) + '/chapter/' + encodeURIComponent(fname));
    const data = await resp.json();
    return resp.ok ? (data.content || '') : '';
  } catch (e) {
    return '';
  }
}

$('load-summary').addEventListener('click', async () => {
  const name = $('summaries-select').value;
  if (!name) { setStatus('请先选择章节梗概文件'); return; }
  try {
    const resp = await fetch('/api/summaries/' + encodeURIComponent(name));
    const data = await resp.json();
    if (!resp.ok) { setStatus(data.error || '读取失败'); return; }
    currentNovel = name;
    prevChapterContent = '';
    nextChapterContent = '';
    $('writing-outline').value = data.content;
    $('writing-novel-name').value = name;
    $('prev-chapter-select').innerHTML = '<option value="">—— 无 ——</option>';
    $('next-chapter-select').innerHTML = '<option value="">—— 无 ——</option>';
    $('writing-chapter').innerHTML = '<option value="">—— 选择目标章节 ——</option>';
    await loadChapterOptions(name);
    setStatus('已读取章节梗概「' + name + '」', false);
  } catch (e) {
    setStatus('读取失败：' + e.message);
  }
});

$('prev-chapter-select').addEventListener('change', async () => {
  const f = $('prev-chapter-select').value;
  prevChapterContent = f ? await loadChapterContent(currentNovel, f) : '';
});

$('next-chapter-select').addEventListener('change', async () => {
  const f = $('next-chapter-select').value;
  nextChapterContent = f ? await loadChapterContent(currentNovel, f) : '';
});

$('writing-chapter').addEventListener('change', async () => {
  const f = $('writing-chapter').value;
  if (!f) { $('writing-prev-content').value = ''; return; }
  const idx = chapterFiles.indexOf(f);
  if (idx <= 0 || !currentNovel) { $('writing-prev-content').value = ''; return; }
  const start = Math.max(0, idx - 10);
  const prevFiles = chapterFiles.slice(start, idx); // 目标章节之前的（最多 10 章）
  try {
    const parts = [];
    for (const pf of prevFiles) {
      const resp = await fetch('/api/contents/' + encodeURIComponent(currentNovel) + '/chapter/' + encodeURIComponent(pf));
      const data = await resp.json();
      if (resp.ok && data.content) {
        parts.push('【' + pf.replace(/\.md$/, '') + '】\n' + data.content);
      }
    }
    $('writing-prev-content').value = parts.join('\n\n');
    setStatus('已读取前 ' + prevFiles.length + ' 章正文', false);
  } catch (e) {
    $('writing-prev-content').value = '';
  }
});

let styleSample = '';

$('writing-style-file').addEventListener('change', () => {
  const file = $('writing-style-file').files && $('writing-style-file').files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    styleSample = reader.result;
    const hint = $('writing-style-file-hint');
    hint.textContent = '已读取：' + file.name;
    hint.style.color = '#18a058';
  };
  reader.onerror = () => setStatus('读取文件失败');
  reader.readAsText(file, 'utf-8');
});

let currentPolishNovel = '';

async function loadPolishNovels() {
  try {
    const resp = await fetch('/api/contents');
    const data = await resp.json();
    const sel = $('polish-novel-select');
    sel.innerHTML = '<option value="">—— 选择已写正文的小说 ——</option>';
    for (const name of data.contents) {
      const opt = document.createElement('option');
      opt.value = name;
      opt.textContent = name;
      sel.appendChild(opt);
    }
  } catch (e) {
    console.error('加载小说列表失败', e);
  }
}

$('load-polish-chapters').addEventListener('click', async () => {
  const name = $('polish-novel-select').value;
  if (!name) { setStatus('请先选择小说'); return; }
  try {
    const resp = await fetch('/api/contents/' + encodeURIComponent(name) + '/chapters');
    const data = await resp.json();
    if (!resp.ok) { setStatus(data.error || '读取失败'); return; }
    currentPolishNovel = name;
    const box = $('polish-chapters');
    box.innerHTML = '';
    for (const f of data.chapters) {
      const label = document.createElement('label');
      label.className = 'chip';
      const input = document.createElement('input');
      input.type = 'checkbox';
      input.name = 'polish-chapter';
      input.value = f;
      const span = document.createElement('span');
      span.textContent = f.replace(/\.md$/, '');
      label.appendChild(input);
      label.appendChild(span);
      box.appendChild(label);
    }
    setStatus('已加载 ' + data.chapters.length + ' 章，请勾选要润色的章节', false);
  } catch (e) {
    setStatus('读取失败：' + e.message);
  }
});

$('polish-chapters-btn').addEventListener('click', async () => {
  const chapters = Array.from(document.querySelectorAll('input[name="polish-chapter"]:checked')).map((c) => c.value);
  if (!chapters.length) { setStatus('请勾选要润色的章节'); return; }
  const data = await postJson('/api/polish-chapters', {
    ...configPayload(),
    novel_name: currentPolishNovel,
    chapters,
    style: $('polish-style').value.trim(),
  }, $('polish-chapters-btn'), '润色中…', '润色结果');
  if (data && data.message) setStatus(data.message, false);
});

/* ---------- 大纲微调 ---------- */
async function loadRefineNovels() {
  try {
    const resp = await fetch('/api/novels');
    const data = await resp.json();
    const sel = $('refine-novels-select');
    sel.innerHTML = '<option value="">—— 选择已保存的小说 ——</option>';
    for (const name of data.novels) {
      const opt = document.createElement('option');
      opt.value = name;
      opt.textContent = name;
      sel.appendChild(opt);
    }
  } catch (e) {
    console.error('加载小说列表失败', e);
  }
}

$('refine-load-novel').addEventListener('click', async () => {
  const name = $('refine-novels-select').value;
  if (!name) { setStatus('请先选择一个小说'); return; }
  try {
    const resp = await fetch('/api/novels/' + encodeURIComponent(name));
    const data = await resp.json();
    if (!resp.ok) { setStatus(data.error || '读取失败'); return; }
    $('refine-outline').value = data.content;
    $('refine-novel-name').value = name;
    setStatus('已读取大纲「' + name + '」', false);
  } catch (e) {
    setStatus('读取失败：' + e.message);
  }
});

$('refine-outline-file').addEventListener('change', () => {
  const file = $('refine-outline-file').files && $('refine-outline-file').files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    $('refine-outline').value = reader.result;
    const base = file.name.replace(/\.(md|txt|markdown)$/i, '');
    if (base) $('refine-novel-name').value = base;
    const hint = $('refine-outline-file-hint');
    hint.textContent = '已读取：' + file.name;
    hint.style.color = '#18a058';
    setStatus('已读取大纲文件「' + file.name + '」', false);
  };
  reader.onerror = () => setStatus('读取文件失败');
  reader.readAsText(file, 'utf-8');
});

$('refine-outline-btn').addEventListener('click', async () => {
  const outline = $('refine-outline').value.trim();
  const requirement = $('refine-requirement').value.trim();
  if (!outline) { setStatus('请先读取或粘贴现有大纲'); return; }
  if (!requirement) { setStatus('请填写调整要求'); return; }
  const data = await postJson('/api/refine-outline', {
    ...configPayload(),
    outline,
    requirement,
    novel_name: $('refine-novel-name').value.trim(),
  }, $('refine-outline-btn'), '调整中…', '大纲微调');
  if (data && data.message) setStatus(data.message, false);
  if (data && data.saved_path) loadNovels();
});

/* ---------- 章节梗概插入 ---------- */
let currentInsertNovel = '';

async function loadInsertSummaries() {
  try {
    const resp = await fetch('/api/summaries');
    const data = await resp.json();
    const sel = $('insert-summaries-select');
    sel.innerHTML = '<option value="">—— 选择已生成的章节梗概 ——</option>';
    for (const name of data.summaries) {
      const opt = document.createElement('option');
      opt.value = name;
      opt.textContent = name;
      sel.appendChild(opt);
    }
  } catch (e) {
    console.error('加载章节梗概列表失败', e);
  }
}

async function refreshInsertChapters() {
  if (!currentInsertNovel) return;
  try {
    const resp = await fetch('/api/summaries/' + encodeURIComponent(currentInsertNovel) + '/chapters');
    const data = await resp.json();
    if (!resp.ok) return;
    const sel = $('insert-anchor');
    sel.innerHTML = '<option value="">—— 选择参考章节 ——</option>';
    for (const f of data.chapters) {
      const opt = document.createElement('option');
      opt.value = f;
      opt.textContent = f.replace(/\.md$/, '');
      sel.appendChild(opt);
    }
  } catch (e) {
    console.error('刷新章节列表失败', e);
  }
}

$('insert-load-chapters').addEventListener('click', async () => {
  const name = $('insert-summaries-select').value;
  if (!name) { setStatus('请先选择章节梗概'); return; }
  currentInsertNovel = name;
  try {
    const resp = await fetch('/api/summaries/' + encodeURIComponent(name) + '/chapters');
    const data = await resp.json();
    if (!resp.ok) { setStatus(data.error || '读取失败'); return; }
    const sel = $('insert-anchor');
    sel.innerHTML = '<option value="">—— 选择参考章节 ——</option>';
    for (const f of data.chapters) {
      const opt = document.createElement('option');
      opt.value = f;
      opt.textContent = f.replace(/\.md$/, '');
      sel.appendChild(opt);
    }
    setStatus('已加载 ' + data.chapters.length + ' 章，请选择插入位置', false);
  } catch (e) {
    setStatus('读取失败：' + e.message);
  }
});

$('insert-chapter-btn').addEventListener('click', async () => {
  const anchor = $('insert-anchor').value;
  if (!currentInsertNovel) { setStatus('请先读取章节列表'); return; }
  if (!anchor) { setStatus('请选择参考章节'); return; }
  const requirement = $('insert-requirement').value.trim();
  if (!requirement) { setStatus('请填写新章节梗概的要求'); return; }
  const data = await postJson('/api/insert-chapter', {
    ...configPayload(),
    novel_name: currentInsertNovel,
    anchor_chapter: anchor,
    position: $('insert-position').value,
    requirement,
  }, $('insert-chapter-btn'), '生成并插入中…', '新章节梗概');
  if (data && data.message) setStatus(data.message, false);
  if (data && data.ok) await refreshInsertChapters();
});

const DEFAULT_CHAPTERS = ['默认（自动）', '1～10章', '10～30章', '30～50章', '50～100章', '100～200章', '200～500章', '500～800章', '800～1200章', '1200～1600章', '1600～2000章', '2000～2500章', '2500章以上'];
const LENGTH_CHAPTERS = {
  '短故事': ['1章'],
  '短篇': ['1章'],
  '中篇': ['最多20章', '1～10章', '10～20章'],
  '长篇': ['最多200章', '1～20章', '20～50章', '50～100章', '100～200章'],
  '超长篇': ['1～500章', '500～1000章', '1000～1500章', '1500～2000章', '2000章以上'],
};

function fillChapters(opts) {
  const sel = $('chapters');
  sel.innerHTML = '';
  for (const o of opts) {
    const opt = document.createElement('option');
    opt.value = (o === '默认（自动）') ? '' : o;
    opt.textContent = o;
    sel.appendChild(opt);
  }
}

$('length').addEventListener('change', () => {
  const len = $('length').value;
  fillChapters((len && LENGTH_CHAPTERS[len]) ? LENGTH_CHAPTERS[len] : DEFAULT_CHAPTERS);
});

/* ---------- 多选下拉 ---------- */
function buildMultiSelect(select) {
  const wrap = document.createElement('div');
  wrap.className = 'multiselect';
  wrap.id = select.id;

  const placeholder = (select.querySelector('option[value=""]') || {}).textContent || '请选择';

  const trigger = document.createElement('button');
  trigger.type = 'button';
  trigger.className = 'ms-trigger';
  const valueEl = document.createElement('span');
  valueEl.className = 'ms-value is-empty';
  valueEl.textContent = placeholder;
  const caret = document.createElement('span');
  caret.className = 'ms-caret';
  caret.textContent = '▾';
  trigger.appendChild(valueEl);
  trigger.appendChild(caret);

  const panel = document.createElement('div');
  panel.className = 'ms-panel';

  const makeOption = (value, text) => {
    const label = document.createElement('label');
    label.className = 'ms-option';
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.value = value;
    const span = document.createElement('span');
    span.textContent = text;
    label.appendChild(cb);
    label.appendChild(span);
    return label;
  };

  Array.from(select.children).forEach((child) => {
    if (child.tagName === 'OPTGROUP') {
      const group = document.createElement('div');
      group.className = 'ms-group';
      const gl = document.createElement('div');
      gl.className = 'ms-group-label';
      gl.textContent = child.label;
      group.appendChild(gl);
      Array.from(child.children).forEach((opt) => {
        if (opt.value) group.appendChild(makeOption(opt.value, opt.textContent));
      });
      panel.appendChild(group);
    } else if (child.tagName === 'OPTION' && child.value) {
      panel.appendChild(makeOption(child.value, child.textContent));
    }
  });

  wrap.appendChild(trigger);
  wrap.appendChild(panel);
  select.replaceWith(wrap);

  const inputs = wrap.querySelectorAll('input[type="checkbox"]');
  const refresh = () => {
    const sel = Array.from(inputs).filter((i) => i.checked).map((i) => i.value);
    valueEl.textContent = sel.length ? sel.join('、') : placeholder;
    valueEl.classList.toggle('is-empty', sel.length === 0);
  };

  trigger.addEventListener('click', (e) => {
    e.stopPropagation();
    const isOpen = wrap.classList.contains('open');
    document.querySelectorAll('.multiselect.open').forEach((o) => o.classList.remove('open'));
    if (!isOpen) wrap.classList.add('open');
  });
  inputs.forEach((i) => i.addEventListener('change', refresh));
  refresh();
}

function initMultiSelects() {
  document.querySelectorAll('select[data-multi]').forEach(buildMultiSelect);
}

document.addEventListener('click', (e) => {
  document.querySelectorAll('.multiselect.open').forEach((o) => {
    if (!o.contains(e.target)) o.classList.remove('open');
  });
});

initMultiSelects();
loadConfig();
loadNovels();
loadSummaries();
loadCoherenceNovels();
loadPolishNovels();
loadRefineNovels();
loadInsertSummaries();


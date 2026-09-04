const $ = (id) => document.getElementById(id);

function setPreview(inputId, imgId) {
  const input = $(inputId);
  const img = $(imgId);
  input.addEventListener('change', () => {
    const file = input.files && input.files[0];
    if (file) {
      img.src = URL.createObjectURL(file);
      img.classList.add('show');
    }
  });
}

async function loadTemplates() {
  try {
    const resp = await fetch('/api/templates');
    const data = await resp.json();
    const sel = $('template');
    for (const name of data.templates) {
      const opt = document.createElement('option');
      opt.value = name;
      opt.textContent = name;
      sel.appendChild(opt);
    }
  } catch (e) {
    console.error('加载模板失败', e);
  }
}

function setStatus(msg, isError = true) {
  const el = $('status');
  el.textContent = msg;
  el.style.color = isError ? '#d64545' : '#18a058';
}

$('generate').addEventListener('click', async () => {
  const sourceInput = $('source');
  if (!sourceInput.files || !sourceInput.files[0]) {
    setStatus('请先上传源照片');
    return;
  }
  const fd = new FormData();
  fd.append('source', sourceInput.files[0]);

  const targetInput = $('target');
  if (targetInput.files && targetInput.files[0]) {
    fd.append('target', targetInput.files[0]);
  } else if ($('template').value) {
    fd.append('template', $('template').value);
  } else {
    setStatus('请上传目标图或选择一个模板');
    return;
  }

  fd.append('top_text', $('top-text').value);
  fd.append('bottom_text', $('bottom-text').value);

  const btn = $('generate');
  btn.disabled = true;
  btn.textContent = '生成中…（首次运行需下载模型，可能较久）';
  setStatus('处理中，请稍候…', false);

  try {
    const resp = await fetch('/api/generate', { method: 'POST', body: fd });
    const data = await resp.json();
    if (!resp.ok) {
      setStatus(data.error || '生成失败');
      return;
    }
    const result = $('result');
    result.src = data.url + '?t=' + Date.now();
    result.classList.add('show');
    $('download').href = data.url;
    $('result-panel').hidden = false;
    setStatus('生成成功！', false);
  } catch (e) {
    setStatus('请求失败：' + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = '生成表情包';
  }
});

setPreview('source', 'source-preview');
setPreview('target', 'target-preview');
loadTemplates();

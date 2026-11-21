const form = document.querySelector('#download-form');
const input = document.querySelector('#video-url');
const field = document.querySelector('#url-field');
const clear = document.querySelector('#clear-button');
const submit = document.querySelector('#submit-button');
const label = document.querySelector('.button-label');
const message = document.querySelector('#message');

function showMessage(text, kind = '') {
  message.textContent = text;
  message.className = `message ${kind}`;
}

function updateClear() { clear.hidden = !input.value.length; }
input.addEventListener('input', () => {
  field.classList.remove('invalid');
  showMessage('');
  updateClear();
});
clear.addEventListener('click', () => {
  input.value = '';
  input.focus();
  updateClear();
  showMessage('');
});
updateClear();

function allowedUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && [
      'instagram.com', 'www.instagram.com', 'm.instagram.com',
      'tiktok.com', 'www.tiktok.com', 'm.tiktok.com',
      'vm.tiktok.com', 'vt.tiktok.com'
    ].includes(url.hostname.toLowerCase());
  } catch { return false; }
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const url = input.value.trim();
  if (!allowedUrl(url)) {
    field.classList.add('invalid');
    input.focus();
    showMessage('Cole uma URL HTTPS válida do Instagram ou TikTok.', 'error');
    return;
  }
  const format = new FormData(form).get('format');
  submit.disabled = true;
  submit.classList.add('loading');
  label.textContent = 'Preparando arquivo...';
  showMessage('Buscando o vídeo. Isso pode demorar alguns instantes.');

  try {
    const response = await fetch('/api/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, format })
    });
    if (!response.ok) {
      let detail = 'Não foi possível baixar este vídeo.';
      try { detail = (await response.json()).detail || detail; } catch {}
      throw new Error(typeof detail === 'string' ? detail : 'Verifique o link e tente novamente.');
    }
    const blob = await response.blob();
    if (!blob.size) throw new Error('O arquivo recebido está vazio.');
    const blobUrl = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = blobUrl;
    a.download = `baixai.${format}`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.setTimeout(() => URL.revokeObjectURL(blobUrl), 60_000);
    showMessage('Arquivo pronto! O download foi enviado ao navegador.', 'success');
  } catch (error) {
    showMessage(error?.message || 'Falha de conexão. Tente novamente.', 'error');
  } finally {
    submit.disabled = false;
    submit.classList.remove('loading');
    label.textContent = 'Baixar agora';
  }
});

document.querySelector('#paste-button').addEventListener('click', async () => {
  try {
    input.value = (await navigator.clipboard.readText()).trim();
    input.dispatchEvent(new Event('input'));
    if (!input.value) showMessage('A área de transferência está vazia.', 'error');
  } catch {
    showMessage('Cole o link manualmente no campo acima.', 'error');
  }
  input.focus();
});

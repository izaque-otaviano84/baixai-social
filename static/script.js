const form = document.querySelector('#download-form');
const input = document.querySelector('#video-url');
const field = document.querySelector('#url-field');
const clearButton = document.querySelector('#clear-button');
const pasteButton = document.querySelector('#paste-button');
const submitButton = document.querySelector('#submit-button');
const buttonLabel = document.querySelector('.button-label');
const message = document.querySelector('#message');
const formats = [...document.querySelectorAll('input[name="format"]')];

function showMessage(text, kind = '') {
  message.textContent = text;
  message.className = `message ${kind}`;
}
function updateClear() { clearButton.hidden = !input.value; }
function selectedFormat() { return formats.find(x => x.checked)?.value || 'mp4'; }
function updateButtonLabel() {
  if (!submitButton.classList.contains('loading')) buttonLabel.textContent = selectedFormat() === 'mp3' ? 'Baixar áudio' : 'Baixar vídeo';
}
formats.forEach(x => x.addEventListener('change', updateButtonLabel));
input.addEventListener('input', () => {
  field.classList.remove('invalid');
  showMessage('');
  updateClear();
});
clearButton.addEventListener('click', () => {
  input.value = '';
  input.focus();
  input.dispatchEvent(new Event('input'));
});
pasteButton.addEventListener('click', async () => {
  try {
    if (!navigator.clipboard?.readText) throw new Error('permission');
    const value = await navigator.clipboard.readText();
    if (!value.trim()) {
      showMessage('A área de transferência está vazia.', 'error');
      return;
    }
    input.value = value.trim();
    input.dispatchEvent(new Event('input'));
    input.focus();
  } catch {
    input.focus();
    showMessage('Não foi possível colar automaticamente. Toque no campo e use Colar.', 'error');
  }
});
updateClear();
updateButtonLabel();

function allowedUrl(raw) {
  try {
    const parsed = new URL(raw);
    return parsed.protocol === 'https:' && !parsed.username && !parsed.password && !parsed.port && [
      'instagram.com', 'www.instagram.com', 'm.instagram.com',
      'tiktok.com', 'www.tiktok.com', 'm.tiktok.com', 'vm.tiktok.com', 'vt.tiktok.com'
    ].includes(parsed.hostname.toLowerCase());
  } catch { return false; }
}

form.addEventListener('submit', async event => {
  event.preventDefault();
  const url = input.value.trim();
  if (!allowedUrl(url)) {
    field.classList.add('invalid');
    input.focus();
    showMessage('Cole um link HTTPS válido do Instagram ou TikTok.', 'error');
    return;
  }
  const format = selectedFormat();
  submitButton.disabled = true;
  submitButton.classList.add('loading');
  buttonLabel.textContent = 'Preparando arquivo…';
  showMessage('Buscando o vídeo. Isso pode levar alguns instantes.');
  try {
    const response = await fetch('/api/download', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({url, format}),
      cache: 'no-store'
    });
    if (!response.ok) {
      let detail = 'Não foi possível baixar este vídeo.';
      try { detail = (await response.json()).detail || detail; } catch {}
      throw new Error(typeof detail === 'string' ? detail : 'Verifique o link e tente novamente.');
    }
    const blob = await response.blob();
    if (!blob.size) throw new Error('O arquivo recebido está vazio.');
    const blobUrl = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = blobUrl;
    link.download = `baixai.${format}`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(blobUrl), 60000);
    showMessage('Pronto! Seu arquivo foi enviado para downloads.', 'success');
  } catch (error) {
    showMessage(error?.message || 'O download falhou. Tente novamente.', 'error');
  } finally {
    submitButton.disabled = false;
    submitButton.classList.remove('loading');
    updateButtonLabel();
  }
});

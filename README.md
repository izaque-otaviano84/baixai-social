# Baixaí — atualização Apple-inspired + TikTok autorizado

Aplicação FastAPI + yt-dlp + FFmpeg. Interface adaptativa, visual discreto inspirado nas recomendações de materiais da Apple, título compacto, botão **Colar**, escolha entre MP4 e MP3, modo claro/escuro e painel opcional de **acesso autorizado ao TikTok**.

## Principais alterações

- `static/index.html`, `static/styles.css`, `static/script.js`: UI renovada, com título menor, fontes de sistema, formulário como foco, botão de colar e suporte a iPhone/desktop e modo escuro.
- `app.py`: aceita `private: true` somente para TikTok, exige chave de administrador e configura cookies da conta autorizada. Mantém os limites por IP, tamanho, duração e tamanho do corpo da requisição.
- `worker.py`: preserva o isolamento via subprocesso, limite de 40 MiB e bloqueio de conexões para IPs internos. Cookies são escritos apenas em arquivo temporário com permissões 0600, no worker, e excluídos ao final.
- `Dockerfile`: mantém usuário sem privilégios, FFmpeg e deploy via Docker.

## Publicar no repositório existente

Atualize **os arquivos correspondentes**, mantendo os caminhos da raiz:
`app.py`, `worker.py`, `Dockerfile`, `static/index.html`, `static/styles.css`, `static/script.js`, `README.md`, `tests/test_app.py`.

O `render.yaml` e `requirements.txt` continuam compatíveis. No Render, se o serviço estiver conectado ao branch `main` com deploy automático, o commit disparará um novo deploy. **Faça backup da versão atual antes de trocar os arquivos.**

## Uso público e privado

- **Modo padrão:** links públicos de Instagram e TikTok, sem login e sem usar cookies de administrador.
- **Modo autorizado:** somente para vídeos do TikTok acessíveis à sua própria sessão ou a uma conta à qual você tem permissão. Mesmo autenticado, alguns downloads podem falhar por restrições do TikTok ou do yt-dlp.
- Conteúdos privados de terceiros sem autorização, DRM ou acessos não concedidos pela plataforma **não são contornados**.

### Configurar o modo autorizado no Render

Em **Render > seu Web Service > Environment**, adicione:

| Variável | Valor |
| --- | --- |
| `PRIVATE_DOWNLOAD_KEY` | Uma chave aleatória forte, com ao menos 32 caracteres. Gere localmente com `python -c "import secrets;print(secrets.token_urlsafe(32))"` |
| `TIKTOK_COOKIES_BASE64` | Conteúdo em Base64 de um arquivo Netscape `cookies.txt` contendo cookies da sessão TikTok autorizada |

O arquivo `cookies.txt` deve conter a linha inicial `# Netscape HTTP Cookie File` e cookies do domínio `.tiktok.com`/`tiktok.com`. Gere-o **localmente**, não no navegador público do site, e confirme que se refere a uma conta que pode visualizar o vídeo. As instruções oficiais de `yt-dlp` para exportação estão em <https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp>.

Converta localmente para Base64:

```sh
# macOS / Linux
python3 -c 'import base64,pathlib;print(base64.b64encode(pathlib.Path("cookies.txt").read_bytes()).decode())'
```

```powershell
# Windows PowerShell
[Convert]::ToBase64String([IO.File]::ReadAllBytes((Resolve-Path .\cookies.txt)))
```

**Segurança:** Base64 não é criptografia. Não envie cookies, códigos de sessão ou a chave de administrador por chat, GitHub, HTML ou JavaScript; configure-os somente nas variáveis secretas do Render. Uma sessão exportada pode dar acesso à conta — use uma conta dedicada quando possível e revogue a sessão se for exposta. Não publique logs contendo esses valores. Se não configurar as duas variáveis, o modo público continua funcionando e o modo privado responde com erro 503.

O acesso privado é exclusivo da API administrativa. Envie a chave por um cliente de API autorizado, em HTTPS.

## Desenvolvimento e testes

Linux com Python 3.12+ e FFmpeg:

```sh
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt pytest httpx
pytest -q
uvicorn app:app --reload --port 10000
```

No Windows/macOS também é possível testar com Docker:

```sh
docker build -t baixai .
docker run --rm -p 10000:10000 baixai
```

Abra <http://localhost:10000>.

A API aceita `POST /api/download` com `{"url":"https://www.tiktok.com/@exemplo/video/123456789","format":"mp4","private":false}`. Para o modo autorizado envie `private:true` e o cabeçalho `X-Baixai-Admin-Key`. O serviço utiliza um download por vez e exclui o arquivo temporário ao concluir a resposta.

## Limitações

- Render Free pode hibernar após inatividade e possui franquias de horas/transferência; confira <https://render.com/docs/free>.
- O serviço usa IPs de datacenter, que podem ser bloqueados por Instagram/TikTok.
- Limites atuais: 40 MiB, 10 minutos, 90 segundos por processamento (configurável por `PROCESS_TIMEOUT_SECONDS`), 4 tentativas por minuto por IP e 20 por minuto globalmente (contagem em memória).
- Os testes automáticos simulam o download para exercitar as respostas e a limpeza; **não demonstram que vídeos privados reais funcionem**. Teste no serviço publicado com um vídeo autorizado.

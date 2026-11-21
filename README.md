# Baixaí

Aplicação em português para baixar um vídeo público autorizado do Instagram ou TikTok em MP4 ou extrair seu áudio em MP3. A interface funciona sem conta e sem anúncios. O backend usa FastAPI, yt-dlp e FFmpeg.

## Desenvolvimento

O worker usa recursos do Linux. No Windows ou macOS, use Docker.

```sh
docker build -t baixai .
docker run --rm -p 10000:10000 baixai
```

Em Linux com Python 3.12 e FFmpeg instalados:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt pytest httpx
python -m pytest -q
python -m uvicorn app:app --port 10000
```

Abra http://localhost:10000. Os testes automatizados verificam validação, respostas HTTP e limpeza usando um arquivo simulado. Para verificar cada plataforma, use um vídeo público próprio ou explicitamente autorizado e teste os dois formatos no endereço do deploy.

## Render

Use um Web Service Free com o Dockerfile da raiz ou o Blueprint em `render.yaml`. O container escuta em `0.0.0.0` na porta do ambiente `PORT` (padrão 10000). O health check é `/health`. `PROCESS_TIMEOUT_SECONDS` tem padrão de 90 segundos. O serviço não exige tokens, cookies ou credenciais de plataforma.

O Render Free oferece HTTPS e 750 horas por mês por workspace. A instância hiberna após 15 minutos sem tráfego. Confira as franquias de transferência e build em Billing. Com um método de pagamento cadastrado, o tráfego acima da franquia pode gerar cobrança. O Render pode suspender instâncias gratuitas que iniciem alto volume de tráfego. Consulte https://render.com/docs/free.

## API e limites

`POST /api/download` recebe JSON com `url` e `format` (`mp4` ou `mp3`) e devolve um anexo no formato solicitado. O serviço processa um arquivo por vez, incluindo a transferência, e apaga o diretório temporário no término da resposta ou em caso de erro. Limites de 40 MiB, 10 minutos por vídeo, 4 tentativas por minuto por IP e 20 por minuto no serviço. Os limites de requisição são mantidos em memória.

O serviço limita a entrada a links de vídeo das duas plataformas e as conexões do extrator a IPs públicos na porta 443. É necessário que a plataforma ofereça um formato HTTPS direto e permita o acesso pelo IP do servidor. Conteúdo privado, publicações com múltiplos vídeos, feeds e links que exijam autenticação ficam fora do escopo.

## Manutenção

Atualize a versão de yt-dlp em `requirements.txt` quando um extrator deixar de funcionar. Rode os testes, confirme os downloads autorizados nos dois formatos e envie o commit ao branch acompanhado pelo Render. Acompanhe o health check e os logs de build. O plano Free permite voltar a um dos dois últimos deploys.

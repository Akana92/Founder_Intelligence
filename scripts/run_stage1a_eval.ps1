$ErrorActionPreference = 'Stop'
$env:OPENAI_API_KEY = ''
$env:LANGSMITH_TRACING = 'false'
$env:DDA_LANGSMITH_TRACING = 'false'
if (-not $env:UV_CACHE_DIR) {
  $env:UV_CACHE_DIR = '.uv-cache-stage1a-eval'
}
uv run --offline --no-sync --no-default-groups --group stage1a --group stage1a-rag-local --group eval-ragas --group dev investment-dd run-eval --dataset public_us_frozen_v1

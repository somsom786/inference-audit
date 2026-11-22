#!/usr/bin/env bash
# Phase 9 local single-GPU experiment. Run in WSL, with no other GPU workloads.
set -euo pipefail
root="${INFERENCE_AUDIT_VLLM_HOME:-$HOME/.local/share/inference-audit-vllm}"
model="${INFERENCE_AUDIT_GGUF:-$HOME/models/Qwen3-8B-Q4_K_M.gguf}"
port="${INFERENCE_AUDIT_VLLM_PORT:-18091}"
context="${INFERENCE_AUDIT_VLLM_CONTEXT:-1536}"
smi=/usr/lib/wsl/lib/nvidia-smi
case "${1:-serve}" in
  metadata)
    mkdir -p "$root/tokenizer"
    base=https://huggingface.co/Qwen/Qwen3-8B/resolve/b968826d9c46dd6066d109eabc6255188de91218
    for name in config.json generation_config.json tokenizer.json tokenizer_config.json merges.txt vocab.json; do
      if [[ ! -s "$root/tokenizer/$name" ]]; then
        curl --fail --location --max-time 60 --max-filesize 25000000 --silent --show-error "$base/$name" -o "$root/tokenizer/$name.tmp"
        mv "$root/tokenizer/$name.tmp" "$root/tokenizer/$name"
      fi
    done
    ;;
  compute)
    "$root/env/bin/python" -c 'import torch, vllm, vllm._C_stable_libtorch; x=torch.ones(8,device="cuda"); print(torch.__version__, torch.version.cuda, torch.cuda.get_device_name(), vllm.__version__, (x*x).sum().item())'
    ;;
  serve)
    shift || true
    test -f "$model" && test -f "$root/tokenizer/tokenizer.json" && test -x "$root/env/bin/vllm"
    mkdir -p "$root"
    exec 9>"$root/serve.lock"
    flock -n 9 || { echo 'An owned vLLM session already holds the lock.' >&2; exit 1; }
    for _ in {1..5}; do
      IFS=, read -r used free busy < <("$smi" -i 0 --query-gpu=memory.used,memory.free,utilization.gpu --format=csv,noheader,nounits)
      if (( used > 2850 || free < 9300 || busy > 10 )); then
        echo "Idle gate refused launch (used=$used MiB, free=$free MiB, busy=$busy%)." >&2
        exit 1
      fi
      sleep .5
    done
    export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 CUDA_VISIBLE_DEVICES=0
    export VLLM_NO_USAGE_STATS=1 XDG_CACHE_HOME="$root/cache"
    exec "$root/env/bin/vllm" serve "$model" --tokenizer "$root/tokenizer" \
      --hf-config-path "$root/tokenizer" --served-model-name audit-qwen3-8b \
      --quantization gguf --host 127.0.0.1 --port "$port" \
      --dtype half --max-model-len "$context" --max-num-seqs 8 \
      --default-chat-template-kwargs '{"enable_thinking":false}' \
      --gpu-memory-utilization 0.67 "$@"
    ;;
  health) curl --fail --silent --show-error "http://127.0.0.1:$port/health";;
  models) curl --fail --silent --show-error "http://127.0.0.1:$port/v1/models";;
  metrics) curl --fail --silent --show-error "http://127.0.0.1:$port/metrics";;
  *) echo 'Use metadata, compute, serve, health, models, or metrics.' >&2; exit 2;;
esac

#!/usr/bin/env bash
# pal-bench: measure how fast each AI model runs on YOUR Pal Pro, and write a results table.
#
#   ./pal-bench.sh            download (if needed) and test the models that fit in 4 GB
#   ./pal-bench.sh --quick    just the three small ones
#
# "Prompt" speed = how fast it reads what you said. "Reply" speed = how fast it writes
# the answer. People speak about 3-4 tokens per second, so a reply speed above ~5 keeps up
# with talking.
#
# Needs llama.cpp built by install-pro.sh (llama-bench). Results go to bench-results.md.
set -uo pipefail

MODELS_DIR=${PAL_MODELS:-/opt/pal/models}
BENCH=${PAL_LLAMA_BENCH:-/opt/pal/llama.cpp/build/bin/llama-bench}
MODE=${1:-}
HF=https://huggingface.co

# name | file | url path on Hugging Face
ALL=(
  "Qwen2.5 0.5B|qwen2.5-0.5b-instruct-q4_k_m.gguf|Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main"
  "Llama 3.2 1B|Llama-3.2-1B-Instruct-Q4_K_M.gguf|bartowski/Llama-3.2-1B-Instruct-GGUF/resolve/main"
  "Gemma 3 1B|google_gemma-3-1b-it-Q4_K_M.gguf|bartowski/google_gemma-3-1b-it-GGUF/resolve/main"
  "Qwen2.5 1.5B|qwen2.5-1.5b-instruct-q4_k_m.gguf|Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main"
  "Llama 3.2 3B|Llama-3.2-3B-Instruct-Q4_K_M.gguf|bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main"
  "Qwen2.5 3B|qwen2.5-3b-instruct-q4_k_m.gguf|Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main"
  "Phi-3.5 mini 3.8B|Phi-3.5-mini-instruct-Q4_K_M.gguf|bartowski/Phi-3.5-mini-instruct-GGUF/resolve/main"
)
if [[ "${MODE}" == "--quick" ]]; then ALL=("${ALL[@]:0:4}"); fi

[[ -x "$BENCH" ]] || { echo "llama-bench not found at $BENCH - run install-pro.sh first"; exit 1; }
mkdir -p "$MODELS_DIR"

temp() { awk '{printf "%.0f", $1/1000}' /sys/class/thermal/thermal_zone0/temp 2>/dev/null; }
RES=bench-results.md
{
  echo "# Pi Pal Pro - AI speed on this Pal"
  echo
  echo "$(tr -d '\0' < /proc/device-tree/model 2>/dev/null), $(free -h | awk '/Mem:/{print $2}') RAM, $(date '+%Y-%m-%d')"
  echo
  echo "| Model | File size | Prompt (tok/s) | Reply (tok/s) | Keeps up with talking? | CPU temp after |"
  echo "|---|---|---|---|---|---|"
} > "$RES"

for row in "${ALL[@]}"; do
  IFS='|' read -r name file path <<< "$row"
  f="$MODELS_DIR/$file"
  if [[ ! -s "$f" ]]; then
    echo "== downloading $name"
    if ! curl -fL --retry 3 -o "$f.part" "$HF/$path/$file"; then
      echo "   download failed - skipping $name"; rm -f "$f.part"; continue
    fi
    mv "$f.part" "$f"
  fi
  # A 4 GB Pal needs room for the OS, The Shelf and speech too; skip anything over ~2.6 GB.
  size=$(stat -c %s "$f")
  if (( size > 2800000000 )) && (( $(awk '/MemTotal/{print $2}' /proc/meminfo) < 6000000 )); then
    echo "   $name is too big for this Pal's RAM - skipping"; continue
  fi
  echo "== testing $name"
  # avg_ts in llama-bench's JSON output is the average tokens per second
  pp=$("$BENCH" -m "$f" -t 4 -p 64 -n 0 -r 2 -o json 2>/dev/null | python3 -c 'import json,sys; print("%.1f" % json.load(sys.stdin)[0]["avg_ts"])' 2>/dev/null)
  tg=$("$BENCH" -m "$f" -t 4 -p 0 -n 64 -r 2 -o json 2>/dev/null | python3 -c 'import json,sys; print("%.1f" % json.load(sys.stdin)[0]["avg_ts"])' 2>/dev/null)
  [[ -n "$tg" ]] || { echo "   test failed for $name"; continue; }
  keep=$(awk -v t="$tg" 'BEGIN{print (t>=8)?"yes, easily":(t>=5)?"yes":(t>=3.5)?"just about":"no - it will lag"}')
  printf "| %s | %s | %s | %s | %s | %s°C |\n" "$name" "$(numfmt --to=iec "$size")" "${pp:-?}" "$tg" "$keep" "$(temp)" >> "$RES"
  echo "   prompt ${pp:-?} tok/s, reply $tg tok/s"
  sleep 20   # let it cool a little so one model's heat doesn't slow the next
done

echo
cat "$RES"

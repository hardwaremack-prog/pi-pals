#!/usr/bin/env bash
# Pi Pals Pro setup: turns a Raspberry Pi 5 (4 GB) Pal into one you can talk to.
# Run on 64-bit Raspberry Pi OS Lite (Bookworm or newer), after the normal Pal setup:
#   sudo ./install-pro.sh                 default brain: Qwen2.5 1.5B
#   sudo PAL_MODEL=fast ./install-pro.sh  quickest replies: Qwen2.5 0.5B
#   sudo PAL_MODEL=smart ./install-pro.sh smartest that fits: Llama 3.2 3B (slower)
#
# Installs: llama.cpp (the AI brain), whisper.cpp (hearing), Piper (speaking),
# and two services - pal-llm (keeps the model loaded) and pal-voice (the button loop).
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "Run with sudo: sudo ./install-pro.sh"; exit 1; }
HERE="$(cd "$(dirname "$0")" && pwd)"
P=/opt/pal
M=$P/models
HF=https://huggingface.co

case "${PAL_MODEL:-default}" in
  fast)  MODEL_FILE=qwen2.5-0.5b-instruct-q4_k_m.gguf; MODEL_URL=$HF/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/$MODEL_FILE ;;
  smart) MODEL_FILE=Llama-3.2-3B-Instruct-Q4_K_M.gguf;  MODEL_URL=$HF/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main/$MODEL_FILE ;;
  *)     MODEL_FILE=qwen2.5-1.5b-instruct-q4_k_m.gguf; MODEL_URL=$HF/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/$MODEL_FILE ;;
esac

echo "== packages"
apt-get update
apt-get install -y git cmake build-essential libcurl4-openssl-dev alsa-utils \
  python3-venv python3-gpiozero curl

mkdir -p $M /etc/pal

echo "== llama.cpp (AI brain) - takes ~15 minutes to build on a Pi 5"
[[ -d $P/llama.cpp ]] || git clone --depth 1 https://github.com/ggml-org/llama.cpp $P/llama.cpp
cmake -S $P/llama.cpp -B $P/llama.cpp/build -DCMAKE_BUILD_TYPE=Release -DLLAMA_CURL=OFF
cmake --build $P/llama.cpp/build -j4 --target llama-server llama-bench llama-cli

echo "== whisper.cpp (hearing)"
[[ -d $P/whisper.cpp ]] || git clone --depth 1 https://github.com/ggml-org/whisper.cpp $P/whisper.cpp
cmake -S $P/whisper.cpp -B $P/whisper.cpp/build -DCMAKE_BUILD_TYPE=Release
cmake --build $P/whisper.cpp/build -j4 --target whisper-cli

echo "== Piper (speaking)"
python3 -m venv --system-site-packages $P/venv
$P/venv/bin/pip install --upgrade pip piper-tts

fetch() { [[ -s "$2" ]] || curl -fL --retry 3 -o "$2" "$1"; }
echo "== models"
fetch "$MODEL_URL" "$M/$MODEL_FILE"
fetch "$HF/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin" "$M/ggml-base.en.bin"
V=$HF/rhasspy/piper-voices/resolve/main/en/en_US/amy/low
fetch "$V/en_US-amy-low.onnx" "$M/en_US-amy-low.onnx"
fetch "$V/en_US-amy-low.onnx.json" "$M/en_US-amy-low.onnx.json"

install -m 755 "$HERE/pal-voice.py" /usr/local/bin/pal-voice
install -m 755 "$HERE/pal-bench.sh" /usr/local/bin/pal-bench
if [[ ! -f /etc/pal/voice.env ]]; then
  cat > /etc/pal/voice.env <<EOF
# Pi Pal Pro settings. Restart after changes:  sudo systemctl restart pal-llm pal-voice
PAL_CHARACTER=pip
PAL_MODEL_FILE=$M/$MODEL_FILE
PAL_BUTTON_PIN=17
# Run 'arecord -l' and 'aplay -l' to find your mic and speaker, e.g. plughw:1,0
PAL_MIC=default
PAL_SPEAKER=default
EOF
fi

cp "$HERE/pal-llm.service" "$HERE/pal-voice.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now pal-llm.service pal-voice.service

echo
echo "Done. Hold the button and talk. To test over SSH:  pal-voice --keyboard"
echo "To measure every model's speed on this Pal:     pal-bench"

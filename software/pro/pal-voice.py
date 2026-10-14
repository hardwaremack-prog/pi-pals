#!/usr/bin/env python3
"""
pal-voice: talk to your Pi Pal Pro. Everything runs on the Pal itself, with no internet.

  Hold the button (or press Enter)  ->  speak  ->  let go
  whisper.cpp turns your voice into text       (speech-to-text)
  llama.cpp's small AI model writes an answer  (the "brain")
  Piper reads the answer out loud              (text-to-speech)

The answer is spoken sentence by sentence while the AI is still writing, so the Pal starts
talking after the first sentence instead of waiting for the whole reply.

The heart LED shows what it's doing (via /run/pal/mood, read by pal-heartbeat.py):
blue = listening, purple swirl = thinking, cyan flicker = talking.

Usage:
  pal-voice.py                     button on GPIO17 (pin 11 to pin 9/GND)
  pal-voice.py --keyboard          press Enter to start and stop talking (testing over SSH)
  pal-voice.py --text              type instead of talk; still speaks the answers
  pal-voice.py --pal dot           choose the character (pip, dot, penny, sunny, gourdy,
                                   gobbles, flurry, hop)
Settings can also come from /etc/pal/voice.env (see install-pro.sh).
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request

LLM_URL = os.environ.get("PAL_LLM_URL", "http://127.0.0.1:8080/v1/chat/completions")
WHISPER_BIN = os.environ.get("PAL_WHISPER_BIN", "/opt/pal/whisper.cpp/build/bin/whisper-cli")
WHISPER_MODEL = os.environ.get("PAL_WHISPER_MODEL", "/opt/pal/models/ggml-base.en.bin")
PIPER_VOICE = os.environ.get("PAL_PIPER_VOICE", "/opt/pal/models/en_US-amy-low.onnx")
MIC_DEVICE = os.environ.get("PAL_MIC", "default")
SPEAKER_DEVICE = os.environ.get("PAL_SPEAKER", "default")
BUTTON_PIN = int(os.environ.get("PAL_BUTTON_PIN", "17"))
MOOD_FILE = "/run/pal/mood"
MAX_RECORD_S = 15
HISTORY_TURNS = 6          # remember the last few exchanges; small models get confused by more

PERSONALITIES = {
    "pip":     "Pip the Chick, a cheerful, curious little chick who loves spring and new things",
    "dot":     "Dot the Dino, a friendly, slightly clumsy dinosaur who loves facts about nature",
    "penny":   "Penny the Piggy, a warm, thrifty piggy who loves saving and making plans",
    "sunny":   "Sunny, a bright, upbeat little sun who loves summer and encouraging people",
    "gourdy":  "Gourdy the Pumpkin, a playful pumpkin who is a tiny bit spooky and loves fall",
    "gobbles": "Gobbles the Turkey, a grateful, chatty turkey who loves food and family",
    "flurry":  "Flurry the Snowman, a calm, gentle snowman who loves winter and cozy things",
    "hop":     "Hop the Bunny, a bouncy, kind bunny who loves games and surprises",
}


def system_prompt(pal):
    who = PERSONALITIES.get(pal, PERSONALITIES["pip"])
    return (f"You are {who}. You live inside a small figurine with a tiny computer in it. "
            "You are talking out loud, so answer in one to three short, simple sentences with "
            "no lists, no emoji and no markdown. Be kind, honest and family-friendly. If you are "
            "not sure about something, say so instead of guessing.")


# ---------------------------------------------------------------- LED mood
def set_mood(mood):
    try:
        os.makedirs(os.path.dirname(MOOD_FILE), exist_ok=True)
        if mood:
            with open(MOOD_FILE, "w") as f:
                f.write(mood)
        elif os.path.exists(MOOD_FILE):
            os.remove(MOOD_FILE)
    except OSError:
        pass


# ---------------------------------------------------------------- listening
class Recorder:
    """Records 16 kHz mono WAV with arecord between start() and stop()."""

    def __init__(self):
        self.proc = None
        self.path = None

    def start(self):
        fd, self.path = tempfile.mkstemp(suffix=".wav", prefix="pal-")
        os.close(fd)
        self.proc = subprocess.Popen(
            ["arecord", "-q", "-D", MIC_DEVICE, "-f", "S16_LE", "-r", "16000", "-c", "1",
             "-d", str(MAX_RECORD_S), self.path])

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            self.proc.wait(timeout=3)
        self.proc = None
        return self.path


def transcribe(wav):
    """Speech to text with whisper.cpp. Returns '' if nothing was heard."""
    out = subprocess.run(
        [WHISPER_BIN, "-m", WHISPER_MODEL, "-f", wav, "-t", "4", "-nt", "-np", "-l", "en"],
        capture_output=True, text=True, timeout=60).stdout
    text = " ".join(line.strip() for line in out.splitlines()).strip()
    # whisper marks silence and noise like [BLANK_AUDIO] or (wind blowing)
    text = re.sub(r"\[[^\]]*\]|\([^)]*\)", "", text).strip()
    return text


# ---------------------------------------------------------------- thinking
def ask_llm(messages):
    """Streams the answer from llama-server and yields whole sentences as they finish."""
    body = json.dumps({"messages": messages, "stream": True, "temperature": 0.7,
                       "max_tokens": 160}).encode()
    req = urllib.request.Request(LLM_URL, body, {"Content-Type": "application/json"})
    buf = ""
    with urllib.request.urlopen(req, timeout=120) as resp:
        for raw in resp:
            line = raw.decode("utf-8", "ignore").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                delta = json.loads(data)["choices"][0]["delta"].get("content") or ""
            except (ValueError, KeyError, IndexError):
                continue
            buf += delta
            # Hand over each finished sentence straight away.
            # (very short bits like "Oh!" are joined to the next sentence so it sounds natural)
            while True:
                m = next((m for m in re.finditer(r"[.!?](\s|$)", buf) if m.end() >= 12), None)
                if not m:
                    break
                yield buf[:m.end()].strip()
                buf = buf[m.end():]
    if buf.strip():
        yield buf.strip()


# ---------------------------------------------------------------- talking
class Voice:
    def __init__(self):
        from piper import PiperVoice
        self.voice = PiperVoice.load(PIPER_VOICE)
        self.rate = self.voice.config.sample_rate

    def _pcm(self, text):
        v = self.voice
        if hasattr(v, "synthesize_stream_raw"):           # piper-tts 1.2
            yield from v.synthesize_stream_raw(text)
        else:                                             # piper-tts 1.3+
            for chunk in v.synthesize(text):
                yield chunk.audio_int16_bytes

    def say(self, text):
        text = re.sub(r"[*_#`>]", "", text)               # never read markdown symbols aloud
        player = subprocess.Popen(
            ["aplay", "-q", "-D", SPEAKER_DEVICE, "-r", str(self.rate), "-f", "S16_LE",
             "-t", "raw", "-c", "1", "-"], stdin=subprocess.PIPE)
        for pcm in self._pcm(text):
            player.stdin.write(pcm)
        player.stdin.close()
        player.wait()


# ---------------------------------------------------------------- one exchange
def reply(history, user_text, voice, pal):
    history.append({"role": "user", "content": user_text})
    messages = [{"role": "system", "content": system_prompt(pal)}] + history[-HISTORY_TURNS * 2:]
    set_mood("thinking")
    t0 = time.monotonic()
    first = None
    answer = []
    try:
        for sentence in ask_llm(messages):
            if first is None:
                first = time.monotonic() - t0
            print(f"  {pal}: {sentence}", flush=True)
            answer.append(sentence)
            set_mood("speaking")
            if voice:
                voice.say(sentence)
            set_mood("thinking")
    except OSError as e:
        print(f"  (the AI isn't answering: {e}. Is pal-llm running?)")
        answer = ["Hmm, my brain is still waking up. Try again in a moment."]
        if voice:
            voice.say(answer[0])
    history.append({"role": "assistant", "content": " ".join(answer)})
    set_mood(None)
    if first is not None:
        print(f"  (first words after {first:.1f}s)")


def main():
    ap = argparse.ArgumentParser(description="Talk to a Pi Pal Pro")
    ap.add_argument("--pal", default=os.environ.get("PAL_CHARACTER", "pip"),
                    choices=sorted(PERSONALITIES))
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--keyboard", action="store_true", help="Enter to start/stop talking")
    mode.add_argument("--text", action="store_true", help="type instead of talking")
    ap.add_argument("--quiet", action="store_true", help="don't speak (print only)")
    args = ap.parse_args()

    voice = None if args.quiet else Voice()
    history = []
    rec = Recorder()

    def heard_one(wav):
        set_mood("thinking")
        t0 = time.monotonic()
        text = transcribe(wav)
        os.remove(wav)
        if not text:
            set_mood(None)
            print("  (didn't catch that)")
            return
        print(f"you: {text}   ({time.monotonic() - t0:.1f}s to hear)")
        reply(history, text, voice, args.pal)

    print(f"{args.pal.title()} is ready.")
    try:
        if args.text:
            while True:
                text = input("you: ").strip()
                if text:
                    reply(history, text, voice, args.pal)
        elif args.keyboard:
            while True:
                input("[Enter] to talk ")
                set_mood("listening")
                rec.start()
                input("  listening... [Enter] when done ")
                heard_one(rec.stop())
        else:
            from gpiozero import Button
            button = Button(BUTTON_PIN, pull_up=True, bounce_time=0.05)
            while True:
                button.wait_for_press()
                set_mood("listening")
                rec.start()
                button.wait_for_release(timeout=MAX_RECORD_S)
                heard_one(rec.stop())
    except (KeyboardInterrupt, EOFError):
        print()
    finally:
        rec.stop()
        set_mood(None)


if __name__ == "__main__":
    sys.exit(main())

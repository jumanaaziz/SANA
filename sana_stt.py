#!/usr/bin/env python3
"""
sana_stt.py — SANA Speech-to-Text (faster-whisper)
====================================================
Mic     : INMP441 → arecord plughw:0,0
Engine  : faster-whisper small (change to medium for better accuracy)
Trigger : TTP223 touch GPIO17

Supported speech patterns:
    Arabic:
        فصل أربعة وأربعين       → Classroom 44
        مختبر خمسة وثلاثين      → Lab 35
        مختبر عشرين             → Lab 20
        مختبر خمسة              → Lab 5
        مكتب خمسة وأربعين       → Office 45
        حمام                    → Bathroom
        وحدة تقنية ثمانية وثلاثين → IT Unit 38

    English:
        class 44                → Classroom 44
        lab 20                  → Lab 20
        office 45               → Office 45
        bathroom                → Bathroom
        it unit 38              → IT Unit 38
"""

import re
import time
import queue
import threading
import subprocess

from faster_whisper import WhisperModel
from gpiozero import Button

# ── CONFIG ────────────────────────────────────────────────────────────────────
TOUCH_PIN          = 17
MIC_DEVICE         = "plughw:0,0"
ACTIVE_RECORD_SECS = 5
POST_TTS_DELAY     = 4.0
TMP_WAV            = "/tmp/sana_voice.wav"
WHISPER_MODEL_SIZE = "small"   # change to "medium" for better compound numbers

# ── RESULT QUEUE ──────────────────────────────────────────────────────────────
stt_result_queue: queue.Queue = queue.Queue()
_mic_lock = threading.Lock()

# ── ARABIC NUMBER WORDS → DIGITS ──────────────────────────────────────────────
# Singles
ONES = {
    "صفر": 0, "واحد": 1, "اثنين": 2, "اثنان": 2, "ثلاثة": 3,
    "أربعة": 4, "اربعة": 4, "خمسة": 5, "ستة": 6, "سبعة": 7,
    "ثمانية": 8, "تسعة": 9, "عشرة": 10,
    "أحد عشر": 11, "احد عشر": 11,
    "اثنا عشر": 12, "اثني عشر": 12,
    "ثلاثة عشر": 13, "أربعة عشر": 14,
    "خمسة عشر": 15, "ستة عشر": 16,
    "سبعة عشر": 17, "ثمانية عشر": 18, "تسعة عشر": 19,
}

TENS = {
    "عشرون": 20, "عشرين": 20,
    "ثلاثون": 30, "ثلاثين": 30,
    "أربعون": 40, "أربعين": 40, "اربعين": 40,
    "خمسون": 50, "خمسين": 50,
    "ستون": 60, "ستين": 60,
    "سبعون": 70, "سبعين": 70,
    "ثمانون": 80, "ثمانين": 80,
    "تسعون": 90, "تسعين": 90,
}

def _normalize(text: str) -> str:
    """Normalize Arabic text — remove diacritics and normalize alef."""
    text = re.sub(r'[\u064B-\u065F]', '', text)   # remove diacritics
    text = text.replace('أ', 'ا').replace('إ', 'ا').replace('آ', 'ا')
    text = text.replace('ة', 'ه')
    return text.strip()


def words_to_number(text: str) -> str:
    """
    Convert Arabic number words to digits in text.
    Handles:
      - Simple: "خمسة" → "5"
      - Tens: "عشرين" → "20"
      - Compound: "خمسة وعشرين" → "25"
      - Mixed: "مختبر خمسة وعشرين" → "مختبر 25"

    Strategy: scan for tens, check if preceded by ones word + و
    """
    normalized = _normalize(text)

    # ── Step 1: compound numbers (ones + و + tens) ────────────────────────────
    # Pattern: <one_word> و <ten_word>  OR  <one_word> و<ten_word>
    for t_word, t_val in sorted(TENS.items(), key=lambda x: -len(x[0])):
        for o_word, o_val in sorted(ONES.items(), key=lambda x: -len(x[0])):
            if o_val == 0:
                continue
            n_t = _normalize(t_word)
            n_o = _normalize(o_word)
            # Try with space after و and without
            for pattern in [f"{n_o} و {n_t}", f"{n_o} و{n_t}", f"{n_o} وَ{n_t}"]:
                if pattern in normalized:
                    result = str(t_val + o_val)
                    # Replace in original text too
                    for orig_sep in [f" و ", f" و"]:
                        candidate = o_word + orig_sep + t_word
                        text = text.replace(candidate, result)
                    normalized = normalized.replace(pattern, result)
                    break

    # ── Step 2: simple tens ───────────────────────────────────────────────────
    for t_word, t_val in sorted(TENS.items(), key=lambda x: -len(x[0])):
        n_t = _normalize(t_word)
        if n_t in normalized:
            text = text.replace(t_word, str(t_val))
            normalized = normalized.replace(n_t, str(t_val))

    # ── Step 3: simple ones ───────────────────────────────────────────────────
    for o_word, o_val in sorted(ONES.items(), key=lambda x: -len(x[0])):
        n_o = _normalize(o_word)
        if n_o in normalized:
            text = text.replace(o_word, str(o_val))
            normalized = normalized.replace(n_o, str(o_val))

    return text


# ── ROOM TYPE KEYWORDS ────────────────────────────────────────────────────────
ROOM_TYPE_MAP = [
    (["فصل", "قاعة", "كلاس", "class"],            "Classroom"),
    (["مختبر", "معمل", "لاب", "lab"],              "Lab"),
    (["مكتب", "اوفيس", "office"],                  "Office"),
    (["حمام", "دورة مياه", "مرحاض", "bathroom"],   "Bathroom"),
    (["وحدة تقنية", "تقنية المعلومات", "it unit"], "IT Unit"),
    (["غرفة مشروع", "مشروع تخرج", "gp"],           "GP Experiment Room"),
]


def _extract_type(text: str) -> str:
    tl = _normalize(text.lower())
    for keywords, eng in ROOM_TYPE_MAP:
        for kw in keywords:
            if _normalize(kw) in tl:
                return eng
    return ""


def _extract_number(text: str) -> str:
    # Western digits
    hits = re.findall(r'\d+', text)
    if hits:
        return hits[0]
    # Arabic-Indic ٠١٢٣٤٥٦٧٨٩
    indic = re.findall(r'[٠-٩]+', text)
    if indic:
        return indic[0].translate(str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789'))
    return ""


def _suffix_score(text: str, room_name: str) -> int:
    has_a = "أ" in text or " a" in text.lower()
    has_b = "ب" in text or " b" in text.lower()
    if has_a and room_name.endswith(" A"): return 20
    if has_b and room_name.endswith(" B"): return 20
    if has_a and room_name.endswith(" B"): return -20
    if has_b and room_name.endswith(" A"): return -20
    return 0


def match_room(raw_text: str, map_data: dict) -> str:
    """
    Convert spoken Arabic/English to exact map.json room name.
    Pipeline:
        1. Convert Arabic number words → digits
        2. Extract type + number
        3. Score against rooms
    """
    # Step 1 — number words → digits
    text = words_to_number(raw_text.strip())
    print(f"[STT] After conversion: '{text}'", flush=True)

    rooms = map_data.get("rooms", [])

    # Step 2 — direct fuzzy match (English)
    tl = _normalize(text.lower())
    for room in rooms:
        rl = _normalize(room["name"].lower())
        if rl in tl or tl in rl:
            return room["name"]

    # Step 3 — extract type + number
    room_type   = _extract_type(text)
    room_number = _extract_number(text)
    print(f"[STT] type='{room_type}' number='{room_number}'", flush=True)

    if not room_type and not room_number:
        return ""

    # Bathroom — no number needed
    if room_type == "Bathroom":
        for room in rooms:
            if room["name"] == "Bathroom":
                return room["name"]
        return ""

    # Score rooms
    candidates = []
    for room in rooms:
        name  = room["name"]
        score = 0

        if room_type:
            if not name.startswith(room_type):
                continue
            score += 50

        if room_number:
            name_nums = re.findall(r'\d+', name)
            if not name_nums or name_nums[0] != room_number:
                continue
            score += 50

        score += _suffix_score(text, name)
        candidates.append((score, name))

    # Number-only fallback
    if not candidates and room_number and not room_type:
        for room in rooms:
            name = room["name"]
            name_nums = re.findall(r'\d+', name)
            if name_nums and name_nums[0] == room_number:
                candidates.append((30 + _suffix_score(text, name), name))

    if not candidates:
        return ""

    candidates.sort(key=lambda x: x[0], reverse=True)
    best = candidates[0][1]
    print(f"[STT] Matched: '{best}'", flush=True)
    return best


# ── RECORDING ─────────────────────────────────────────────────────────────────

def _record(seconds: int) -> bool:
    for attempt in range(3):
        try:
            subprocess.run([
                "arecord", "-D", MIC_DEVICE,
                "-f", "S16_LE",
                "-r", "16000",
                "-c", "1",
                "-d", str(seconds),
                TMP_WAV,
            ], check=True, capture_output=True)
            return True
        except Exception as e:
            print(f"[STT] arecord attempt {attempt+1}: {e}", flush=True)
            time.sleep(0.5)
    return False


def _transcribe(whisper: WhisperModel) -> str:
    try:
        segments, info = whisper.transcribe(
            TMP_WAV,
            beam_size=5,
            language="ar",
            vad_filter=True,
            condition_on_previous_text=False,
        )
        text = " ".join(seg.text.strip() for seg in segments).strip()
        print(f"[STT] Lang={info.language} Raw='{text}'", flush=True)
        return text
    except Exception as e:
        print(f"[STT] transcribe error: {e}", flush=True)
        return ""


def _record_and_transcribe(seconds: int, whisper: WhisperModel) -> str:
    with _mic_lock:
        if not _record(seconds):
            return ""
        return _transcribe(whisper)


# ── STT ENGINE ────────────────────────────────────────────────────────────────

class STTEngine:

    def __init__(self, speak_callback=None, pause_callback=None,
                 resume_callback=None, map_data=None):
        self._running          = False
        self._active_listening = False
        self._listen_lock      = threading.Lock()
        self._speak            = speak_callback  or (lambda t: print(f"[TTS] {t}"))
        self._pause            = pause_callback  or (lambda: None)
        self._resume           = resume_callback or (lambda: None)
        self._map_data         = map_data or {}

        print(f"[STT] Loading Whisper {WHISPER_MODEL_SIZE}...", flush=True)
        self._whisper = WhisperModel(
            WHISPER_MODEL_SIZE,
            device="cpu",
            compute_type="int8",
        )
        print("[STT] Whisper ready ✅", flush=True)

        self._button = Button(TOUCH_PIN, pull_up=False, bounce_time=0.1)
        self._button.when_pressed = self._on_touch
        print("[STT] Touch sensor ready on GPIO17", flush=True)

    def _on_touch(self):
        print("[STT] Touch triggered!", flush=True)
        if not self._active_listening:
            threading.Thread(
                target=self._active_listen,
                kwargs={"trigger": "touch"},
                daemon=True,
            ).start()

    def _active_listen(self, trigger: str = "touch"):
        with self._listen_lock:
            if self._active_listening:
                return
            self._active_listening = True

        try:
            self._pause()
            time.sleep(0.3)

            self._speak("ما هي وجهتك؟")
            time.sleep(POST_TTS_DELAY)

            print("[STT] 🎤 Listening... speak now!", flush=True)
            raw_text = _record_and_transcribe(ACTIVE_RECORD_SECS, self._whisper)
            print(f"[STT] Got: '{raw_text}'", flush=True)

            if not raw_text:
                self._speak("لم أسمع شيئاً، حاول مرة أخرى")
                return

            english_room = match_room(raw_text, self._map_data)

            if english_room:
                print(f"[STT] Room: '{english_room}'", flush=True)
                stt_result_queue.put({
                    "type":         "navigation",
                    "text":         raw_text,
                    "english_room": english_room,
                    "trigger":      trigger,
                })
            else:
                self._speak("لم أجد هذا المكان، قل مثلاً: فصل أربعة وأربعين، أو مختبر عشرين")

        except Exception as e:
            print(f"[STT] Error: {e}", flush=True)
            self._speak("حدث خطأ، حاول مرة أخرى")

        finally:
            self._resume()
            with self._listen_lock:
                self._active_listening = False

    def listen_once(self) -> str:
        print("[STT] 🎤 Listening for yes/no...", flush=True)
        return _record_and_transcribe(4, self._whisper)

    def start(self):
        self._running = True
        print("[STT] Engine started — touch GPIO17 to navigate", flush=True)

    def stop(self):
        self._running = False
        try:
            self._button.close()
        except Exception:
            pass
        print("[STT] Engine stopped", flush=True)

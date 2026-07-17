#!/usr/bin/env python3
"""
Lumi Startup — Name + Mode Selection
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Uses VOSK for offline speech recognition (already on your Pi)
Model: vosk-model-small-en-us-0.15

Flow:
  1. Lumi asks name — child speaks — VOSK recognizes offline
  2. Name saved to profile
  3. Lumi asks mode — child says "online" or "offline"
     OR presses RIGHT (online) / LEFT (offline)
  4. Correct curriculum launches
"""

import os, json, time, queue, threading
from pathlib import Path
from datetime import datetime

# ── VOSK offline speech recognition ───────────────────────────
try:
    import vosk
    import sounddevice as sd
    VOSK_OK = True
except ImportError:
    VOSK_OK = False
    print("[WARN] vosk or sounddevice not installed")

# ── Fallback: Google STT via SpeechRecognition ─────────────────
try:
    import speech_recognition as sr
    SR_OK = True
except ImportError:
    SR_OK = False

# ══════════════════════════════════════════════════════════════
#  VOSK SETUP
# ══════════════════════════════════════════════════════════════

# Path to your already-downloaded Vosk model on the Pi
VOSK_MODEL_PATH = os.path.expanduser("~/Desktop/vosk-model-small-en-us-0.15")

_vosk_model      = None
_vosk_model_lock = threading.Lock()

def load_vosk_model():
    """Load Vosk model once and cache it."""
    global _vosk_model
    if not VOSK_OK:
        return None
    if _vosk_model is not None:
        return _vosk_model
    with _vosk_model_lock:
        if not os.path.exists(VOSK_MODEL_PATH):
            print(f"[VOSK] Model not found at {VOSK_MODEL_PATH}")
            return None
        print(f"[VOSK] Loading model from {VOSK_MODEL_PATH} ...")
        try:
            vosk.SetLogLevel(-1)   # suppress noisy logs
            _vosk_model = vosk.Model(VOSK_MODEL_PATH)
            print("[VOSK] Model loaded ✓")
        except Exception as e:
            print(f"[VOSK] Failed to load: {e}")
            _vosk_model = None
    return _vosk_model


def listen_vosk(timeout=8, sample_rate=16000):
    """
    Listen using Vosk offline STT.
    Returns recognized text or empty string.
    """
    model = load_vosk_model()
    if model is None:
        return ""

    q = queue.Queue()

    def _callback(indata, frames, time_info, status):
        q.put(bytes(indata))

    rec  = vosk.KaldiRecognizer(model, sample_rate)
    text = ""

    try:
        with sd.RawInputStream(
            samplerate=sample_rate,
            blocksize=8000,
            dtype='int16',
            channels=1,
            callback=_callback,
        ):
            print("  [VOSK] Listening...", flush=True)
            deadline = time.time() + timeout
            silence_start = None
            SILENCE_TIMEOUT = 1.8   # stop after 1.8s silence

            while time.time() < deadline:
                try:
                    data = q.get(timeout=0.1)
                except queue.Empty:
                    continue

                if rec.AcceptWaveform(data):
                    import json as _json
                    result = _json.loads(rec.Result())
                    word   = result.get("text","").strip()
                    if word:
                        text = word
                        break   # got a complete utterance
                else:
                    # Check partial result for silence detection
                    import json as _json
                    partial = _json.loads(rec.PartialResult()).get("partial","")
                    if partial:
                        silence_start = None   # speech detected
                    else:
                        if silence_start is None and text:
                            silence_start = time.time()
                        elif silence_start and time.time() - silence_start > SILENCE_TIMEOUT:
                            break   # silence after speech — stop

            # Get any remaining partial result
            if not text:
                import json as _json
                final = _json.loads(rec.FinalResult()).get("text","").strip()
                if final:
                    text = final

    except Exception as e:
        print(f"  [VOSK] Error: {e}")

    if text:
        print(f"  [VOSK] Heard: '{text}'")
    return text.lower().strip()


def listen_google(timeout=7):
    """Fallback: Google STT (online)."""
    if not SR_OK:
        return input("\n[YOU] ").strip().lower()
    r = sr.Recognizer()
    r.energy_threshold         = 250
    r.pause_threshold          = 0.7
    r.dynamic_energy_threshold = True
    print("  [MIC] Listening...", flush=True)
    try:
        with sr.Microphone() as src:
            r.adjust_for_ambient_noise(src, duration=0.2)
            audio = r.listen(src, timeout=timeout, phrase_time_limit=6)
        text = r.recognize_google(audio).lower().strip()
        print(f"  [YOU] {text}")
        return text
    except sr.WaitTimeoutError:  return ""
    except sr.UnknownValueError: return ""
    except Exception as e:
        print(f"  [SR] {e}"); return ""


def listen_best(timeout=8):
    """
    Try Vosk first (offline, best for Pi).
    Fall back to Google STT if Vosk fails.
    """
    if VOSK_OK and os.path.exists(VOSK_MODEL_PATH):
        result = listen_vosk(timeout=timeout)
        if result:
            return result
        print("  [VOSK] No result — trying Google STT")

    return listen_google(timeout=timeout)


# ══════════════════════════════════════════════════════════════
#  NAME EXTRACTION HELPERS
# ══════════════════════════════════════════════════════════════
def clean_name(raw: str) -> str:
    """Extract first name from raw speech."""
    raw = raw.lower().strip()
    
    # Remove filler phrases
    for filler in [
        "my name is","i am","i'm","call me","it is","its",
        "the name is","name is","they call me","you can call me",
        "i go by","just call me",
    ]:
        raw = raw.replace(filler, "").strip()
    
    # Take first word only
    words = raw.split()
    if not words:
        return ""
    
    name = words[0].strip(".,!?'\"")
    
    # Must be at least 2 chars and alphabetic
    if len(name) >= 2 and name.isalpha():
        return name.capitalize()
    
    return ""


def confirm_name(name: str, speak_fn, listen_fn) -> bool:
    """Ask child to confirm their name. Returns True if confirmed."""
    speak_fn(f"I heard {name}. Is that correct? Say yes or no.")
    ans = listen_fn(timeout=6)
    return any(w in ans for w in ["yes","yeah","yep","correct","right","sure","ok","yea"])


# ══════════════════════════════════════════════════════════════
#  PROGRESS STORAGE
# ══════════════════════════════════════════════════════════════
DATA_FILE = Path.home() / ".braille_lumi" / "progress.json"

def _load():
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    if DATA_FILE.exists():
        with open(DATA_FILE) as f:
            return json.load(f)
    return {}

def _save_db(data):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def get_or_create_profile(name: str):
    """Get existing profile or create new one. Returns (profile, data, is_new)."""
    data = _load()
    key  = name.strip().lower()
    now  = datetime.now().isoformat()

    if key not in data:
        data[key] = {
            "name":            name.strip().capitalize(),
            "created":         now,
            "last_seen":       now,
            "total_sessions":  1,
            "stars":           0,
            "alpha_pos":       0,
            "number_pos":      0,
            "chapter":         0,
            "alpha_done":      [],
            "numbers_done":    [],
            "quiz_scores":     [],
        }
        _save_db(data)
        print(f"  [PROFILE] New profile created: {data[key]['name']}")
        return data[key], data, True
    else:
        data[key]["last_seen"]      = now
        data[key]["total_sessions"] = data[key].get("total_sessions", 0) + 1
        _save_db(data)
        p = data[key]
        print(f"  [PROFILE] Returning: {p['name']} | "
              f"stars={p.get('stars',0)} | "
              f"letters={len(p.get('alpha_done',[]))} | "
              f"numbers={len(p.get('numbers_done',[]))}")
        return p, data, False

def save_profile(data, profile):
    data[profile["name"].lower()] = profile
    _save_db(data)

def print_all_profiles():
    data = _load()
    if not data:
        print("  [No profiles yet]")
        return
    print(f"\n  Saved profiles ({len(data)}):")
    for k, p in data.items():
        print(f"    • {p['name']:12} ⭐{p.get('stars',0):4} | "
              f"Letters {len(p.get('alpha_done',[]))}/26 | "
              f"Numbers {len(p.get('numbers_done',[]))}/100 | "
              f"Sessions {p.get('total_sessions',0)}")


# ══════════════════════════════════════════════════════════════
#  STARTUP FLOW — ask name then mode
# ══════════════════════════════════════════════════════════════
def run_startup(speak_fn, wait_btn_fn, btn_left, btn_right):
    """
    Full startup flow:
      1. Ask name (with retry + confirmation)
      2. Save profile
      3. Ask mode (voice OR button)
    
    Returns: (profile, data, offline: bool)
    """

    # ── Step 1: Ask name ──────────────────────────────────────
    speak_fn("Hi there! I am Lumi, your braille learning friend. What is your name?")

    name    = ""
    attempts = 0

    while not name and attempts < 4:
        attempts += 1
        raw = listen_best(timeout=9)

        if raw:
            candidate = clean_name(raw)
            if candidate:
                # Confirm the name
                if confirm_name(candidate, speak_fn, listen_best):
                    name = candidate
                    speak_fn(f"Great! Hello {name}!")
                else:
                    speak_fn("No problem! What is your name? Please say it clearly.")
            else:
                speak_fn("I could not catch your name clearly. Please try again.")
        else:
            if attempts < 4:
                speak_fn("I did not hear anything. Please say your name.")
            else:
                speak_fn(
                    "I am having trouble hearing you. "
                    "I will call you my friend for now. "
                    "Press the right button to continue."
                )
                btn_right.clear()
                deadline = time.time() + 20
                while not btn_right.is_set() and time.time() < deadline:
                    time.sleep(0.05)
                name = "Friend"

    # ── Step 2: Save profile ──────────────────────────────────
    profile, data, is_new = get_or_create_profile(name)

    if is_new:
        speak_fn(
            f"Nice to meet you {profile['name']}! "
            f"I am going to help you learn braille!"
        )
    else:
        stars    = profile.get("stars", 0)
        letters  = len(profile.get("alpha_done", []))
        numbers  = len(profile.get("numbers_done", []))
        sessions = profile.get("total_sessions", 1)
        speak_fn(
            f"Welcome back {profile['name']}! "
            f"Great to see you again. "
            f"You have {stars} stars, "
            f"know {letters} letters and {numbers} numbers, "
            f"and this is session number {sessions}. "
            f"Let us keep learning!"
        )

    # ── Step 3: Ask mode ──────────────────────────────────────
    speak_fn(
        f"Now {profile['name']}, would you like online mode or offline mode? "
        f"In online mode I use a smart AI to talk with you — you need internet. "
        f"In offline mode I guide you with the buttons — no internet needed. "
        f"Say online or offline, or press the right button for online "
        f"and the left button for offline."
    )

    # Listen for voice AND watch buttons simultaneously
    mode_result  = [None]
    mode_stop    = threading.Event()

    def _listen_for_mode():
        """Background thread — listen for voice mode selection."""
        raw = listen_best(timeout=12)
        if mode_stop.is_set():
            return
        if "offline" in raw or raw in ["off","button","buttons","no internet"]:
            mode_result[0] = "offline"
        elif "online" in raw or raw in ["on","internet","voice","ai"]:
            mode_result[0] = "online"
        else:
            mode_result[0] = None   # unclear
        mode_stop.set()

    t = threading.Thread(target=_listen_for_mode, daemon=True)
    btn_left.clear()
    btn_right.clear()
    t.start()

    deadline = time.time() + 15
    while time.time() < deadline and not mode_stop.is_set():
        if btn_right.is_set():
            mode_result[0] = "online"
            mode_stop.set()
            break
        if btn_left.is_set():
            mode_result[0] = "offline"
            mode_stop.set()
            break
        time.sleep(0.05)

    mode = mode_result[0]

    # If unclear voice response — ask once more with buttons only
    if mode is None:
        speak_fn(
            "I did not catch that. "
            "Press the RIGHT button for online, "
            "or the LEFT button for offline."
        )
        btn_left.clear()
        btn_right.clear()
        deadline2 = time.time() + 20
        while time.time() < deadline2:
            if btn_right.is_set(): mode = "online";  break
            if btn_left.is_set():  mode = "offline"; break
            time.sleep(0.05)

    # Default to offline if still nothing
    if mode is None:
        mode = "offline"
        speak_fn("Starting offline mode by default.")

    # ── Confirm mode to child ──────────────────────────────────
    offline = (mode == "offline")

    if offline:
        speak_fn(
            f"Offline mode it is {profile['name']}! "
            f"You will use the three buttons. "
            f"The right button moves you forward and confirms. "
            f"The left button goes back and repeats. "
            f"The middle button switches between chapters. "
            f"Chapter 1 is the alphabet from A to Z. "
            f"Chapter 2 is numbers from 1 to 100. "
            f"Chapter 3 is games. "
            f"When the dots on the device move, "
            f"put your finger on them and feel the braille pattern. "
            f"I will guide you through every single step. "
            f"Let us start!"
        )
    else:
        speak_fn(
            f"Online mode {profile['name']}! "
            f"Connecting to the smart AI assistant now. "
            f"You can speak naturally and I will listen. "
            f"Say goodbye any time to end the session."
        )

    return profile, data, offline
---DONE---


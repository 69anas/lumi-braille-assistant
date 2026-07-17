
#!/usr/bin/env python3
"""
Lumi — Smart Braille Learning Device  v9.2
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FIXED: Button polling instead of event detection
       Buttons: LEFT=GPIO19  RIGHT=GPIO26  MODE=GPIO20
"""

import os, json, time, threading, subprocess, tempfile
from pathlib import Path
from datetime import datetime

from lumi_startup import (
    run_startup, save_profile,
    print_all_profiles, VOSK_OK, VOSK_MODEL_PATH
)
from lumi_offline import (
    LumiOffline, BRAILLE_ALPHA, BRAILLE_DIGITS,
    NUMBER_INDICATOR, ALPHABET, NUMBERS
)
from lumi_online import LumiOnlineAgent

# ══════════════════════════════════════════════════════════════
#  CONFIG — EDIT THESE
# ══════════════════════════════════════════════════════════════
ELEVENLABS_API_KEY = "YOUR_ELEVENLABS_KEY"
ELEVENLABS_VOICE   = "Charlotte"
AGENT_ID           = "YOUR_AGENT_ID"

# ── Button pins (confirmed FREE from pin scan) ─────────────────
PIN_BTN_LEFT  = 19   # Physical pin 35
PIN_BTN_RIGHT = 26   # Physical pin 37
PIN_BTN_MODE  = 20   # Physical pin 38

# ── Solenoid pins ──────────────────────────────────────────────
LARGE_DOT_PINS = {1: 17, 2: 18, 3: 27, 4: 22, 5: 23, 6: 24}
SMALL_CELL_1   = {1: 4,  2: 7,  3: 8,  4: 9,  5: 10, 6: 11}
# Uncomment when wired:
# SMALL_CELL_2 = {1: 12, 2: 14, 3: 15, 4: 16, 5: 19, 6: 20}

CELL_PINS     = [SMALL_CELL_1]
ALL_SOLENOIDS = list(LARGE_DOT_PINS.values()) + list(SMALL_CELL_1.values())

DOT_HOLD_TIME = 3.0

# ══════════════════════════════════════════════════════════════
#  IMPORTS
# ══════════════════════════════════════════════════════════════
try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    print("[WARN] No GPIO — simulation mode")

try:
    import pygame
    pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=512)
    PYGAME_OK = True
except Exception:
    PYGAME_OK = False

try:
    from elevenlabs.client import ElevenLabs
    from elevenlabs import VoiceSettings
    _el_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
    EL_OK = (ELEVENLABS_API_KEY != "YOUR_ELEVENLABS_KEY")
except Exception:
    EL_OK = False

try:
    from gtts import gTTS
    GTTS_OK = True
except ImportError:
    GTTS_OK = False

try:
    import pyttsx3 as _pyttsx3_mod
    PYTTSX3_OK = True
except ImportError:
    PYTTSX3_OK = False

# ══════════════════════════════════════════════════════════════
#  GPIO SETUP
# ══════════════════════════════════════════════════════════════
def setup_gpio():
    if not GPIO_AVAILABLE:
        print("[SIM] Keyboard mode: L=left  R=right  M=mode  Enter")
        return
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    # Solenoids start LOW (off)
    for pin in ALL_SOLENOIDS:
        GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)
    # Buttons — just setup input, NO event detection
    for pin in [PIN_BTN_LEFT, PIN_BTN_RIGHT, PIN_BTN_MODE]:
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    print(f"[GPIO] Ready | L=GPIO{PIN_BTN_LEFT} R=GPIO{PIN_BTN_RIGHT} M=GPIO{PIN_BTN_MODE}")


# ══════════════════════════════════════════════════════════════
#  BUTTON POLLING — reads pins directly, no event detection
#  This is the fix — polling is reliable, events were not
# ══════════════════════════════════════════════════════════════
def wait_btn(timeout=45):
    """
    Poll buttons directly every 20ms.
    Returns 'left' / 'right' / 'mode' / 'timeout'.
    Waits for button release before returning to prevent double-firing.
    """
    if not GPIO_AVAILABLE:
        print("  [Buttons: L=left  R=right  M=mode  Enter]", flush=True)
        try:
            k = input().strip().lower()
            if k == 'l': return 'left'
            if k == 'm': return 'mode'
            return 'right'
        except:
            return 'timeout'

    deadline   = time.time() + timeout
    DEBOUNCE   = 0.05   # 50ms debounce confirmation

    while time.time() < deadline:
        # Read all three pins
        l = GPIO.input(PIN_BTN_LEFT)
        r = GPIO.input(PIN_BTN_RIGHT)
        m = GPIO.input(PIN_BTN_MODE)

        # LEFT pressed (reads 0 when pressed — active low)
        if l == 0:
            time.sleep(DEBOUNCE)
            if GPIO.input(PIN_BTN_LEFT) == 0:
                print("  [BTN] LEFT")
                # Wait for release
                while GPIO.input(PIN_BTN_LEFT) == 0:
                    time.sleep(0.01)
                time.sleep(0.05)
                return 'left'

        # RIGHT pressed
        if r == 0:
            time.sleep(DEBOUNCE)
            if GPIO.input(PIN_BTN_RIGHT) == 0:
                print("  [BTN] RIGHT")
                while GPIO.input(PIN_BTN_RIGHT) == 0:
                    time.sleep(0.01)
                time.sleep(0.05)
                return 'right'

        # MODE pressed
        if m == 0:
            time.sleep(DEBOUNCE)
            if GPIO.input(PIN_BTN_MODE) == 0:
                print("  [BTN] MODE")
                while GPIO.input(PIN_BTN_MODE) == 0:
                    time.sleep(0.01)
                time.sleep(0.05)
                return 'mode'

        time.sleep(0.02)

    return 'timeout'


# Button events for run_startup compatibility
_btn_left  = threading.Event()
_btn_right = threading.Event()
_btn_mode  = threading.Event()

def poll_buttons_for_startup(timeout=15):
    """
    Used during startup mode selection.
    Polls buttons and sets Events so run_startup can detect them.
    Runs in background thread.
    """
    if not GPIO_AVAILABLE:
        return
    deadline = time.time() + timeout
    while time.time() < deadline:
        if GPIO.input(PIN_BTN_LEFT)  == 0:
            time.sleep(0.05)
            if GPIO.input(PIN_BTN_LEFT) == 0:
                _btn_left.set()
                while GPIO.input(PIN_BTN_LEFT) == 0: time.sleep(0.01)
                return
        if GPIO.input(PIN_BTN_RIGHT) == 0:
            time.sleep(0.05)
            if GPIO.input(PIN_BTN_RIGHT) == 0:
                _btn_right.set()
                while GPIO.input(PIN_BTN_RIGHT) == 0: time.sleep(0.01)
                return
        if GPIO.input(PIN_BTN_MODE)  == 0:
            time.sleep(0.05)
            if GPIO.input(PIN_BTN_MODE) == 0:
                _btn_mode.set()
                while GPIO.input(PIN_BTN_MODE) == 0: time.sleep(0.01)
                return
        time.sleep(0.02)


# ══════════════════════════════════════════════════════════════
#  HARDWARE — SOLENOID CONTROL
#  Large dots (pull-type): LOW = spring UP (shown), HIGH = pulled DOWN (hidden)
#  Small dots (push-type): HIGH = pushed UP (shown), LOW = dropped DOWN (hidden)
# ══════════════════════════════════════════════════════════════
_auto_clear_timer = None

def trigger_auto_clear(seconds=5.0):
    """Safety: cuts all power after X seconds to prevent overheating."""
    global _auto_clear_timer
    if _auto_clear_timer is not None:
        _auto_clear_timer.cancel()
    _auto_clear_timer = threading.Timer(seconds, do_clear)
    _auto_clear_timer.start()


def _sim(label, dots):
    d = set(dots)
    r = lambda a, b: ("●●" if a in d and b in d else
                      "●○" if a in d else "○●" if b in d else "○○")
    print(f"  [{label}]  {r(1,2)} | {r(3,4)} | {r(5,6)}")


def do_show_letter(letter):
    letter = letter.strip().lower()
    dots   = BRAILLE_ALPHA.get(letter, [])
    print(f"  [BRAILLE] Letter {letter.upper()} → dots {dots}")

    if not GPIO_AVAILABLE:
        _sim("LARGE", dots)
        _sim("CELL0", dots)
        return

    for dot in range(1, 7):
        if dot in dots:
            # SHOW dot
            if dot in LARGE_DOT_PINS:
                GPIO.output(LARGE_DOT_PINS[dot], GPIO.LOW)   # spring up
            if dot in SMALL_CELL_1:
                GPIO.output(SMALL_CELL_1[dot], GPIO.HIGH)    # push up
        else:
            # HIDE dot
            if dot in LARGE_DOT_PINS:
                GPIO.output(LARGE_DOT_PINS[dot], GPIO.HIGH)  # pull down
            if dot in SMALL_CELL_1:
                GPIO.output(SMALL_CELL_1[dot], GPIO.LOW)     # drop down

    trigger_auto_clear(DOT_HOLD_TIME + 1.0)


def do_show_word(word):
    word = word.strip().lower()[:5]
    print(f"  [BRAILLE] Word: {word.upper()}")
    for i, ch in enumerate(word):
        if i >= len(CELL_PINS): break
        dots = BRAILLE_ALPHA.get(ch, [])
        if not GPIO_AVAILABLE:
            _sim(f"CELL{i}", dots); continue
        for dot, pin in CELL_PINS[i].items():
            try:
                GPIO.output(pin, GPIO.HIGH if dot in dots else GPIO.LOW)
            except: pass
    trigger_auto_clear(7.0)


def do_show_number(n):
    try:
        n = int(str(n).strip())
    except (ValueError, TypeError):
        n = 0
    s        = str(n)
    patterns = [BRAILLE_DIGITS.get(d, []) for d in s]
    print(f"  [BRAILLE] Number {n} → {patterns}")

    if not GPIO_AVAILABLE:
        _sim("NUM_IND", NUMBER_INDICATOR)
        for i, dots in enumerate(patterns):
            _sim(f"CELL{i}", dots)
        return

    # Show number indicator on large display
    for dot in range(1, 7):
        if dot in LARGE_DOT_PINS:
            GPIO.output(LARGE_DOT_PINS[dot],
                        GPIO.LOW if dot in NUMBER_INDICATOR else GPIO.HIGH)
    time.sleep(0.5)

    # Show digit pattern on cells
    for i, dots in enumerate(patterns[:len(CELL_PINS)]):
        for dot, pin in CELL_PINS[i].items():
            try:
                GPIO.output(pin, GPIO.HIGH if dot in dots else GPIO.LOW)
            except: pass

    # Also show first digit on large display
    if patterns:
        for dot in range(1, 7):
            if dot in LARGE_DOT_PINS:
                GPIO.output(LARGE_DOT_PINS[dot],
                            GPIO.LOW if dot in patterns[0] else GPIO.HIGH)

    trigger_auto_clear(DOT_HOLD_TIME + 1.0)


def do_clear():
    """Cut power to all solenoids — safe resting state."""
    global _auto_clear_timer
    if _auto_clear_timer is not None:
        _auto_clear_timer.cancel()
        _auto_clear_timer = None
    if not GPIO_AVAILABLE:
        print("  [SIM] All solenoids off")
        return
    for pin in ALL_SOLENOIDS:
        try:
            GPIO.output(pin, GPIO.LOW)
        except: pass
    print("  [GPIO] All solenoids OFF — resting")


# ══════════════════════════════════════════════════════════════
#  TTS
# ══════════════════════════════════════════════════════════════
_stop_speaking = threading.Event()
_speaking_lock = threading.Lock()
_VOICE_CACHE   = {}


def _get_voice_id(name):
    if name in _VOICE_CACHE: return _VOICE_CACHE[name]
    voices = _el_client.voices.get_all().voices
    for v in voices:
        if v.name.lower() == name.lower():
            _VOICE_CACHE[name] = v.voice_id; return v.voice_id
    if voices:
        _VOICE_CACHE[name] = voices[0].voice_id; return voices[0].voice_id
    raise ValueError("No voices")


def _play_mp3(path):
    _stop_speaking.clear()
    pygame.mixer.music.load(path)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        if _stop_speaking.is_set():
            pygame.mixer.music.stop(); break
        time.sleep(0.04)
    try: pygame.mixer.music.unload()
    except: pass


def _tts_el(text):
    audio = _el_client.text_to_speech.convert(
        voice_id=_get_voice_id(ELEVENLABS_VOICE),
        text=text,
        model_id="eleven_turbo_v2",
        voice_settings=VoiceSettings(
            stability=0.50, similarity_boost=0.80,
            style=0.20, use_speaker_boost=True),
        output_format="mp3_44100_128",
    )
    with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f:
        tmp = f.name
        for chunk in audio: f.write(chunk)
    _play_mp3(tmp); os.unlink(tmp)


def _tts_gtts(text):
    tts = gTTS(text=text, lang='en', slow=False)
    with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f:
        tmp = f.name
    tts.save(tmp); _play_mp3(tmp); os.unlink(tmp)


def _tts_pyttsx3(text):
    e = _pyttsx3_mod.init()
    e.setProperty('rate', 145); e.setProperty('volume', 1.0)
    for v in e.getProperty('voices'):
        if any(w in v.name.lower() for w in ['zira','hazel','female','karen','victoria']):
            e.setProperty('voice', v.id); break
    e.say(text); e.runAndWait(); e.stop()


def _tts_espeak(text):
    proc = subprocess.Popen(['espeak','-s','130','-v','en+f3','--',text])
    while proc.poll() is None:
        if _stop_speaking.is_set(): proc.terminate(); break
        time.sleep(0.04)


def speak(text):
    with _speaking_lock:
        print(f"\n[LUMI] {text}")
        _stop_speaking.clear()
        if EL_OK and PYGAME_OK:
            try: _tts_el(text); return
            except Exception as e: print(f"  [EL] {e}")
        if GTTS_OK and PYGAME_OK:
            try: _tts_gtts(text); return
            except Exception as e: print(f"  [gTTS] {e}")
        if PYTTSX3_OK:
            try: _tts_pyttsx3(text); return
            except Exception as e: print(f"  [pyttsx3] {e}")
        try: _tts_espeak(text)
        except: print("  [no audio]")


def add_stars(p, data, n=1):
    p["stars"] = p.get("stars", 0) + n
    save_profile(data, p)
    speak(f"You earned {n} star{'s' if n>1 else ''}! "
          f"You now have {p['stars']} stars!")


# ══════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════
def main():
    print("\n" + "═"*60)
    print("  Lumi — Smart Braille Learning Device  v9.2")
    print("  Buttons: L=GPIO19  R=GPIO26  M=GPIO20  (polling)")
    print("═"*60)
    print_all_profiles()

    tts = ("ElevenLabs" if EL_OK and PYGAME_OK else
           "gTTS"       if GTTS_OK and PYGAME_OK else
           "pyttsx3"    if PYTTSX3_OK else "espeak")
    vosk_ok     = VOSK_OK and os.path.exists(VOSK_MODEL_PATH)
    agent_ready = (AGENT_ID           != "YOUR_AGENT_ID" and
                   ELEVENLABS_API_KEY != "YOUR_ELEVENLABS_KEY")

    print(f"\n  TTS   : {tts}")
    print(f"  VOSK  : {'READY ✓' if vosk_ok else 'NOT FOUND — Google STT fallback'}")
    print(f"  GPIO  : {'yes' if GPIO_AVAILABLE else 'simulation'}")
    print(f"  Agent : {'READY ✓' if agent_ready else 'keys not set'}")
    print()

    setup_gpio()

    # Start button polling thread for startup mode selection
    t = threading.Thread(target=poll_buttons_for_startup,
                         args=(20,), daemon=True)
    t.start()

    # Startup: ask name + mode
    profile, data, offline = run_startup(
        speak_fn    = speak,
        btn_left    = _btn_left,
        btn_right   = _btn_right,
        wait_btn_fn = wait_btn,
    )

    # Launch curriculum
    try:
        if offline:
            lumi = LumiOffline(
                name           = profile["name"],
                profile        = profile,
                data           = data,
                speak_fn       = speak,
                fire_large_fn  = lambda dots, hold=None: None,
                show_letter_fn = do_show_letter,
                show_number_fn = do_show_number,
                clear_fn       = do_clear,
                wait_btn_fn    = wait_btn,
                save_fn        = save_profile,
                add_stars_fn   = lambda n: add_stars(profile, data, n),
            )
            lumi.run()

        else:
            if not agent_ready:
                speak("Agent keys not set. Starting offline mode.")
                lumi = LumiOffline(
                    name           = profile["name"],
                    profile        = profile,
                    data           = data,
                    speak_fn       = speak,
                    fire_large_fn  = lambda dots, hold=None: None,
                    show_letter_fn = do_show_letter,
                    show_number_fn = do_show_number,
                    clear_fn       = do_clear,
                    wait_btn_fn    = wait_btn,
                    save_fn        = save_profile,
                    add_stars_fn   = lambda n: add_stars(profile, data, n),
                )
                lumi.run()
            else:
                agent = LumiOnlineAgent(
                    child_name     = profile["name"],
                    profile        = profile,
                    data           = data,
                    show_letter_fn = do_show_letter,
                    show_word_fn   = do_show_word,
                    show_number_fn = do_show_number,
                    clear_fn       = do_clear,
                    save_fn        = save_profile,
                    agent_id       = AGENT_ID,
                    api_key        = ELEVENLABS_API_KEY,
                )
                agent.run()

    except KeyboardInterrupt:
        pass
    finally:
        speak(
            f"Goodbye {profile['name']}! "
            f"You have {profile.get('stars', 0)} stars. "
            f"See you next time!"
        )
        do_clear()
        if GPIO_AVAILABLE:
            try: GPIO.cleanup()
            except: pass
        print("\n[SESSION ENDED]")
        print_all_profiles()


if __name__ == "__main__":
    main()

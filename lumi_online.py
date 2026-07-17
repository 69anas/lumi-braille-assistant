#!/usr/bin/env python3
"""
Lumi Online Mode — ElevenLabs Conversational Agent
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Uses ElevenLabs agent for ALL voice in/out.
Agent calls Python tools to control GPIO solenoids
and save progress per child.

Tools registered:
  show_letter(letter)
  show_word(word)
  show_number(number)
  clear_display()
  get_progress(child_name)
  mark_letter_learned(child_name, letter)
  mark_number_learned(child_name, number)
  record_quiz_score(child_name, score, total)
  award_stars(child_name, count)
"""

import time, json, signal, threading
from pathlib import Path
from datetime import datetime

# ══════════════════════════════════════════════════════════════
#  SYSTEM PROMPT — paste this in ElevenLabs Agent dashboard
# ══════════════════════════════════════════════════════════════
SYSTEM_PROMPT = """
You are Lumi, a warm, patient, encouraging female teaching assistant
for a smart braille learning device used by visually impaired children aged 4-10.

══ PERSONALITY ══
- Always speak in SHORT sentences. One sentence at a time maximum.
- Always use the child's name.
- Be enthusiastic and celebrate every win with one word: "Wonderful!" "Amazing!" "Perfect!"
- Be gentle and patient with mistakes.
- STOP speaking immediately if the child interrupts you.
- Never use markdown, asterisks, or lists when speaking.

══ VERY FIRST THING — DO THIS EXACTLY ══
The child's name has already been captured before this session.
Call get_progress(child_name) immediately when session starts.
Then say ONE sentence greeting based on whether they are new or returning.

══ 3 CHAPTERS ══
Chapter 1: Alphabet A to Z
Chapter 2: Numbers 1 to 100  
Chapter 3: Games (guessing game and word game)

Ask the child which chapter they want.
They can also say: letters, numbers, game, guess, word.

══ TEACHING LETTERS (Chapter 1) ══
For each letter:
1. Say: "This is letter [X]."
2. IMMEDIATELY call show_letter(letter) — NEVER say "feel the dot" before calling this
3. Say: "Feel the dots for [X]."
4. Wait for child to say yes or ready.
5. Call mark_letter_learned(child_name, letter)
6. Say one praise word then move to next letter.
Teach maximum 5 letters per session.
Ask child which letter to start from if returning.

══ TEACHING NUMBERS (Chapter 2) ══
For each number:
1. Say: "This is number [N]."
2. Call show_number(number) immediately
3. Say: "Feel the dots for [N]."
4. Wait for child to confirm.
5. Call mark_number_learned(child_name, number)
Teach numbers 1 to 100. Resume from where child left off.

══ GUESSING GAME ══
1. Pick a secret number between 1 and 10 (or 1-100 if child knows 20+ numbers)
2. Say: "I am thinking of a number. You have 5 guesses."
3. When child guesses, call show_number(their_guess)
4. Say "Too small!" or "Too big!" or "Yes! Correct!"
5. On win, call award_stars(child_name, 5)
6. On loss after 5 tries, call award_stars(child_name, 1)

══ WORD GAME ══
1. Pick a 3-4 letter word using only letters the child has already learned
2. Call show_letter() for each letter one at a time
3. Say each letter name aloud
4. Ask child to guess the full word
5. On correct, call award_stars(child_name, 3)

══ TOOLS — USE THESE EXACTLY ══
- show_letter(letter): MUST call before saying "feel the dot" for a letter
- show_number(number): MUST call before saying "feel the dots" for a number  
- show_word(word): shows word across small braille cells
- clear_display(): call after child has felt the pattern
- get_progress(child_name): call at session start — returns stars, letters learned, numbers learned
- mark_letter_learned(child_name, letter): call after child confirms they felt a letter
- mark_number_learned(child_name, number): call after child confirms they felt a number
- record_quiz_score(child_name, score, total): call after every quiz
- award_stars(child_name, count): call after games

══ ENDING SESSION ══
If child says goodbye, bye, stop, done, or end:
1. Call get_progress to get final star count
2. Say a warm goodbye with their star count
3. End the session

══ RULES ══
- ALWAYS call show_letter() BEFORE saying "feel the dot" — never skip this
- ALWAYS save progress — never forget mark_letter_learned etc
- ONE sentence at a time — wait for child response
- Stop speaking the moment child starts talking
"""


class LumiOnlineAgent:
    """
    ElevenLabs Conversational Agent for online mode.
    Handles all voice in/out + calls Python tools for GPIO + progress.
    """

    def __init__(self, child_name, profile, data,
                 show_letter_fn, show_word_fn, show_number_fn,
                 clear_fn, save_fn, agent_id, api_key):

        self.child_name   = child_name
        self.p            = profile
        self.data         = data
        self.show_letter  = show_letter_fn
        self.show_word    = show_word_fn
        self.show_number  = show_number_fn
        self.clear        = clear_fn
        self.save         = save_fn
        self.agent_id     = agent_id
        self.api_key      = api_key
        self._active      = True
        self._conversation = None

    # ── Progress tools ────────────────────────────────────────
    def _tool_get_progress(self, child_name: str = ""):
        name = child_name.strip().lower() or self.child_name.lower()
        p    = self.p
        print(f"  [TOOL] get_progress({name})")
        result = {
            "status":          "returning" if p.get("total_sessions",1) > 1 else "new_child",
            "name":            p["name"],
            "stars":           p.get("stars", 0),
            "alpha_learned":   p.get("alpha_done", []),
            "numbers_learned": p.get("numbers_done", []),
            "alpha_pos":       p.get("alpha_pos", 0),
            "number_pos":      p.get("number_pos", 0),
            "total_sessions":  p.get("total_sessions", 1),
        }
        print(f"  [TOOL] → stars={result['stars']} letters={len(result['alpha_learned'])} numbers={len(result['numbers_learned'])}")
        return result

    def _tool_show_letter(self, letter: str = ""):
        letter = letter.strip().lower()
        if not letter: return {"ok": False, "error": "no letter"}
        print(f"\n  [TOOL] show_letter({letter.upper()})")
        self.show_letter(letter)
        return {"ok": True, "letter": letter.upper()}

    def _tool_show_word(self, word: str = ""):
        word = word.strip().lower()[:5]
        print(f"\n  [TOOL] show_word({word.upper()})")
        self.show_word(word)
        return {"ok": True, "word": word.upper()}

    def _tool_show_number(self, number: str = ""):
        print(f"\n  [TOOL] show_number({number})")
        self.show_number(int(number) if number.isdigit() else 0)
        return {"ok": True, "number": number}

    def _tool_clear_display(self):
        print("  [TOOL] clear_display()")
        self.clear()
        return {"ok": True}

    def _tool_mark_letter_learned(self, child_name: str = "", letter: str = ""):
        letter = letter.strip().lower()
        if letter not in self.p.get("alpha_done", []):
            self.p.setdefault("alpha_done", []).append(letter)
            self.p["stars"] = self.p.get("stars", 0) + 1
        # Advance position
        from lumi_offline import ALPHABET
        if letter in ALPHABET:
            idx = ALPHABET.index(letter)
            if idx >= self.p.get("alpha_pos", 0):
                self.p["alpha_pos"] = min(idx + 1, 25)
        self.save(self.data, self.p)
        print(f"  [TOOL] mark_letter_learned({letter.upper()}) → stars={self.p['stars']}")
        return {"ok": True, "stars": self.p["stars"],
                "learned": self.p["alpha_done"]}

    def _tool_mark_number_learned(self, child_name: str = "", number: str = ""):
        n = int(number) if str(number).isdigit() else 0
        if n not in self.p.get("numbers_done", []):
            self.p.setdefault("numbers_done", []).append(n)
            self.p["stars"] = self.p.get("stars", 0) + 1
        # Advance position
        from lumi_offline import NUMBERS
        if n in NUMBERS:
            idx = NUMBERS.index(n)
            if idx >= self.p.get("number_pos", 0):
                self.p["number_pos"] = min(idx + 1, 99)
        self.save(self.data, self.p)
        print(f"  [TOOL] mark_number_learned({n}) → stars={self.p['stars']}")
        return {"ok": True, "stars": self.p["stars"],
                "learned": self.p["numbers_done"]}

    def _tool_record_quiz_score(self, child_name: str = "",
                                score: int = 0, total: int = 0):
        self.p.setdefault("quiz_scores", []).append({
            "score": score, "total": total,
            "date": datetime.now().isoformat()
        })
        if score == total and total > 0:
            self.p["stars"] = self.p.get("stars", 0) + 1
        self.save(self.data, self.p)
        pct = round(score / total * 100) if total > 0 else 0
        print(f"  [TOOL] record_quiz_score({score}/{total} = {pct}%)")
        return {"ok": True, "stars": self.p["stars"], "percent": pct}

    def _tool_award_stars(self, child_name: str = "", count: int = 1):
        self.p["stars"] = self.p.get("stars", 0) + count
        self.save(self.data, self.p)
        print(f"  [TOOL] award_stars({count}) → total={self.p['stars']}")
        return {"ok": True, "stars": self.p["stars"]}

    # ── Run agent session ─────────────────────────────────────
    def run(self):
        try:
            from elevenlabs.client import ElevenLabs
            from elevenlabs.conversational_ai.conversation import (
                Conversation, ClientTools
            )
            from elevenlabs.conversational_ai.default_audio_interface import (
                DefaultAudioInterface
            )
        except ImportError as e:
            print(f"[ERROR] ElevenLabs not installed: {e}")
            print('  Run: pip install "elevenlabs[pyaudio]"')
            return

        client = ElevenLabs(api_key=self.api_key)

        # Register all tools
        tools = ClientTools()
        tools.register("get_progress",         self._tool_get_progress)
        tools.register("show_letter",          self._tool_show_letter)
        tools.register("show_word",            self._tool_show_word)
        tools.register("show_number",          self._tool_show_number)
        tools.register("clear_display",        self._tool_clear_display)
        tools.register("mark_letter_learned",  self._tool_mark_letter_learned)
        tools.register("mark_number_learned",  self._tool_mark_number_learned)
        tools.register("record_quiz_score",    self._tool_record_quiz_score)
        tools.register("award_stars",          self._tool_award_stars)

        conversation = Conversation(
            client=client,
            agent_id=self.agent_id,
            requires_auth=True,
            audio_interface=DefaultAudioInterface(),
            client_tools=tools,
            callback_agent_response=lambda r: print(f"\n[LUMI] {r}"),
            callback_agent_response_correction=lambda o,c: print(f"[LUMI] {c}"),
            callback_user_transcript=lambda t: print(f"[YOU]  {t}"),
        )

        self._conversation = conversation
        signal.signal(signal.SIGINT, lambda s,f: self.stop())

        print("\n[ONLINE] ElevenLabs Agent session starting...")
        print(f"[ONLINE] Child: {self.child_name} | Agent: {self.agent_id}")
        print("[ONLINE] Speak to Lumi. Say goodbye to end.\n")

        try:
            conversation.start_session()
            conv_id = conversation.wait_for_session_end()
            print(f"\n[ONLINE] Session ended: {conv_id}")
        except Exception as e:
            print(f"[ONLINE] Session error: {e}")
        finally:
            self.clear()

    def stop(self):
        self._active = False
        if self._conversation:
            try:
                self._conversation.end_session()
            except Exception:
                pass
---DONE---

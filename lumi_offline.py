
#!/usr/bin/env python3
"""
Lumi Offline Mode  v9.1 — Short, direct speech
3 Chapters: Alphabet | Numbers | Games
Navigation: RIGHT=next  LEFT=back  MODE=chapter
"""

import time, random, threading

BRAILLE_ALPHA = {
    'a':[1],'b':[1,2],'c':[1,4],'d':[1,4,5],'e':[1,5],
    'f':[1,2,4],'g':[1,2,4,5],'h':[1,2,5],'i':[2,4],'j':[2,4,5],
    'k':[1,3],'l':[1,2,3],'m':[1,3,4],'n':[1,3,4,5],'o':[1,3,5],
    'p':[1,2,3,4],'q':[1,2,3,4,5],'r':[1,2,3,5],'s':[2,3,4],
    't':[2,3,4,5],'u':[1,3,6],'v':[1,2,3,6],'w':[2,4,5,6],
    'x':[1,3,4,6],'y':[1,3,4,5,6],'z':[1,3,5,6],
}
BRAILLE_DIGITS = {
    '1':[1],'2':[1,2],'3':[1,4],'4':[1,4,5],'5':[1,5],
    '6':[1,2,4],'7':[1,2,4,5],'8':[1,2,5],'9':[2,4],'0':[2,4,5],
}
NUMBER_INDICATOR = [3,4,5,6]
ALPHABET = list("abcdefghijklmnopqrstuvwxyz")
NUMBERS  = list(range(1, 101))

EASY_WORDS = [
    "cat","dog","hat","sun","bee","cup","ant","map","fun",
    "ball","fish","bird","frog","duck","hot","bed","log",
    "run","tap","bag","can","fan","man","pan","van",
]

# Short one-line descriptions per letter
LETTER_HINT = {
    'a':"One dot, top left.",
    'b':"Two dots, left side.",
    'c':"Two dots across the top.",
    'd':"Three dots, top and right.",
    'e':"Two dots, top left and middle right.",
    'f':"Three dots, top L shape.",
    'g':"Four dots, square at top.",
    'h':"Three dots, left and top right.",
    'i':"Two dots, right side.",
    'j':"Three dots, right side.",
    'k':"Two dots, left going down.",
    'l':"Three dots, left side.",
    'm':"Three dots, top and middle left.",
    'n':"Four dots, two rows.",
    'o':"Three dots, triangle shape.",
    'p':"Four dots, left and top.",
    'q':"Five dots.",
    'r':"Four dots.",
    's':"Three dots, middle.",
    't':"Four dots, top heavy.",
    'u':"Three dots, two left one bottom right.",
    'v':"Four dots, three left one bottom right.",
    'w':"Four dots, right side.",
    'x':"Four dots, cross shape.",
    'y':"Five dots spread out.",
    'z':"Four dots, two sides.",
}

PRAISE = ["Well done!","Brilliant!","Amazing!","Perfect!","Excellent!","Great job!"]


class LumiOffline:

    def __init__(self, name, profile, data,
                 speak_fn, fire_large_fn, show_letter_fn,
                 show_number_fn, clear_fn, wait_btn_fn,
                 save_fn, add_stars_fn):
        self.name        = name
        self.p           = profile
        self.data        = data
        self.speak       = speak_fn
        self.fire_large  = fire_large_fn
        self.show_letter = show_letter_fn
        self.show_number = show_number_fn
        self.clear       = clear_fn
        self.wait_btn    = wait_btn_fn
        self.save        = save_fn
        self.add_stars   = add_stars_fn
        self.chapter     = profile.get("chapter", 0)
        self.alpha_pos   = profile.get("alpha_pos",  0)
        self.number_pos  = profile.get("number_pos", 0)
        self._active     = True

    def _praise(self):
        return random.choice(PRAISE)

    def _save(self):
        self.p["chapter"]    = self.chapter
        self.p["alpha_pos"]  = self.alpha_pos
        self.p["number_pos"] = self.number_pos
        self.save(self.data, self.p)

    def stop(self):
        self._active = False

    # ── Chapter announcer ─────────────────────────────────────
    def _announce(self):
        names = ["Alphabet.", "Numbers.", "Games."]
        self.speak(f"Chapter {self.chapter + 1}. {names[self.chapter]}")

    # ════════════════════════════════════════════════════════
    #  CHAPTER 1 — ALPHABET A-Z
    # ════════════════════════════════════════════════════════
    def run_alpha(self):
        letter = ALPHABET[self.alpha_pos]
        done   = len(self.p.get("alpha_done", []))
        self.speak(f"Alphabet. Letter {self.alpha_pos + 1} of 26. {done} learned.")

        while self._active:
            letter = ALPHABET[self.alpha_pos]
            btn = self.wait_btn(timeout=60)

            if btn == 'mode':
                self.chapter = (self.chapter + 1) % 3
                self._save(); self._announce(); return

            elif btn == 'right':
                # Teach the letter
                self.speak(f"{letter.upper()}. {LETTER_HINT[letter]}")
                self.show_letter(letter)
                self.speak("Feel the dots.")
                time.sleep(3.0)
                self.clear()
                self.speak("Press right if felt. Left to repeat.")

                btn2 = self.wait_btn(timeout=15)

                if btn2 == 'right':
                    self.speak(f"{self._praise()}")
                    if letter not in self.p.get("alpha_done", []):
                        self.p.setdefault("alpha_done", []).append(letter)
                    self.add_stars(1)
                    if self.alpha_pos < 25:
                        self.alpha_pos += 1
                        self._save()
                        self.speak(f"Next. {ALPHABET[self.alpha_pos].upper()}.")
                    else:
                        self.speak(f"All 26 letters done {self.name}! Champion!")
                        self.add_stars(5)
                        self.alpha_pos = 0
                        self._save(); return

                elif btn2 == 'mode':
                    self.chapter = (self.chapter + 1) % 3
                    self._save(); self._announce(); return

                else:
                    # left or timeout — repeat
                    self.speak(f"{letter.upper()} again.")

            elif btn == 'left':
                if self.alpha_pos > 0:
                    self.alpha_pos -= 1
                    self._save()
                    self.speak(f"Back. {ALPHABET[self.alpha_pos].upper()}.")
                else:
                    self.speak("Already at A.")

            elif btn == 'timeout':
                self.speak(f"{ALPHABET[self.alpha_pos].upper()}. Press right.")

    # ════════════════════════════════════════════════════════
    #  CHAPTER 2 — NUMBERS 1-100
    # ════════════════════════════════════════════════════════
    def _number_word(self, n):
        ones = ["","one","two","three","four","five","six","seven",
                "eight","nine","ten","eleven","twelve","thirteen",
                "fourteen","fifteen","sixteen","seventeen","eighteen",
                "nineteen","twenty"]
        tens = ["","","twenty","thirty","forty","fifty",
                "sixty","seventy","eighty","ninety","one hundred"]
        if n <= 20:    return ones[n]
        elif n == 100: return "one hundred"
        elif n % 10 == 0: return tens[n // 10]
        else: return f"{tens[n//10]} {ones[n%10]}"

    def run_numbers(self):
        n    = NUMBERS[self.number_pos]
        done = len(self.p.get("numbers_done", []))
        self.speak(f"Numbers. Number {self.number_pos + 1} of 100. {done} learned.")

        while self._active:
            n   = NUMBERS[self.number_pos]
            btn = self.wait_btn(timeout=60)

            if btn == 'mode':
                self.chapter = (self.chapter + 1) % 3
                self._save(); self._announce(); return

            elif btn == 'right':
                self.speak(f"{n}. {self._number_word(n)}.")
                self.show_number(n)
                self.speak("Feel the dots.")
                time.sleep(3.0)
                self.clear()
                self.speak("Press right if felt. Left to repeat.")

                btn2 = self.wait_btn(timeout=15)

                if btn2 == 'right':
                    self.speak(f"{self._praise()}")
                    if n not in self.p.get("numbers_done", []):
                        self.p.setdefault("numbers_done", []).append(n)
                    self.add_stars(1)
                    if self.number_pos < 99:
                        self.number_pos += 1
                        self._save()
                        self.speak(f"Next. {NUMBERS[self.number_pos]}.")
                    else:
                        self.speak(f"All 100 numbers done {self.name}! Incredible!")
                        self.add_stars(20)
                        self.number_pos = 0
                        self._save(); return

                elif btn2 == 'mode':
                    self.chapter = (self.chapter + 1) % 3
                    self._save(); self._announce(); return

                else:
                    self.speak(f"{n} again.")

            elif btn == 'left':
                if self.number_pos > 0:
                    self.number_pos -= 1
                    self._save()
                    self.speak(f"Back. {NUMBERS[self.number_pos]}.")
                else:
                    self.speak("Already at 1.")

            elif btn == 'timeout':
                self.speak(f"{NUMBERS[self.number_pos]}. Press right.")

    # ════════════════════════════════════════════════════════
    #  CHAPTER 3 — GAMES
    # ════════════════════════════════════════════════════════
    def run_games(self):
        self.speak("Games. Right for guessing game. Left for word game.")
        btn = self.wait_btn(timeout=15)
        if btn == 'mode':
            self.chapter = (self.chapter + 1) % 3
            self._save(); self._announce(); return
        elif btn == 'left':
            self._word_game()
        else:
            self._guess_game()

    def _guess_game(self):
        done    = len(self.p.get("numbers_done", []))
        max_num = 20 if done >= 10 else 10
        secret  = random.randint(1, max_num)

        self.speak(f"Guess my number. 1 to {max_num}. 7 tries.")

        low, high = 1, max_num

        for attempt in range(1, 8):
            if not self._active: return
            mid = (low + high) // 2
            self.speak(f"Try {attempt}. Is it {mid}? Right if same or higher. Left if lower.")
            self.show_number(mid)
            time.sleep(1.0)
            self.clear()

            btn = self.wait_btn(timeout=20)

            if btn == 'mode':
                self.chapter = (self.chapter + 1) % 3
                self._save(); self._announce(); return

            elif btn == 'right':
                if mid == secret:
                    self.speak(f"Yes! {secret}! {self._praise()} 5 stars!")
                    self.add_stars(5)
                    self.show_number(secret)
                    time.sleep(3.0); self.clear()
                    self.speak("Right to play again. Mode to change chapter.")
                    btn = self.wait_btn(timeout=15)
                    if btn == 'mode':
                        self.chapter = (self.chapter + 1) % 3
                        self._save(); self._announce()
                    else:
                        self._guess_game()
                    return
                else:
                    low = mid + 1
                    if low > high: break
                    self.speak("Higher.")

            elif btn == 'left':
                high = mid - 1
                if high < low: break
                self.speak("Lower.")

            elif btn == 'timeout':
                self.speak("Press right or left!")

        self.speak(f"It was {secret}. 1 star for trying!")
        self.add_stars(1)
        self.show_number(secret)
        time.sleep(3.0); self.clear()
        self.speak("Right to play again.")
        btn = self.wait_btn(timeout=15)
        if btn == 'mode':
            self.chapter = (self.chapter + 1) % 3
            self._save(); self._announce()
        else:
            self._guess_game()

    def _word_game(self):
        learned   = self.p.get("alpha_done", [])
        available = [w for w in EASY_WORDS
                     if all(c in learned for c in w) and len(w) <= 4]

        if not available:
            self.speak(f"Learn more letters first. {len(learned)} known.")
            self.speak("Mode to go to alphabet.")
            self.wait_btn(timeout=10)
            self.chapter = 0; self._save()
            return

        word = random.choice(available)
        self.speak(f"Word game. {len(word)} letters. Press right.")
        btn = self.wait_btn(timeout=15)
        if btn == 'mode':
            self.chapter = (self.chapter + 1) % 3
            self._save(); self._announce(); return

        for ch in word:
            self.speak(ch.upper())
            self.show_letter(ch)
            time.sleep(3.3)
            self.clear()
            time.sleep(0.3)

        self.speak(f"The word was {word}. Press right if you got it.")
        btn = self.wait_btn(timeout=15)

        if btn == 'right':
            self.speak(f"{self._praise()} {word}! 3 stars!")
            self.add_stars(3)
        elif btn == 'left':
            self.speak("Let us try again!")
            self._word_game(); return
        elif btn == 'mode':
            self.chapter = (self.chapter + 1) % 3
            self._save(); self._announce(); return

        self.speak("Right for another word.")
        btn = self.wait_btn(timeout=15)
        if btn == 'right': self._word_game()
        elif btn == 'mode':
            self.chapter = (self.chapter + 1) % 3
            self._save(); self._announce()

    # ════════════════════════════════════════════════════════
    #  MAIN RUN
    # ════════════════════════════════════════════════════════
    def run(self):
        done_a = len(self.p.get("alpha_done", []))
        done_n = len(self.p.get("numbers_done", []))
        stars  = self.p.get("stars", 0)

        if done_a == 0 and done_n == 0:
            self.speak(
                f"Offline mode {self.name}. "
                f"Right moves forward. Left goes back. Middle changes chapter."
            )
        else:
            self.speak(
                f"Welcome back {self.name}. "
                f"{stars} stars. {done_a} letters. {done_n} numbers."
            )

        time.sleep(0.3)
        self._announce()

        while self._active:
            if   self.chapter == 0: self.run_alpha()
            elif self.chapter == 1: self.run_numbers()
            elif self.chapter == 2: self.run_games()
            if self._active:
                self._announce()

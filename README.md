# Lumi — Smart Braille Learning Device

AI-powered braille learning assistant for visually impaired 
children. Runs on Raspberry Pi 4B with physical solenoid dots.

## Features
- Offline speech recognition via VOSK (no internet needed)
- Multi-layer TTS: ElevenLabs → gTTS → pyttsx3 → espeak
- ElevenLabs Conversational AI Agent (online mode)
- GPIO solenoid control for physical braille dots
- Per-child progress saving and session resume
- 3 chapters: Alphabet A-Z, Numbers 1-100, Games

## Hardware
- Raspberry Pi 4B 2GB
- 6 pull-type solenoids (large braille display)
- USB microphone + 3.5mm speaker
- 3 navigation buttons (LEFT / RIGHT / MODE)

## Audio Stack
| Priority | Engine | Mode |
|---|---|---|
| 1 | ElevenLabs TTS | Online |
| 2 | gTTS | Online |
| 3 | pyttsx3 | Offline |
| 4 | espeak | Offline |

## Speech Recognition
- VOSK offline acoustic model
- Grammar-constrained for improved accuracy
- Google STT fallback when online

## Run
pip install -r requirements.txt
python3 lumi_main.py

## Author
Anas Raja — Mechatronics Engineering, Air University Islamabad  
Freelance embedded AI developer — fiverr.com/anasraja_17

# Jarvis AI — local desktop starter

A local Flask website with Gemini-powered command understanding, browser speech recognition/speech synthesis, and a small allowlist of desktop actions.

## Important security notes
- The API key pasted into chat should be treated as exposed. Revoke/rotate it in Google AI Studio before using this project.
- Put the replacement key only in `.env`; never in HTML/JS or Git.
- This app binds to `127.0.0.1` only. Do not expose port 5000 to your LAN or the public internet.
- Voice recognition uses your browser's Web Speech API and may rely on the browser vendor's online speech service.
- WhatsApp is launch-only. Jarvis does not read/send messages or automate account interactions. Gmail and login/submission actions are blocked by policy.
- Scrolling and play/pause send fixed Page Up/Page Down or Space keystrokes to the currently focused desktop window. Focus the intended window first.
- File opening is limited to paths inside your home directory. Files are opened locally and are not uploaded to Gemini.
- This is a starter, not a security boundary against a person who can edit the code or control the same desktop session.

## Install on Ubuntu
```bash
cd jarvis_ai
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env
```
Put your replacement key after `GEMINI_API_KEY=` and save.

Optional for desktop key presses under X11:
```bash
sudo apt install python3-tk python3-dev scrot
```
If pyautogui installation is troublesome, the AI and app-opening features can still work; scrolling/play-pause will show a fallback.

Run:
```bash
python app.py
```
Open **http://127.0.0.1:5000** in Chrome. Allow microphone access. Use a desktop browser, not a mobile emulator, for desktop controls.

## Try these
- “Open YouTube”
- “Open Google”
- “Search Google for current Prime Minister of India”
- “Search YouTube for relaxing music”
- “Open WhatsApp”
- “Open File Explorer”
- “Scroll down”
- “Pause the video”
- “Who is the Chief Minister of Kerala?”

## Limitations
- This version does not directly control arbitrary buttons or page DOM inside every browser tab. It opens approved URLs and sends limited keyboard shortcuts to the active window.
- It does not guarantee live/current answers without web search. For up-to-date facts, ask Jarvis to open Google and search.
- Browser speech recognition support varies; current Chrome/Chromium builds are recommended.

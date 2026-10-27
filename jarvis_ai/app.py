import os
import re
import json
import logging
import subprocess
from pathlib import Path
from urllib.parse import quote_plus
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
from google import genai
from google.genai import types, errors

# Configure safe backend logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [Jarvis] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("jarvis")

# Ensure .env is loaded from the directory containing app.py
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)

HOME = Path.home().resolve()
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip() or "gemini-3.5-flash-lite"
api_key = os.getenv("GEMINI_API_KEY", "").strip()

app = Flask(__name__)

# Initialize Gemini client safely
client = None
if api_key:
    try:
        client = genai.Client(api_key=api_key)
        logger.info("Gemini client initialized with model '%s'", MODEL)
    except Exception as e:
        logger.error("Failed to initialize Gemini client: %s", type(e).__name__)
else:
    logger.warning("No GEMINI_API_KEY found in .env.")


def sanitize_log(msg: str) -> str:
    """Mask any API keys or credential patterns from log strings."""
    if not msg:
        return ""
    if api_key and len(api_key) > 6:
        msg = msg.replace(api_key, f"{api_key[:4]}...{api_key[-4:]}")
    # Mask common key tokens (e.g. AIza..., AQ...., or alphanumeric strings >= 32 chars)
    msg = re.sub(r'(?:AIza[0-9A-Za-z-_]{35}|AQ\.[0-9A-Za-z-_]{40,})', '[REDACTED_KEY]', msg)
    return msg


SYSTEM_JARVIS = """
You are Jarvis, a concise, friendly, and highly intelligent desktop voice assistant. The user may speak English or Hindi.
Return ONLY valid JSON with keys: intent, target, query, reply.
Allowed intents: open_app, open_url, google_search, youtube_search, scroll, play_pause,
click_video, file_open, answer, blocked.
Allowed targets: youtube, google, whatsapp, files, browser.
Rules:
- Classify commands; never claim you performed an action.
- Speak in character: polite, concise, gentlemanly, and efficient.
- Do not perform logins, send messages/emails, purchase items, post, delete, or submit forms.
- Requests to sign in, log in, send WhatsApp messages, send Gmail, access passwords, or submit forms => blocked.
- "open YouTube" => open_url target youtube. "open Google" => open_url target google.
- A request to search on Google => google_search, query is the search phrase.
- A request to search YouTube => youtube_search, query is the search phrase.
- "scroll down/up" => scroll, target is down/up.
- "play/pause/stop video/music/YouTube" (e.g. "play video", "stop video", "pause YouTube", "resume", "stop playing") => play_pause, target is play, pause, stop, or toggle.
- "click/open/play the first/second/third/Nth video" or "play video number N" => click_video, query is the number (e.g. "1", "2", "3").
- "click the video" or "open the video" (no number) => click_video, query is "1".
- "open WhatsApp" => open_app target whatsapp (launch only; no account interaction).
- "open file explorer" / "open files" => open_app target files.
- If user asks a general question, intent answer and reply should answer if known; if current facts may have changed, suggest searching Google.
- Correct grammar naturally in reply when useful, without shaming the user.
- Keep reply in the language the user used where possible.
"""

SYSTEM_FRIDAY = """
You are F.R.I.D.A.Y., Tony Stark's witty, sharp, helpful, and friendly Irish AI assistant. The user may speak English or Hindi.
Return ONLY valid JSON with keys: intent, target, query, reply.
Allowed intents: open_app, open_url, google_search, youtube_search, scroll, play_pause,
click_video, file_open, answer, blocked.
Allowed targets: youtube, google, whatsapp, files, browser.
Rules:
- Classify commands; never claim you performed an action.
- Speak in character: crisp, warm, capable, occasionally addressing the user naturally as Boss.
- Do not perform logins, send messages/emails, purchase items, post, delete, or submit forms.
- Requests to sign in, log in, send WhatsApp messages, send Gmail, access passwords, or submit forms => blocked.
- "open YouTube" => open_url target youtube. "open Google" => open_url target google.
- A request to search on Google => google_search, query is the search phrase.
- A request to search YouTube => youtube_search, query is the search phrase.
- "scroll down/up" => scroll, target is down/up.
- "play/pause/stop video/music/YouTube" (e.g. "play video", "stop video", "pause YouTube", "resume", "stop playing") => play_pause, target is play, pause, stop, or toggle.
- "click/open/play the first/second/third/Nth video" or "play video number N" => click_video, query is the number (e.g. "1", "2", "3").
- "click the video" or "open the video" (no number) => click_video, query is "1".
- "open WhatsApp" => open_app target whatsapp (launch only; no account interaction).
- "open file explorer" / "open files" => open_app target files.
- If user asks a general question, intent answer and reply should answer concisely.
- Keep reply in the language the user used where possible.
"""

SYSTEM = SYSTEM_JARVIS

BLOCKED_PATTERNS = [
    r"\b(sign\s*in|log\s*in|login|signin)\b",
    r"\b(send|write|type|read)\s+(a\s+)?(whatsapp|message|text|chat)\b",
    r"\b(send|write|compose)\s+(an?\s+)?(email|mail|gmail)\b",
    r"\b(delete|remove|erase|format|rm\s+-rf)\s+(file|folder|directory|disk|all)\b",
    r"\b(buy|purchase|checkout|pay|order)\b",
    r"\b(password|credential|secret)\b",
    r"\bsubmit\s+(form|application)\b"
]


def extract_json_payload(raw_text: str) -> dict:
    """Safely extracts JSON from model output, handling optional markdown fences."""
    raw_text = raw_text.strip()
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_text, re.DOTALL)
    if fence_match:
        return json.loads(fence_match.group(1))
    brace_match = re.search(r"(\{.*\})", raw_text, re.DOTALL)
    if brace_match:
        return json.loads(brace_match.group(1))
    return json.loads(raw_text)


def fallback_local_parse(text: str) -> dict:
    """Local deterministic command parsing in case Gemini is temporarily unavailable."""
    t = text.lower().strip()

    # Blocked commands check
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, t):
            return {
                "intent": "blocked",
                "target": "",
                "query": "",
                "reply": "I can't sign in, send messages or emails, submit forms, or delete files. You stay in control."
            }

    # Open approved URLs/Apps
    if re.search(r"\b(open|launch|go\s*to)\s+youtube\b", t):
        return {"intent": "open_url", "target": "youtube", "query": "", "reply": "Opening YouTube."}
    if re.search(r"\b(open|launch|go\s*to)\s+google\b", t):
        return {"intent": "open_url", "target": "google", "query": "", "reply": "Opening Google."}
    if re.search(r"\b(open|launch)\s+whatsapp\b", t):
        return {"intent": "open_app", "target": "whatsapp", "query": "", "reply": "Opening WhatsApp."}
    if re.search(r"\b(open|launch)\s+(file\s*explorer|files|my\s*files|folder)\b", t):
        return {"intent": "open_app", "target": "files", "query": "", "reply": "Opening File Explorer."}

    # YouTube Search
    yt_search = re.search(r"\b(?:search\s+youtube\s+for|search\s+for\s+(.+)\s+on\s+youtube|search\s+on\s+youtube\s+for)\s*(.*)", t)
    if yt_search:
        q = (yt_search.group(1) or yt_search.group(2) or "").strip()
        return {"intent": "youtube_search", "target": "youtube", "query": q, "reply": f"Searching YouTube for {q}." if q else "What should I search for on YouTube?"}

    # Google Search
    g_search = re.search(r"\b(?:search\s+google\s+for|search\s+for\s+(.+)\s+on\s+google|google\s+search\s+for|search\s+the\s+web\s+for)\s*(.*)", t)
    if g_search:
        q = (g_search.group(1) or g_search.group(2) or "").strip()
        return {"intent": "google_search", "target": "google", "query": q, "reply": f"Searching Google for {q}." if q else "What should I search for?"}

    # Scroll
    if re.search(r"\bscroll\s+down\b", t):
        return {"intent": "scroll", "target": "down", "query": "", "reply": "Scrolling down."}
    if re.search(r"\bscroll\s+up\b", t):
        return {"intent": "scroll", "target": "up", "query": "", "reply": "Scrolling up."}

    # Click video by number
    _ordinals = {"first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3,
                 "fourth": 4, "4th": 4, "fifth": 5, "5th": 5,
                 "sixth": 6, "6th": 6, "seventh": 7, "7th": 7,
                 "eighth": 8, "8th": 8, "ninth": 9, "9th": 9, "tenth": 10, "10th": 10}
    _cv = re.search(r"\b(click|open|play|select)\s+(the\s+)?(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|\d+(?:st|nd|rd|th)?)\s+video\b", t)
    if _cv:
        raw = _cv.group(3)
        num = _ordinals.get(raw) or int(re.sub(r"[^\d]", "", raw) or 1)
        return {"intent": "click_video", "target": "youtube", "query": str(num), "reply": f"Clicking video number {num}."}
    if re.search(r"\b(click|open|play)\s+(the\s+)?video\b", t):
        return {"intent": "click_video", "target": "youtube", "query": "1", "reply": "Clicking the first video."}
    if re.search(r"\bplay\s+video\s+number\s+(\d+)\b", t):
        m = re.search(r"\bplay\s+video\s+number\s+(\d+)\b", t)
        return {"intent": "click_video", "target": "youtube", "query": m.group(1), "reply": f"Clicking video number {m.group(1)}."}

    # Play / Pause / Stop YouTube and Media
    if re.search(r"\b(play|resume|start|unpause)\s+(the\s+)?(video|youtube|media|song|music|playback)\b", t):
        return {"intent": "play_pause", "target": "play", "query": "", "reply": "Resuming video playback."}
    if re.search(r"\b(pause|stop|halt)\s+(the\s+)?(video|youtube|media|song|music|playback)\b", t):
        return {"intent": "play_pause", "target": "pause", "query": "", "reply": "Stopping video playback."}
    if re.search(r"\b(play|pause|stop\s*playing|toggle\s*play)\b", t):
        target = "play" if "play" in t and "pause" not in t and "stop" not in t else ("pause" if "pause" in t or "stop" in t else "toggle")
        return {"intent": "play_pause", "target": target, "query": "", "reply": "Controlling media playback."}

    return None


def gemini_json(text: str, personality: str = "jarvis") -> dict:
    sys_prompt = SYSTEM_FRIDAY if personality == "friday" else SYSTEM_JARVIS
    if not client:
        # Check if local command matches even if key is missing
        local = fallback_local_parse(text)
        if local:
            return local
        return {
            "intent": "answer",
            "target": "",
            "query": "",
            "reply": "Please add your Gemini API key to the .env file, then restart Jarvis."
        }

    try:
        result = client.models.generate_content(
            model=MODEL,
            contents=text,
            config=types.GenerateContentConfig(
                system_instruction=sys_prompt,
                response_mime_type="application/json",
                temperature=0.2,
            ),
        )
        data = extract_json_payload(result.text)
        if isinstance(data, dict):
            return data
        return {"intent": "answer", "reply": "Sorry, I couldn't understand that."}
    except Exception as e:
        err_type = type(e).__name__
        err_msg = str(e)
        logger.error("Gemini API call failed [%s] for model '%s': %s", err_type, MODEL, sanitize_log(err_msg)[:300])

        # Attempt fallback local parsing for critical desktop actions
        local = fallback_local_parse(text)
        if local:
            logger.info("Recovered command using local fallback parser: %s", local.get("intent"))
            return local

        # Re-raise to trigger categorized user feedback in /api/command
        raise


def launch(url: str):
    subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def desktop_key(key: str) -> bool:
    """Fixed key press automation (never arbitrary shell commands)."""
    try:
        import pyautogui
        pyautogui.press(key)
        return True
    except Exception as e:
        logger.warning("desktop_key failed for key '%s': %s", key, e)
        return False


def get_browser_window_id() -> str | None:
    """Find the foreground browser window (YouTube preferred, then any browser)."""
    try:
        out = subprocess.check_output(["wmctrl", "-l"], text=True, stderr=subprocess.DEVNULL)
        lines = out.splitlines()
        # Prefer YouTube window
        for line in lines:
            if "youtube" in line.lower():
                return line.split()[0]
        # Any browser window
        for kw in ["chromium", "chrome", "brave", "firefox", "edge", "opera", "vivaldi"]:
            for line in lines:
                if kw in line.lower():
                    return line.split()[0]
    except Exception:
        pass
    return None


def scroll_browser_window(direction: str) -> tuple[bool, str]:
    """
    Scroll the active browser window using xdotool.
    direction: 'down' or 'up'
    """
    wid_hex = get_browser_window_id()
    scroll_key = "Down" if direction == "down" else "Up"
    try:
        # Focus window and send multiple Down/Up key presses for a smooth scroll
        if wid_hex:
            wid_int = str(int(wid_hex, 16))
            for _ in range(5):
                subprocess.run(
                    ["xdotool", "key", "--window", wid_int, scroll_key],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
            return True, f"Scrolled {direction} in the browser."
        else:
            # No browser window found — try active window
            for _ in range(5):
                subprocess.run(
                    ["xdotool", "key", scroll_key],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
            return True, f"Sent scroll {direction} to the active window."
    except Exception as e:
        logger.warning("scroll_browser_window failed: %s", e)
        return False, f"Could not scroll {direction}. Ensure xdotool is installed."


def click_youtube_video(index: int = 1) -> tuple[bool, str]:
    """
    Click the Nth video thumbnail on the currently open YouTube page using xdotool.
    Uses Tab navigation: focuses the YouTube window, then tabs to the video links.
    index: 1-based video number
    """
    wid_hex = get_browser_window_id()
    if not wid_hex:
        return False, "No browser window found. Please open YouTube first."

    try:
        wid_int = str(int(wid_hex, 16))
        # Activate / focus the window
        subprocess.run(["xdotool", "windowactivate", "--sync", wid_int],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        import time
        time.sleep(0.3)

        # Press Tab (index) times to reach the Nth video link, then Enter
        # Each Tab press advances focus to the next interactive element (video thumbnail)
        for _ in range(index):
            subprocess.run(["xdotool", "key", "--window", wid_int, "Tab"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(0.08)

        subprocess.run(["xdotool", "key", "--window", wid_int, "Return"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True, f"Clicked video number {index} on YouTube."
    except Exception as e:
        logger.warning("click_youtube_video failed: %s", e)
        return False, "Could not click the video. Ensure xdotool is installed and YouTube is open."


def get_mpris_players() -> list[str]:
    """Find all active MPRIS media player services on the user D-Bus (Brave, Chrome, Firefox, VLC, etc.)."""
    try:
        out = subprocess.check_output(["busctl", "--user", "list"], text=True, stderr=subprocess.DEVNULL)
        return [line.split()[0] for line in out.splitlines() if line.startswith("org.mpris.MediaPlayer2.")]
    except Exception:
        return []


def get_mpris_title(player: str) -> str | None:
    """Extract current video or track title from player metadata."""
    try:
        out = subprocess.check_output([
            "busctl", "--user", "get-property", player,
            "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player", "Metadata"
        ], text=True, stderr=subprocess.DEVNULL)
        m = re.search(r'"xesam:title"\s+s\s+"([^"]+)"', out)
        if m:
            return m.group(1).strip()
    except Exception:
        pass
    return None


def control_youtube_media(command: str = "toggle") -> tuple[bool, str]:
    """
    Control YouTube and media playback:
    1. MPRIS D-Bus (works in background for Brave, Chrome, Chromium, Firefox, Spotify, VLC)
    2. xdotool window targeted key 'k' (YouTube standard shortcut)
    3. pyautogui active window fallback
    Returns: (success_bool, user_reply)
    """
    cmd = command.lower().strip()
    if cmd in ("play", "resume", "start"):
        mpris_method = "Play"
        action_verb = "Playing"
    elif cmd in ("pause", "stop", "halt"):
        mpris_method = "Pause"
        action_verb = "Stopped"
    else:
        mpris_method = "PlayPause"
        action_verb = "Toggled playback for"

    # Tier 1: MPRIS D-Bus
    players = get_mpris_players()
    detected_title = None
    mpris_success = False

    for p in players:
        title = get_mpris_title(p)
        res = subprocess.run([
            "busctl", "--user", "call", p,
            "/org/mpris/MediaPlayer2",
            "org.mpris.MediaPlayer2.Player",
            mpris_method
        ], capture_output=True, text=True)
        if res.returncode == 0:
            mpris_success = True
            if title and not detected_title:
                detected_title = title

    if mpris_success:
        if detected_title:
            return True, f"{action_verb} '{detected_title}'."
        return True, f"{action_verb} YouTube / media playback."

    # Tier 2: xdotool targeting YouTube windows
    try:
        out = subprocess.check_output(["wmctrl", "-l"], text=True, stderr=subprocess.DEVNULL)
        yt_windows = [line.split()[0] for line in out.splitlines() if "youtube" in line.lower()]
        if yt_windows:
            wid_int = str(int(yt_windows[0], 16))
            # 'k' is YouTube's dedicated play/pause shortcut
            subprocess.run(["xdotool", "key", "--window", wid_int, "k"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True, f"{action_verb} YouTube video."
    except Exception as e:
        logger.debug("xdotool fallback error: %s", e)

    # Tier 3: Active window fallback
    ok = desktop_key("k") or desktop_key("space")
    if ok:
        return True, f"{action_verb} media in the active window."
    return False, "Could not detect an active YouTube player. Please ensure YouTube is open."


def safe_file_open(user_path: str):
    """Only open files/folders strictly inside the user's home directory."""
    p = Path(user_path).expanduser()
    if not p.is_absolute():
        p = HOME / p
    try:
        resolved = p.resolve(strict=True)
        if resolved != HOME and HOME not in resolved.parents:
            return False, "For safety, Jarvis can open only files inside your home folder."
        if not resolved.exists():
            return False, "I couldn't find that file or folder."
        subprocess.Popen(["xdg-open", str(resolved)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True, f"Opening {resolved.name}."
    except (OSError, RuntimeError):
        return False, "I couldn't open that path. Check the file or folder name."


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/status")
def status():
    return jsonify({
        "configured": bool(client and api_key),
        "model": MODEL
    })


@app.post("/api/command")
def command():
    payload = request.get_json(silent=True) or {}
    text = str(payload.get("text", "")).strip()
    if not text:
        return jsonify({"reply": "I didn't hear a command.", "action": "none"})
    if len(text) > 1500:
        return jsonify({"reply": "Please keep commands under 1,500 characters.", "action": "none"}), 400

    personality = str(payload.get("personality", "jarvis")).lower().strip()
    if personality not in ("jarvis", "friday"):
        personality = "jarvis"

    logger.info("Processing command (%s): '%s'", personality.upper(), text[:100])

    try:
        data = gemini_json(text, personality=personality)
    except Exception as e:
        err_str = str(e)
        low = err_str.lower()
        if "503" in err_str or "unavailable" in low:
            reply = f"The Gemini model ({MODEL}) is currently experiencing high demand (503). Please try again in a few moments."
        elif "429" in err_str or "resource_exhausted" in low or "quota" in low:
            reply = "Gemini API rate limit or quota exceeded (429). Please wait before trying again."
        elif "404" in err_str or "not_found" in low:
            reply = f"The model '{MODEL}' was not found. Please verify GEMINI_MODEL in your .env file."
        elif "400" in err_str or "401" in err_str or "403" in err_str or "permission_denied" in low or "invalid_argument" in low:
            reply = "Gemini API authentication failed. Please verify your GEMINI_API_KEY in .env."
        elif "connect" in low or "timeout" in low:
            reply = "Network connection to Gemini failed. Please check your internet connection."
        else:
            reply = "I couldn't reach Gemini. Check your API key, internet connection, and API quota."

        return jsonify({"reply": reply, "action": "error", "error_type": type(e).__name__})

    intent = str(data.get("intent", "answer")).lower()
    target = str(data.get("target", "") or "").lower().strip()
    query = str(data.get("query", "") or "").strip()[:300]
    reply = str(data.get("reply", "") or "").strip()[:1200]
    action = "none"

    # 1. Blocked commands check
    if intent == "blocked":
        reply = reply or "I can't sign in, send messages or emails, or submit account actions. You stay in control."
        logger.info("Command blocked by security policy: '%s'", text[:50])

    # 2. Open URL
    elif intent in ("open_url", "open_app") and target in ("youtube", "google", "browser"):
        urls = {
            "youtube": "https://www.youtube.com/",
            "google": "https://www.google.com/",
            "browser": "https://www.google.com/"
        }
        url = urls.get(target, "https://www.google.com/")
        launch(url)
        action = "opened"
        reply = reply or f"Opening {target.capitalize()}."
        logger.info("Opened URL: %s", url)

    # 3. Google Search
    elif intent == "google_search":
        if query:
            launch("https://www.google.com/search?q=" + quote_plus(query))
            action = "opened"
            reply = reply or f"Searching Google for {query}."
            logger.info("Performed Google search: '%s'", query)
        else:
            reply = "What should I search for on Google?"

    # 4. YouTube Search
    elif intent == "youtube_search":
        if query:
            launch("https://www.youtube.com/results?search_query=" + quote_plus(query))
            action = "opened"
            reply = reply or f"Searching YouTube for {query}."
            logger.info("Performed YouTube search: '%s'", query)
        else:
            reply = "What should I search for on YouTube?"

    # 5. Open Apps (Files / WhatsApp)
    elif intent == "open_app":
        if target in ("files", "file explorer", "explorer", "file_explorer"):
            subprocess.Popen(["xdg-open", str(HOME)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            action = "opened"
            reply = reply or "Opening File Explorer."
            logger.info("Opened File Explorer for %s", HOME)
        elif target == "whatsapp":
            # Launch only. No clicks, login, message reading, or sending.
            launched = False
            for cmd in (["whatsapp-for-linux"], ["snap", "run", "whatsapp-for-linux"], ["flatpak", "run", "com.whatsapp.WhatsApp"], ["whatsapp"]):
                try:
                    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    launched = True
                    break
                except (OSError, FileNotFoundError):
                    pass
            if not launched:
                launch("https://web.whatsapp.com/")
            action = "opened"
            reply = reply or "Opening WhatsApp. I won't sign in or interact with messages."
            logger.info("Launched WhatsApp (launch-only)")
        else:
            reply = "I can only launch approved applications (File Explorer, WhatsApp, Browser)."

    # 6. Scroll in active browser window
    elif intent == "scroll":
        direction = target if target in ("up", "down") else ("down" if "down" in text.lower() else "up")
        ok, scroll_msg = scroll_browser_window(direction)
        action = "key_sent" if ok else "manual"
        reply = scroll_msg if ok else (reply or "Could not scroll. Ensure the browser is open and xdotool is installed.")
        logger.info("Scroll %s triggered (success=%s)", direction, ok)

    # 7. Play / Pause / Stop YouTube and media
    elif intent == "play_pause":
        cmd_type = target if target in ("play", "pause", "stop", "toggle") else ("pause" if any(w in text.lower() for w in ("pause", "stop", "halt")) else ("play" if any(w in text.lower() for w in ("play", "resume", "start")) else "toggle"))
        ok, status_msg = control_youtube_media(cmd_type)
        action = "media_controlled" if ok else "manual"
        reply = status_msg if ok else (reply or "I couldn't detect an active YouTube player. Press 'k' or Space in your browser.")
        logger.info("Media control (%s) result: %s (ok=%s)", cmd_type, status_msg, ok)

    # 8. Click Nth YouTube video
    elif intent == "click_video":
        try:
            video_num = max(1, int(query)) if query and query.isdigit() else 1
        except ValueError:
            video_num = 1
        ok, cv_msg = click_youtube_video(video_num)
        action = "clicked" if ok else "manual"
        reply = cv_msg if ok else (reply or "Could not click the video. Please ensure YouTube is open in your browser.")
        logger.info("click_video #%d result: %s (ok=%s)", video_num, cv_msg, ok)

    # 9. Open safe local file
    elif intent == "file_open":
        path = str(data.get("query", "")).strip()
        if path:
            ok, message = safe_file_open(path)
            reply = message
            action = "opened" if ok else "blocked"
            logger.info("File open '%s' result: %s", path, message)
        else:
            reply = "Say the name or relative path of a file inside your home folder."

    # 10. General Answer
    else:
        reply = reply or "I'm here. What would you like to know?"
        logger.info("Answer generated (intent=%s)", intent)

    return jsonify({
        "reply": reply,
        "action": action,
        "intent": intent,
        "corrected": text
    })


if __name__ == "__main__":
    # Local-only server; bind strictly to 127.0.0.1
    logger.info("Starting Jarvis AI on http://127.0.0.1:5000 (Model: %s)", MODEL)
    app.run(host="127.0.0.1", port=5000, debug=False)

// J.A.R.V.I.S // MARK VII HUD INTERFACE LOGIC

// DOM Elements
const clockTime = document.getElementById("clockTime");
const clockSeconds = document.getElementById("clockSeconds");
const systemState = document.getElementById("systemState");
const footerState = document.getElementById("footerState");
const telemState = document.getElementById("telemState");
const audioStreamState = document.getElementById("audioStreamState");

const optJarvis = document.getElementById("optJarvis");
const optFriday = document.getElementById("optFriday");
const coreLabel = document.getElementById("coreLabel");
const corePrompt = document.getElementById("corePrompt");
const reactorButton = document.getElementById("reactorButton");

const userStreamLine = document.getElementById("userStreamLine");
const userTranscript = document.getElementById("userTranscript");
const aiStreamLine = document.getElementById("aiStreamLine");
const aiTag = document.getElementById("aiTag");
const aiResponse = document.getElementById("aiResponse");

const hudCommandForm = document.getElementById("hudCommandForm");
const commandInput = document.getElementById("commandInput");
const transmitBtn = document.getElementById("transmitBtn");

const btnVoiceToggle = document.getElementById("btnVoiceToggle");
const voiceBtnLabel = document.getElementById("voiceBtnLabel");
const btnStopVoice = document.getElementById("btnStopVoice");
const btnAudioToggle = document.getElementById("btnAudioToggle");
const audioIcon = document.getElementById("audioIcon");
const audioLabel = document.getElementById("audioLabel");

const btnHistoryToggle = document.getElementById("btnHistoryToggle");
const logDrawer = document.getElementById("logDrawer");
const btnCloseDrawer = document.getElementById("btnCloseDrawer");
const logHistoryList = document.getElementById("logHistoryList");
const logCount = document.getElementById("logCount");

// State Variables
let currentPersonality = "jarvis"; // "jarvis" or "friday"
let continuousMode = false;
let isListening = false;
let isJarvisSpeaking = false;
let isAudioMuted = false;
let recognition = null;
let restartTimeout = null;
let directivesCount = 0;
let audioCtx = null;

// ==========================================
// 1. LIVE HUD CLOCK & TELEMETRY
// ==========================================
function updateClock() {
  const now = new Date();
  const hrs = String(now.getHours()).padStart(2, "0");
  const mins = String(now.getMinutes()).padStart(2, "0");
  const secs = String(now.getSeconds()).padStart(2, "0");
  
  if (clockTime) clockTime.textContent = `${hrs}:${mins}`;
  if (clockSeconds) clockSeconds.textContent = secs;
}
setInterval(updateClock, 1000);
updateClock();

// ==========================================
// 2. PROCEDURAL SVG RADIAL TICKS
// ==========================================
function generateSvgTicks() {
  const group = document.getElementById("svgTicksGroup");
  if (!group) return;
  const count = 72; // every 5 degrees
  const cx = 250, cy = 250, rOuter = 236, rInner = 224;
  let html = "";
  
  for (let i = 0; i < count; i++) {
    const angle = (i * 360 / count) * (Math.PI / 180);
    const isMajor = i % 6 === 0;
    const inner = isMajor ? rInner - 4 : rInner;
    const x1 = cx + rOuter * Math.cos(angle);
    const y1 = cy + rOuter * Math.sin(angle);
    const x2 = cx + inner * Math.cos(angle);
    const y2 = cy + inner * Math.sin(angle);
    const stroke = isMajor ? "rgba(0, 242, 254, 0.7)" : "rgba(0, 242, 254, 0.25)";
    const width = isMajor ? 2 : 1;
    html += `<line x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}" stroke="${stroke}" stroke-width="${width}" />`;
  }
  group.innerHTML = html;
}
generateSvgTicks();

// ==========================================
// 3. CANVAS SCI-FI BACKGROUND GRID
// ==========================================
const gridCanvas = document.getElementById("gridCanvas");
if (gridCanvas) {
  const ctx = gridCanvas.getContext("2d");
  function resizeCanvas() {
    gridCanvas.width = window.innerWidth;
    gridCanvas.height = window.innerHeight;
    drawGrid();
  }
  function drawGrid() {
    const w = gridCanvas.width, h = gridCanvas.height;
    ctx.clearRect(0, 0, w, h);
    
    ctx.strokeStyle = currentPersonality === "friday" ? "rgba(245, 158, 11, 0.05)" : "rgba(0, 242, 254, 0.04)";
    ctx.lineWidth = 1;
    const step = 48;

    for (let x = 0; x <= w; x += step) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, h);
      ctx.stroke();
    }
    for (let y = 0; y <= h; y += step) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(w, y);
      ctx.stroke();
    }
  }
  window.addEventListener("resize", resizeCanvas);
  resizeCanvas();
}

// ==========================================
// 4. SYNTHESIZED WEB AUDIO HUD SOUNDS
// ==========================================
function playHudBeep(freq = 600, duration = 0.08) {
  try {
    if (!audioCtx) {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (audioCtx.state === "suspended") {
      audioCtx.resume();
    }
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.type = "sine";
    osc.frequency.setValueAtTime(freq, audioCtx.currentTime);
    gain.gain.setValueAtTime(0.04, audioCtx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + duration);
    osc.connect(gain);
    gain.connect(audioCtx.destination);
    osc.start();
    osc.stop(audioCtx.currentTime + duration);
  } catch (e) {}
}

// ==========================================
// 5. HUD STATE MANAGER
// ==========================================
function setHudState(state) {
  const upper = state.toUpperCase();
  if (systemState) systemState.textContent = upper;
  if (footerState) footerState.textContent = upper;
  if (telemState) telemState.textContent = upper;

  if (state === "listening") {
    reactorButton.classList.add("listening");
    reactorButton.classList.remove("speaking");
    corePrompt.textContent = "LISTENING // SPEAK ANYTIME";
    if (audioStreamState) audioStreamState.textContent = "ENGAGED";
  } else if (state === "speaking") {
    reactorButton.classList.remove("listening");
    reactorButton.classList.add("speaking");
    corePrompt.textContent = "TRANSMITTING VOCAL DATA";
    if (audioStreamState) audioStreamState.textContent = "TRANSMITTING";
  } else if (state === "processing") {
    reactorButton.classList.remove("listening", "speaking");
    corePrompt.textContent = "PROCESSING DIRECTIVE...";
    if (audioStreamState) audioStreamState.textContent = "ANALYZING";
  } else {
    reactorButton.classList.remove("listening", "speaking");
    corePrompt.textContent = continuousMode ? "CONTINUOUS VOICE ACTIVE" : "CLICK CORE TO ENGAGE";
    if (audioStreamState) audioStreamState.textContent = continuousMode ? "STANDBY (ACTIVE)" : "STANDBY";
  }
}

// ==========================================
// 6. PERSONALITY SWITCHER (JARVIS vs FRIDAY)
// ==========================================
function switchPersonality(name) {
  currentPersonality = name.toLowerCase();
  playHudBeep(750, 0.1);

  if (currentPersonality === "friday") {
    document.body.classList.remove("theme-jarvis");
    document.body.classList.add("theme-friday");
    optFriday.classList.add("active");
    optJarvis.classList.remove("active");
    coreLabel.textContent = "F.R.I.D.A.Y";
    aiTag.textContent = "FRIDAY //";
    aiResponse.textContent = "Friday online, Boss. Ready for your directives.";
  } else {
    document.body.classList.remove("theme-friday");
    document.body.classList.add("theme-jarvis");
    optJarvis.classList.add("active");
    optFriday.classList.remove("active");
    coreLabel.textContent = "J.A.R.V.I.S";
    aiTag.textContent = "JARVIS //";
    aiResponse.textContent = "Jarvis online and at your service, sir.";
  }

  if (gridCanvas && typeof drawGrid === "function") drawGrid();
  addLogEntry("system", `Active AI personality switched to ${coreLabel.textContent}.`);
}

optJarvis.addEventListener("click", () => switchPersonality("jarvis"));
optFriday.addEventListener("click", () => switchPersonality("friday"));

// ==========================================
// 7. SPEECH SYNTHESIS & ECHO SUPPRESSION
// ==========================================
function getAssistantVoice() {
  if (!("speechSynthesis" in window)) return null;
  const voices = window.speechSynthesis.getVoices();
  if (!voices || !voices.length) return null;

  if (currentPersonality === "friday") {
    // Prefer Irish or female English voices for Friday
    const irish = voices.find(v => v.lang.includes("en-IE") || v.name.toLowerCase().includes("irish"));
    if (irish) return irish;
    const female = voices.find(v => v.lang.startsWith("en") && (v.name.toLowerCase().includes("female") || v.name.toLowerCase().includes("samantha") || v.name.toLowerCase().includes("victoria")));
    if (female) return female;
  }
  // Default Jarvis (British or clear English male/refined voice)
  const british = voices.find(v => v.lang.includes("en-GB") || v.name.toLowerCase().includes("uk") || v.name.toLowerCase().includes("george") || v.name.toLowerCase().includes("oliver"));
  if (british) return british;
  return voices.find(v => v.lang.startsWith("en")) || voices[0];
}

if ("speechSynthesis" in window) {
  window.speechSynthesis.onvoiceschanged = () => {};
}

function speakReply(text) {
  if (isAudioMuted || !("speechSynthesis" in window)) {
    setHudState(continuousMode ? "listening" : "idle");
    return;
  }

  try {
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = /[\u0900-\u097F]/.test(text) ? "hi-IN" : (currentPersonality === "friday" ? "en-IE" : "en-GB");
    utterance.rate = 1.02;

    const voice = getAssistantVoice();
    if (voice) utterance.voice = voice;

    utterance.onstart = () => {
      isJarvisSpeaking = true;
      setHudState("speaking");
      // Pause microphone so assistant doesn't hear itself
      if (recognition && isListening) {
        try { recognition.stop(); } catch (_) {}
      }
    };

    const onFinish = () => {
      isJarvisSpeaking = false;
      setHudState(continuousMode ? "listening" : "idle");
      // Automatically resume continuous listening after reply finishes
      if (continuousMode) {
        if (restartTimeout) clearTimeout(restartTimeout);
        restartTimeout = setTimeout(() => {
          if (continuousMode && !isJarvisSpeaking) startVoice();
        }, 350);
      }
    };

    utterance.onend = onFinish;
    utterance.onerror = onFinish;

    window.speechSynthesis.speak(utterance);
  } catch (err) {
    isJarvisSpeaking = false;
    setHudState(continuousMode ? "listening" : "idle");
  }
}

// ==========================================
// 8. CONTINUOUS SPEECH RECOGNITION (WEB SPEECH API)
// ==========================================
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

if (SpeechRecognition) {
  recognition = new SpeechRecognition();
  recognition.lang = "en-IN";
  recognition.continuous = true;
  recognition.interimResults = false;

  recognition.onstart = () => {
    isListening = true;
    updateVoiceUI(true);
    setHudState("listening");
    playHudBeep(880, 0.08);
  };

  recognition.onend = () => {
    isListening = false;
    // Auto-restart if continuous mode is active and not currently speaking
    if (continuousMode && !isJarvisSpeaking) {
      if (restartTimeout) clearTimeout(restartTimeout);
      restartTimeout = setTimeout(() => {
        if (continuousMode && !isJarvisSpeaking) startVoice();
      }, 300);
    } else if (!continuousMode) {
      updateVoiceUI(false);
      setHudState("idle");
    }
  };

  recognition.onerror = e => {
    if (e.error === "no-speech" || e.error === "aborted") return;
    if (e.error === "not-allowed" || e.error === "service-not-allowed") {
      stopVoice();
      showAiResponse("Microphone permission denied. Please allow microphone access in browser settings.", true);
      return;
    }
    console.warn("Speech recognition notice:", e.error);
  };

  recognition.onresult = e => {
    let transcript = "";
    for (let i = e.resultIndex; i < e.results.length; ++i) {
      if (e.results[i].isFinal) {
        transcript += e.results[i][0].transcript;
      }
    }
    transcript = transcript.trim();
    if (!transcript && e.results[0] && e.results[0][0]) {
      transcript = e.results[0][0].transcript.trim();
    }

    if (transcript) {
      handleUserDirective(transcript);
    }
  };
} else {
  if (btnVoiceToggle) {
    btnVoiceToggle.disabled = true;
    voiceBtnLabel.textContent = "VOICE N/A";
  }
}

function startVoice() {
  if (!recognition || !continuousMode || isJarvisSpeaking) return;
  try {
    recognition.start();
  } catch (err) {}
}

function toggleContinuousVoice() {
  if (continuousMode) {
    stopVoice();
  } else {
    continuousMode = true;
    updateVoiceUI(true);
    startVoice();
  }
}

function stopVoice() {
  continuousMode = false;
  if (restartTimeout) clearTimeout(restartTimeout);
  if (recognition) {
    try { recognition.stop(); } catch (_) {}
  }
  if ("speechSynthesis" in window) {
    window.speechSynthesis.cancel();
  }
  isJarvisSpeaking = false;
  isListening = false;
  updateVoiceUI(false);
  setHudState("idle");
  playHudBeep(400, 0.1);
}

function updateVoiceUI(active) {
  if (active) {
    btnVoiceToggle.classList.add("active");
    voiceBtnLabel.textContent = "VOICE: ON";
  } else {
    btnVoiceToggle.classList.remove("active");
    voiceBtnLabel.textContent = "VOICE: OFF";
  }
}

// Click Arc Reactor Core directly to toggle continuous listening!
reactorButton.addEventListener("click", () => {
  toggleContinuousVoice();
});

btnVoiceToggle.addEventListener("click", () => {
  toggleContinuousVoice();
});

btnStopVoice.addEventListener("click", () => {
  stopVoice();
});

// Audio reply toggle
btnAudioToggle.addEventListener("click", () => {
  isAudioMuted = !isAudioMuted;
  if (isAudioMuted) {
    audioIcon.textContent = "🔇";
    audioLabel.textContent = "SPEECH: OFF";
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
  } else {
    audioIcon.textContent = "🔊";
    audioLabel.textContent = "SPEECH: ON";
  }
  playHudBeep(650, 0.05);
});

// ==========================================
// 9. COMMAND EXECUTION & HOLOGRAPHIC STREAM
// ==========================================
function showUserTranscript(text) {
  userTranscript.textContent = `"${text}"`;
  userStreamLine.style.display = "flex";
}

function showAiResponse(text, isError = false) {
  aiResponse.textContent = text;
  aiStreamLine.className = `stream-line ai-line${isError ? " error" : ""}`;
}

async function handleUserDirective(text) {
  text = text.trim();
  if (!text) return;

  if ("speechSynthesis" in window) {
    window.speechSynthesis.cancel();
  }

  showUserTranscript(text);
  showAiResponse("Processing neural query...");
  setHudState("processing");
  if (transmitBtn) transmitBtn.disabled = true;

  addLogEntry("user", text);

  try {
    const res = await fetch("/api/command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text,
        personality: currentPersonality
      })
    });

    const data = await res.json();
    const isErr = data.action === "error";
    const reply = data.reply || "Directive processed.";

    showAiResponse(reply, isErr);
    addLogEntry(isErr ? "system" : "bot", reply);
    speakReply(reply);
  } catch (err) {
    const errorMsg = "Local server connection lost. Check app.py running on port 5000.";
    showAiResponse(errorMsg, true);
    addLogEntry("system", errorMsg);
    setHudState(continuousMode ? "listening" : "idle");
  } finally {
    if (transmitBtn) transmitBtn.disabled = false;
    commandInput.value = "";
    commandInput.focus();
  }
}

hudCommandForm.addEventListener("submit", e => {
  e.preventDefault();
  handleUserDirective(commandInput.value);
});

// ==========================================
// 10. HISTORY LOG DRAWER
// ==========================================
function addLogEntry(who, text) {
  directivesCount++;
  if (logCount) logCount.textContent = directivesCount;

  const now = new Date();
  const timeStr = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}:${String(now.getSeconds()).padStart(2, "0")}`;

  const entry = document.createElement("div");
  entry.className = `log-entry ${who}`;
  
  const timeSpan = document.createElement("span");
  timeSpan.className = "log-time";
  timeSpan.textContent = `[${timeStr}]`;

  const textSpan = document.createElement("span");
  textSpan.className = "log-text";
  const prefix = who === "user" ? "USER: " : (who === "bot" ? `${coreLabel.textContent}: ` : "SYS: ");
  textSpan.textContent = `${prefix}${text}`;

  entry.append(timeSpan, textSpan);
  logHistoryList.appendChild(entry);
  logHistoryList.scrollTop = logHistoryList.scrollHeight;
}

btnHistoryToggle.addEventListener("click", () => {
  logDrawer.classList.toggle("open");
  playHudBeep(700, 0.05);
});

btnCloseDrawer.addEventListener("click", () => {
  logDrawer.classList.remove("open");
});

// Check backend status on load
fetch("/api/status")
  .then(r => r.json())
  .then(data => {
    if (data.configured) {
      addLogEntry("system", `Gemini model ${data.model} connected successfully.`);
    } else {
      addLogEntry("system", "Gemini API key missing in .env.");
    }
  })
  .catch(() => {
    addLogEntry("system", "Flask backend is offline.");
  });

console.log("Jarvis Mark VII HUD loaded.");

// Background module of /domage/ (amando.xm): chiptune3 (libopenmpt in WebAssembly) replaces the
// ModPlug plugin. Browsers block sound before a gesture: it starts on the first click or key press
// in the frameset (content frame or this one); the button pauses and resumes it. Loops forever.
import { ChiptuneJsPlayer } from "./chiptune/chiptune3.js";

const btn = document.getElementById("play");
const state = document.getElementById("state");
let player = null, ready = false, playing = false, starting = false;

function show() {
  btn.textContent = playing ? "Pause" : "Play";
  btn.setAttribute("aria-pressed", String(playing));
}

function start() {
  if (player || starting) return;
  starting = true;
  state.textContent = "loading...";
  player = new ChiptuneJsPlayer({ repeatCount: -1 });
  player.onInitialized(() => {
    player.context.resume();
    player.load("amando.xm");
  });
  player.onError(() => { state.textContent = "cannot play here"; });
  player.onMetadata(() => { ready = true; playing = true; state.textContent = "Amando"; show(); });
}

btn.addEventListener("click", () => {
  if (!player) return start();
  if (!ready) return;
  player.togglePause();
  playing = !playing;
  show();
});

// First gesture in this frame starts the tune; the content frame calls startTune() on its own first gesture.
window.startTune = start;
const go = (e) => { if (!e.target.closest || !e.target.closest("#play")) start(); };
document.addEventListener("pointerdown", go, { once: true });
document.addEventListener("keydown", go, { once: true });

"""
friday/hud.py
-------------
JARVIS holographic orb HUD — PySide6 QWebEngineView + Canvas 2D.

Always-on-top, frameless, click-through, per-pixel transparent overlay in the
top-right corner. Embeds the Holographic Interface design with a 9-state visual
machine:
  idle | wake | listening | thinking | speaking | noting | error | fading

FridayCore (background thread) puts events on a queue.Queue.
A GUI-thread QTimer polls the queue and pushes state changes via runJavaScript().

WebView2/pywebview could not do per-pixel transparency on Windows 11 (it paints
"transparent" pixels as a solid box). Qt's QWebEngineView with a frameless
WA_TranslucentBackground widget + transparent page background is the proven path.
"""

import json
from queue import Empty, Queue

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineWidgets import QWebEngineView

from friday import config as cfg

# ── Event constants (imported by main.py and FridayCore) ─────────────────────
EVT_WAKE_DETECTED  = "wake_detected"
EVT_PARTIAL        = "partial"
EVT_COMMAND_FINAL  = "command_final"
EVT_THINKING       = "thinking"
EVT_SPEAKING_START = "speaking_start"
EVT_SPEAKING_END   = "speaking_end"
EVT_NOTING         = "noting"
EVT_NOTE_SAVED     = "note_saved"
EVT_ERROR          = "error"
EVT_SHUTDOWN       = "shutdown"

# ── Embedded holographic HTML ─────────────────────────────────────────────────
_HUD_HTML = """\
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Friday HUD</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  html,body{height:100%;width:100%;overflow:hidden;background:transparent;}
  canvas{position:fixed;inset:0;width:100%;height:100%;display:block;background:transparent;
         filter:drop-shadow(0 0 22px rgba(255,170,40,0.30));}
</style>
</head>
<body>
<canvas id="c"></canvas>
<script>
const cvs = document.getElementById('c');
const ctx = cvs.getContext('2d');
let DPR = Math.min(window.devicePixelRatio || 1, 2);

function fit() {
  DPR = Math.min(window.devicePixelRatio || 1, 2);
  cvs.width  = window.innerWidth  * DPR;
  cvs.height = window.innerHeight * DPR;
}
fit();
addEventListener('resize', fit);

// ── State machine ─────────────────────────────────────────────────────────────
// Called from Python via window.evaluate_js()
let hudState    = 'idle';
let hudText     = '';
let stateT      = 0;
let canvasAlpha = 0.45;
let targetAlpha = 0.45;
let orbCY       = 0;   // orb vertical centre, set each frame

function setHudState(state, text) {
  hudState    = state;
  hudText     = text || '';
  stateT      = t;
  targetAlpha = (state === 'idle' || state === 'fading') ? 0.45 : 1.0;
}

function RGB() {
  switch (hudState) {
    case 'noting':   return [40,  200, 255];   // cyan
    case 'error':    return [255,  60,  40];   // red
    case 'thinking': return [150, 210, 255];   // ice blue
    default:         return [255, 170,  40];   // amber
  }
}
function C(a) { const [r,g,b] = RGB(); return `rgba(${r},${g},${b},${a})`; }

function speedMul() {
  switch (hudState) {
    case 'wake':                         return 3.0;
    case 'thinking':                     return 2.5;
    case 'listening': case 'speaking':
    case 'noting':                       return 1.8;
    case 'error':                        return 2.0;
    case 'fading':                       return 0.6;
    default:                             return 1.0;
  }
}

function sphereRadius() {
  return Math.min(window.innerWidth, window.innerHeight) * 0.36;
}

// ── Sphere geometry (built once) ─────────────────────────────────────────────
const N_LAT = 26, N_LON = 40;
const bv = [];
for (let i = 1; i < N_LAT; i++) {
  const th = Math.PI * i / N_LAT;
  for (let j = 0; j < N_LON; j++) {
    const ph = 2 * Math.PI * j / N_LON;
    bv.push({
      sx: Math.sin(th) * Math.cos(ph),
      sy: Math.cos(th),
      sz: Math.sin(th) * Math.sin(ph),
      jitter: Math.random() * 0.5 + 0.5
    });
  }
}

const nodes = [];
for (let i = 0; i < 160; i++) {
  const u = Math.random(), v = Math.random();
  const th = Math.acos(2 * u - 1), ph = 2 * Math.PI * v;
  const r  = 0.35 + Math.random() * 0.65;
  nodes.push({
    sx: r * Math.sin(th) * Math.cos(ph),
    sy: r * Math.cos(th),
    sz: r * Math.sin(th) * Math.sin(ph),
    size:  Math.random() * 1.4 + 0.4,
    pulse: Math.random() * Math.PI * 2
  });
}

const edges = [];
for (let i = 0; i < nodes.length; i++) {
  for (let j = i + 1; j < nodes.length; j++) {
    const dx = nodes[i].sx - nodes[j].sx;
    const dy = nodes[i].sy - nodes[j].sy;
    const dz = nodes[i].sz - nodes[j].sz;
    if (dx*dx + dy*dy + dz*dz < 0.14 && Math.random() < 0.35)
      edges.push([i, j, Math.random()]);
  }
}

const motes = [];
for (let i = 0; i < 70; i++)
  motes.push({ e: (Math.random() * edges.length) | 0, t: Math.random(), s: Math.random() * 0.005 + 0.002 });

const dust = [];
for (let i = 0; i < 420; i++) {
  const u = Math.random(), v = Math.random();
  const th = Math.acos(2 * u - 1), ph = 2 * Math.PI * v;
  const r  = Math.pow(Math.random(), 0.5) * 0.95;
  dust.push({
    sx: r * Math.sin(th) * Math.cos(ph),
    sy: r * Math.cos(th),
    sz: r * Math.sin(th) * Math.sin(ph),
    a: Math.random() * 0.6 + 0.2
  });
}

// ── 3-D helpers ───────────────────────────────────────────────────────────────
function rot(p, ax, ay) {
  const cy2 = Math.cos(ay), sy2 = Math.sin(ay);
  let x = p.x * cy2 - p.z * sy2, z = p.x * sy2 + p.z * cy2;
  const cx2 = Math.cos(ax), sx2 = Math.sin(ax);
  let y = p.y * cx2 - z * sx2; z = p.y * sx2 + z * cx2;
  return { x, y, z };
}
// Uses global orbCY so all geometry centres on the orb, not the canvas midpoint
function project(p, w) {
  const FOV = 700, sc = FOV / (FOV + p.z);
  return { x: w / 2 + p.x * sc, y: orbCY + p.y * sc, s: sc };
}

// ── Render loop ───────────────────────────────────────────────────────────────
let t = 0, ayAcc = 0;

function frame() {
  t++;

  // Auto-transitions
  if (hudState === 'wake'   && (t - stateT) > 36)  setHudState('listening', '');
  if (hudState === 'fading' && (t - stateT) > 120) setHudState('idle', '');

  // Smooth opacity
  canvasAlpha += (targetAlpha - canvasAlpha) * 0.07;

  const W = cvs.width, H = cvs.height;
  ctx.clearRect(0, 0, W, H);   // leave cleared pixels fully transparent
  ctx.save();
  ctx.scale(DPR, DPR);
  ctx.globalAlpha = canvasAlpha;

  const w = W / DPR, h = H / DPR, cx = w / 2;
  orbCY     = h * 0.42;
  const R   = sphereRadius();
  const spd = speedMul();
  ayAcc    += 0.0042 * spd;
  const ax  = Math.sin(t * 0.0023) * 0.25 + 0.15;
  const ay  = ayAcc;
  const glowM = hudState === 'idle' ? 0.55 : 1.2;

  // ── Core ambient glow ──────────────────────────────────────────────────────
  const grd = ctx.createRadialGradient(cx, orbCY, 10, cx, orbCY, R * 1.4);
  grd.addColorStop(0,    C(0.32 * glowM));
  grd.addColorStop(0.35, C(0.16 * glowM));
  grd.addColorStop(1,    C(0));
  ctx.fillStyle = grd;
  ctx.beginPath(); ctx.arc(cx, orbCY, R * 1.4, 0, Math.PI * 2); ctx.fill();

  // ── Orbital rings ──────────────────────────────────────────────────────────
  ctx.lineWidth = 1;
  for (let ri = 0; ri < 5; ri++) {
    const tilt  = (ri - 2) * 0.10 + Math.sin(t * 0.001) * 0.05;
    const ringR = R * 1.05 + ri * (R * 0.057);
    ctx.beginPath();
    for (let i = 0; i <= 240; i++) {
      const a  = (i / 240) * Math.PI * 2;
      const p  = rot(
        { x: Math.cos(a) * ringR, y: Math.sin(a) * ringR * tilt, z: Math.sin(a) * ringR },
        ax * 0.6, ay * 0.6 + ri * 0.3
      );
      const pr = project(p, w);
      i === 0 ? ctx.moveTo(pr.x, pr.y) : ctx.lineTo(pr.x, pr.y);
    }
    ctx.strokeStyle = C(0.18 + 0.06 * Math.sin(t * 0.01 + ri));
    ctx.stroke();
  }

  // ── Sphere wireframe dots ──────────────────────────────────────────────────
  const [cr, cg, cb] = RGB();
  for (const v0 of bv) {
    const p  = rot({ x: v0.sx * R, y: v0.sy * R, z: v0.sz * R }, ax, ay);
    const pr = project(p, w);
    const a  = 0.18 + (pr.s - 0.6) * 0.9;
    const tw = v0.jitter * (0.8 + 0.4 * Math.sin(t * 0.04 + v0.sx * 3));
    ctx.globalAlpha = canvasAlpha * Math.max(0, Math.min(1, a * tw));
    ctx.fillStyle = `rgba(${cr},${Math.round(cg * 0.85)},${Math.round(cb * 0.35)},0.55)`;
    ctx.fillRect(pr.x - 0.6, pr.y - 0.6, 1.2, 1.2);
  }
  ctx.globalAlpha = canvasAlpha;

  // ── Inner dust ─────────────────────────────────────────────────────────────
  for (const d of dust) {
    const p  = rot({ x: d.sx * R, y: d.sy * R, z: d.sz * R }, ax, ay);
    const pr = project(p, w);
    ctx.globalAlpha = canvasAlpha * d.a * (0.5 + 0.5 * Math.sin(t * 0.02 + d.sx * 5));
    ctx.fillStyle = `rgb(${cr},${Math.round(cg * 0.85)},${Math.round(cb * 0.45)})`;
    ctx.fillRect(pr.x, pr.y, 1, 1);
  }
  ctx.globalAlpha = canvasAlpha;

  // ── Circuit edges ──────────────────────────────────────────────────────────
  ctx.lineWidth = 0.6;
  for (const e of edges) {
    const na = nodes[e[0]], nb = nodes[e[1]];
    const pa = project(rot({ x: na.sx * R, y: na.sy * R, z: na.sz * R }, ax, ay), w);
    const pb = project(rot({ x: nb.sx * R, y: nb.sy * R, z: nb.sz * R }, ax, ay), w);
    ctx.strokeStyle = C(0.10 + 0.10 * Math.sin(t * 0.03 + e[2] * 6));
    ctx.beginPath(); ctx.moveTo(pa.x, pa.y); ctx.lineTo(pb.x, pb.y); ctx.stroke();
  }

  // ── Circuit nodes ──────────────────────────────────────────────────────────
  for (const n of nodes) {
    const p     = rot({ x: n.sx * R, y: n.sy * R, z: n.sz * R }, ax, ay);
    const pr    = project(p, w);
    const pulse = 0.6 + 0.4 * Math.sin(t * 0.05 + n.pulse);
    ctx.fillStyle = C(0.85 * pulse);
    ctx.beginPath(); ctx.arc(pr.x, pr.y, n.size * pr.s * 1.1, 0, Math.PI * 2); ctx.fill();
  }

  // ── Travelling data motes ─────────────────────────────────────────────────
  for (const m of motes) {
    m.t += m.s;
    if (m.t > 1) { m.t = 0; m.e = (Math.random() * edges.length) | 0; }
    const e = edges[m.e], na = nodes[e[0]], nb = nodes[e[1]];
    const px = (na.sx + (nb.sx - na.sx) * m.t) * R;
    const py = (na.sy + (nb.sy - na.sy) * m.t) * R;
    const pz = (na.sz + (nb.sz - na.sz) * m.t) * R;
    const pr = project(rot({ x: px, y: py, z: pz }, ax, ay), w);
    ctx.fillStyle = C(0.95);
    ctx.beginPath(); ctx.arc(pr.x, pr.y, 1.4 * pr.s, 0, Math.PI * 2); ctx.fill();
  }

  // ── HUD core glyph (mechanical rotating rings) ────────────────────────────
  const core = project(rot({ x: 0, y: 0, z: 0 }, ax, ay), w);
  ctx.save();
  ctx.translate(core.x, core.y);
  const Rc = R * 0.26;
  const cr2 = t * 0.010, cr3 = t * 0.018, cr4 = -t * 0.014;

  // ambient core glow
  const cg2 = ctx.createRadialGradient(0, 0, 0, 0, 0, Rc * 1.5);
  cg2.addColorStop(0,   C(0.55));
  cg2.addColorStop(0.5, C(0.22));
  cg2.addColorStop(1,   C(0));
  ctx.fillStyle = cg2;
  ctx.beginPath(); ctx.arc(0, 0, Rc * 1.5, 0, Math.PI * 2); ctx.fill();

  // crosshair lines
  ctx.strokeStyle = C(0.35); ctx.lineWidth = 0.6;
  ctx.beginPath();
  ctx.moveTo(-Rc * 1.4, 0); ctx.lineTo(-Rc * 0.55, 0);
  ctx.moveTo( Rc * 0.55, 0); ctx.lineTo( Rc * 1.4,  0);
  ctx.moveTo(0, -Rc * 1.4); ctx.lineTo(0, -Rc * 0.55);
  ctx.moveTo(0,  Rc * 0.55); ctx.lineTo(0,  Rc * 1.4);
  ctx.stroke();

  // outer ring with tick marks
  ctx.save(); ctx.rotate(cr2);
  ctx.strokeStyle = C(0.9); ctx.lineWidth = 1;
  ctx.beginPath(); ctx.arc(0, 0, Rc, 0, Math.PI * 2); ctx.stroke();
  ctx.beginPath(); ctx.arc(0, 0, Rc * 0.93, 0, Math.PI * 2);
  ctx.strokeStyle = C(0.45); ctx.stroke();
  ctx.strokeStyle = C(0.85); ctx.lineWidth = 1;
  for (let i = 0; i < 72; i++) {
    const a   = i / 72 * Math.PI * 2;
    const len = (i % 6 === 0) ? Rc * 0.10 : Rc * 0.05;
    const r0  = Rc * 0.93;
    ctx.beginPath();
    ctx.moveTo(Math.cos(a) * r0,         Math.sin(a) * r0);
    ctx.lineTo(Math.cos(a) * (r0 - len), Math.sin(a) * (r0 - len));
    ctx.stroke();
  }
  ctx.restore();

  // middle broken-arc ring (counter-rotates)
  ctx.save(); ctx.rotate(cr4);
  ctx.strokeStyle = C(0.95); ctx.lineWidth = 2;
  const arcR = Rc * 0.78;
  const arcs = [[0.0,1.10],[1.50,0.70],[2.55,0.45],[3.30,1.20],[4.85,0.55],[5.70,0.40]];
  for (const [s, sp] of arcs) {
    ctx.beginPath(); ctx.arc(0, 0, arcR, s, s + sp); ctx.stroke();
  }
  ctx.fillStyle = C(0.95);
  for (const [s, sp] of arcs) {
    for (const a of [s, s + sp]) {
      ctx.beginPath(); ctx.arc(Math.cos(a) * arcR, Math.sin(a) * arcR, 1.6, 0, Math.PI * 2); ctx.fill();
    }
  }
  ctx.restore();

  // segmented pie wheel
  ctx.save(); ctx.rotate(cr3);
  const wheelR = Rc * 0.55;
  for (let i = 0; i < 16; i++) {
    const a1 = i / 16 * Math.PI * 2, a2 = a1 + (Math.PI * 2 / 16) * 0.86;
    ctx.beginPath(); ctx.moveTo(0, 0); ctx.arc(0, 0, wheelR, a1, a2); ctx.closePath();
    ctx.fillStyle = C((i % 4 === 0) ? 0.55 : 0.18); ctx.fill();
  }
  ctx.strokeStyle = C(0.8); ctx.lineWidth = 1;
  ctx.beginPath(); ctx.arc(0, 0, wheelR, 0, Math.PI * 2); ctx.stroke();
  ctx.beginPath(); ctx.arc(0, 0, wheelR * 0.72, 0, Math.PI * 2);
  ctx.strokeStyle = C(0.45); ctx.stroke();
  ctx.restore();

  // inner concentric rings
  for (let i = 0; i < 3; i++) {
    ctx.strokeStyle = C(0.6 - i * 0.15); ctx.lineWidth = 0.6;
    ctx.beginPath(); ctx.arc(0, 0, Rc * (0.34 - i * 0.08), 0, Math.PI * 2); ctx.stroke();
  }

  // bright core dot
  const dg = ctx.createRadialGradient(0, 0, 0, 0, 0, Rc * 0.20);
  dg.addColorStop(0,    C(1));
  dg.addColorStop(0.45, C(0.75));
  dg.addColorStop(1,    C(0));
  ctx.fillStyle = dg;
  ctx.beginPath(); ctx.arc(0, 0, Rc * 0.20, 0, Math.PI * 2); ctx.fill();
  ctx.restore();  // end core glyph

  // ── EQ bars (listening / speaking / noting) ────────────────────────────────
  if (['listening', 'speaking', 'noting'].includes(hudState)) {
    ctx.globalAlpha = canvasAlpha;
    const barCY = orbCY + R * 0.52;
    for (let i = 0; i < 9; i++) {
      const bx    = cx - 36 + i * 9;
      const phase = (t * 0.4) + i * 0.6;
      const bh    = Math.round(8 + 14 * Math.abs(Math.sin(phase)));
      ctx.fillStyle = C(0.85);
      ctx.fillRect(bx, barCY - bh / 2, 5, bh);
    }
  }

  // ── State label text ───────────────────────────────────────────────────────
  ctx.globalAlpha = canvasAlpha;
  if (hudText) {
    ctx.fillStyle = C(0.9);
    ctx.font = 'bold 10px Consolas,monospace';
    ctx.textAlign = 'center';
    const display = hudText.length > 26 ? hudText.substring(0, 23) + '...' : hudText;
    ctx.fillText(display, cx, orbCY + R + 22);
  }

  ctx.restore();
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
</script>
</body>
</html>
"""


# ── HUD class ─────────────────────────────────────────────────────────────────

class FridayHUD:
    """Holographic orb overlay. prepare() builds it; start() blocks until closed."""

    def __init__(self, event_queue: Queue):
        self.event_queue = event_queue
        self._app     = None
        self._view    = None
        self._timer   = None
        self._running = False

    def prepare(self):
        """Build the Qt overlay window. Call on the main thread before the core thread."""
        self._app = QApplication.instance() or QApplication([])

        view = QWebEngineView()
        # Frameless + always-on-top; Qt.Tool keeps it out of the taskbar / alt-tab.
        view.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        # Per-pixel transparency (Windows: only honoured for frameless windows).
        view.setAttribute(Qt.WA_TranslucentBackground, True)
        # Click-through: mouse events pass to whatever app is beneath the orb.
        view.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        # Transparent web layer so the canvas's cleared pixels show the desktop.
        view.page().setBackgroundColor(QColor(Qt.transparent))
        view.setHtml(_HUD_HTML)

        view.setFixedSize(cfg.HUD_WINDOW_W, cfg.HUD_WINDOW_H)
        try:
            sw = self._app.primaryScreen().geometry().width()
        except Exception:
            sw = 1920
        view.move(sw - cfg.HUD_WINDOW_W - cfg.HUD_MARGIN_PX, cfg.HUD_MARGIN_PX)

        self._view = view

    def start(self):
        """Show the overlay, start the queue-drain timer, run the Qt loop (blocks)."""
        self._running = True
        self._view.show()
        # GUI-thread timer replaces the old drain thread: runJavaScript must run on
        # the GUI thread, and the periodic tick keeps the Python interpreter alive
        # so FridayCore's SIGINT/Ctrl+C handler still fires under app.exec().
        self._timer = QTimer()
        self._timer.timeout.connect(self._drain)
        self._timer.start(cfg.HUD_QUEUE_POLL_MS)
        self._app.exec()

    def stop(self):
        """Tear down the overlay, which makes app.exec() return."""
        self._running = False
        try:
            if self._timer:
                self._timer.stop()
            if self._view:
                self._view.close()
            if self._app:
                self._app.quit()
        except Exception:
            pass

    # ── Internal ──────────────────────────────────────────────────────────────

    def _drain(self):
        try:
            while True:
                evt = self.event_queue.get_nowait()
                self._handle_event(evt)
        except Empty:
            pass

    def _js(self, code: str):
        try:
            if self._view:
                self._view.page().runJavaScript(code)
        except Exception:
            pass

    def _handle_event(self, evt: dict):
        kind    = evt.get("event")
        payload = evt.get("payload") or {}

        if kind == EVT_WAKE_DETECTED:
            self._js('setHudState("wake","")')
        elif kind == EVT_PARTIAL:
            t = json.dumps(payload.get("text", ""))
            self._js(f'setHudState("listening",{t})')
        elif kind == EVT_COMMAND_FINAL:
            t = json.dumps(payload.get("text", ""))
            self._js(f'setHudState("listening",{t})')
        elif kind == EVT_THINKING:
            self._js('setHudState("thinking","")')
        elif kind == EVT_SPEAKING_START:
            t = json.dumps(payload.get("text", ""))
            self._js(f'setHudState("speaking",{t})')
        elif kind == EVT_SPEAKING_END:
            self._js('setHudState("fading","")')
        elif kind == EVT_NOTING:
            self._js('setHudState("noting","")')
        elif kind == EVT_NOTE_SAVED:
            count = payload.get("count", 0)
            self._js(f'setHudState("fading","Saved ({count} today)")')
        elif kind == EVT_ERROR:
            t = json.dumps(payload.get("text", "Error"))
            self._js(f'setHudState("error",{t})')
        elif kind == EVT_SHUTDOWN:
            self.stop()


def make_hud(event_queue) -> FridayHUD:
    """Convenience factory called from main.py."""
    return FridayHUD(event_queue)

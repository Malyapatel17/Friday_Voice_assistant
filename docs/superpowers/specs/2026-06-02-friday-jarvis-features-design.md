# Friday — JARVIS-style Features (HUD + Ask + Notes + Personality)

**Date:** 2026-06-02
**Branch:** `staging/jarvis-features` (off `main`)
**Status:** Design — pending user review

## 1. Problem and goal

Friday today is a fixed-vocabulary command launcher: four verbs (`work` / `home` / `close_tabs` / `rest`), no visual feedback, and no conversational ability — even though `friday/conversation.py` already scaffolds Groq chat (unused). The user wants Friday to feel like Iron Man's JARVIS: a cool always-present visual presence, the ability to ask questions and get spoken answers, and a small daily-utility win.

**Goal of this spec:** add three user-visible features plus a cross-cutting personality layer, without disturbing the four existing verbs or the tray/startup flow that was just stabilised.

**In scope:**

1. **JARVIS HUD overlay** — Tkinter-based transparent corner orb pinned top-right of the primary monitor, with idle / wake / listening / thinking / speaking states.
2. **Ask mode** — wire up `GroqChat` behind an `"ask <question>"` command; spoken reply via existing TTS.
3. **Voice notes** — `"take a note"` captures up to 30 s of speech and appends to a dated markdown file; `"read my notes"` plays back today's entries.
4. **Personality layer** — varied wake-word acknowledgements, time-of-day greetings, JARVIS-tone system prompt for GroqChat.

**Out of scope:**

- New wake words (still only `"friday"`).
- Streaming TTS / real-time mic-driven waveform animation.
- PyQt / Electron / web-based HUD.
- Persistent conversation memory across Friday restarts (only within a single process lifetime).
- Voice-note search, edit, delete (read + append only).
- Touching the existing `work` / `home` / `close_tabs` / `rest` dispatchers.

**Non-goals (explicitly deferred):**

- Calendar / email / system-control integrations.
- A second wake word for ambient mode.
- Multi-user profiles.

## 2. Architecture

### 2.1 Concurrency model (load-bearing)

Tkinter's `mainloop()` must run on the main thread. `FridayCore.run()` currently blocks the main thread too. Both cannot stay there.

**Resolution:**

- **Main thread:** Tkinter root + HUD `mainloop()`.
- **Background daemon thread:** `FridayCore.run()` (Vosk wake-word loop + Whisper command transcription + TTS + dispatcher).
- **IPC:** a single `queue.Queue` of event dicts. `FridayCore` calls `event_queue.put({"event": ..., "payload": ...})`. HUD drains the queue from `root.after(50, ...)`.

The PyAudio stream and TTS calls all remain inside the FridayCore thread — they are already serialised there today, and TTS already stops/starts the mic stream to prevent feedback. The HUD never touches PyAudio.

**Shutdown:** Ctrl+C in the console, "Quit" on the HUD, or `rest` verb each set `FridayCore.running = False`. The thread join is bounded by where FridayCore was when the flag flipped: ≤32 ms if in STANDBY (one Vosk frame), up to ~6 s if mid-command (the `record_command` loop). HUD waits up to 7 s on `thread.join(timeout=7)`, then calls `root.destroy()` regardless and the process exits.

### 2.2 Event protocol

The queue carries a fixed set of event types. HUD reacts to each by updating its drawing state machine.

| Event             | Payload                          | HUD reaction                                |
|-------------------|----------------------------------|---------------------------------------------|
| `wake_detected`   | `None`                           | IDLE → WAKE pulse, then LISTENING           |
| `partial`         | `{"text": str}`                  | update transcript line under orb            |
| `command_final`   | `{"text": str}`                  | freeze transcript line, brief flash         |
| `thinking`        | `None`                           | LISTENING → THINKING (spinner inside ring)  |
| `speaking_start`  | `{"text": str}`                  | THINKING → SPEAKING; show reply text        |
| `speaking_end`    | `None`                           | SPEAKING → IDLE after 3 s fade              |
| `noting`          | `None`                           | LISTENING but with "noting…" label          |
| `note_saved`      | `{"count": int}`                 | brief "saved" toast, then IDLE              |
| `error`           | `{"text": str}`                  | red ring flash, error text below, 5 s       |
| `shutdown`        | `None`                           | destroy root                                |

`FridayCore` never references Tkinter. The HUD never references PyAudio. Only the queue crosses the line.

### 2.3 Module layout

New files:

```
friday/hud.py            -- Tkinter HUD: orb canvas + state machine + animator
friday/notes.py          -- voice-note capture and playback
friday/personality.py    -- wake-word acks, time-of-day greetings
```

Modified files:

```
main.py                  -- restructured around (HUD on main thread, FridayCore on daemon thread)
friday/audio.py          -- parse_command extended with "ask"/"note_*" tokens; returns (token, payload)
friday/conversation.py   -- SYSTEM_PROMPT rewritten in JARVIS tone
friday/config.py         -- adds GROQ_MODEL, NOTES_DIR, HUD_* constants
.gitignore               -- adds /notes/
```

No existing function is renamed or deleted. `parse_command`'s return type changes (see §3.3) — every call site is in this repo and gets updated in the same change.

### 2.4 Dependencies

| Package           | Why                              | New?        |
|-------------------|----------------------------------|-------------|
| `tkinter`         | HUD                              | stdlib      |
| `groq`            | Ask mode                         | already in conversation.py imports |
| `python-dotenv`   | Load `GROQ_API_KEY` from `.env`  | **new**     |
| `pyttsx3`         | TTS                              | already used |
| `pyaudio`, `vosk`, `faster-whisper`, `pygame` | as today | unchanged |

`requirements.txt` gains `groq` and `python-dotenv`. Auto-install on tray launch is unchanged (still just `pystray`, `pillow`).

## 3. Feature detail

### 3.1 JARVIS HUD overlay (`friday/hud.py`)

**Window:**

- Root is `tk.Tk()` created in `main.py`.
- HUD lives in a `tk.Toplevel(root)` with `overrideredirect(True)` (no title bar), `wm_attributes("-topmost", True)`, `wm_attributes("-transparentcolor", "#010203")` (Windows-only — a sentinel colour the canvas paints as "see-through"), `wm_attributes("-alpha", 1.0)` (master opacity used for fades).
- Size: 220×260 px (180 px orb + 80 px text strip below).
- Position: pinned to top-right of the primary monitor with a 24 px margin. Computed once from `root.winfo_screenwidth()`.

**Drawing:** a single `tk.Canvas` 220×260 with the transparent sentinel as `bg`. Orb is two concentric arcs (outer ring + inner glow) drawn each frame. Waveform is 9 vertical bars centred in the ring whose heights are sampled from a precomputed sinusoidal table indexed by frame count. Transcript and reply text are `create_text` items below the orb.

**State machine:**

```
IDLE  --wake_detected-->  WAKE
WAKE  --(after pulse animation, ~600 ms)-->  LISTENING
LISTENING  --partial-->  LISTENING (update text)
LISTENING  --command_final-->  THINKING_OR_DISPATCH
THINKING_OR_DISPATCH  --thinking-->  THINKING
THINKING  --speaking_start-->  SPEAKING
SPEAKING  --speaking_end-->  FADING (300 ms ring dim + alpha 1.0->0.4)
FADING  --(done)-->  IDLE
ANY  --noting-->  NOTING (LISTENING variant; label says "noting...")
NOTING  --note_saved-->  FADING
ANY  --error-->  ERROR (red ring, error text, 5 s) --> FADING
```

**Animator:** a single `root.after(33, _tick)` loop runs at ~30 fps regardless of state; per-state code reads frame counter and updates canvas items. No per-state scheduling, no thread.

**Idle behaviour:** alpha 0.4, no animation, "FRIDAY" label inside ring, no transcript line. The window is click-through-OFF — clicking the orb opens a context menu (Quit Friday, Open Log).

### 3.2 Ask mode

**Trigger:** `parse_command` returns `("ask", payload)` when the utterance matches:

- starts with `"ask "` (e.g. `"ask what's the capital of peru"`)
- starts with a question word (`what`, `who`, `when`, `where`, `why`, `how`, `is`, `are`, `can`, `should`) — implicit ask
- contains `"question for you"` or `"got a question"` (with the question following)

(Note: `"hey friday"` is not a trigger here — the wake word has already fired by the time `parse_command` runs.)

The `payload` is the substring after the trigger phrase, stripped. If empty (`"ask"` with no follow-up), main.py speaks "Ask me what, boss?" and returns to standby without calling Groq.

The implicit-question-word trigger comes **after** the existing verb matches in `parse_command` (work / home / close_tabs / rest), so the four legacy verbs are never shadowed.

**Dispatch (`main.py:_handle_command`):**

```python
elif cmd == "ask":
    self._on_ask(payload)
```

`_on_ask`:

1. Push `thinking` event.
2. If `check_internet()` is False → speak "I'm offline boss, can't reach my brain right now." → return to standby.
3. Lazily construct `self._chat = GroqChat(api_key, GROQ_MODEL)` if not built. API key comes from `os.environ["GROQ_API_KEY"]` (loaded by `dotenv.load_dotenv()` at startup). Missing key → speak "I need an API key for that boss, check the readme." → return.
4. `reply = self._chat.ask(payload)`. On any exception, log and speak "Something went wrong reaching the brain boss." → return.
5. Push `speaking_start` with `text=reply`, speak reply via existing `_speak`, push `speaking_end`, return to standby.

**System prompt** (replaces existing `SYSTEM_PROMPT` in `friday/conversation.py`):

> You are Friday, a witty, concise AI assistant in the spirit of Tony Stark's JARVIS. Speak to the user as "boss" or "sir". Keep replies short and natural for voice output — no markdown, no lists, no bullet points. Maximum three sentences. Mild dry humour is welcome; do not over-explain. If you do not know something, say so briefly.

**Model:** `GROQ_MODEL = "llama-3.1-8b-instant"` in `config.py` (Groq free tier, low latency). Override via env var `GROQ_MODEL` if set.

**History:** unchanged from the existing scaffolding — last 10 turns kept in memory per `GroqChat` instance, reset on Friday restart.

**Failure modes:** all caught, all degrade to TTS apology, none crash FridayCore.

### 3.3 Voice notes (`friday/notes.py`)

**Storage:** `{PROJECT}/notes/YYYY-MM-DD.md`. Directory created on first write. Added to `.gitignore`.

**Format:**

```markdown
# Notes — 2026-06-02

- 09:14  buy milk on the way home
- 11:42  remind anu about the dentist appointment
```

**`parse_command` triggers:**

- `note_start`: any of `"take a note"`, `"new note"`, `"make a note"`, `"note this"`, `"remember this"`.
- `note_read`: any of `"read my notes"`, `"what are my notes"`, `"play my notes"`, `"any notes"`.

**Capture flow (`_on_note_start`):**

1. Speak "Go ahead boss." (uses personality variant).
2. Push `noting` event.
3. Call `audio.record_command(max_seconds=30.0, silence_secs=2.0)` — longer than command capture so the user can pause mid-thought.
4. Transcribe with Whisper (same call as commands, no special config).
5. If text is empty → speak "Didn't catch that boss." → push `speaking_end` (no `note_saved`, since nothing was saved) → return.
6. `notes.append(text)` — writes `- HH:MM  {text}` to today's file (creates if missing). Returns total entry count for today.
7. Speak "Noted boss." → push `note_saved` with count → return.

**Read flow (`_on_note_read`):**

1. `entries = notes.read_today()` — returns list of `(time_str, text)`.
2. If empty → speak "No notes today boss." → return.
3. Push `speaking_start` with text="\n".join(entries).
4. For each `(time, text)` → speak `"At {time}, {text}."`. Throttled by TTS itself.
5. Push `speaking_end`.

**`notes.py` API:**

```python
def append(text: str) -> int          # returns new total entry count for today
def read_today() -> list[tuple[str, str]]  # [(HH:MM, text), ...] in file order
def _today_path() -> Path              # internal; ensures parent dir
```

No edit / delete API. Out of scope.

### 3.4 Personality layer (`friday/personality.py`)

```python
WAKE_ACKS = [
    "Yes boss",
    "I'm listening sir",
    "At your service",
    "Standing by",
    "Go ahead boss",
    "Boss?",
    "How can I help",
    "Right here sir",
]

def wake_ack() -> str:
    return random.choice(WAKE_ACKS)

def greet_for_time_of_day(now: datetime | None = None) -> str:
    # 05:00-11:59 -> "Good morning sir"
    # 12:00-16:59 -> "Good afternoon boss"
    # 17:00-21:59 -> "Good evening sir"
    # 22:00-04:59 -> "You're up late boss"
    ...
```

**Wiring:**

- `main.py:109` (current `self._speak("Yes boss, I'm listening")`) → `self._speak(personality.wake_ack())`.
- `main.py` startup (after model load, before main loop) → `self._speak(personality.greet_for_time_of_day())`. Gated by a `--no-greeting` CLI flag for debugging.
- `friday/conversation.py:SYSTEM_PROMPT` → JARVIS-tone string above.

That is the entire personality surface. No persistence, no mood, no config.

## 4. Configuration changes (`friday/config.py`)

Appended:

```python
# ── Ask mode (GroqChat) ─────────────────────────────
GROQ_MODEL = "llama-3.1-8b-instant"

# ── Voice notes ─────────────────────────────────────
NOTES_DIR = "notes"  # relative to project root

# ── HUD ─────────────────────────────────────────────
HUD_MARGIN_PX      = 24
HUD_ORB_SIZE_PX    = 180
HUD_TEXT_HEIGHT_PX = 80
HUD_FADE_DELAY_SEC = 3.0
HUD_IDLE_ALPHA     = 0.40
HUD_ACTIVE_ALPHA   = 1.00
HUD_TRANSPARENT_KEY = "#010203"  # sentinel colour painted as see-through
```

`EDGE_VOICE` (referenced by `tts.py:_speak_online`) does **not** exist in `config.py` today. Out of scope for this spec — the online path is dormant. Leave it alone.

## 5. `.gitignore`

Append:

```
/notes/
.env
```

## 6. Setup notes for the user (not code)

- Create `.env` next to `main.py` containing `GROQ_API_KEY=...`. Free key at https://console.groq.com.
- `.env` is git-ignored.
- If the key is missing, Ask mode degrades to a spoken apology; HUD / notes / existing verbs are unaffected.

## 7. Risks and mitigations

| Risk                                                                                      | Mitigation                                                                                                            |
|-------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------|
| Tkinter `-transparentcolor` is Windows-only; macOS/Linux see opaque sentinel              | Fine — Friday is Windows-only per CLAUDE.md. Document as Windows assumption in `hud.py` header.                       |
| HUD on main thread + FridayCore on daemon thread changes shutdown semantics               | Explicit teardown order: `running=False` → join with 2 s timeout → `root.destroy()`. Existing Ctrl+C handler refactored. |
| `tray` launches via `pythonw.exe` (no console) — Tkinter still draws fine                 | Verified by inspection; pythonw + Tkinter is standard. Tray-launch path tested in §9.                                  |
| Groq API rate limits / key revoked                                                        | All Groq calls in try/except; user gets a spoken apology, FridayCore continues.                                       |
| Wake-word false positives during Ask reply (Friday hears herself)                         | Already mitigated by `tts._speak_offline` stopping the mic stream. SPEAKING state in HUD is purely visual.            |
| Notes file conflicts under concurrent appends                                             | Single-process, single-thread writer (FridayCore thread). No concurrency.                                              |
| Whisper transcribes a 30 s note slowly on CPU fallback                                    | Acceptable — user is told "Noted boss" only after transcription completes. HUD shows NOTING state throughout.         |

## 8. Branch and merge strategy

- New branch `staging/jarvis-features` off current `main`.
- All work lands on the branch via subagent-owned commits (see §10).
- No squash on merge to `main` — keep individual subagent commits for traceability.
- The previous spec's reboot-test (Task 6) is **not** blocked by this work; if reboot uncovers a regression there, it gets fixed on `main` and `staging/jarvis-features` rebases.

## 9. Manual verification plan

No automated tests (per CLAUDE.md: "no tests, lints, or build steps configured"). Each feature gets a manual checklist; all run under `start_friday.bat` (console attached) and again under tray launch (pythonw, no console).

**HUD:**
- [ ] Orb appears top-right within 2 s of FridayCore start, idle gray, 40 % opacity.
- [ ] On `"Friday"`, orb pulses cyan, ack heard, state → LISTENING.
- [ ] Live partial transcript appears under the orb during command capture.
- [ ] After dispatch, HUD shows THINKING (Ask) or SPEAKING (other verbs).
- [ ] Returns to IDLE within 3 s of `speaking_end`.
- [ ] Survives sleep/wake of the monitor.

**Ask mode:**
- [ ] `"Friday"` → `"ask what's the capital of peru"` → spoken reply within ~2 s, ≤3 sentences.
- [ ] Offline (Wi-Fi off) → `"I'm offline boss…"` apology, no crash.
- [ ] Bad/missing API key → `"I need an API key…"` apology, no crash.
- [ ] Two consecutive asks remember context (one history turn in the same Friday process).

**Notes:**
- [ ] `"Friday"` → `"take a note"` → "Go ahead boss" → speak content → "Noted boss" → file `notes/YYYY-MM-DD.md` contains `- HH:MM  <content>`.
- [ ] `"Friday"` → `"read my notes"` → today's entries read back in order.
- [ ] No notes today → `"No notes today boss."`.

**Personality:**
- [ ] Five wake-word triggers in a row produce at least three distinct acks.
- [ ] Startup greeting matches time of day.
- [ ] Ask replies feel JARVIS-toned (subjective; user judges).

**Regression on existing verbs:**
- [ ] `"start work"` still opens Gmail (work profile) + Claude + ChatGPT (personal) + VS Code.
- [ ] `"daddy is home"` still opens YouTube + Hotstar + Prime.
- [ ] `"close all tabs"` still closes browsers + opens shutdown dialog.
- [ ] `"you can rest"` still exits Friday cleanly (and now also destroys the HUD).

## 10. Subagent decomposition (input to writing-plans / executing-plans)

Three subagents. **Agent A merges first** because it owns the concurrency refactor every other change builds on.

### Agent A — HUD + concurrency refactor

- New: `friday/hud.py` (orb, state machine, animator).
- Modify: `main.py` — restructure entry point: create `tk.Tk()` root, create `event_queue`, start `FridayCore(event_queue=queue).run()` in daemon thread, run `mainloop()`. Refactor `_speak` and `_handle_standby` / `_handle_command` to push events.
- Modify: `friday/config.py` — add HUD constants.
- Modify: nothing else.

Verifies: HUD section of §9 + regression on existing verbs.

### Agent B — Ask mode + personality

- New: `friday/personality.py`.
- Modify: `friday/conversation.py` — rewrite `SYSTEM_PROMPT`. Public API unchanged.
- Modify: `friday/audio.py:parse_command` — add `"ask"` token, return `(token, payload)` tuple. **This is a breaking signature change introduced by Agent B**; Agent B updates `main.py:_handle_command` to consume the tuple at the same time. Agent A leaves `parse_command` alone, so its `main.py` continues to use the legacy single-string return until B merges.
- Modify: `main.py:_handle_command` — add `ask` branch + `_on_ask`. Replace fixed wake ack with `personality.wake_ack()`. Add startup greeting + `--no-greeting` flag.
- Modify: `friday/config.py` — add `GROQ_MODEL`.
- Modify: `requirements.txt` — add `groq`, `python-dotenv`.
- Modify: `main.py` entry point — `dotenv.load_dotenv()` before `FridayCore` constructor.

Verifies: Ask + Personality sections of §9.

### Agent C — Voice notes

- New: `friday/notes.py`.
- Modify: `friday/audio.py:parse_command` — add `note_start` / `note_read` tokens (payload empty). Consumes the `(token, payload)` tuple signature **established by Agent B** — so Agent C must merge **after** Agent B.
- Modify: `main.py:_handle_command` — add `note_start` / `note_read` branches + `_on_note_start` / `_on_note_read`.
- Modify: `.gitignore` — add `/notes/`, `.env`.

Verifies: Notes section of §9.

**Merge order:** strictly **A → B → C** on `staging/jarvis-features`. B and C cannot parallelise because both extend `parse_command` and C depends on B's tuple signature. (B and C *can* be authored in parallel by separate subagents — the dependency is at merge/integration time, not authoring time. C just needs to rebase on B before merging.) Final reconciliation commit on the branch only if integration surfaces a conflict the subagents couldn't resolve solo.

## 11. Out-of-scope follow-ups (note for later)

- Real-time waveform driven by `record_command` amplitude samples (requires AudioManager → HUD event for amplitude — extra wire).
- Streaming Groq responses with token-by-token TTS.
- Notes search / edit / delete commands.
- HUD-context menu items beyond Quit / Open Log.
- Persistent conversation memory (SQLite or jsonl) so Ask mode remembers across restarts.

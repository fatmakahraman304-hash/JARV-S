"""Offline 'Hey FRIDAY' detection on 16 kHz microphone frames."""
from __future__ import annotations

from importlib.util import find_spec
import json
import os
import queue
import threading
from pathlib import Path
from typing import Callable

MODEL_NAME = "vosk-model-small-en-us-0.15"
# Vosk may transcribe the FRIDAY (EY-TIR) wake word as "either".
KEYPHRASE = "hey friday"
KEYPHRASES = ("hey friday", "hello friday", "hey either", "hey aether", "hey ether")
DEFAULT_THRESHOLD = 0.8
SAMPLE_RATE = 16000


def _model_path():
    # Match Vosk's search order without importing its native library on the UI thread.
    for root in (os.getenv("VOSK_MODEL_PATH"), "/usr/share/vosk",
                 Path.home() / "AppData/Local/vosk", Path.home() / ".cache/vosk"):
        if root:
            path = Path(root) / MODEL_NAME
            if all((path / part).is_file() for part in ("am/final.mdl", "conf/model.conf", "graph/Gr.fst")):
                return path
    return None


def is_ready() -> bool:
    return find_spec("vosk") is not None and _model_path() is not None


def install_and_download(logger: Callable[[str], None] = print,
                         notify: Callable[[str], None] | None = None) -> tuple[bool, str]:
    """Install Vosk and its small acoustic model on explicit setup."""
    try:
        if find_spec("vosk") is None:
            from core.installer import _pip
            if not _pip("vosk", log=logger):
                return False, "Çevrimdışı ses tanıyıcı kurulamadı."
        from vosk import Model
        message = "Hey FRIDAY için çevrimdışı ses modeli hazırlanıyor…"
        logger(message)
        if notify:
            notify(message)
        Model(model_name=MODEL_NAME)
        if not is_ready():
            return False, "Ses modeli bulunamadı."
        return True, "Hazır. Uyandırmak için ‘Hey FRIDAY’ de."
    except (Exception, SystemExit) as exc:
        return False, f"Ses modeli kurulamadı: {exc}"


class WakeWordDetector:
    """
    Runs the wake model in a dedicated thread. The mic thread calls feed() with
    raw int16 frames; detections invoke on_detect() (called from this thread —
    the callback must marshal to whatever loop/UI it needs).
    """

    def __init__(self, on_detect: Callable[[], None],
                 threshold: float = DEFAULT_THRESHOLD,
                 logger: Callable[[str], None] = print,
                 notify: Callable[[str], None] | None = None):
        self._on_detect = on_detect
        self._threshold = threshold
        self._logger    = logger
        # See PluginRegistry: `logger` is the console and gets everything,
        # `notify` is the activity log and gets only what the user must act on.
        self._notify    = notify or (lambda _msg: None)
        self._queue: queue.Queue = queue.Queue(maxsize=50)
        self._thread: threading.Thread | None = None
        self._running = False
        self._model = None
        self._ready = False
        self._generation = 0

    def start(self) -> bool:
        """Load the model and spawn the inference thread. Returns True on success.
        Safe to call again — a no-op if already running. Never raises."""
        if self._running:
            return True
        try:
            from vosk import Model, KaldiRecognizer
            model_path = _model_path()
            if model_path is None:
                raise FileNotFoundError(MODEL_NAME)
            self._model = KaldiRecognizer(Model(str(model_path)), SAMPLE_RATE,
                                          json.dumps([*KEYPHRASES, "[unk]"]))
            self._model.SetWords(True)
        except Exception as e:
            self._logger(f"Wake word: could not load model — {e}")
            self._notify("Wake word unavailable — use the WAKE NOW button.")
            self._model = None
            return False
        self._running = True
        self._ready = True
        self._queue = queue.Queue(maxsize=50)
        self._thread = threading.Thread(target=self._loop, args=(self._queue, self._model),
                                        daemon=True, name="WakeWordThread")
        self._thread.start()
        self._logger("Wake word: listening for 'Hey FRIDAY'.")
        return True

    def stop(self) -> None:
        self._running = False
        self._generation += 1
        # unblock the thread if it's waiting on the queue
        try:
            self._queue.put_nowait(None)
        except Exception:
            pass
        self._model = None
        self._ready = False

    @property
    def ready(self) -> bool:
        return self._ready

    def reset(self) -> None:
        """Forget what was heard so far — call it when the assistant goes to sleep.
        Done on the detector's own thread, which is the only one that touches
        the model."""
        self._generation += 1

    @staticmethod
    def _reset_model(model) -> None:
        # The model keeps its recent audio features and scores. Left alone, one
        # "Hey FRIDAY" fired a dozen times in a row (measured: 12), and audio
        # from before the assistant woke was still in there when it went back
        # to sleep — so it could wake again on words said minutes earlier.
        try:
            model.Reset()
        except Exception:
            pass

    def feed(self, frame_int16) -> None:
        """Called from the mic callback (real-time thread). Must stay cheap and
        never block — the frame is copied and dropped if the queue is backed up."""
        if not self._running:
            return
        try:
            frames, generation = self._queue, self._generation
            # frame_int16 is a numpy int16 array (possibly 2-D mono) — flatten to 1-D
            data = frame_int16[:, 0].copy() if getattr(frame_int16, "ndim", 1) > 1 else frame_int16.copy()
            frames.put_nowait((generation, data))
        except queue.Full:
            pass
        except Exception:
            pass

    def _loop(self, frames, model) -> None:
        import numpy as np
        active_generation = None
        while self._running and frames is self._queue:
            try:
                item = frames.get()
                if item is None or not self._running or frames is not self._queue:
                    break
                generation, frame = item
                if generation != self._generation:
                    continue
                if active_generation != generation:
                    self._reset_model(model)
                    active_generation = generation
                pcm = np.asarray(frame, dtype=np.int16).tobytes()
                if not model.AcceptWaveform(pcm):
                    continue
                result = json.loads(model.Result())
                # Vosk may retain preceding unknown speech across a pause. Match
                # the last two tokens and their confidence, ignoring that prefix.
                words = (result.get("result") or [])[-2:]
                if (" ".join(word.get("word", "") for word in words) in KEYPHRASES
                        and all(word.get("conf", 0) >= self._threshold for word in words)):
                    # drain any backlog and clear the model, so one utterance is one wake
                    if generation != self._generation or frames is not self._queue or not self._running:
                        continue
                    self.reset()
                    self._reset_model(model)
                    try:
                        self._on_detect()
                    except Exception as e:
                        self._logger(f"Wake word: on_detect error — {e}")
            except Exception as e:
                self._logger(f"Wake word: inference error — {e}")

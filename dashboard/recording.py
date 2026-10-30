"""
recording.py — dataset recorder for the Early Fire Detection dashboard (FastAPI).

Adds a "Data Capture" page at /record. Pick a label (Normal / Warning / Fire), press Start,
and every thermal frame the Pico sends is saved as raw °C until the timer ends or you press
Stop. One recording = one session = one scene with one label.

Integration in server.py (already done in the supplied server.py — 3 lines):

    import recording
    app.include_router(recording.router)                 # adds /record page + API
    recording.add_frame(data)                            # in receive_frame(), after model_dump()

Files: recording.py next to server.py, record_panel.html in static/.

add_frame() finds the 24x32 frame in the payload by itself (flat list of 768 values or a
24x32 nested list, under any key) and picks up the ambient reading if a key contains "amb".

Data is written to ./thermal_dataset/ on the server:
    <label>/<session>.npz    frames (N x 24 x 32 float32 °C), timestamps, ambient
    <label>/<session>.png    contact sheet (8 frames) for a quick visual check
    index.csv                one row per session
Download everything as a zip from the page.

Optional protection: set the environment variable RECORD_KEY on the server; the page will
ask for it once and send it with every request.
"""
import csv
import io
import os
import re
import shutil
import threading
import time
import zipfile
from datetime import datetime

import numpy as np
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel

ROWS, COLS = 24, 32
LABELS = ("normal", "warning", "fire")
_HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("THERMAL_DATASET_DIR", os.path.join(_HERE, "thermal_dataset"))
TARGET_PER_CLASS = int(os.environ.get("RECORD_TARGET", "15"))
_KEY = os.environ.get("RECORD_KEY", "")
_SAFE = re.compile(r"^[A-Za-z0-9_\-]{1,60}$")

router = APIRouter()
_lock = threading.Lock()
_state = {
    "active": False, "label": None, "session": None, "note": "",
    "started": 0.0, "duration": 0.0, "frames": [], "stamps": [], "ambient": [],
    "last_frame": None, "last_ambient": None, "last_frame_time": 0.0,
    "last_saved": None, "error": None,
}


# ------------------------------------------------------------------ frame extraction
def _find_frame(obj):
    if isinstance(obj, (list, tuple)):
        if len(obj) == ROWS * COLS and all(isinstance(v, (int, float)) for v in obj):
            return np.asarray(obj, dtype=np.float32).reshape(ROWS, COLS)
        if len(obj) == ROWS and all(isinstance(r, (list, tuple)) and len(r) == COLS for r in obj):
            return np.asarray(obj, dtype=np.float32)
        for v in obj:
            f = _find_frame(v)
            if f is not None:
                return f
    elif isinstance(obj, dict):
        for v in obj.values():
            f = _find_frame(v)
            if f is not None:
                return f
    return None


def _find_ambient(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (int, float)) and "amb" in str(k).lower():
                return float(v)
            if isinstance(v, dict):
                a = _find_ambient(v)
                if a is not None:
                    return a
    return None


def add_frame(payload):
    """Call this for every telemetry packet the Pico sends. Cheap when not recording."""
    frame = _find_frame(payload)
    if frame is None:
        return
    amb = _find_ambient(payload) if isinstance(payload, dict) else None
    finished = None
    with _lock:
        now = time.time()
        _state["last_frame"], _state["last_ambient"], _state["last_frame_time"] = frame, amb, now
        if _state["active"]:
            _state["frames"].append(frame)
            _state["stamps"].append(now)
            _state["ambient"].append(amb)
            if _state["duration"] and now - _state["started"] >= _state["duration"]:
                finished = _take_session_locked()
    if finished:
        # write files off the event loop so frame reception never stalls
        threading.Thread(target=_save, args=finished, daemon=True).start()


# ------------------------------------------------------------------ saving
def _take_session_locked():
    s = _state
    out = (s["label"], s["session"], s["note"], s["frames"], s["stamps"], s["ambient"])
    s.update(active=False, frames=[], stamps=[], ambient=[])
    return out


def _save(label, session, note, frames, stamps, ambient):
    if not frames:
        with _lock:
            _state["error"] = f"No frames received for '{session}' — is the board sending?"
        return
    d = os.path.join(DATA_DIR, label)
    os.makedirs(d, exist_ok=True)
    F = np.stack(frames).astype(np.float32)
    amb = np.array([np.nan if a is None else a for a in ambient], dtype=np.float32)
    np.savez_compressed(os.path.join(d, f"{session}.npz"), frames=F, timestamps=np.array(stamps),
                        ambient=amb, label=label, session=session, note=note)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        idx = np.linspace(0, len(F) - 1, min(8, len(F))).astype(int)
        fig, axs = plt.subplots(2, 4, figsize=(10, 4.2))
        vmin, vmax = float(F.min()), float(F.max())
        for ax in axs.flat:
            ax.axis("off")
        for ax, i in zip(axs.flat, idx):
            im = ax.imshow(F[i], cmap="jet", vmin=vmin, vmax=vmax)
            ax.set_title(f"#{i}  max {F[i].max():.1f}°C", fontsize=8)
        fig.colorbar(im, ax=axs, shrink=0.8, label="°C")
        fig.suptitle(f"{label} / {session} — {len(F)} frames", fontsize=10)
        fig.savefig(os.path.join(d, f"{session}.png"), dpi=80)
        plt.close(fig)
    except Exception:
        pass
    _write_index()
    with _lock:
        _state["last_saved"] = {"label": label, "session": session, "frames": len(F)}
        _state["error"] = None


def _sessions():
    out = []
    for label in LABELS:
        d = os.path.join(DATA_DIR, label)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".npz"):
                continue
            p = os.path.join(d, fn)
            try:
                with np.load(p) as z:
                    F, ts, amb = z["frames"], z["timestamps"], z["ambient"]
                    note = str(z["note"]) if "note" in z else ""
            except Exception:
                continue
            out.append({
                "label": label, "session": fn[:-4], "frames": int(len(F)),
                "seconds": round(float(ts[-1] - ts[0]), 1) if len(ts) > 1 else 0.0,
                "max_c": round(float(F.max()), 1), "mean_c": round(float(F.mean()), 1),
                "ambient_c": None if np.isnan(amb).all() else round(float(np.nanmean(amb)), 1),
                "note": note,
                "recorded": datetime.fromtimestamp(float(ts[0])).isoformat(timespec="minutes") if len(ts) else "",
            })
    out.sort(key=lambda r: r["recorded"])
    return out


def _write_index():
    rows = _sessions()
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, "index.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["recorded", "label", "session", "frames", "seconds", "max_c", "mean_c", "ambient_c", "note"])
        for r in rows:
            w.writerow([r["recorded"], r["label"], r["session"], r["frames"], r["seconds"],
                        r["max_c"], r["mean_c"], r["ambient_c"] if r["ambient_c"] is not None else "", r["note"]])


# ------------------------------------------------------------------ API
def _auth(key):
    if _KEY and key != _KEY:
        raise HTTPException(401, "Recording key required")


class StartReq(BaseModel):
    label: str
    session: str
    seconds: float = 60
    note: str = ""


@router.post("/record/start")
def start(req: StartReq, x_record_key: str = Header(default="")):
    _auth(x_record_key)
    if req.label not in LABELS:
        raise HTTPException(400, "label must be normal, warning or fire")
    if not _SAFE.match(req.session):
        raise HTTPException(400, "session name: letters, numbers, _ and - only")
    if os.path.exists(os.path.join(DATA_DIR, req.label, f"{req.session}.npz")):
        raise HTTPException(409, f"session '{req.session}' already exists")
    with _lock:
        if _state["active"]:
            raise HTTPException(409, "already recording")
        _state.update(active=True, label=req.label, session=req.session, note=req.note[:200],
                      started=time.time(), duration=max(0.0, float(req.seconds)),
                      frames=[], stamps=[], ambient=[], error=None)
    return {"ok": True}


@router.post("/record/stop")
def stop(x_record_key: str = Header(default="")):
    _auth(x_record_key)
    with _lock:
        if not _state["active"]:
            return {"ok": True, "saved": None}
        finished = _take_session_locked()
    _save(*finished)
    return {"ok": True}


@router.post("/record/discard")
def discard(x_record_key: str = Header(default="")):
    _auth(x_record_key)
    with _lock:
        _state.update(active=False, frames=[], stamps=[], ambient=[])
    return {"ok": True}


@router.get("/record/status")
def status():
    with _lock:
        s = _state
        f = s["last_frame"]
        el = time.time() - s["started"] if s["active"] else 0
        st = {
            "active": s["active"], "label": s["label"], "session": s["session"],
            "elapsed": round(el, 1), "duration": s["duration"], "frames": len(s["frames"]),
            "live_age": round(time.time() - s["last_frame_time"], 1) if s["last_frame_time"] else None,
            "frame": None if f is None else [round(float(v), 1) for v in f.flat],
            "ambient": s["last_ambient"], "last_saved": s["last_saved"], "error": s["error"],
        }
    # auto-finish a timed session even if frames stopped arriving
    if st["active"] and st["duration"] and st["elapsed"] >= st["duration"] + 3:
        stop(x_record_key=_KEY)
    return st


@router.get("/record/sessions")
def sessions():
    rows = _sessions()
    counts = {l: sum(1 for r in rows if r["label"] == l) for l in LABELS}
    frames = {l: sum(r["frames"] for r in rows if r["label"] == l) for l in LABELS}
    return {"sessions": rows, "counts": counts, "frames": frames, "target": TARGET_PER_CLASS}


@router.delete("/record/sessions/{label}/{session}")
def delete_session(label: str, session: str, x_record_key: str = Header(default="")):
    _auth(x_record_key)
    if label not in LABELS or not _SAFE.match(session):
        raise HTTPException(400, "bad name")
    for ext in (".npz", ".png"):
        p = os.path.join(DATA_DIR, label, session + ext)
        if os.path.exists(p):
            os.remove(p)
    _write_index()
    return {"ok": True}


@router.get("/record/preview/{label}/{session}.png")
def preview(label: str, session: str):
    if label not in LABELS or not _SAFE.match(session):
        raise HTTPException(400, "bad name")
    p = os.path.join(DATA_DIR, label, session + ".png")
    if not os.path.exists(p):
        raise HTTPException(404, "no preview")
    return FileResponse(p, media_type="image/png")


@router.get("/record/download")
def download():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        if os.path.isdir(DATA_DIR):
            for root, _, files in os.walk(DATA_DIR):
                for fn in files:
                    full = os.path.join(root, fn)
                    z.write(full, os.path.relpath(full, os.path.dirname(os.path.abspath(DATA_DIR)) or "."))
    buf.seek(0)
    name = f"thermal_dataset_{datetime.now():%Y%m%d_%H%M}.zip"
    return StreamingResponse(buf, media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/record", response_class=HTMLResponse)
def page():
    path = os.path.join(_HERE, "static", "record_panel.html")
    if not os.path.exists(path):
        path = os.path.join(_HERE, "record_panel.html")
    with open(path, encoding="utf-8") as fh:
        return fh.read().replace("__NEEDS_KEY__", "true" if _KEY else "false")

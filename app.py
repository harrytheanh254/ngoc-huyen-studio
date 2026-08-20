# -*- coding: utf-8 -*-
"""
Ngoc Huyen Studio - TTS Web App
Chạy: python app.py -> mở http://127.0.0.1:5000
Tự tìm mọi file trong thư mục cài đặt (không hardcode).
"""
import os
import re
import io
import sys
import uuid
import json
import shutil
import tempfile
import threading
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, render_template, request, jsonify, send_from_directory, send_file, make_response

# ---- Tự xác định thư mục cài đặt (nơi chứa file app.py) ----
BASE_DIR = Path(__file__).parent.resolve()
PIPELINE_DIR = BASE_DIR / "pipeline"
DATA_DIR = BASE_DIR / "data"
PRODUCT_DIR = BASE_DIR / "san-pham"
PREVIEW_DIR = BASE_DIR / "preview"
VIDEO_DIR = BASE_DIR / "video_output"
UPLOAD_DIR = BASE_DIR / "upload_images"

for d in (PRODUCT_DIR, PREVIEW_DIR, VIDEO_DIR, UPLOAD_DIR, DATA_DIR):
    d.mkdir(exist_ok=True, parents=True)

# Thêm pipeline vào sys.path
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

import tts_ngochuyen as tts  # noqa: E402
import loanwords_dynamic  # noqa: E402
from piper.config import SynthesisConfig  # noqa: E402

# ---- Preview auto-cleanup (>15 days) ----
def cleanup_preview():
    """Xóa file trong preview/ cũ hơn 15 ngày."""
    try:
        cutoff = datetime.now() - timedelta(days=15)
        for f in PREVIEW_DIR.glob("*"):
            if f.is_file():
                mtime = datetime.fromtimestamp(f.stat().st_mtime)
                if mtime < cutoff:
                    f.unlink(missing_ok=True)
    except Exception:
        pass

cleanup_preview()  # Chạy 1 lần khi khởi động

# ---- Flask app ----
app = Flask(__name__, static_folder=str(BASE_DIR / "static"), template_folder=str(BASE_DIR / "templates"))
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB

# ---- Trạng thái render ----
RENDERS = {}
RENDER_LOCK = threading.Lock()
_rendering = False
_render_thread = None

def build_filter_chain(eq: str, volume: float, pitch: float) -> str:
    filters = []
    if eq == "strong":
        filters.append("highpass=f=80,equalizer=f=1800:t=q:w=1.2:g=4,equalizer=f=4500:t=q:w=1.5:g=3.5,equalizer=f=9000:t=q:w=1.5:g=2,lowpass=f=11000")
    elif eq == "accent":
        filters.append("highpass=f=60,equalizer=f=300:t=q:w=1.2:g=3.5,equalizer=f=1200:t=q:w=1.2:g=3,equalizer=f=2600:t=q:w=1.5:g=2.5,equalizer=f=5000:t=q:w=1.5:g=1.5,lowpass=f=12000")
    elif eq == "vbee":
        filters.append("highpass=f=120,equalizer=f=800:t=q:w=1.5:g=2,equalizer=f=2500:t=q:w=1.2:g=3.5,equalizer=f=6000:t=q:w=1.8:g=2,lowpass=f=12000,loudnorm=I=-14:TP=-1.5:LRA=9")
    else:
        filters.append("loudnorm=I=-16:TP=-1.5:LRA=11")
    if volume != 1.0:
        filters.append(f"volume={volume}")
    if pitch != 0.0:
        filters.append(f"asetrate=44100*{2**(pitch/12)},aresample=44100")
    return ",".join(filters)

def find_ffmpeg() -> str:
    candidates = [
        os.environ.get("FFMPEG", ""),
        shutil.which("ffmpeg") or "",
        str(BASE_DIR / "ffmpeg" / "bin" / "ffmpeg.exe"),
        str(BASE_DIR / "ffmpeg" / "ffmpeg.exe"),
    ]
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return ""

FFMPEG = find_ffmpeg()

def get_voice():
    model_path = PIPELINE_DIR / "ngoc_huyen.onnx"
    voice = tts.PiperVoice.load(str(model_path))
    tts.patch_anh_phoneme(voice)
    tts.patch_phatam_fix(voice)
    return voice

def render_job(rid: str, text: str, settings: dict):
    global _rendering
    try:
        RENDERS[rid]["status"] = "processing"
        RENDERS[rid]["message"] = "Đang xử lý văn bản..."
        
        # Xóa chú thích #... trước khi xử lý
        text = re.sub(r"#[^\n]*", "", text).strip()
        if not text:
            raise RuntimeError("Văn bản trống sau khi xóa chú thích")
        
        text_proc = tts.vietnamize_text(text)
        sentences = tts.split_into_sentences(text_proc)
        total = len(sentences)
        RENDERS[rid]["total"] = total

        speed = float(settings.get("speed", 1.3))
        pause = float(settings.get("pause", 0.18))
        pause_comma = float(settings.get("pause_comma", 0.18))
        noise_scale = float(settings.get("noise_scale", 0.667))
        noise_w = float(settings.get("noise_w", 0.8))
        eq = settings.get("eq", "vbee")
        volume = float(settings.get("volume", 1.0))
        pitch = float(settings.get("pitch", 0.0))

        syn = SynthesisConfig(
            length_scale=1.0 / speed,
            noise_scale=noise_scale,
            noise_w_scale=noise_w,
        )
        voice = get_voice()

        parts = []
        done = 0
        for i, s in enumerate(sentences):
            if not re.search(r"[A-Za-zÀ-ỹ0-9]", s):
                continue
            try:
                wav = tts.synth_sentence(voice, syn, s)
            except Exception:
                continue
            parts.append(wav)
            last_ch = s[-1] if s else ""
            if last_ch in "，,。.":
                parts.append(tts.silence(pause_comma if last_ch in "，," else pause))
            done += 1
            RENDERS[rid]["progress"] = done
            RENDERS[rid]["message"] = f"Đang đọc câu {done}/{total}..."

        if not parts:
            raise RuntimeError("Không có câu nào đọc được (text trống?)")

        full = b"".join(parts)
        RENDERS[rid]["message"] = "Đang ghi audio..."

        out_name = f"{datetime.now():%Y%m%d_%H%M%S}_{rid[:8]}.mp3"
        out_path = PREVIEW_DIR / out_name

        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        tts.write_wav_pcm(full, tmp.name)

        ff = FFMPEG
        if not ff:
            raise RuntimeError("Không tìm thấy ffmpeg để xuất MP3")
        ff_args = [ff, "-y", "-i", tmp.name, "-codec:a", "libmp3lame", "-qscale:a", "2",
                   "-af", build_filter_chain(eq, volume, pitch)]
        subprocess.run(ff_args + [str(out_path)], capture_output=True)
        os.unlink(tmp.name)

        # Lấy duration
        dur = 0
        try:
            ffprobe = ff.replace("ffmpeg.exe", "ffprobe.exe")
            if os.path.isfile(ffprobe):
                res = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration",
                                      "-of", "default=noprint_wrappers=1:nokey=1", str(out_path)],
                                     capture_output=True, text=True)
                if res.returncode == 0 and res.stdout.strip():
                    dur = float(res.stdout.strip())
        except Exception:
            pass

        RENDERS[rid]["status"] = "done"
        RENDERS[rid]["message"] = "Hoàn tất"
        RENDERS[rid]["file"] = out_name
        RENDERS[rid]["duration"] = dur
    except Exception as e:
        RENDERS[rid]["status"] = "error"
        RENDERS[rid]["error"] = str(e)
    finally:
        with RENDER_LOCK:
            _rendering = False


# ---- Routes ----

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/tts", methods=["POST"])
def api_tts():
    global _rendering, _render_thread
    data = request.get_json(force=True, silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "Vui lòng nhập văn bản"}), 400

    with RENDER_LOCK:
        if _rendering:
            return jsonify({"error": "Đang render audio khác, chờ xong rồi thử lại"}), 409
        _rendering = True

    rid = uuid.uuid4().hex
    RENDERS[rid] = {
        "status": "queued", "progress": 0, "total": 0,
        "message": "Bắt đầu...", "error": None, "file": None,
        "text_preview": text[:80], "duration": 0,
    }
    settings = data.get("settings") or {}
    _render_thread = threading.Thread(target=render_job, args=(rid, text, settings), daemon=True)
    _render_thread.start()
    return jsonify({"id": rid})


@app.route("/api/status/<rid>")
def api_status(rid):
    r = RENDERS.get(rid)
    if not r:
        return jsonify({"error": "Không tìm thấy job"}), 404
    return jsonify({
        "status": r["status"], "progress": r["progress"],
        "total": r["total"], "message": r["message"],
        "error": r["error"], "file": r["file"],
        "duration": r.get("duration", 0),
    })


@app.route("/api/history")
def api_history():
    items = []
    for f in sorted(PREVIEW_DIR.glob("*.mp3"), key=lambda x: x.stat().st_mtime, reverse=True):
        stat = f.stat()
        dur = 0
        try:
            ffprobe = FFMPEG.replace("ffmpeg.exe", "ffprobe.exe")
            if os.path.isfile(ffprobe):
                res = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration",
                                      "-of", "default=noprint_wrappers=1:nokey=1", str(f)],
                                     capture_output=True, text=True)
                if res.returncode == 0 and res.stdout.strip():
                    dur = float(res.stdout.strip())
        except Exception:
            pass
        items.append({
            "name": f.name,
            "url": f"/preview/{f.name}",
            "size": stat.st_size,
            "size_mb": round(stat.st_size / 1024 / 1024, 2),
            "mtime": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
            "duration": dur,
        })
    return jsonify(items)


@app.route("/preview/<name>")
def serve_preview(name):
    return send_from_directory(PREVIEW_DIR, name)


@app.route("/api/history/<name>", methods=["DELETE"])
def api_history_delete(name):
    f = PREVIEW_DIR / name
    if f.exists():
        f.unlink()
    return jsonify({"ok": True})


@app.route("/api/history/<name>/rename", methods=["POST"])
def api_history_rename(name):
    data = request.get_json(force=True, silent=True) or {}
    new_base = (data.get("new_name") or "").strip()
    if not new_base:
        return jsonify({"error": "Tên file không được để trống"}), 400
    new_name = new_base if new_base.lower().endswith(".mp3") else new_base + ".mp3"
    old = PREVIEW_DIR / name
    new = PREVIEW_DIR / new_name
    if not old.exists():
        return jsonify({"error": "File không tồn tại"}), 404
    if new.exists():
        return jsonify({"error": "File đã tồn tại"}), 409
    old.rename(new)
    return jsonify({"ok": True, "new_name": new_name})


@app.route("/api/loanwords")
def api_loanwords():
    data = loanwords_dynamic.get_all()
    items = list(reversed([{"word": k, "reading": v} for k, v in data.items()]))
    return jsonify({"total": len(items), "items": items})


@app.route("/api/loanwords", methods=["POST"])
def api_loanwords_add():
    data = request.get_json(force=True, silent=True) or {}
    word = (data.get("word") or "").strip()
    reading = (data.get("reading") or "").strip()
    if not word or not reading:
        return jsonify({"error": "Thiếu từ hoặc cách đọc"}), 400
    loanwords_dynamic.add_words([(word, reading)])
    return jsonify({"ok": True})


@app.route("/api/loanwords/<word>", methods=["PUT"])
def api_loanwords_update(word):
    data = request.get_json(force=True, silent=True) or {}
    reading = (data.get("reading") or "").strip()
    if not reading:
        return jsonify({"error": "Thiếu cách đọc"}), 400
    ok = loanwords_dynamic.update_word(word, reading)
    return jsonify({"ok": ok})


@app.route("/api/loanwords/<word>", methods=["DELETE"])
def api_loanwords_delete(word):
    ok = loanwords_dynamic.remove_word(word)
    return jsonify({"ok": ok})


@app.route("/api/scan", methods=["POST"])
def api_scan():
    data = request.get_json(force=True, silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "Thiếu văn bản"}), 400
    items = loanwords_dynamic.scan_new_words(text)
    return jsonify({"items": items})


@app.route("/api/scan", methods=["GET"])
def api_scan_get():
    # Trả về bản nháp nếu có
    draft_file = DATA_DIR / "scan_draft.json"
    if draft_file.exists():
        try:
            return jsonify(json.loads(draft_file.read_text(encoding="utf-8")))
        except Exception:
            pass
    return jsonify({"items": []})


@app.route("/api/scan/draft", methods=["POST"])
def api_scan_draft():
    data = request.get_json(force=True, silent=True) or {}
    items = data.get("items") or []
    (DATA_DIR / "scan_draft.json").write_text(
        json.dumps({"items": items}, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return jsonify({"ok": True})


@app.route("/api/scan/apply", methods=["POST"])
def api_scan_apply():
    data = request.get_json(force=True, silent=True) or {}
    items = data.get("items") or []
    if not items:
        return jsonify({"error": "Không có từ để thêm"}), 400
    pairs = [(it["word"], it["reading"]) for it in items if it.get("word") and it.get("reading")]
    loanwords_dynamic.add_words(pairs)
    (DATA_DIR / "scan_draft.json").write_text(json.dumps({"items": []}, ensure_ascii=False), encoding="utf-8")
    return jsonify({"ok": True, "added": len(pairs)})


@app.route("/api/scan", methods=["DELETE"])
def api_scan_clear():
    (DATA_DIR / "scan_draft.json").write_text(json.dumps({"items": []}, ensure_ascii=False), encoding="utf-8")
    return jsonify({"ok": True})


@app.route("/api/merge", methods=["POST"])
def api_merge():
    data = request.get_json(force=True, silent=True) or {}
    files = data.get("files") or []
    if not files:
        return jsonify({"error": "Không có file để gộp"}), 400
    if not FFMPEG:
        return jsonify({"error": "Thiếu ffmpeg"}), 500
    out_name = data.get("output_name") or f"merged_{datetime.now():%Y%m%d_%H%M%S}.mp3"
    out_path = PRODUCT_DIR / out_name
    flist = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8")
    try:
        for f in files:
            src = PREVIEW_DIR / f
            if src.exists():
                flist.write(f"file '{src.resolve()}'\n")
        flist.close()
        subprocess.run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", flist.name,
                       "-c", "copy", str(out_path)], capture_output=True)
    finally:
        os.unlink(flist.name)
    if out_path.exists():
        return jsonify({"ok": True, "name": out_name, "url": f"/san-pham/{out_name}"})
    return jsonify({"error": "Gộp thất bại"}), 500


@app.route("/san-pham/<name>")
def serve_product(name):
    return send_from_directory(PRODUCT_DIR, name)


@app.route("/api/download/<name>")
def api_download(name):
    """Download với header Content-Disposition -> trình duyệt hiện 'Save As'."""
    f = PREVIEW_DIR / name
    if not f.exists():
        f = PRODUCT_DIR / name
    if not f.exists():
        return jsonify({"error": "File không tồn tại"}), 404
    resp = send_file(f, as_attachment=True, download_name=name)
    resp.headers["Content-Disposition"] = f'attachment; filename="{name}"'
    return resp


# ---- Video endpoints ----
@app.route("/api/video/upload-image", methods=["POST"])
def api_video_upload_image():
    if "file" not in request.files:
        return jsonify({"error": "Thiếu file"}), 400
    f = request.files["file"]
    if f.filename == "":
        return jsonify({"error": "Chưa chọn file"}), 400
    ext = Path(f.filename).suffix.lower()
    if ext not in [".jpg", ".jpeg", ".png", ".webp"]:
        return jsonify({"error": "Chỉ chấp nhận JPG, PNG, WEBP"}), 400
    out_name = f"img_{uuid.uuid4().hex}{ext}"
    out_path = UPLOAD_DIR / out_name
    f.save(out_path)
    return jsonify({"ok": True, "url": f"/upload-images/{out_name}"})


@app.route("/upload-images/<name>")
def serve_upload_image(name):
    return send_from_directory(UPLOAD_DIR, name)


@app.route("/api/video/preview-frame", methods=["POST"])
def api_video_preview_frame():
    data = request.get_json(force=True, silent=True) or {}
    img_url = data.get("image_url", "")
    text = data.get("text", "")
    text_color = data.get("text_color", "#FFFFFF")
    text_size = int(data.get("text_size", 40))
    text_y = int(data.get("text_y", 85))
    brightness = int(data.get("brightness", 100))

    img_path = UPLOAD_DIR / Path(img_url).name
    if not img_path.exists():
        return jsonify({"error": "Ảnh không tồn tại"}), 404

    out_name = f"preview_{uuid.uuid4().hex}.png"
    out_path = VIDEO_DIR / out_name

    # Tạo ảnh preview bằng ffmpeg (drawtext + brightness)
    brightness_filter = f"eq=brightness={(brightness - 100) / 100:.2f}"
    if text:
        # Escape text cho drawtext
        safe_text = text.replace("'", "\\'").replace(":", "\\:")
        vf = f"{brightness_filter},drawtext=text='{safe_text}':fontcolor={text_color}:fontsize={text_size}:x=(w-text_w)/2:y=h*{text_y/100}"
    else:
        vf = brightness_filter

    cmd = [FFMPEG, "-y", "-i", str(img_path), "-vf", vf, "-frames:v", "1", str(out_path)]
    subprocess.run(cmd, capture_output=True)

    if out_path.exists():
        return jsonify({"ok": True, "image": f"/video-output/{out_name}"})
    return jsonify({"error": "Tạo preview thất bại"}), 500


@app.route("/api/video/create", methods=["POST"])
def api_video_create():
    data = request.get_json(force=True, silent=True) or {}
    img_url = data.get("image_url", "")
    audio_url = data.get("audio_url", "")
    text = data.get("text", "")
    text_color = data.get("text_color", "#FFFFFF")
    text_size = int(data.get("text_size", 40))
    text_y = int(data.get("text_y", 85))
    brightness = int(data.get("brightness", 100))
    output_name = (data.get("output_name") or "").strip()

    img_path = UPLOAD_DIR / Path(img_url).name
    if not img_path.exists():
        return jsonify({"error": "Ảnh không tồn tại"}), 404

    audio_path = None
    for base in (PREVIEW_DIR, PRODUCT_DIR):
        cand = base / Path(audio_url).name
        if cand.exists():
            audio_path = cand
            break
    if not audio_path:
        return jsonify({"error": "Audio không tồn tại"}), 404

    if not output_name:
        output_name = f"video_{datetime.now():%Y%m%d_%H%M%S}.mp4"
    elif not output_name.lower().endswith(".mp4"):
        output_name += ".mp4"
    out_path = VIDEO_DIR / output_name

    brightness_filter = f"eq=brightness={(brightness - 100) / 100:.2f}"
    if text:
        safe_text = text.replace("'", "\\'").replace(":", "\\:")
        vf = f"{brightness_filter},drawtext=text='{safe_text}':fontcolor={text_color}:fontsize={text_size}:x=(w-text_w)/2:y=h*{text_y/100}"
    else:
        vf = brightness_filter

    cmd = [FFMPEG, "-y", "-loop", "1", "-i", str(img_path), "-i", str(audio_path),
           "-vf", vf, "-c:v", "libx264", "-preset", "fast", "-crf", "23",
           "-c:a", "aac", "-b:a", "128k", "-shortest", "-pix_fmt", "yuv420p", str(out_path)]
    res = subprocess.run(cmd, capture_output=True)

    if out_path.exists():
        size_mb = round(out_path.stat().st_size / 1024 / 1024, 2)
        dur = 0
        try:
            ffprobe = FFMPEG.replace("ffmpeg.exe", "ffprobe.exe")
            if os.path.isfile(ffprobe):
                r = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration",
                                    "-of", "default=noprint_wrappers=1:nokey=1", str(out_path)],
                                   capture_output=True, text=True)
                if r.returncode == 0 and r.stdout.strip():
                    dur = float(r.stdout.strip())
        except Exception:
            pass
        return jsonify({"ok": True, "name": output_name, "url": f"/video-output/{output_name}", "size_mb": size_mb, "duration": dur})
    return jsonify({"error": "Tạo video thất bại: " + res.stderr.decode(errors="ignore")[:200]}), 500


@app.route("/api/video/list", methods=["GET"])
def api_video_list():
    items = []
    for f in sorted(VIDEO_DIR.glob("*.mp4"), key=lambda x: x.stat().st_mtime, reverse=True):
        stat = f.stat()
        dur = 0
        try:
            ffprobe = FFMPEG.replace("ffmpeg.exe", "ffprobe.exe")
            if os.path.isfile(ffprobe):
                r = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration",
                                    "-of", "default=noprint_wrappers=1:nokey=1", str(f)],
                                   capture_output=True, text=True)
                if r.returncode == 0 and r.stdout.strip():
                    dur = float(r.stdout.strip())
        except Exception:
            pass
        items.append({
            "name": f.name,
            "url": f"/video-output/{f.name}",
            "size": stat.st_size,
            "size_mb": round(stat.st_size / 1024 / 1024, 2),
            "mtime": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
            "duration": dur,
        })
    return jsonify(items)


@app.route("/api/video/<name>", methods=["DELETE"])
def api_video_delete(name):
    f = VIDEO_DIR / name
    if f.exists():
        f.unlink()
    return jsonify({"ok": True})


@app.route("/video-output/<name>")
def serve_video_output(name):
    return send_from_directory(VIDEO_DIR, name)


if __name__ == "__main__":
    # Tự mở browser
    import webbrowser
    threading.Timer(1.5, lambda: webbrowser.open("http://127.0.0.1:5000")).start()
    app.run(host="127.0.0.1", port=5000, debug=False)
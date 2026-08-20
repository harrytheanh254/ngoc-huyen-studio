
# -*- coding: utf-8 -*-
"""
App TTS giọng Ngọc Huyền (Piper) v2 - render TỪNG CÂU + ngắt nghỉ tự nhiên.
Cách dùng:
  python tts_ngochuyen.py --text "Xin chào" --out out.wav
  python tts_ngochuyen.py --file text.txt --out out.wav   (file UTF-8)
  python tts_ngochuyen.py --file text.txt --out out.mp3   (cần ffmpeg)
  python tts_ngochuyen.py --file text.txt --out out.mp3 --speed 1.35
  python tts_ngochuyen.py --file text.txt --out out.mp3 --speed 1.35 --pause 0.18
"""
import argparse
import sys
import wave
import subprocess
import tempfile
import os
import re
import io
import shutil
from pathlib import Path

import loanwords_vi

MODEL_DIR = Path(__file__).parent
MODEL = MODEL_DIR / "ngoc_huyen.onnx"
SAMPLE_RATE = 22050


def find_ffmpeg() -> str:
    """Tự tìm ffmpeg: env FFMPEG > PATH > đường dẫn mặc định Windows.

    Chạy được trên mọi máy (không hardcode máy cá nhân). Trả về "" nếu không tìm thấy.
    """
    candidates = [
        os.environ.get("FFMPEG", ""),
        shutil.which("ffmpeg") or "",
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        r"C:\Users\Khang\Desktop\ffmpeg\ffmpeg-8.1.2-essentials_build\bin\ffmpeg.exe",
    ]
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return ""


FFMPEG = find_ffmpeg()


def split_into_sentences(text: str, comma_split: bool = False, max_len: int = 999):
    """Tách text thành các cụm đọc (GIỮ NGUYÊN dấu câu trong cụm).

    CHỐT 2026-08-12 (bản C — LO duyệt "hoàn hảo"): KHÔNG chẻ theo dấu phẩy,
    KHÔNG chẻ 60 ký tự thủ công. Chỉ tách theo dấu chấm/!? -> mỗi cụm = 1 câu
    giữ trọn chấm/phẩy, để Piper TỰ ngắt nghỉ theo đúng dấu câu (tự nhiên,
    hết hiện tượng hạ giọng/nuốt âm cuối vì từ cuối cụm bị đẩy về biên).
    max_len: chỉ chẻ khi 1 câu hiếm hoi quá dài (>999 ký tự) để tránh drift.
    """
    # tách theo dòng trước
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    sentences = []
    for line in lines:
        # loại markdown heading / separator
        if re.match(r'^#{1,6}\s', line) or re.match(r'^[*_\-]{3,}$', line):
            continue
        if comma_split:
            # tách theo chấm + phẩy (phẩy tiếng Việt và phẩy TQ)
            parts = re.findall(r'[^.!?…,，]+[.!?…,，]*', line)
        else:
            parts = re.findall(r'[^.!?…]+[.!?…]*', line)
        for p in parts:
            p = p.strip()
            if not p:
                continue
            # gộp cụm quá ngắn vào cụm trước (trừ khi là cụm đầu)
            if len(p) < 10 and sentences:
                sentences[-1] = sentences[-1] + " " + p
            elif len(p) <= max_len:
                sentences.append(p)
            else:
                # chẻ cụm dài tại khoảng trắng gần mốc max_len (giữ phẩy ở đầu phần sau)
                rest = p
                while len(rest) > max_len:
                    cut = rest.rfind(" ", 0, max_len + 1)
                    if cut < 15:
                        cut = max_len
                    head, rest = rest[:cut].strip(), rest[cut:].strip()
                    if head:
                        sentences.append(head)
                if rest:
                    sentences.append(rest)
    return sentences


def patch_anh_phoneme(voice):
    """FIX phát âm 'anh' (không dấu) thành 'ănh'.

    Root cause: dict E_tS sửa 'anh' -> aɲ (a NGẮN + ɲ) -> model đọc như 'ănh'.
    Model được train với dict SYS gốc: 'anh' -> e-ɲ (cùng phoneme với
    cành/e-2ɲ, mạnh/e-6ɲ, lành/e-2ɲ mà tai người không chê).
    Patch: sau khi phonemize, thay mọi 'a'+'ɲ' (chỉ nhóm 'anh' không dấu:
    anh, canh, nhanh, xanh, thanh, tranh, khanh, chanh, hanh...) bằng 'e'+'-'+'ɲ'.
    KHÔNG đụng: 'ăn' (a+n), 'an' (a+ː+n), 'cành/mạnh/lành' (e-...ɲ có sẵn).

    LO xác nhận bản C (e-ɲ) chuẩn — Telegram msg 775, 2026-08-08.
    """
    orig = voice.phonemize

    def patched(text):
        res = orig(text)
        for word in res:
            for i in range(len(word) - 1):
                if word[i] == "a" and word[i + 1] == "ɲ":
                    word[i : i + 2] = ["e", "-", "ɲ"]
        return res

    voice.phonemize = patched


def patch_phatam_fix(voice):
    """FIX phát âm các từ thiếu train đọc bừa: lúc, ùm, ừm.

    Root cause (2026-08-10): 'lúc' phonemize ra lˌuɜc (stress phụ), 'ùm' thiếu
    âm trầm (đọc như 'um' vô cảm), 'ừm' thiếu độ dài ư. Model chưa học các từ
    này trong data train (ừm=0 lần, ùm chỉ trong từ ghép).
    FIX2 (LO nghe msg 968): lúc lˌuɜc -> lˈuɜc (stress chính), ùm ˈu2m -> ˈu2mː
    (m dài cho vang trầm), ừm ˈy2m -> ˈyː2m (ư dài). Ép về chuỗi model quen:
    u2m (cùm/trùm/bùm), y2 (từ/mừ/hừ/ừ) đều có trong train.
    """
    orig = voice.phonemize

    def patched(text):
        res = orig(text)
        # 'cớ' là dấu SẮC (c+ơ+sắc) -> phoneme chuẩn ơ+sắc = ˈəːɜ (như tớ/sớ/lớn).
        # Espeak map nhầm 'cớ' thành kˈəː4 (thanh hỏi) vì không có từ trong dict.
        # CHỈ sửa khi text gốc chứa 'cớ' (không đụng 'cở' hỏi).
        has_co = bool(re.search(r"cớ", text))
        no_co = not re.search(r"cở", text)
        fix_co_sac = has_co and no_co
        for word in res:
            # loop 6 ký tự: 'được' = ɗˌyə6c bị stress phụ ˌ (giống bug 'lúc')
            i = 0
            while i <= len(word) - 6:
                s = "".join(word[i : i + 6])
                if s == "ɗˌyə6c":
                    # ép về stress chính, đọc giống đước/đượt (model quen)
                    word[i : i + 6] = ["ɗ", "ˈ", "y", "ə", "6", "c"]
                    i += 6
                else:
                    i += 1
            i = 0
            while i <= len(word) - 5:
                s = "".join(word[i : i + 5])
                if s == "lˌuɜc":
                    word[i : i + 5] = ["l", "ˈ", "u", "ɜ", "c"]
                    i += 5
                elif s == "kˈəː4" and fix_co_sac:
                    # 'cớ' (dấu sắc) espeak map nhầm thành thanh hỏi 4; ép về
                    # chuẩn sắc ơ+sắc = ˈəːɜ giống tớ/sớ/lớn/gớm
                    word[i : i + 5] = ["k", "ˈ", "ə", "ː", "ɜ"]
                    i += 5
                else:
                    i += 1
            i = 0
            while i <= len(word) - 4:
                s = "".join(word[i : i + 4])
                # ùm/ừm CHỈ khi đứng 1 mình (tượng thanh trong truyện); không đụng
                # trùm/bùm/cùm/hừm (model đã học, đọc tốt). Ký tự sau có thể là
                # space hoặc dấu câu (!?,;.…) vì "ùm!" / "ừm," vẫn là tượng thanh.
                def standalone(idx):
                    left_ok = idx == 0 or word[idx - 1] == " "
                    right = idx + 4
                    right_ok = right >= len(word) or word[right] in (" ", "!", "?", ",", ";", ".", "…")
                    return left_ok and right_ok

                if s == "ˈu2m":
                    if standalone(i):
                        word[i : i + 4] = ["ˈ", "u", "2", "m", "ː"]
                        i += 5
                    else:
                        i += 1
                elif s == "ˈy2m":
                    if standalone(i):
                        word[i : i + 4] = ["ˈ", "y", "ː", "2", "m"]
                        i += 5
                    else:
                        i += 1
                else:
                    i += 1
        return res

    voice.phonemize = patched


def synth_sentence(voice, syn_config, sentence: str) -> bytes:
    """Render 1 câu -> PCM data (16-bit mono 22050, KHÔNG có WAV header)."""
    b = io.BytesIO()
    with wave.open(b, "wb") as wf:
        voice.synthesize_wav(sentence, wf, syn_config=syn_config)
    b.seek(0)
    with wave.open(b, "rb") as rf:
        n = rf.getnframes()
        ch = rf.getnchannels()
        sw = rf.getsampwidth()
        data = rf.readframes(n)
        # nếu stereo -> xuống mono, nếu 16-bit là chuẩn
        if ch == 2:
            import array
            a = array.array('h')
            a.frombytes(data)
            mono = array.array('h', a[0::2])
            data = mono.tobytes()
    return data


def silence(seconds: float) -> bytes:
    """Tạo khoảng lặng PCM (16-bit mono)."""
    n = int(SAMPLE_RATE * seconds)
    return b"\x00\x00" * n


def write_wav_pcm(pcm: bytes, path: str):
    """Ghi PCM 16-bit mono 22050 thành file WAV chuẩn."""
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm)


# Ký tự tiếng Nhật/Trung (chữ Hán + các chữ tượng hình khác). espeak không
# phonemize được -> piper đọc bừa thành "chinese-letter" LẶP LẠI theo số ký tự
# (vd 牛头人 -> tʃˈaɪniːzlˈetə x3 = chuỗi "m n y dài"). Phải XÓA hoàn toàn khỏi
# văn bản trước khi vào pipeline (không đụng tiếng Việt có dấu).
HANZI_RE = re.compile(r"[\u3400-\u9FFF\uF900-\uFAFF]+")


def strip_hanzi(text: str) -> str:
    """Loại chữ Hán/Nhật (CJK) còn sót khỏi văn bản — an toàn, không đụng tiếng Việt."""
    return HANZI_RE.sub("", text)


# LO quyết 2026-08-15: bỏ hết từ điển cứng (NAMES, GLITCH_FIXES, EN_READINGS)
# để Piper đọc theo MẶC ĐỊNH — vì sau này TTS nhiều truyện, không hardcode từ
# của riêng 1 bộ. Từ Anh/tên ngoại còn sót sẽ tự xử bằng bước syllablize (bước 3)
# và espeak. Chấp nhận: NTR/ok/iori... nghe hơi lệch, nhưng tổng quát cho mọi truyện.

# Đọc phụ âm đơn khi đánh vần
CONS_READ = {
    "b": "b", "c": "c", "d": "đ", "f": "ph", "g": "g", "h": "h",
    "j": "gi", "k": "c", "l": "l", "m": "m", "n": "n", "p": "p",
    "q": "qu", "r": "r", "s": "s", "t": "t", "v": "v", "w": "vê",
    "x": "x", "y": "d", "z": "d",
}

# Nguyên âm -> đọc (đơn + đôi)
VOW_READ = {
    "a": "a", "e": "e", "i": "i", "o": "o", "u": "u",
    "ai": "ai", "ei": "ây", "ou": "âu", "au": "ao", "ea": "i",
    "ee": "i", "oo": "u", "oa": "ô", "ua": "u-a", "ui": "uy",
}

# Từ tiếng Việt không dấu thường gặp — KHÔNG đánh vần (bảo vệ khỏi nhầm là ngoại lai)
VIET_SKIP = {
    "anh", "em", "the", "ten", "cho", "cua", "co", "va", "la", "ma",
    "toi", "that", "lam", "dung", "deu", "moi", "dau", "cuoi", "nho",
    "lon", "nha", "mot", "hai", "ba", "nam", "bay", "tam", "chin",
    "muoi", "gan", "xa", "me", "bo", "ong", "di", "ve", "den", "tu",
    "doi", "con", "van", "gio", "may", "hay", "khi", "neu", "qua",
    "roi", "cung", "luon", "them", "muon", "dieu", "ben", "minh",
    "ban", "cang", "vua", "sao", "thay", "ngay", "thu", "mot", "nguoi",
    "chu", "chi", "truoc", "sau", "tren", "duoi", "giua", "ngoai",
    "trong", "la", "theo", "vao", "ra", "len", "xuong", "dung", "sai",
    "xung", "suy", "sang", "som", "suon", "mau", "lao", "cao", "mang",
    "tung", "giang", "san", "mua", "mung", "dong", "giong", "deo",
    "neo", "veo", "so", "sua", "cau", "tau", "bau", "tau", "chau",
    # từ Việt KHÔNG dấu dài >=5 ký tự dính regex syllablize sai
    "hoang", "doanh", "huynh", "toanh", "thoang",
}


def _read_syl(syl: str) -> str:
    """Đọc 1 âm tiết kiểu Việt: phụ âm đầu + nguyên âm."""
    vowels = "aeiou"
    # tách nguyên âm cuối
    i = 0
    while i < len(syl) and syl[i] not in vowels:
        i += 1
    cons, vow = syl[:i], syl[i:]
    if not vow:
        # toàn phụ âm -> đánh vần từng chữ
        return "-".join(CONS_READ.get(c, c) for c in cons)
    if len(vow) > 1 and vow in VOW_READ:
        v = VOW_READ[vow]
    elif vow in ("ya", "yo", "yu", "ye"):
        v = vow
    elif vow[0] in "uo" and len(vow) == 2:
        v = VOW_READ.get(vow, VOW_READ[vow[0]])
    else:
        v = VOW_READ.get(vow[0], vow[0])
    if not cons:
        return v
    c = CONS_READ.get(cons[0], cons[0])
    return c + v


def _syllablize(word: str) -> str:
    """Tách từ Latin thành âm tiết Việt hóa (phụ âm làm onset của nguyên âm sau)."""
    w = word.lower()
    vowels = "aeiou"
    syls = []
    pending = ""
    for ch in w:
        if ch in vowels:
            syl = pending + ch
            syls.append(_read_syl(syl))
            pending = ""
        else:
            pending += ch
    if pending:
        for c in pending:
            syls.append(CONS_READ.get(c, c))
    return "-".join(syls)


def _vietnum(n: int) -> str:
    """Chuyển số nguyên sang chữ Việt (6 -> sáu, 56 -> năm mươi sáu, 2024 -> hai nghìn không trăm hai mươi tư)."""
    if n == 0:
        return "không"
    units = ["không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]
    digits = [int(c) for c in str(n)]
    # nhóm 3 chữ số từ phải: [hàng nghìn, hàng triệu, hàng tỷ]
    groups = []
    s = str(n)
    while s:
        groups.insert(0, s[-3:])
        s = s[:-3]
    group_names = ["", "nghìn", "triệu", "tỷ"]
    out_parts = []
    for gi, g in enumerate(groups):
        if int(g) == 0:
            continue
        gv = _vietnum3(g, units)
        gn = group_names[len(groups) - 1 - gi]
        out_parts.append(f"{gv} {gn}".strip())
    return " ".join(out_parts).strip()


def _vietnum3(g: str, units: list) -> str:
    """Đọc 1 nhóm 1-3 chữ số kiểu Việt: 0->'', 5->năm, 15->mười lăm, 105->một trăm linh năm."""
    d = [int(c) for c in g.zfill(3)]
    h, t, u = d[-3], d[-2], d[-1]
    parts = []
    if h:
        parts.append("một trăm" if h == 1 else f"{units[h]} trăm")
    if t:
        if t == 1:
            parts.append("mười")
        else:
            parts.append(f"{units[t]} mươi")
    else:
        if h and u:
            parts.append("linh")
    if u:
        if t >= 2 and u == 1:
            parts.append("mốt")
        elif t >= 1 and u == 4:
            parts.append("tư")
        elif t >= 1 and u == 5:
            parts.append("lăm")
        else:
            parts.append(units[u])
    elif t == 0 and not h:
        parts.append(units[u])
    return " ".join(parts)


def vietnamese_numbers(text: str) -> str:
    """Thay mọi số nguyên trong text bằng chữ Việt (giữ nguyên dấu câu kèm sau).
    6 -> sáu, 56 -> năm mươi sáu. KHÔNG đụng số trong URL/ngày/giờ dạng ghép ký tự."""
    def repl(m):
        num = int(m.group(0))
        return _vietnum(num)
    return re.sub(r"\b\d+\b", repl, text)


def vietnamize_text(text: str) -> str:
    """Phiên âm mọi từ lạ (tiếng Anh/tên Nhật/viết tắt) sang kiểu Việt hóa
    để Piper đọc đúng, hết glitch lặp âm (vd NTR -> en-ti-a, Hanayama -> ha-na-da-ma)."""
    # 0.7. TỪ ĐIỂN ĐỌC THUẦN VIỆT VAY MƯỢN (loanwords_vi.py — LO yêu cầu 2026-08-19):
    #      thay ĐÚNG mọi từ Anh/Nhật còn sót (sex->sét, loli->lô li, hentai->hen tai,
    #      anime->a ni me, cosplay->cót lay, NPC->nờ pê xê, gank->ganh, ...) bằng cách
    #      đọc Việt hóa CÓ DẤU. Đặt TRƯỚC bước xử lý dấu câu để cụm có '-'/','/''' còn
    #      nguyên khớp được, và trước bước 0.4 để ký tự '-' không thành "trừ" làm hỏng cụm.
    text = loanwords_vi.apply_loanwords(text)
    # 0.6. XÓA chữ Hán/Nhật (CJK) trước hết: espeak không phonemize được nên piper
    #      đọc bừa thành "chinese-letter" lặp theo số ký tự (m n y dài). Đặt TRƯỚC
    #      bước 0.4 vì nếu để lọt xuống đó, `[^\w,.\s]` KHÔNG xóa được (do \w match
    #      ký tự CJK trong Python) -> chữ Hán sống sót vào piper.
    text = strip_hanzi(text)
    # 0.5. số -> chữ Việt (6 -> sáu) để model đọc nhất quán; chữ Việt có dấu
    #      nên bước syllablize (chỉ A-Za-z) không đụng vào.
    text = vietnamese_numbers(text)
    # 0.4. CHỈ GIỮ: chữ cái + số + phẩy ',' + chấm '.' (chấm = ngắt câu).
    #      MỌI ký tự khác (? ! ; : " ' ( ) … _ ...) -> phẩy ',' (ngắt nghỉ 0.18s
    #      như dấu phẩy) — LO chốt 2026-08-15 (lúc đầu "bỏ hẳn", LO đổi thành
    #      "ngắt nghỉ 0.18 như dấu phẩy"). Riêng 2+ chấm liền nhau (.., ...,
    #      …) cũng -> phẩy; '.' đơn giữ nguyên.
    #      Dấu '+' đọc thành "cộng", '-' đọc thành "trừ", '=' đọc "bằng"
    #      (LO chốt 2026-08-15: truyện không có xăng-ti-mét nên '-' = trừ).
    text = re.sub(r"\+", " cộng ", text)
    text = re.sub(r"-", " trừ ", text)
    text = re.sub(r"=", " bằng ", text)
    text = re.sub(r"…|\.{2,}", ",", text)
    # Python \w match cả dấu gạch dưới -> chuyển '_' thành phẩy trước
    text = re.sub(r"_", ",", text)
    # MỌI ký tự còn lại không phải chữ/số/,/./space -> phẩy (ngắt nghỉ như dấu phẩy)
    text = re.sub(r"[^\w,.\s]", ",", text)
    # làm sạch space thừa + space quanh phẩy: 'a,  b' -> 'a, b'; 'a , b' -> 'a, b'
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\s*,\s*", ", ", text)
    text = re.sub(r",\s+,", ",", text)
    # phẩy rác: đầu dòng, cuối dòng/câu, liền trước chấm
    text = re.sub(r"^[,\s]+|[,\s]+$", "", text)
    text = re.sub(r",\s*\.", ".", text)
    text = re.sub(r",\s*\n", "\n", text)
    # 3. chuỗi Latin dài còn lại (tên riêng...) -> tách âm tiết Việt hóa.
    #    CHỈ từ >=5 ký tự: tên Nhật/Anh (Hanayama, Yamamoto, manager...) đều dài;
    #    từ tiếng Việt KHÔNG dấu thường ngắn (tay, xanh, kinh, cay...) hoặc bắt đầu
    #    bằng cụm phụ âm thuần Việt (th, ch, nh, ng, tr, ph, kh, gh, gi, qu, ngh)
    #    nên không bị đụng. VIET_SKIP bổ trợ cho từ dài lạ.
    def repl(m):
        w = m.group(0)
        if w.lower() in VIET_SKIP:
            return w
        return _syllablize(w)
    text = re.sub(
        r"\b(?!th|ch|nh|ng|tr|ph|kh|gh|gi|qu|ngh)[A-Za-z]{5,}\b",
        repl, text, flags=re.IGNORECASE)
    return text


def main():
    ap = argparse.ArgumentParser(description="TTS giọng Ngọc Huyền (Piper) v2 - theo câu")
    ap.add_argument("--text", help="Text cần đọc")
    ap.add_argument("--file", help="File text UTF-8")
    ap.add_argument("--out", required=True, help="File đầu ra .wav hoặc .mp3")
    ap.add_argument("--speed", type=float, default=1.3, help="Tốc độ đọc (mặc định 1.3)")
    ap.add_argument("--pause", type=float, default=0.18, help="Khoảng lặng sau chấm/!/? (giây, mặc định 0.18 — LO chốt bản C 2026-08-13)")
    ap.add_argument("--pause-comma", type=float, default=0.18, help="Khoảng lặng sau phẩy (giây, mặc định 0.18 — LO chốt bản C 2026-08-13)")
    ap.add_argument("--pause-para", type=float, default=0.8, help="Khoảng lặng giữa đoạn (giây, mặc định 0.8)")
    ap.add_argument("--noise-scale", type=float, default=0.667, help="Noise scale (mặc định 0.667 — chuẩn cộng đồng Piper, LO chốt 2026-08-19)")
    ap.add_argument("--noise-w", type=float, default=0.8, help="Noise w (mặc định 0.8 — chuẩn cộng đồng Piper, LO chốt 2026-08-19)")
    ap.add_argument("--eq", default="none", choices=["none", "strong", "accent", "vbee"], help="EQ hậu kỳ (vbee = EQ giọng nữ narrator thương mại; strong = EQ rõ chữ; accent = EQ nhấn dấu thanh; none = loudnorm chuẩn)")
    ap.add_argument("--model", default=str(MODEL), help="Đường dẫn model .onnx (mặc định ngoc_huyen.onnx)")
    args = ap.parse_args()

    if args.file:
        raw_lines = Path(args.file).read_text(encoding="utf-8").splitlines()
        # Strip YAML frontmatter (--- ... ---)
        if raw_lines and raw_lines[0].strip() == "---":
            end_fm = None
            for i in range(1, len(raw_lines)):
                if raw_lines[i].strip() == "---":
                    end_fm = i
                    break
            if end_fm is not None:
                raw_lines = raw_lines[end_fm + 1:]
        # Skip chapter heading line (# Chương X...)
        start = 0
        for i, ln in enumerate(raw_lines):
            if re.match(r"^#{1,3}\s*(Chương|Chapter)\s*\d+", ln, re.IGNORECASE):
                start = i + 1
                break
        while start < len(raw_lines) and not raw_lines[start].strip():
            start += 1
        text = "\n".join(raw_lines[start:])
    elif args.text:
        text = args.text
    else:
        print("Cần --text hoặc --file")
        sys.exit(2)

    # Phiên âm các từ lạ (tiếng Anh/tên Nhật/viết tắt) sang kiểu Việt hóa
    # để hết glitch lặp âm (vd NTR -> nờ tê rờ, Hanayama -> ha na da ma)
    text = vietnamize_text(text)

    sentences = split_into_sentences(text)
    print(f"Tổng {len(text)} ký tự, {len(sentences)} câu")

    from piper.voice import PiperVoice
    from piper.config import SynthesisConfig

    voice = PiperVoice.load(args.model)
    patch_anh_phoneme(voice)
    patch_phatam_fix(voice)
    syn = SynthesisConfig(length_scale=1.0 / args.speed, noise_scale=args.noise_scale, noise_w_scale=args.noise_w)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    parts = []
    skipped = 0
    for i, s in enumerate(sentences):
        # bỏ qua câu không có chữ/số (chỉ dấu ngoặc, em-dash...) -> Piper trả 0 frame
        if not re.search(r"[A-Za-zÀ-ỹ0-9]", s):
            skipped += 1
            continue
        try:
            wav = synth_sentence(voice, syn, s)
        except Exception:
            skipped += 1
            continue
        parts.append(wav)
        # ngắt nghỉ theo kiểu dấu câu (khớp kênh: mean 0.36s, mỗi ~2.4s)
        # LƯU Ý: Piper TỰ thêm ~0.15-0.2s silence sau mỗi cụm -> không thêm nữa sau phẩy.
        # dấu chấm/!? -> thêm args.pause (tổng ~0.35s, khớp kênh); dấu phẩy -> Piper tự nghỉ ngắn.
        # Cụm CHẺ (kết thúc không phải dấu câu — do max_len cắt giữa câu) chỉ nghỉ nhẹ 0.06s
        # để không nghe khựng/mất từ.
        last_ch = s[-1] if s else ""
        # LO chốt bản C 2026-08-13: chấm/!/? và phẩy đều = 0.18s (giống Piper tự ngắt)
        if last_ch in "，,。.":
            pause = args.pause_comma if last_ch in "，," else args.pause
        else:
            pause = 0.0
        parts.append(silence(pause))
        if i % 25 == 0 or i == len(sentences) - 1:
            print(f"  [{i+1}/{len(sentences)}] {len(s)} ký tự OK")
    if skipped:
        print(f"  (bỏ qua {skipped} câu trống/không đọc được)")

    full = b"".join(parts)
    tmp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp_wav.close()
    write_wav_pcm(full, tmp_wav.name)

    if str(out_path).lower().endswith(".mp3"):
        if not FFMPEG:
            print("LỖI: xuất .mp3 cần ffmpeg — cài ffmpeg vào PATH hoặc đặt biến môi trường FFMPEG")
            sys.exit(1)
        ff_args = [FFMPEG, "-y", "-i", tmp_wav.name, "-codec:a", "libmp3lame", "-qscale:a", "2"]
        if args.eq == "strong":
            # EQ đầy đủ (cắt trầm + boost rõ chữ): highpass 80, boost 1800/4500/9000, lowpass 11000
            ff_args += ["-af", "highpass=f=80,equalizer=f=1800:t=q:w=1.2:g=4,equalizer=f=4500:t=q:w=1.5:g=3.5,equalizer=f=9000:t=q:w=1.5:g=2,lowpass=f=11000"]
        elif args.eq == "accent":
            # EQ nhấn DẤU THANH: dấu huyền/nặng năng lượng thấp (~300Hz) + sắc/ngã/hỏi cao hơn (~2600-5000Hz)
            # boost vùng trầm-trung để dấu nặng/huyền rõ, boost trung-cao để sắc/ngã sáng hơn
            ff_args += ["-af", "highpass=f=60,equalizer=f=300:t=q:w=1.2:g=3.5,equalizer=f=1200:t=q:w=1.2:g=3,equalizer=f=2600:t=q:w=1.5:g=2.5,equalizer=f=5000:t=q:w=1.5:g=1.5,lowpass=f=12000"]
        elif args.eq == "vbee":
            # EQ giọng nữ narrator kiểu commercial (gần Vbee):
            # - Cắt bùng trầm dưới 120Hz (giọng nữ không cần trầm)
            # - Boost nhẹ 800Hz: làm ấm giọng, tránh mỏng
            # - Boost 2500Hz: vùng "presence" quan trọng nhất → rõ chữ, rõ dấu
            # - Boost nhẹ 6000Hz: không khí, sáng tự nhiên
            # - Cắt trên 12kHz (tránh siêu âm ồn)
            # - loudnorm I=-14: to hơn 2dB so với -16 (nghe trên phone không cần vặn to)
            ff_args += ["-af",
                "highpass=f=120,"
                "equalizer=f=800:t=q:w=1.5:g=2,"
                "equalizer=f=2500:t=q:w=1.2:g=3.5,"
                "equalizer=f=6000:t=q:w=1.8:g=2,"
                "lowpass=f=12000,"
                "loudnorm=I=-14:TP=-1.5:LRA=9"
            ]
        else:
            # loudnorm (LO chốt C: hết vỡ đỉnh, đồng đều tiếng)
            ff_args += ["-af", "loudnorm=I=-16:TP=-1.5:LRA=11"]
        subprocess.run(ff_args + [str(out_path)], capture_output=True)
        os.unlink(tmp_wav.name)
    else:
        os.replace(tmp_wav.name, str(out_path))

    size = os.path.getsize(out_path)
    print(f"XONG: {out_path} ({size/1024/1024:.2f} MB)")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""
loanwords_dynamic.py — Kho từ điển ĐỘNG do người dùng chủ động quản lý.

Chỉ lưu từ vào kho khi người dùng duyệt và bấm thêm từ giao diện (Quét từ -> Thêm).
Tuyệt đối KHÔNG tự động học hay thêm từ vào kho khi render.

File: loanwords_dynamic.json (cùng thư mục module này).
"""
import json
import re
import threading
from pathlib import Path

_DYNAMIC_FILE = Path(__file__).parent / "loanwords_dynamic.json"
_LOCK = threading.Lock()

# Token Latin bất kỳ (kể cả có dấu nháy / gạch nối như "don't", "can't", "e-mail")
_TOKEN_RE = re.compile(r"[A-Za-z]+(?:['\u2019-][A-Za-z]+)*")

# Từ chức năng tiếng Anh phổ biến — bỏ qua khi quét
_SCAN_SKIP = {
    #-article/determiner
    "a", "an", "the",
    # pronoun
    "i", "me", "my", "mine", "you", "your", "yours", "he", "him", "his", "she", "her", "hers",
    "it", "its", "we", "us", "our", "ours", "they", "them", "their", "theirs",
    "this", "that", "these", "those", "who", "whom", "whose", "which", "what",
    "myself", "yourself", "himself", "herself", "itself", "ourselves", "themselves",
    # be / have / do
    "is", "am", "are", "was", "were", "be", "been", "being",
    "has", "have", "had", "having",
    "do", "does", "did", "doing",
    # modal
    "can", "could", "will", "would", "shall", "should", "may", "might", "must",
    # preposition
    "to", "of", "in", "on", "at", "by", "for", "with", "from", "up", "about",
    "into", "through", "during", "before", "after", "above", "below", "between",
    "under", "over", "out", "off", "down", "near", "behind", "beyond", "around",
    # conjunction
    "and", "but", "or", "nor", "so", "yet", "both", "either", "neither", "not",
    "only", "if", "then", "than", "because", "since", "while", "although",
    "unless", "until", "when", "where", "how", "as",
    # adverb
    "not", "also", "very", "often", "just", "still", "already", "too", "here",
    "there", "now", "then", "never", "always", "sometimes", "really",
    "again", "even", "maybe", "perhaps", "actually", "basically",
    # verb common
    "get", "go", "come", "take", "make", "say", "see", "know", "think", "want",
    "need", "look", "find", "give", "tell", "ask", "work", "try", "use", "put",
    "keep", "let", "begin", "seem", "help", "show", "hear", "play", "run", "move",
    "live", "believe", "bring", "happen", "must", "call", "sit", "stand", "lose",
    "pay", "meet", "include", "continue", "set", "learn", "change", "lead",
    "understand", "watch", "follow", "stop", "speak", "read", "grow", "open",
    "walk", "win", "offer", "remember", "love", "consider", "appear", "buy",
    "wait", "serve", "die", "send", "expect", "build", "stay", "fall", "cut",
    "reach", "kill", "remain", "suggest", "raise", "pass", "sell", "require",
    "report", "decide", "pull",
    # common short
    "ok", "no", "yes", "oh", "hey", "hi", "bye", "well", "sure", "right",
    "wrong", "true", "false", "same", "different", "new", "old", "good", "bad",
    "big", "small", "long", "short", "first", "last", "next", "back", "still",
    "way", "thing", "man", "girl", "boy", "day", "time", "year", "people",
    "lot", "something", "nothing", "everything", "someone", "anyone", "everyone",
    # numbers
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "hundred", "thousand", "million",
}

# ── VBEE phonetic mapping ──────────────────────────────────────────
# Phụ âm → cách đọc VBEE (theo IPA rules)
_C_VBEE = {
    "b": "b", "c": "k", "d": "đ", "f": "ph", "g": "g", "h": "h",
    "j": "gi", "k": "c", "l": "l", "m": "m", "n": "n", "p": "p",
    "q": "qu", "r": "r", "s": "x", "t": "t", "v": "v", "w": "goét",
    "x": "x", "y": "d", "z": "đ",
}

# Nguyên âm đôi / diphthong
_V_VBEE = {
    "ai": "ai", "ay": "ây", "au": "ao", "ei": "ây", "eu": "êu",
    "ia": "i-a", "ie": "i-e", "iu": "iu", "oa": "ô-a", "oe": "ô-e",
    "oi": "ôi", "oo": "u", "ou": "âu", "ua": "u-a", "ue": "u-e",
    "ui": "uy", "uo": "u-o", "uy": "u-i",
}

# Nhóm phụ âm đầu đặc biệt (consonant clusters) → đọc theo VBEE
_ONSET_SPECIAL = {
    "br": "b-r", "cr": "c-r", "dr": "đ-r", "fr": "ph-r",
    "gr": "g-r", "pr": "p-r", "tr": "t-r", "bl": "b-l",
    "cl": "c-l", "fl": "ph-l", "gl": "g-l", "pl": "p-l", "sl": "x-l",
    "ch": "c", "sh": "s", "th": "th", "wh": "goét",
    "ck": "c", "ph": "ph",
}

# Nhóm phụ âm cuối → thêm stop sau fricative (VBEE rule)
_CODA_STOP = {"s": "ch", "z": "ch", "x": "ch", "f": "t", "v": "t", "sh": "s"}

# Từ thông dụng VBEE — đọc theo phiên âm chuẩn, override phonetic rules
_VBEE_COMMON = {
    "the": "dờ", "this": "dít-x", "that": "dát", "them": "dẻm",
    "there": "dê-r", "their": "dê-r", "they": "dây", "than": "dần",
    "then": "dân", "these": "di-x", "those": "dô-x", "there": "dê-r",
    "what": "goét", "when": "goên", "where": "goê-r", "which": "goét-c",
    "who": "hư", "why": "goai", "how": "hao", "has": "dét",
    "have": "hep", "had": "hét", "can": "cân", "may": "mây",
    "will": "goi", "would": "goút", "could": "cút", "should": "sút",
    "must": "mét-x-t", "not": "nót", "but": "bét", "and": "ân",
    "for": "phờ", "are": "a-r", "was": "goét", "were": "goơ-r",
    "his": "hít-x", "her": "hơ-r", "she": "xi", "him": "hìm",
    "her": "hơ-r", "its": "ít-x", "our": "ao-r", "out": "ao-t",
    "all": "o", "also": "o-xo", "just": "giét-x-t", "more": "mô-r",
    "most": "mô-x-t", "much": "méc", "very": "vê-r",
    "from": "phờ-rôm", "some": "xẻm", "such": "séc",
    "only": "oan", "other": "é-dờ", "each": "it-c",
    "make": "mây-c", "like": "lai-c", "take": "tây-c",
    "come": "côm", "give": "gíp", "think": "thinh-c",
    "know": "nô", "see": "xi", "get": "gét",
    "new": "niu", "now": "nao", "way": "uây",
    "day": "đây", "time": "tai-m", "year": "yi-r",
    "people": "pi-po", "man": "mân", "woman": "goém",
    "child": "cai-len", "world": "goớ-len", "life": "lai-ph",
    "hand": "hân", "part": "pa-t", "place": "plây-x",
    "case": "kây-x", "week": "uui-c", "work": "goéc-c",
    "back": "béc-c", "good": "gút", "great": "gré-t",
    "long": "long", "little": "lit-tờ", "same": "xây-m",
    "big": "bích", "high": "hai", "small": "x-mo",
    "old": "o", "right": "rai-t", "tell": "têo",
    "use": "iu-x", "every": "ê-vờ-r", "still": "x-tin",
    "name": "nây-m", "need": "ni-t", "first": "phéc-x-t",
    "keep": "ki-p", "let": "lét", "turn": "teo-n",
    "move": "mu-p", "play": "p-lây", "try": "trai",
    "ask": "a-x-c", "need": "nit", "feel": "fi-o",
    "become": "bi-côm", "leave": "li-p", "put": "pút",
    "mean": "min", "keep": "ki-p", "help": "hético",
    "start": "x-ta-t", "show": "sô", "hear": "hi-r",
    "run": "rân", "move": "mu-p", "live": "li-p",
    "believe": "bi-li-p", "bring": "bring", "happen": "hé-pân",
    "write": "rai-t", "provide": "pro-pai", "sit": "xit",
    "stand": "x-tân", "lose": "lu-x", "pay": "pây",
    "include": "in-CLU", "continue": "con-ti-niu",
    "set": "xét", "learn": "lọc-n", "change": "ché-n",
    "lead": "li-t", "understand": "ân-de-x-tân",
    "watch": "goét-c", "follow": "phô-lo", "stop": "x-tót",
    "create": "c-ri-ét", "speak": "x-pi-c", "read": "rit",
    "allow": "a-lao", "add": "ét", "spend": "x-pen",
    "grow": "grô", "open": "ô-pân", "walk": "goóc",
    "win": "goinh", "offer": "ô-phờ", "remember": "ri-mem-bờ",
    "love": "lép", "hold": "hô-len", "appear": "ê-pi-r",
    "buy": "bai", "wait": "goét", "eat": "it",
    "train": "tré-n", "air": "e-r", "horse": "hóc-x",
    "music": "miu-zi-c", "car": "ca-r", "book": "búc",
    "water": "goét-tờ", "food": "fút", "house": "hao-x",
    "family": "phờ-mi-li", "friend": "phờ-ren",
    "city": "xi-ti", "country": "câu-nhờ",
    "school": "x-cu", "student": "xi-ten",
    "teacher": "ti-cờ", "doctor": "dóc-tờ",
    "money": "mô-ni", "number": "năm-bờ",
    "problem": "pro-blẻm", "question": "quét-x-non",
    "answer": "an-xờ", "example": "ig-zân-plờ",
    "point": "poin-t", " government": "gờ-van-men",
    "company": "côm-pa-ni", "system": "xít-tem",
    "program": "pro-gr_reordered", "question": "quét-x-non",
    "business": "bi-nét-x", "market": "ma-két",
    "service": "sơ-vít", "report": "ri-po-t",
    "internet": "in-tờ-net", "email": "i-meo",
    "smartphone": "x-mát-phôn", "computer": "côm-piu-tờ",
    "technology": "téc-no-lo-gi", "data": "đa-ta",
    "manager": "mê-nờ", "concert": "cơn-xét",
    "barista": "ba-rít-ta", "whisky": "gui-x-ki",
    "station": "x-tây-sừn", "sushi": "xu-xi",
    "faster": "phát-x-tờ", "oscar": "ót-x-ca-r",
    "brain": "b-rên", "chair": "che-r",
    "star": "x-ta", "wish": "guýt-s", "six": "xích-x",
    "test": "tét-x-t", "bad": "bát-đ",
    "hello": "hê-lô", "thank": "thanh-c",
}


def _letters(w: str) -> int:
    """Số ký tự chữ cái trong token (bỏ dấu nháy/gạch nối khi đếm độ dài)."""
    return sum(1 for c in w if c.isalpha())


def _load() -> dict:
    try:
        if _DYNAMIC_FILE.exists():
            return json.loads(_DYNAMIC_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save(data: dict):
    tmp = _DYNAMIC_FILE.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    tmp.replace(_DYNAMIC_FILE)


def _reading_for(token: str) -> str:
    """Phiên âm token sang cách đọc tiếng Việt theo quy tắc VBEE.
    Chỉ phiên âm phần chữ cái (bỏ dấu nháy/gạch nối)."""
    letters = re.sub(r"[^A-Za-z]", "", token)
    if not letters:
        return ""
    # 1. Từ viết tắt: tất cả hoa (≥2 chữ) HOẶC toàn phụ âm
    if _is_abbreviation(letters):
        return _spell_abbreviation(letters)
    # 2. Từ thông dụng có sẵn reading
    low = letters.lower()
    if low in _VBEE_COMMON:
        return _VBEE_COMMON[low]
    # 3. Phonetic rules
    return _vbee_phonetic(letters)


def _is_abbreviation(word: str) -> bool:
    """Từ viết tắt: tất cả hoa HOẶC toàn phụ âm."""
    if word.isupper() and len(word) >= 2:
        return True
    if not any(c in "aeiou" for c in word.lower()) and len(word) >= 2:
        return True
    return False


def _spell_abbreviation(word: str) -> str:
    """Đánh vần từ viết tắt: QL4H → quờ-lờ-bốn-hắt."""
    _SPELL = {
        "b": "bê", "c": "xê", "d": "đê", "f": "ép", "g": "gờ",
        "h": "hắt", "j": "gi", "k": "ca", "l": "lờ", "m": "mờ",
        "n": "nờ", "p": "pê", "q": "quờ", "r": "rờ", "s": "ét",
        "t": "tê", "v": "vê", "w": "goét", "x": "ích", "y": "i",
        "z": "zét",
    }
    parts = []
    for c in word:
        if c.isdigit():
            from tts_ngochuyen import _vietnum
            parts.append(_vietnum(int(c)))
        else:
            parts.append(_SPELL.get(c.lower(), c))
    return "-".join(parts)


def _vbee_phonetic(word: str) -> str:
    """Phiên âm từ tiếng Anh theo quy tắc VBEE (syllable-based).
    Tách từng âm tiết: phụ âm (onset) + nguyên âm (nucleus), xử lý VBEE rules.
    Xử lý đúng vowel digraphs (oo, ea, ai, ei, ou...)."""
    w = word.lower()
    vowels = "aeiou"
    syls = []
    pending = ""
    i = 0

    while i < len(w):
        ch = w[i]
        if ch in vowels:
            # Thử match vowel digraph/trigraph trước (oo, ea, ai, ei, ou, au, oi...)
            vow_end = i + 1
            if i + 2 <= len(w) and w[i:i+2] in _V_VBEE:
                vow_end = i + 2
            # Build syllable: pending consonants + vowel cluster
            syl = pending + w[i:vow_end]
            syls.append(_map_syllable_vbee(syl))
            pending = ""
            i = vow_end
        else:
            pending += ch
            i += 1

    # Phụ âm còn lại ở cuối từ (coda)
    if pending:
        syls.append(_map_coda_cluster(pending))

    return "-".join(syls)


def _map_syllable_vbee(syl: str) -> str:
    """Map 1 âm tiết (onset + nucleus) theo VBEE rules."""
    vowels = "aeiou"
    # Tách phụ âm đầu (onset)
    i = 0
    while i < len(syl) and syl[i] not in vowels:
        i += 1
    cons = syl[:i]
    vow = syl[i:]

    # Map nguyên âm
    if not vow:
        return ""
    if len(vow) >= 2 and vow[:2] in _V_VBEE:
        v = _V_VBEE[vow[:2]]
        if len(vow) > 2:
            v += _map_syllable_vbee(vow[2:])  # còn lại
    else:
        v = _V_VBEE.get(vow[0], vow[0])

    # Map phụ âm
    if not cons:
        return v
    c = _map_onset(cons)
    return c + v


def _map_onset(cluster: str) -> str:
    """Map nhóm phụ âm đầu theo VBEE."""
    if not cluster:
        return ""
    if len(cluster) == 1:
        return _C_VBEE.get(cluster, cluster)
    # Kiểm tra nhóm đặc biệt (2-3 chữ)
    for length in range(min(3, len(cluster)), 1, -1):
        prefix = cluster[:length]
        if prefix in _ONSET_SPECIAL:
            rest_vn = _map_onset(cluster[length:])
            return _ONSET_SPECIAL[prefix] + ("-" + rest_vn if rest_vn else "")
    # Mặc định: giữ nguyên phụ âm đầu, gạch nối phần còn lại
    first = _C_VBEE.get(cluster[0], cluster[0])
    rest_vn = _map_onset(cluster[1:])
    return first + ("-" + rest_vn if rest_vn else "")


def _map_coda_cluster(cluster: str) -> str:
    """Map nhóm phụ âm cuối theo VBEE: thêm stop sau fricative, xử lý digraph."""
    if not cluster:
        return ""
    if len(cluster) == 1:
        c = cluster[0]
        if c in _CODA_STOP:
            return _C_VBEE.get(c, c) + _CODA_STOP[c]
        return _C_VBEE.get(c, c)

    # Nhóm phụ âm cuối: xử lý digraph trước, rồi từng chữ
    parts = []
    i = 0
    while i < len(cluster):
        # Kiểm tra digraph/trigraph trước (không apply _C_VBEE cho digraph trong _CODA_STOP)
        for length in range(min(3, len(cluster) - i), 1, -1):
            sub = cluster[i:i+length]
            if sub in _CODA_STOP:
                parts.append(_CODA_STOP[sub])
                i += length
                break
        else:
            # Ký tự đơn
            c = cluster[i]
            mapped = _C_VBEE.get(c, c)
            if c in _CODA_STOP:
                parts.append(mapped)
                parts.append(_CODA_STOP[c])
            else:
                parts.append(mapped)
            i += 1
    return "-".join(parts)


def learn_loanwords(text: str) -> list:
    """Không tự động học từ nữa — luôn trả về rỗng theo yêu cầu người dùng."""
    return []


def get_all() -> dict:
    """Toàn bộ kho từ động hiện tại."""
    return _load()


def count() -> int:
    return len(_load())


def scan_new_words(text: str) -> list:
    """Quét text, trả về từ nước ngoài / không dấu (≥2 chữ Latin) CHƯA có trong kho.
    Từ nào đã có trong kho sẽ bị bỏ qua (không hiển thị)."""
    dynamic_map = _load()

    result = []
    seen = set()
    for m in _TOKEN_RE.finditer(text):
        token = m.group(0)
        key = token.lower()
        if len(key) < 3:
            continue
        if key in _SCAN_SKIP:
            continue
        if key in seen:
            continue
        seen.add(key)
        # Bỏ qua từ đã có trong kho
        if key in dynamic_map:
            continue
        result.append({
            "word": token,
            "key": key,
            "reading": _reading_for(token),
            "in_dict": False,
        })
    return result


def get_all_loanwords() -> dict:
    """Kho từ động (loanwords_dynamic.json)."""
    return _load()


def add_words(pairs: list) -> int:
    """Thêm/sửa nhiều từ vào kho động. pairs = [(word, reading), ...].
    Trả về số từ đã thêm. Từ mới thêm được xếp lên đầu."""
    if not pairs:
        return 0
    with _LOCK:
        dynamic = _load()
        added_count = 0
        for word, reading in pairs:
            w = (word or "").strip().lower()
            r = (reading or "").strip()
            if not w or not r:
                continue
            dynamic.pop(w, None)
            dynamic[w] = r
            added_count += 1
        _save(dynamic)
    return added_count


def remove_word(word: str) -> bool:
    """Xóa một từ khỏi kho động."""
    with _LOCK:
        dynamic = _load()
        w = (word or "").strip().lower()
        if w in dynamic:
            del dynamic[w]
            _save(dynamic)
            return True
    return False


def update_word(word: str, reading: str) -> bool:
    """Sửa cách đọc của một từ đã có trong kho động (đưa lên đầu danh sách)."""
    w = (word or "").strip().lower()
    r = (reading or "").strip()
    if not w or not r:
        return False
    with _LOCK:
        dynamic = _load()
        if w not in dynamic:
            return False
        dynamic.pop(w, None)
        dynamic[w] = r
        _save(dynamic)
    return True

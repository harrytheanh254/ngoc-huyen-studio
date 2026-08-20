# -*- coding: utf-8 -*-
"""
vietnamize.py — Phiên âm từ tiếng Anh / từ viết tắt sang kiểu "Việt hóa" để Piper đọc đúng.

Ý tưởng: espeak-ng đọc từ tiếng Anh (vd "building") thành IPA tiếng Anh (bˈɪldɪŋ)
và model tiếng Việt gặp âm lạ (ɪ, ɹ, æ...) → glitch lặp âm.
Giải pháp: map IPA -> chữ Việt gần đúng ("bui đin"), và từ viết tắt (NTR, AI)
thì tách tên chữ cái kiểu Việt ("nờ tê rờ").

Cách dùng:
    from vietnamize import vietnamize_word
    vietnamize_word("building")  # -> "bui đin"
    vietnamize_word("NTR")       # -> "nờ tê rờ"
    vietnamize_word("Iori")      # -> "i-ô-ri"
"""
import re
from piper.phonemize_espeak import EspeakPhonemizer

_ph = EspeakPhonemizer()

# ---------------------------------------------------------------
# 1. MAP IPA tiếng Anh -> chữ Việt (phiên âm kiểu bình dân)
#    Đọc theo cách người Việt phát âm từ mượn tiếng Anh.
# ---------------------------------------------------------------
IPA_TO_VI = {
    # nguyên âm
    "ɪ": "i", "iː": "i", "i": "i",
    "ʊ": "u", "uː": "u", "u": "u",
    "e": "ê", "eɪ": "ây", "ɛ": "e", "æ": "e",
    "ə": "ơ", "ɚ": "ơ", "ɜː": "ơ", "ɜ": "ơ", "ɝ": "ơ",
    "ʌ": "a", "ɑː": "a", "ɑ": "a", "ɒ": "o", "ɔː": "o", "ɔ": "o",
    "oʊ": "âu", "o": "ô", "əʊ": "âu",
    "aɪ": "ai", "aʊ": "ao", "ɔɪ": "oi",
    "ɪə": "ia", "eə": "e", "ʊə": "ua",
    # phụ âm
    "p": "p", "b": "b", "t": "t", "d": "đ", "k": "c", "ɡ": "g", "g": "g",
    "f": "ph", "v": "v", "θ": "th", "ð": "đ", "s": "x", "z": "d",
    "ʃ": "s", "ʒ": "gi", "h": "h",
    "tʃ": "ch", "dʒ": "gi",
    "m": "m", "n": "n", "ŋ": "ng", "l": "l", "r": "r", "ɹ": "r",
    "j": "d", "w": "u", "ɾ": "r", "ʔ": "",
    # dấu nhấn — bỏ
    "ˈ": "", "ˌ": "", "ː": "", ".": "", "'": "",
}

# các ký tự IPA không nên xuất hiện sau khi map (debug)
_KNOWN = set(IPA_TO_VI.keys())


def _ipa_to_vi(ipa: str) -> str:
    """Chuỗi IPA -> chữ Việt, gộp theo thứ tự ưu tiên (âm dài 2 ký tự trước)."""
    out = []
    i = 0
    # ưu tiên các âm 2-3 ký tự trước
    keys = sorted(IPA_TO_VI.keys(), key=len, reverse=True)
    while i < len(ipa):
        matched = False
        for k in keys:
            if ipa.startswith(k, i):
                v = IPA_TO_VI[k]
                if v:
                    out.append(v)
                i += len(k)
                matched = True
                break
        if not matched:
            out.append(ipa[i])
            i += 1
    return "".join(out)


# ---------------------------------------------------------------
# 2. Tách từ viết tắt -> tên chữ cái kiểu Việt
#    NTR -> "nờ tê rờ"
# ---------------------------------------------------------------
LETTER_NAMES_VI = {
    "a": "ây", "b": "bê", "c": "xê", "d": "đê", "e": "e", "f": "ép",
    "g": "gê", "h": "hát", "i": "i", "j": "gi", "k": "ca", "l": "e-lờ",
    "m": "em-mờ", "n": "nờ", "o": "ô", "p": "pê", "q": "cu", "r": "rờ",
    "s": "ét", "t": "tê", "u": "u", "v": "vê", "w": "vê-kép",
    "x": "ích-xì", "y": "i-dài", "z": "dét",
}

# tên chữ cái theo kiểu LO: N -> "nờ", R -> "rờ" (không phải "en-nờ", "e-rờ")
LETTER_NAMES_SHORT = {
    "a": "a", "b": "bê", "c": "xê", "d": "đê", "e": "e", "f": "phờ",
    "g": "gờ", "h": "hờ", "i": "i", "j": "gi", "k": "ca", "l": "lờ",
    "m": "mờ", "n": "nờ", "o": "ô", "p": "pờ", "q": "quy", "r": "rờ",
    "s": "sờ", "t": "tê", "u": "u", "v": "vê", "w": "vê-kép",
    "x": "xờ", "y": "i-dài", "z": "dờ",
}


def _spell_acronym(word: str) -> str:
    """NTR -> 'nờ tê rờ' (tên chữ cái ngắn kiểu LO)."""
    return " ".join(LETTER_NAMES_SHORT.get(c.lower(), c) for c in word)


# ---------------------------------------------------------------
# 3. Phát hiện từ lạ + tự động phiên âm
# ---------------------------------------------------------------
# âm IPA nước ngoài => từ bị espeak đọc sai kiểu tiếng Anh
_FOREIGN_HINTS = "ʐðɹæɪʊɒʌɚɝθʒ"


def detect_foreign_phonemes(word: str) -> list:
    """Trả list âm lạ nếu espeak phonemize từ này ra âm nước ngoài."""
    try:
        r = _ph.phonemize("vi", word)
        flat = "".join("".join(x) for x in r)
    except Exception:
        return []
    return [c for c in _FOREIGN_HINTS if c in flat]


def vietnamize_word(word: str) -> str:
    """
    Chuyển 1 từ lạ sang cách viết Piper đọc được.
    - Nếu toàn chữ hoa (viết tắt): NTR -> nờ tê rờ
    - Nếu có âm IPA nước ngoài: phiên âm IPA tiếng Anh -> chữ Việt
    - Nếu là tên riêng dài có âm lạ: phiên âm từng phần
    - Không lạ: trả nguyên
    """
    word_clean = word.strip(".,!?;:()\"'“”")
    if not word_clean:
        return word
    # viết tắt: toàn chữ hoa, dài 2-6
    if word_clean.isupper() and 2 <= len(word_clean) <= 6 and word_clean.isalpha():
        return _spell_acronym(word_clean)
    # có âm lạ -> phiên âm IPA en-us -> Việt
    if detect_foreign_phonemes(word_clean):
        try:
            r = _ph.phonemize("en-us", word_clean)
            flat = "".join("".join(x) for x in r)
            vi = _ipa_to_vi(flat)
            # nếu phiên âm ra quá dài/lạ, fallback tách ký tự theo tên chữ cái
            if not vi or len(vi) > len(word_clean) * 3:
                return _spell_acronym(word_clean)
            return vi
        except Exception:
            return _spell_acronym(word_clean)
    return word


def vietnamize_text(text: str) -> str:
    """Thay tất cả từ lạ trong text bằng phiên âm Việt hóa."""
    # giữ nguyên chữ hoa đầu câu không bị hỏng; tokenizer tìm từ Latin
    def repl(m):
        return vietnamize_word(m.group(0))
    return re.sub(r"[A-Za-zÀ-ỹ0-9]+", repl, text)


if __name__ == "__main__":
    # test nhanh
    tests = ["building", "NTR", "AI", "Iori", "GTA", "school", "club", "game",
             "boss", "level", "computer", "phone", "internet", "love", "boy",
             "girl", "friend", "money", "king", "queen", "world", "story",
             "chapter", "Yagami", "Trường", "người", "18"]
    for w in tests:
        print(f"{w:14} -> {vietnamize_word(w)}")

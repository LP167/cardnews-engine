#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SOURCE_PUBLICATION PDF → 카드뉴스용 구조화 JSON

SOURCE_PUBLICATION은 KaTeX로 조판돼 있다. 수식은 전부 `KaTeX_*` 폰트 스팬이라
**수식 위치를 좌표로 자동 검출**할 수 있다. 이게 자동화의 핵심이다.
한글 본문은 KoPubWorld* 스팬이므로 둘을 분리해 읽는다.

  python3 extract.py ../2017_수학/2017_수학_문제1.pdf
  python3 extract.py ../2017_수학/*.pdf --outdir out

산출: <문항>.json  (메타 · 절별 본문 · 핵심 아이디어 · 시나리오 · 감점 · 수식 크롭 좌표)
"""
import sys, os, re, json, argparse, unicodedata as U

try:
    import pymupdf
except ImportError:
    import fitz as pymupdf

# ── 절 표제 ─────────────────────────────────────────────
# 원숫자는 한글 뒤에 찍힌다("한눈에 보기②"). 한글만으로 매칭한다.
SECTIONS = [
    ("problem",  r"기출문제·원문"),
    ("glance",   r"한눈에보기"),
    ("first",    r"첫인상잡기"),
    ("steps",    r"단계별풀이"),
    ("script",   r"면접답변시나리오"),
    ("check",    r"스스로점검"),
    ("review",   r"되돌아보기"),
]
MATH_FONT = re.compile(r"^KaTeX")
_T3 = re.compile(r"^Type3")
_HANGUL = re.compile(r"[가-힣ㄱ-ㅎㅏ-ㅣ]")

def is_math(sp):
    """수식 스팬인가.

    주의 — Type3를 통째로 수식으로 보면 안 된다(교차검증에서 잡힌 버그).
    Type3는 '글리프가 문서에 내장됐다'는 저장 방식일 뿐 의미가 아니다.
    이 교재에서 Type3 스팬 226회 중 대부분이 한글('그리고' '경계' '변별점')과
    체크표시 ✓ 였고, 그걸 수식으로 분류해 본문에서 글자가 통째로 사라지고 있었다.
    → KaTeX는 수식. Type3는 **한글이 없을 때만** 수식으로 본다."""
    f, t = sp["font"], sp["text"]
    if MATH_FONT.match(f):
        return True
    if _T3.match(f):
        return not _HANGUL.search(t) and t.strip() not in ("✓", "·", "")
    return False


def nfc(s):
    return U.normalize("NFC", s)


# 페이지 기하 — 분수 가로줄과 근호. 둘 다 글리프가 아니라 그림이라
# 글자만 읽으면 a²/4 가 "a²4" 로, √2 가 그냥 "2" 로 뭉개진다.
GEOM = {}


def page_geom(page):
    """이 페이지의 분수 가로줄 · 근호 위치.

    근호는 clip이 페이지 밖(x1>5000pt)까지 잡혀 있어 rect 폭을 믿으면 안 된다.
    시작 x만 쓴다."""
    bars, rads = [], []
    for d in page.get_drawings():
        r = d["rect"]
        h, w = r.height, r.width
        if h < 2.5 and 2 < w < 80:
            bars.append((r.x0, r.y0, r.x1, r.y1))
        elif 6 < h < 40 and any(it[0] == "c" for it in d["items"]):
            rads.append((r.x0, r.y0, r.y1))
    return {"bars": bars, "rads": rads}


def load(path):
    doc = pymupdf.open(path)
    GEOM.clear()
    spans = []          # (page, y0, x0, x1, y1, text, font, size)
    for pi, page in enumerate(doc):
        GEOM[pi] = page_geom(page)
        # rawdict = 글자 단위 좌표. 스팬 단위로만 보면 수식이 한글 스팬 **안쪽**에
        # 그려진 줄에서 순서가 무너진다(아래 segments 주석 참고).
        for b in page.get_text("rawdict")["blocks"]:
            for l in b.get("lines", []):
                for s in l["spans"]:
                    ch = [dict(c=c["c"], x0=c["bbox"][0], y0=c["bbox"][1],
                               x1=c["bbox"][2], y1=c["bbox"][3], sz=s["size"])
                          for c in s["chars"]]
                    t = "".join(c["c"] for c in ch)
                    if not t.strip():
                        continue
                    x0, y0, x1, y1 = s["bbox"]
                    spans.append(dict(p=pi, x0=x0, y0=y0, x1=x1, y1=y1,
                                      t=t, f=s["font"], sz=s["size"], ch=ch,
                                      is_math=is_math(dict(font=s["font"], text=t))))
    return doc, spans


# ── 수식 → 읽을 수 있는 텍스트 ──────────────────────────
# 카드에는 수식을 PDF 크롭 이미지로 끼워 넣는다(segments의 rect). 그런데
# 핵심 아이디어 · 감점 인용 · 꼬리질문처럼 **문자열로만 실리는 필드**는 그 길이 없어서,
# 수식을 버리면 "판별식이  인 경우", "를  으로 잘못 옮김" 같은 비문이 그대로 카드에 찍힌다.
# KaTeX 글리프는 진짜 유니코드라 위/아래첨자 · 분수 · 근호만 살려 주면 글로 읽힌다.
SUP = {"0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴", "5": "⁵", "6": "⁶",
       "7": "⁷", "8": "⁸", "9": "⁹", "+": "⁺", "−": "⁻", "-": "⁻", "=": "⁼",
       "(": "⁽", ")": "⁾", "n": "ⁿ", "i": "ⁱ"}
SUB = {"0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄", "5": "₅", "6": "₆",
       "7": "₇", "8": "₈", "9": "₉", "+": "₊", "−": "₋", "-": "₋", "=": "₌",
       "(": "₍", ")": "₎", "a": "ₐ", "n": "ₙ", "i": "ᵢ", "j": "ⱼ", "k": "ₖ",
       "m": "ₘ", "x": "ₓ"}


def math_text(chars, bars=(), rads=()):
    """수식 글리프 묶음 → 한 줄 텍스트. (a₁, b₁) · x²+ax+b=0 · a²/4 · 2√a"""
    chars = [c for c in chars if c["c"].strip() and c["c"] != "\u200b"]
    if not chars:
        return ""
    lo = min(c["x0"] for c in chars)
    hi = max(c["x1"] for c in chars)

    # ① 분수 — 가로줄 위가 분자, 아래가 분모
    used, toks = set(), []
    for b in bars:
        if b[2] < lo - 1 or b[0] > hi + 1:
            continue
        inx = [c for c in chars
               if b[0] - 1.5 <= (c["x0"] + c["x1"]) / 2 <= b[2] + 1.5]
        num = [c for c in inx if c["y1"] <= b[1] + 1]
        den = [c for c in inx if c["y0"] >= b[3] - 1]
        if not num or not den:
            continue
        used.update(id(c) for c in num + den)
        toks.append((b[0], "%s/%s" % (math_text(num), math_text(den))))

    body = [c for c in chars if id(c) not in used]
    if body:
        B = max(c["sz"] for c in body)
        full = sorted(c["y1"] for c in body if c["sz"] >= B * 0.85)
        base = full[len(full) // 2] if full else 0
        for c in body:
            t = c["c"]
            if c["sz"] < B * 0.85 and full:
                # 위첨자는 기준선보다 확실히 높다. 아래첨자는 기준선 언저리~아래.
                t = (SUP.get(t, "^" + t) if c["y1"] < base - B * 0.25
                     else SUB.get(t, "_" + t))
            toks.append((c["x0"], t))

    # ② 근호 — 글리프가 아니라 곡선 그림이다
    for rx, ry0, ry1 in rads:
        if lo - 2 <= rx <= hi and any(ry0 - 3 <= c["y0"] and c["y1"] <= ry1 + 3
                                      for c in chars):
            toks.append((rx, "√"))

    s = "".join(t for _, t in sorted(toks, key=lambda z: z[0]))
    s = re.sub(r"\s+", "", s)
    return re.sub(r",(?=\S)", ", ", s)


def line_text(spans, drop_math=False):
    """같은 줄(y가 비슷한) 스팬을 묶어 읽기 좋은 문자열로.

    예전에는 KaTeX 스팬을 통째로 버렸다. 그러면 수식이 있던 자리가 구멍이 나서
    "판별식이  인 경우", "를  으로 잘못 옮김" 같은 비문이 카드에 그대로 실렸다.
    → 이제 수식 자리에 math_text()로 옮긴 글자(a²−4b≤0)를 채운다.
    drop_math=True면 예전처럼 뺀다."""
    if drop_math:
        out, cur, cy, cp = [], [], None, None
        for s in sorted([s for s in spans if not s["is_math"]],
                        key=lambda s: (s["p"], round(s["y0"], 1), s["x0"])):
            if cy is None or s["p"] != cp or abs(s["y0"] - cy) > 4:
                if cur:
                    out.append("".join(x["t"] for x in cur).strip())
                cur, cy, cp = [s], s["y0"], s["p"]
            else:
                cur.append(s)
        if cur:
            out.append("".join(x["t"] for x in cur).strip())
        return [x for x in out if x]
    return [L["text"] for L in segments(spans) if L["text"].strip()]



# ── 인라인 수식 되살리기 ────────────────────────────────
# 한글 문장에서 수식을 빼면 "대칭이동은 좌표를 맞바꾸는 것이므로 , 입니다"가 된다.
# 그래서 한 줄을 [텍스트 조각 | 수식 조각]의 순서열로 돌려준다.
# 수식 조각은 크롭 rect를 들고 있으므로 렌더러가 이미지로 끼워 넣으면 된다.
def to_lines(spans):
    rows, cur, cy, cp = [], [], None, None
    for s in sorted(spans, key=lambda s: (s["p"], round(s["y0"], 1), s["x0"])):
        if cy is None or s["p"] != cp or abs(s["y0"] - cy) > 4:
            if cur: rows.append(cur)
            cur, cy, cp = [s], s["y0"], s["p"]
        else:
            cur.append(s)
    if cur: rows.append(cur)
    return rows


def segments(spans, pad=2.5):
    """줄 단위로 텍스트/수식을 인라인 순서대로 쪼갠다.

    함정 두 개 (둘 다 실제로 걸렸음) —
    ① KaTeX는 아래첨자·분수를 별도 y로 찍는다. 그냥 y로 줄을 나누면 한 시각 줄이
       3~4개로 쪼개져 렌더할 때 수식이 중복된다.
    ② 그렇다고 수식을 근접 병합하면, 같은 x에 있는 수식들이 **줄을 타고 연쇄 병합**된다.
       (P₁(a₁,b₁)이 네 줄에 걸쳐 나오면 h=62pt짜리 rect가 되어 한글까지 크롭에 들어옴)

    → 세로 병합을 아예 하지 않는다. **한글 줄이 만드는 y 밴드**에 수식을 배정하고,
      밴드 안에서 가로로만 병합한다. 밴드에 안 붙는 수식은 독립 display로 본다.
    """
    if not spans:
        return []
    txt = [s for s in spans if not s["is_math"]]
    mth = [s for s in spans if s["is_math"]]
    rows = to_lines(txt)

    bands = []
    for row in rows:
        bands.append({"p": row[0]["p"],
                      "y0": min(x["y0"] for x in row),
                      "y1": max(x["y1"] for x in row),
                      "row": row, "math": []})

    free = []
    for m in mth:
        best, bs = None, 0.0
        for b in bands:
            if b["p"] != m["p"]:
                continue
            ov = min(b["y1"], m["y1"]) - max(b["y0"], m["y0"])
            h = max(1.0, m["y1"] - m["y0"])
            if ov > bs:
                best, bs = b, ov
        if best is not None and bs > (m["y1"] - m["y0"]) * 0.30:
            best["math"].append(m)
        else:
            free.append(m)

    def hmerge(ms, gap=5.0):
        """가로로만 병합한다. 세로는 건드리지 않는다."""
        ms = sorted(ms, key=lambda s: s["x0"])
        out = []
        for m in ms:
            if out and m["x0"] <= out[-1][2] + gap:
                o = out[-1]
                o[1] = min(o[1], m["y0"]); o[2] = max(o[2], m["x1"])
                o[3] = max(o[3], m["y1"]); o[0] = min(o[0], m["x0"])
            else:
                out.append([m["x0"], m["y0"], m["x1"], m["y1"], m["p"]])
        return out

    result = []
    for b in bands:
        blocks = hmerge(b["math"])
        # **글자 단위**로 자른다. 스팬 단위로 x 순서를 매기면 안 되는 줄이 있다 —
        # KaTeX는 한글 한 줄을 스팬 하나로 찍고 그 스팬의 x 범위 **안쪽**에 인라인
        # 수식을 얹는다. 그러면 "판별식이 0인 경우"의 0이 스팬 뒤로 밀려
        # "판별식이 인 경우 … 0" 이 된다(실제로 8번 카드에서 이렇게 나왔다).
        tch = [c for s in b["row"] for c in s["ch"]]
        items = [(c["x0"], 1, "t", c) for c in tch]
        items += [(bl[0], 0, "m", bl) for bl in blocks]
        items.sort(key=lambda z: (z[0], z[1]))
        segs, buf = [], []
        def flush():
            if buf:
                t = nfc("".join(c["c"] for c in buf))
                if t.strip() or segs:
                    segs.append({"type": "text", "t": t if t.strip() else " "})
                buf.clear()
        for _, _, kind, obj in items:
            if kind == "t":
                buf.append(obj)
            else:
                flush()
                # pad를 그대로 주면 크롭이 옆 한글 글자를 물어 수식 뒤에 정체불명의
                # 획이 남는다(2·7번 카드). 이웃 글자 경계까지만 넓힌다.
                left = max([c["x1"] for c in tch if c["x1"] <= obj[0] + 0.5],
                           default=obj[0] - pad)
                right = min([c["x0"] for c in tch if c["x0"] >= obj[2] - 0.5],
                            default=obj[2] + pad)
                x0 = round(max(obj[0] - pad, min(obj[0], left + 0.3)), 1)
                x1 = round(min(obj[2] + pad, max(obj[2], right - 0.3)), 1)
                mc = [c for s in b["math"] for c in s["ch"]
                      if obj[0] - 0.5 <= c["x0"] and c["x1"] <= obj[2] + 0.5]
                g = GEOM.get(obj[4], {"bars": [], "rads": []})
                segs.append({"type": "math", "page": obj[4] + 1,
                             "rect": [x0, round(obj[1] - pad, 1),
                                      x1, round(obj[3] + pad, 1)],
                             "tex": math_text(mc, g["bars"], g["rads"])})
        flush()
        if segs:
            result.append({"page": b["p"] + 1, "y": round(b["y0"], 1), "segs": segs,
                           "plain": "".join(x["t"] if x["type"] == "text" else " ▣ "
                                            for x in segs).strip(),
                           "text": "".join(x["t"] if x["type"] == "text"
                                           else x["tex"] for x in segs).strip()})

    # 본문 줄에 안 붙는 수식 = 독립 display. 같은 줄끼리만 묶는다.
    free.sort(key=lambda s: (s["p"], round(s["y0"], 1), s["x0"]))
    grp = []
    for m in free:
        placed = False
        for g in grp:
            if g[0]["p"] != m["p"]:
                continue
            gy0 = min(x["y0"] for x in g); gy1 = max(x["y1"] for x in g)
            # 세로로 겹치거나 살짝 아래(아래첨자)면 같은 식으로 본다
            if m["y0"] < gy1 + 6 and m["y1"] > gy0 - 6:
                g.append(m); placed = True
                break
        if not placed:
            grp.append([m])
    for g in grp:
        for bl in hmerge(g, gap=14.0):
            mc = [c for s in g for c in s["ch"]
                  if bl[0] - 0.5 <= c["x0"] and c["x1"] <= bl[2] + 0.5]
            gm = GEOM.get(bl[4], {"bars": [], "rads": []})
            tex = math_text(mc, gm["bars"], gm["rads"])
            result.append({"page": bl[4] + 1, "y": round(bl[1], 1),
                           "segs": [{"type": "math", "page": bl[4] + 1,
                                     "rect": [round(bl[0] - pad, 1), round(bl[1] - pad, 1),
                                              round(bl[2] + pad, 1), round(bl[3] + pad, 1)],
                                     "tex": tex}],
                           "plain": "▣", "text": tex})
    result.sort(key=lambda L: (L["page"], L["y"]))
    return result


# ── 메타 ────────────────────────────────────────────────
def meta_of(doc, spans, path):
    """헤더는 줄바꿈으로 끊긴다("답변 준비 권장" / "배분: ...").
    그래서 줄 단위가 아니라 **한 덩어리로 합쳐** 파싱한다."""
    head = [s for s in spans if s["p"] == 0 and s["y0"] < 145]
    lines = [nfc(x) for x in line_text(head)]
    blob = re.sub(r"\s+", " ", " ".join(lines))
    m = {"file": nfc(os.path.basename(path)), "pages": doc.page_count}

    t = re.search(r"(\d{4})학년도\s*(\S+?)\s*문제\s*(\d+)\s*·\s*(.+?)\s*(?:활용|출제|$)", blob)
    if t:
        m["year"], m["subject"] = int(t.group(1)), t.group(2)
        m["no"], m["title"] = int(t.group(3)), t.group(4).strip()

    u = re.search(r"활용\s*모집단위\(?([^)]*)\)?\s*[:：]\s*(.+?)(?:\s*\|\s*출제|$)", blob)
    if u:
        m["session"] = u.group(1).strip()
        m["units"] = [x.strip() for x in re.split(r"·", u.group(2)) if x.strip()]

    r = re.search(r"출제\s*범위\s*[:：]\s*(.+?)(?:\s*\|\s*답변|$)", blob)
    if r:
        cur = r.group(1).strip()
        m["curriculum"] = cur
        # 《과목》 단위로 쪼개 소제목 재료로 쓴다
        m["curriculum_parts"] = [x.strip(" ·") for x in re.findall(r"《[^》]+》[^《]*", cur)]

    b = re.search(r"권장\s*배분\s*[:：]?\s*(.+?)$", blob)
    if b:
        raw = b.group(1).strip()
        m["time_plan_raw"] = raw
        m["time_plan"] = [x.strip() for x in re.split(r"→", raw) if x.strip()]
        m["time_total"] = sum(int(x) for x in re.findall(r"(\d+)\s*분", raw))
    return m


# ── 절 분할 ──────────────────────────────────────────────
def split_sections(spans):
    """절 표제의 (page, y)를 찾아 스팬을 절별로 나눈다."""
    marks = []
    lines = []
    cur, cy, cp = [], None, None
    for s in sorted(spans, key=lambda s: (s["p"], round(s["y0"], 1), s["x0"])):
        if cy is None or s["p"] != cp or abs(s["y0"] - cy) > 4:
            if cur: lines.append(cur)
            cur, cy, cp = [s], s["y0"], s["p"]
        else:
            cur.append(s)
    if cur: lines.append(cur)

    for ln in lines:
        txt = nfc("".join(x["t"] for x in ln if not x["is_math"]))
        flat = re.sub(r"\s", "", txt)
        for key, pat in SECTIONS:
            if re.search(pat, flat):
                marks.append((ln[0]["p"], ln[0]["y0"], key))
                break
    marks.sort()
    out = {k: [] for k, _ in SECTIONS}
    if not marks:
        return out
    for s in spans:
        key = None
        for (p, y, k) in marks:
            if (s["p"], s["y0"]) >= (p, y - 1):
                key = k
            else:
                break
        if key:
            out[key].append(s)
    return out


# ── 수식 덩어리 자동 검출 ────────────────────────────────
def math_blocks(spans, gap_y=9, gap_x=42, min_w=60, min_spans=3):
    """KaTeX 스팬을 근접 병합해 '수식 한 덩어리'의 좌표를 만든다.
    이 좌표가 그대로 카드용 크롭 rect가 된다."""
    ms = [s for s in spans if s["is_math"]]
    ms.sort(key=lambda s: (s["p"], round(s["y0"], 1), s["x0"]))
    blocks = []
    for s in ms:
        placed = False
        for b in blocks:
            if b["p"] != s["p"]:
                continue
            if (s["y0"] < b["y1"] + gap_y and s["y1"] > b["y0"] - gap_y
                    and s["x0"] < b["x1"] + gap_x and s["x1"] > b["x0"] - gap_x):
                b["x0"] = min(b["x0"], s["x0"]); b["x1"] = max(b["x1"], s["x1"])
                b["y0"] = min(b["y0"], s["y0"]); b["y1"] = max(b["y1"], s["y1"])
                b["n"] += 1
                placed = True
                break
        if not placed:
            blocks.append(dict(p=s["p"], x0=s["x0"], x1=s["x1"],
                               y0=s["y0"], y1=s["y1"], n=1))
    # 병합 후 한 번 더 합치기 (연쇄 인접)
    changed = True
    while changed:
        changed = False
        for i in range(len(blocks)):
            for j in range(i + 1, len(blocks)):
                a, b = blocks[i], blocks[j]
                if a["p"] != b["p"]:
                    continue
                if (a["x0"] < b["x1"] + gap_x and a["x1"] > b["x0"] - gap_x
                        and a["y0"] < b["y1"] + gap_y and a["y1"] > b["y0"] - gap_y):
                    a["x0"] = min(a["x0"], b["x0"]); a["x1"] = max(a["x1"], b["x1"])
                    a["y0"] = min(a["y0"], b["y0"]); a["y1"] = max(a["y1"], b["y1"])
                    a["n"] += b["n"]
                    blocks.pop(j); changed = True
                    break
            if changed:
                break
    out = []
    for b in blocks:
        w, h = b["x1"] - b["x0"], b["y1"] - b["y0"]
        if w < min_w or b["n"] < min_spans:
            continue
        out.append(dict(page=b["p"] + 1, spans=b["n"],
                        rect=[round(b["x0"] - 5, 1), round(b["y0"] - 5, 1),
                              round(b["x1"] + 5, 1), round(b["y1"] + 5, 1)],
                        w=round(w, 1), h=round(h, 1),
                        display=w > 150 and h > 18))
    out.sort(key=lambda b: (b["page"], b["rect"][1]))
    return out


# ── 그림(도형) 검출 ──────────────────────────────────────
def figure_blocks(doc, min_parts=12, min_side=110, max_text_ratio=0.10):
    """벡터 드로잉이 몰린 영역 = 그래프·도형.

    세 번 고친 자리다. 실패했던 판별 기준을 기록해 둔다 —
      ① 페이지 전체 min/max  → 클리핑 rect가 페이지 밖(x>5000pt) 좌표를 갖고 있어 터짐
      ② 작은 획(<40pt)만 세기 → 그래프 곡선은 '큰 단일 path'라 통째로 걸러짐
      ③ 현재 기준: **섹션 배경 박스만 제외하고 나머지를 뭉친다.**
         이 교재는 절마다 둥근 사각형 박스를 쓰는데, 그건 '사각형 하나짜리 드로잉'이다.
         그래프는 곡선·눈금·점이 섞여 항목이 여럿이다.
    캡션 '[그림]'이 있으면 그 문항은 도형이 있다는 뜻이므로 검출 결과를 교차 확인한다.
    """
    figs = []
    for pi, page in enumerate(doc):
        W, H = page.rect.width, page.rect.height
        page_area = W * H
        rs = []
        for d in page.get_drawings():
            r = d["rect"]
            x0, y0 = max(0.0, r.x0), max(0.0, r.y0)
            x1, y1 = min(W, r.x1), min(H, r.y1)
            w, h = x1 - x0, y1 - y0
            if w <= 1 or h <= 1:
                continue
            items = d.get("items", [])
            # 섹션 배경 박스: 사각형 하나로 이루어졌고 면적이 크다
            if len(items) <= 2 and all(it[0] == "re" for it in items) and (w * h) > page_area * 0.02:
                continue
            if h < 2.5 and w > 80:              # 구분선·표 괘선
                continue
            rs.append([x0, y0, x1, y1])
        if len(rs) < min_parts:
            continue
        groups = []
        for r in rs:
            hit = None
            for g in groups:
                if (r[0] < g[2] + 24 and r[2] > g[0] - 24
                        and r[1] < g[3] + 24 and r[3] > g[1] - 24):
                    hit = g
                    break
            if hit:
                hit[0] = min(hit[0], r[0]); hit[1] = min(hit[1], r[1])
                hit[2] = max(hit[2], r[2]); hit[3] = max(hit[3], r[3])
                hit[4] += 1
            else:
                groups.append([r[0], r[1], r[2], r[3], 1])
        changed = True
        while changed:
            changed = False
            for a in range(len(groups)):
                for b in range(a + 1, len(groups)):
                    g, h2 = groups[a], groups[b]
                    if (g[0] < h2[2] + 24 and g[2] > h2[0] - 24
                            and g[1] < h2[3] + 24 and g[3] > h2[1] - 24):
                        g[0] = min(g[0], h2[0]); g[1] = min(g[1], h2[1])
                        g[2] = max(g[2], h2[2]); g[3] = max(g[3], h2[3])
                        g[4] += h2[4]
                        groups.pop(b); changed = True
                        break
                if changed:
                    break
        # 텍스트 밀도로 최종 판별 —
        # 그래프는 축 라벨 몇 개뿐이라 글자가 성기고, 절 배경 박스는 본문으로 꽉 차 있다.
        tspans = []
        for b in page.get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                for sp in l["spans"]:
                    if sp["text"].strip():
                        tspans.append(sp["bbox"])
        for g in groups:
            w, h = g[2] - g[0], g[3] - g[1]
            if w < min_side or h < min_side or g[4] < min_parts:
                continue
            area = w * h
            tarea = 0.0
            for (bx0, by0, bx1, by1) in tspans:
                ox = min(g[2], bx1) - max(g[0], bx0)
                oy = min(g[3], by1) - max(g[1], by0)
                if ox > 0 and oy > 0:
                    tarea += ox * oy
            ratio = tarea / area if area else 1.0
            if ratio > max_text_ratio:
                continue
            figs.append(dict(page=pi + 1, parts=g[4], text_ratio=round(ratio, 3),
                             rect=[round(g[0] - 12, 1), round(g[1] - 12, 1),
                                   round(g[2] + 12, 1), round(g[3] + 12, 1)],
                             w=round(w, 1), h=round(h, 1)))
    return figs


def key_ideas(sec_spans, maths=None):
    """⑦되돌아보기의 「핵심 아이디어 ①②③④」.
    대표 요구사항: 카드에 핵심 아이디어 3개를 각각 자세히 제시.
    수식이 섞인 자리는 크롭 좌표(math_ref)로 함께 돌려준다."""
    txt = nfc(" ".join(line_text(sec_spans)))
    m = re.search(r"핵심\s*아이디어\s*[:：]?\s*(.+?)(?:자주\s*하는\s*실수|교육과정\s*메모|연관\s*기출|$)", txt)
    if not m:
        return []
    parts = re.split(r"[①②③④⑤⑥⑦⑧⑨]", m.group(1))
    ideas = [re.sub(r"\s+", " ", p).strip(" ·").strip() for p in parts[1:] if p.strip()]

    # 이 절의 y 구간과 겹치는 수식 덩어리를 붙여 준다
    refs = []
    if maths and sec_spans:
        p0 = min(s["p"] for s in sec_spans); y0 = min(s["y0"] for s in sec_spans)
        y1 = max(s["y1"] for s in sec_spans)
        refs = [b for b in maths
                if b["page"] - 1 == p0 and b["rect"][3] >= y0 and b["rect"][1] <= y1]
    return [{"text": t, "math_refs": [r["rect"] for r in refs][:0] or []} for t in ideas] \
        if False else ideas


def common_mistakes(sec_spans):
    txt = nfc(" ".join(line_text(sec_spans)))
    m = re.search(r"자주\s*하는\s*실수\s*[:：]?\s*(.+?)(?:교육과정\s*메모|연관\s*기출|$)", txt)
    if not m:
        return []
    return [re.sub(r"\s+", " ", x).strip() for x in m.group(1).split("·") if x.strip()]


def penalty(sec_spans):
    """⑥ '이렇게 답하면 감점' 인용 + 해설."""
    lines = [nfc(x) for x in line_text(sec_spans)]
    i = next((k for k, l in enumerate(lines) if "감점" in l), None)
    if i is None:
        return {}
    tail = lines[i:]
    quoted = re.findall(r"[\"“]([^\"”]{10,})[\"”]", " ".join(tail))
    return {"quote": quoted[0] if quoted else "",
            "body": " ".join(tail[1:])[:600]}


def scenario(sec_spans):
    """⑤ 면접 답변 시나리오 — 대표 정의상 이게 '답'이다."""
    lines = [nfc(x) for x in line_text(sec_spans)]
    said = re.findall(r"[“\"]([^”\"]{15,})[”\"]", " ".join(lines))
    qa = []
    joined = " ".join(lines)
    for m in re.finditer(r"Q\.\s*[“\"]?(.+?)[”\"]?\s*A\.\s*[“\"]?(.+?)(?=Q\.|$)", joined):
        qa.append({"q": re.sub(r"\s+", " ", m.group(1)).strip()[:300],
                   "a": re.sub(r"\s+", " ", m.group(2)).strip()[:600]})
    return {"utterances": [re.sub(r"\s+", " ", s).strip() for s in said][:12],
            "followups": qa}


def glance(sec_spans):
    """②한눈에 보기는 2열 표다. 두 가지 함정이 있다(교차검증에서 잡힘) —
      ① y로만 줄을 묶으면 라벨 칸과 값 칸이 섞인다 → **x로 좌우를 가른다**
      ② 라벨이 셀 안에서 **세로 가운데 정렬**이라 값의 첫 줄보다 아래에 있다.
         (난이도 라벨 y=468인데 그 값은 y=459에서 시작)
         → 라벨 y의 **중간점을 셀 경계**로 삼는다.
      ③ 첫 행은 라벨이 값 끝에 붙어 나온다("…최대·최소핵심 주제") → 꼬리에서 떼어낸다.
    """
    if not sec_spans:
        return {}
    txt_spans = [s for s in sec_spans if not s["is_math"]]
    rows = to_lines(txt_spans)
    if not rows:
        return {}
    LABELS = [("핵심주제", "topic", "핵심 주제"),
              ("난이도", "level", "난이도"),
              ("한줄요약", "summary", "한 줄 요약")]

    # 라벨 y 찾기 (라벨은 값 칸보다 왼쪽에 있거나, 값 줄 끝에 붙어 있다)
    label_y = {}
    for row in rows:
        t = nfc("".join(x["t"] for x in row))
        flat = re.sub(r"\s", "", t)
        for flatlab, key, _ in LABELS:
            if flatlab in flat and key not in label_y:
                label_y[key] = min(x["y0"] for x in row)
    if len(label_y) < 2:
        return {}

    order = [k for _, k, _ in LABELS if k in label_y]
    ys = [label_y[k] for k in order]
    # 셀 경계 = 이웃 라벨 y의 중간점
    bounds = [-1e9] + [(ys[i] + ys[i + 1]) / 2 for i in range(len(ys) - 1)] + [1e9]

    # 값 칸의 x 하한: 라벨 줄 중 가장 왼쪽 x + 여유
    lefts = [min(x["x0"] for x in r) for r in rows
             if any(l in re.sub(r"\s", "", nfc("".join(x["t"] for x in r)))
                    for l, _, _ in LABELS)]
    split_x = (min(lefts) if lefts else 50) + 40

    out = {}
    for i, key in enumerate(order):
        parts = []
        for row in rows:
            y = min(x["y0"] for x in row)
            if not (bounds[i] <= y < bounds[i + 1]):
                continue
            keep = [x for x in row if x["x0"] >= split_x]
            if not keep:
                continue
            parts.append(nfc("".join(x["t"] for x in keep)))
        val = re.sub(r"\s+", " ", " ".join(parts)).strip()
        for _, _, disp in LABELS:            # 값 끝에 붙어 나온 라벨 제거
            val = re.sub(re.escape(disp) + r"\s*$", "", val).strip()
            val = re.sub(r"\s*" + re.escape(disp.replace(" ", "")) + r"\s*$", "", val).strip()
        out[key] = val
    return out


def steps(sec_spans):
    """Step 번호는 제목 뒤에 찍힌다("영역의 정체 · ...Step 1"). 어디에 있든 찾는다."""
    lines = [nfc(x) for x in line_text(sec_spans)]
    out, seen = [], set()
    for i, l in enumerate(lines):
        m = re.search(r"Step\s*(\d+)", l)
        if not m or "Step마다" in l:
            continue
        n = int(m.group(1))
        title = re.sub(r"Step\s*\d+", "", l).strip(" ·")
        # 본문 안의 "Step 1에서 얻은..." 같은 참조는 제목이 아니다.
        # 실제 표제는 번호가 줄 끝에 찍히고 길이가 짧다.
        if not title or len(title) > 60 or n in seen or not l.rstrip().endswith(m.group(0)):
            continue
        seen.add(n)
        goal = next((re.sub(r"^지금\s*하려는\s*것\s*[:：]\s*", "", x).strip()
                     for x in lines[i+1:i+5] if "지금 하려는 것" in x), "")
        out.append({"n": n, "title": title[:90], "goal": goal[:200]})
    return out


def figures_by_caption(doc, spans, max_up=380):
    """교재는 도형에 '[그림] …' 캡션을 단다. 그 캡션이 **결정적 앵커**다.

    기하 휴리스틱만으로는 절 배경 박스와 그래프를 안정적으로 가르지 못했다(4회 실패).
    캡션은 오검출이 없으므로 주 경로로 쓴다.

    위쪽 경계 주의 — '캡션 위 가장 가까운 글자'로 잡으면 안 된다.
    축 라벨도 글자라서 크롭이 납작하게 잘린다.
    **캡션 위쪽의 드로잉 범위**로 잡아야 그래프 전체가 들어온다.
    """
    out = []
    for pi, page in enumerate(doc):
        W, H = page.rect.width, page.rect.height
        rows = to_lines([s for s in spans if s["p"] == pi])
        draws = []
        for d in page.get_drawings():
            r = d["rect"]
            x0, y0 = max(0.0, r.x0), max(0.0, r.y0)
            x1, y1 = min(W, r.x1), min(H, r.y1)
            if x1 - x0 > 1 and y1 - y0 > 1:
                draws.append([x0, y0, x1, y1])
        for k, row in enumerate(rows):
            txt = nfc("".join(x["t"] for x in row))
            if "[그림]" not in txt:
                continue
            cap_y = min(x["y0"] for x in row)
            near = [d for d in draws if d[3] < cap_y - 1 and d[1] > cap_y - max_up]
            if not near:
                continue
            x0 = min(d[0] for d in near); x1 = max(d[2] for d in near)
            y0 = min(d[1] for d in near); y1 = max(d[3] for d in near)
            if (x1 - x0) < 80 or (y1 - y0) < 80:
                continue
            out.append(dict(page=pi + 1, source="caption",
                            caption=re.sub(r"\s+", " ", txt).strip()[:120],
                            rect=[round(max(0, x0 - 14), 1), round(max(0, y0 - 14), 1),
                                  round(min(W, x1 + 14), 1), round(min(H, cap_y - 2), 1)],
                            w=round(x1 - x0, 1), h=round(y1 - y0, 1)))
    return out


def extract(path):
    doc, spans = load(path)
    sec = split_sections(spans)
    m = meta_of(doc, spans, path)
    data = {
        "meta": m,
        "glance": glance(sec["glance"]),
        "first_impression": " ".join(line_text(sec["first"]))[:800],
        "steps": steps(sec["steps"]),
        "answer_script": scenario(sec["script"]),      # 대표 정의: 이것이 '답'
        "script_lines": segments(sec["script"]),       # 수식을 인라인 좌표로 되살린 판
        "problem_lines": segments(sec["problem"]),
        "review_lines": segments(sec["review"]),
        "penalty": penalty(sec["check"]),
        "key_ideas": key_ideas(sec["review"]),
        "common_mistakes": common_mistakes(sec["review"]),
        "math": math_blocks(spans),
        # 도형: 캡션 앵커가 주 경로, 기하 검출은 보조(캡션 없는 문항 대비)
        "figures": figures_by_caption(doc, spans) or figure_blocks(doc),
        "figures_geom": figure_blocks(doc),
    }
    return data


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("pdfs", nargs="+")
    ap.add_argument("--outdir", default="out")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    for p in a.pdfs:
        d = extract(p)
        m = d["meta"]
        name = "%d_%s_%02d" % (m.get("year", 0), m.get("subject", "?"), m.get("no", 0))
        with open(os.path.join(a.outdir, name + ".json"), "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        if not a.quiet:
            print("%-14s 아이디어 %d · Step %d · 발화 %d · 꼬리질문 %d · 수식 %d · 그림 %d"
                  % (name, len(d["key_ideas"]), len(d["steps"]),
                     len(d["answer_script"]["utterances"]),
                     len(d["answer_script"]["followups"]),
                     len(d["math"]), len(d["figures"])))

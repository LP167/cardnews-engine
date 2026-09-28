#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PDF에서 **카드에 그대로 얹을 수 있는** 수식 덩어리의 좌표를 찾는다.

  `extractor`의 math_blocks() 는 인라인 수식을 가로 42pt까지 이어 붙인다.
  본문 분석에는 맞지만 **크롭에는 못 쓴다** — 조각 사이의 한글이 사각형 안에
  통째로 딸려 들어와, 잘라 놓으면 수식이 아니라 문단이 된다.

  여기서 쓰는 기준은 하나다.
      **크롭할 수 있는 수식 = 그 사각형 안에 한글 본문이 한 조각도 없는 것.**

  이 기준 하나로 병합 폭까지 정해진다. 먼저 아주 넓게(90pt) 묶어 본다 —
  「(I) … (II)」처럼 한 줄에 나란히 선 형제 수식은 사이가 공백뿐이라 그대로 통과하고,
  문장 속 인라인 조각들은 사이에 한글이 있어 걸린다. 걸린 덩어리만 더 좁은 폭으로
  다시 묶는다. 사람이 손으로 하던 "이건 한 덩어리, 저건 따로" 판단이 이 규칙에서 나온다.

  수식 판별은 추출기와 같은 규칙(KaTeX 폰트, 한글 없는 Type3)을 쓴다.
"""
import re

MATH_FONT = re.compile(r"^KaTeX")
_T3 = re.compile(r"^Type3")
_HANGUL = re.compile(r"[가-힣ㄱ-ㅎㅏ-ㅣ]")

# 넓은 폭부터 시도한다. 한글이 끼면 다음(좁은) 폭으로 되돌린다.
GAPS_X = (90.0, 40.0, 13.0)
GAP_Y  = 8.0
PAD    = 5.0
MIN_W, MIN_H = 55.0, 13.0     # 이보다 작으면 카드에서 못 읽는다


def is_math(font, text):
    if MATH_FONT.match(font or ""):
        return True
    if _T3.match(font or ""):
        return not _HANGUL.search(text) and text.strip() not in ("✓", "·", "")
    return False


def _spans(doc):
    out = []
    for pi, page in enumerate(doc):
        for b in page.get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                for s in l.get("spans", []):
                    t = s.get("text", "")
                    if not t.strip():
                        continue
                    x0, y0, x1, y1 = s["bbox"]
                    out.append({"p": pi, "x0": x0, "y0": y0, "x1": x1, "y1": y1,
                                "t": t, "size": s.get("size", 0),
                                "math": is_math(s.get("font", ""), t)})
    return out


def body_pt(doc):
    """교재 본문 글자의 대표 크기(pt). 인라인 수식 크롭을 카드 본문 글자 크기에
       맞춰 줄일 때 기준이 된다 — 이게 없으면 수식만 혼자 크거나 작게 들어간다."""
    sz = sorted(s["size"] for s in _spans(doc)
                if not s["math"] and _HANGUL.search(s["t"]) and s["size"])
    return round(sz[len(sz) // 2], 2) if sz else 10.0


def _box(members):
    return {"p": members[0]["p"],
            "x0": min(s["x0"] for s in members), "y0": min(s["y0"] for s in members),
            "x1": max(s["x1"] for s in members), "y1": max(s["y1"] for s in members),
            "members": members}


def _cluster(ms, gap_x):
    """가까운 수식 스팬을 묶는다. 연쇄 병합(A~B, B~C ⇒ A~C)까지 처리한다."""
    groups = []
    for s in sorted(ms, key=lambda s: (s["p"], round(s["y0"], 1), s["x0"])):
        hit = None
        for g in groups:
            b = g["box"]
            if b["p"] != s["p"]:
                continue
            if (s["y0"] < b["y1"] + GAP_Y and s["y1"] > b["y0"] - GAP_Y
                    and s["x0"] < b["x1"] + gap_x and s["x1"] > b["x0"] - gap_x):
                hit = g; break
        if hit is None:
            groups.append({"box": _box([s])})
        else:
            hit["box"] = _box(hit["box"]["members"] + [s])
    changed = True
    while changed:
        changed = False
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                a, b = groups[i]["box"], groups[j]["box"]
                if a["p"] != b["p"]:
                    continue
                if (a["x0"] < b["x1"] + gap_x and a["x1"] > b["x0"] - gap_x
                        and a["y0"] < b["y1"] + GAP_Y and a["y1"] > b["y0"] - GAP_Y):
                    groups[i]["box"] = _box(a["members"] + b["members"])
                    groups.pop(j); changed = True; break
            if changed:
                break
    return [g["box"] for g in groups]


def _overlaps(r, s, eps=1.2):
    return (s["x0"] < r[2] - eps and s["x1"] > r[0] + eps
            and s["y0"] < r[3] - eps and s["y1"] > r[1] + eps)


def _rect(b, pad):
    return [b["x0"] - pad, b["y0"] - pad, b["x1"] + pad, b["y1"] + pad]


def _pure(b, txt, pad):
    """사각형 안에 한글 본문이 한 조각도 없는가."""
    r = _rect(b, pad)
    return not any(t["p"] == b["p"] and _overlaps(r, t) for t in txt)


def _refine(members, txt, pad, level=0):
    """넓은 폭으로 묶어 보고, 한글이 끼면 좁은 폭으로 되돌린다."""
    blocks = _cluster(members, GAPS_X[level])
    out, dropped = [], 0
    for b in blocks:
        if _pure(b, txt, pad):
            out.append(b)
        elif level + 1 < len(GAPS_X):
            o, d = _refine(b["members"], txt, pad, level + 1)
            out += o; dropped += d
        else:
            dropped += 1          # 어떤 폭으로도 한글을 못 떼면 크롭 불가
    return out, dropped


def find(doc, pad=PAD, min_w=MIN_W, min_h=MIN_H):
    """크롭 가능한 수식 덩어리 목록. 순수하지 않은(한글이 낀) 것은 버린다."""
    sp = _spans(doc)
    txt = [s for s in sp if not s["math"] and _HANGUL.search(s["t"])]
    blocks, dropped = _refine([s for s in sp if s["math"]], txt, pad)
    kept = []
    for b in blocks:
        w, h = b["x1"] - b["x0"], b["y1"] - b["y0"]
        if w < min_w or h < min_h:
            continue
        kept.append({"kind": "math", "page": b["p"] + 1,
                     "rect": [round(v, 1) for v in _rect(b, pad)],
                     "display": w > 150 and h > 18, "spans": len(b["members"]),
                     "peek": re.sub(r"\s+", " ", "".join(
                         s["t"] for s in sorted(b["members"],
                                                key=lambda s: (round(s["y0"], 1), s["x0"]))))[:60]})
    kept.sort(key=lambda k: (k["page"], k["rect"][1], k["rect"][0]))
    return kept, dropped


def figures(ex, doc=None, pad=PAD * 4, text_limit=3):
    """도형은 추출 JSON의 figures[]를 쓴다. 축 라벨이 bbox 밖으로 나가므로 여백을 크게.

    다만 figures 의 rect 는 믿을 게 못 된다 — 캡션으로 찾은 것이라 페이지 절반을
    통째로 잡아 오는 판이 있다(2017 수학 문제 4). 그대로 카드에 얹으면 본문이
    같이 축소돼 폰에서 6px가 된다. **이 프로젝트가 두 번 죽은 자리다.**
    사각형 안에 한글 본문 줄이 몇 개나 걸리는지 세어 의심스러우면 표시해 둔다."""
    txt = [s for s in _spans(doc) if not s["math"] and _HANGUL.search(s["t"])] if doc else []
    out = []
    for f in (ex.get("figures", []) + ex.get("figures_geom", [])):
        x0, y0, x1, y1 = f["rect"]
        rect = [round(x0 - pad, 1), round(y0 - pad, 1),
                round(x1 + pad, 1), round(y1 + pad, 1)]
        n = sum(1 for t in txt
                if t["p"] == f["page"] - 1 and _overlaps(rect, t))
        it = {"kind": "figure", "page": f["page"], "rect": rect, "display": True,
              "peek": re.sub(r"\s+", " ", f.get("caption") or "")[:60]}
        if n > text_limit:
            it["suspect"] = n      # 도형이 아니라 지면을 잘랐을 가능성
        out.append(it)
    out.sort(key=lambda k: (k["page"], k["rect"][1]))
    return out

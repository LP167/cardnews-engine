#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""새 문항의 작업 폴더를 만든다 — item.json + cards.json 초안 + 재료.md.

  추출 JSON에서 **기계가 확정할 수 있는 것은 전부 채운다.**
    01 표지 · 08 감점 · 09 착지 → 사실상 완성 (연도·문항·교육과정·모집단위·감점 인용)
    02 문제                    → 원문 그대로 (수식 크롭만 지정하면 됨)
    03~07 논증                 → 골격 슬롯 + steps/key_ideas 재료를 TODO에 붙여 둔다

  남는 일은 **논증 카드의 카피를 쓰는 것 하나**다. 그건 교재 해설을 읽고 재구성하는
  판단이라 결정론적 코드로 못 만든다 — 사람이나 LLM이 `재료.md`를 보고 채운다.

쓰기
  python3 scaffold.py 2017_수학_02
  python3 scaffold.py 2017_수학_02 --cards 9 --dir ../수학02
"""
import os, re, sys, json, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine import probsegs

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))          # <project-root>/
OUT_ROOT = os.path.join(ROOT, "03_카드뉴스")

# 9장 논리 골격 (카드_구성_기준_v1). 장수는 고정이 아니다 — 내용이 정한다.
SKELETON = [
    ("cover",     "표지",  None),
    ("prob",      "문제",  None),
    ("dark_img",  "번역",  "주어진 조건을 해석합니다"),
    ("paper",     "환원",  "구하는 것을 바꿉니다"),
    ("dark2",     "도구",  "이 문제를 여는 열쇠"),
    ("paper2",    "실행",  "논증합니다"),
    ("paper",     "검증",  "그게 정말 답입니까"),
    ("dark_wine", "감점",  None),
    ("outro",     "착지",  None),
]

TODO = "TODO"


def clean(s):
    return re.sub(r"\s+", " ", (s or "").strip())


def curriculum_lines(meta):
    """소제목 = 출제 교육과정. 한 줄이 너무 길면 ' · ' 에서 끊는다 —
       표지 헤드 아래는 두세 줄이 한계다."""
    parts = meta.get("curriculum_parts") or [meta.get("curriculum", "")]
    out = []
    for p in parts:
        p = clean(p)
        while len(p) > 46 and " · " in p:
            head, p = p.split(" · ", 1)
            out.append(head)
        if p:
            out.append(p)
    return "\n".join(out[:3])


def units_line(meta):
    """모집단위. 문항별 매핑([8-1, 8-2] …)이 붙어 오는 판이 있어 걷어낸다.
       표지 한 줄에 안 들어가면 앞의 몇 개만 두고 '외'로 접는다."""
    us = []
    for u in meta.get("units", []):
        u = clean(re.sub(r"\[[^\]]*\]", "", u)).strip(" /·,")
        if u:
            us.append(u)
    if not us:
        return ""
    line = " · ".join(us)
    if len(line) > 62:
        keep, n = [], 0
        for u in us:
            if n + len(u) > 52 and keep:
                break
            keep.append(u); n += len(u) + 3
        line = " · ".join(keep) + " 외 %d개 모집단위" % (len(us) - len(keep))
    return "출제 모집단위(%s) · %s" % (meta.get("session", ""), line)


def cover(meta):
    return {
        "type": "cover", "slot": "표지",
        "eyebrow": "EXAM_TRACK",
        "serif_num": "%02d" % meta.get("no", 0),
        # 표지 제목은 자체 작명이 아니라 **몇 년도 · 어떤 문제** (대표 피드백)
        "head": ["%d학년도" % meta.get("year", 0),
                 "%s 문제 %d" % (meta.get("subject", ""), meta.get("no", 0))],
        "sub": curriculum_lines(meta),
        "foot": units_line(meta),
    }


def prob(ex):
    """기출 원문 카드. **수식이 문장 속에 박혀 있으므로 세그먼트로 넘긴다** —
       문자열로 받으면 수식 자리가 ▣ 구멍으로 남는다."""
    no = ex.get("meta", {}).get("no", 0)
    rows = [r for r in probsegs.lines(ex) if probsegs.plain(r)]
    rows = [r for r in rows if not probsegs.plain(r).startswith("기출 문제")]

    # 소문항이 여럿인 문항이 많다(8-1 · 8-2 · 8-3 …). **한 편은 한 소문항만 다룬다** —
    # 전부 담으면 카드가 터져 폰에서 6px가 된다. 이 프로젝트가 두 번 죽은 자리다.
    qs = [i for i, r in enumerate(rows) if re.match(r"^\d+-\d+\.", probsegs.plain(r))]
    qi = qs[0] if qs else None
    nxt = qs[1] if len(qs) > 1 else len(rows)
    head_rows = rows[:qi] if qi is not None else rows[:1]
    tail_rows = rows[qi + 1:nxt] if qi is not None else []

    stem = probsegs.strip_head(head_rows[0], no) if head_rows else []
    # 본문 사이에 홀로 선 수식 줄 = 디스플레이 식. 카드의 그림 자리로 올린다.
    block, rest = None, []
    for r in head_rows[1:]:
        only_math = all("img" in sg for sg in r)
        if only_math and block is None and len(r) == 1:
            block = r[0]["img"]
        else:
            rest += r
    qno, question = TODO, []
    if qi is not None:
        r = list(rows[qi])
        m = re.match(r"^\s*(\d+-\d+\.)\s*(.*)$", r[0].get("t", "")) if "t" in r[0] else None
        if m:
            qno = m.group(1)
            r[0] = {"t": m.group(2)}
            if not m.group(2):
                r = r[1:]
        question = r

    c = {"type": "prob", "slot": "문제", "kick": "기출 문제 원문",
         "stem_segs": stem, "qno": qno, "question_segs": question,
         "dim": True}
    if block:
        c["img"] = block
        # 원문이 짧은 문항은 디스플레이 수식이 본문을 압도한다. 상한을 낮춰 잡는다.
        c["img_h"] = 150
    if rest:
        c["tail_segs"] = rest
    if tail_rows:
        c["after_segs"] = [sg for r in tail_rows for sg in r]
    if len(qs) > 1:
        c["_참고"] = ("이 문항은 소문항이 %d개다. 카드는 %s 하나만 담았다 — "
                      "나머지는 다음 편으로 나눈다." % (len(qs), c["qno"]))
    return c


def penalty(ex):
    p = ex.get("penalty") or {}
    q = clean(p.get("quote")) or TODO
    body = clean(p.get("body"))
    # body 앞머리에 quote가 통째로 반복돼 들어오는 판이 있다. 겹치면 떼어낸다.
    if body.startswith('"' + q) or body.startswith("“" + q):
        body = body[len(q) + 2:].strip()
    return {"type": "dark_wine", "slot": "감점", "kick": "이렇게 답하면 감점",
            "quote": q, "body": body or TODO}


def outro():
    return {
        "type": "outro", "slot": "착지", "kick": "BRAND SOURCE_PUBLICATION은",
        "head": ["합격자가 직접", "한 문항씩 풀었습니다"],
        "body": ("**EXAM_TRACK**\n"
                 "**EXAM_TRACK_2**\n"
                 "**EXAM_TRACK_3**\n\n"
                 "이 대학의 전형으로 합격한 선배들이 문제를 면접장에서 처음 봤을 때부터 "
                 "면접에서 말하는 방법까지 꼼꼼히 적어놨습니다."),
        "cta": ["팔로우하고 댓글에 “면접” 을 남겨 주시면",
                "LEAD_MAGNET 을 무료로 보내 드립니다"],
        "brand": "BRAND",
        "brand_sub": "PRODUCT_LINE",
    }


def argument_card(kind, slot, kick_tail, i, steps):
    """논증 카드 뼈대. 채울 자리를 TODO로 남기고 재료를 힌트로 붙인다."""
    st = steps[i] if i < len(steps) else {}
    kick = "%d · %s" % (i + 1, kick_tail)
    c = {"type": kind, "slot": slot, "kick": kick,
         "head": [TODO, TODO], "_재료": clean(st.get("title") or ""),
         "_목표": clean(st.get("goal") or "")}
    if kind == "dark_img":
        c.update({"img": TODO, "body": TODO})
    elif kind == "dark2":
        c.update({"img": TODO, "img2": TODO, "body": TODO})
    elif kind == "paper2":
        c.update({"img": TODO, "img2": TODO, "mid": TODO, "foot": TODO})
    else:                                   # paper
        c.update({"img": TODO, "foot": TODO})
    return c


def build_cards(ex, n):
    meta  = ex.get("meta", {})
    steps = ex.get("steps", [])
    plan  = list(SKELETON)
    # 장수는 고정이 아니다. 줄이면 논증 카드부터, 늘리면 논증 카드를 복제한다.
    body_idx = [i for i, (_, s, _) in enumerate(plan) if s in
                ("번역", "환원", "도구", "실행", "검증")]
    while len(plan) > n and body_idx:
        plan.pop(body_idx.pop())
    while len(plan) < n:
        plan.insert(plan.index(("paper", "검증", "그게 정말 답입니까")),
                    ("paper", "전개", "이어서 봅니다"))

    cards, k = [], 0
    for no, (kind, slot, kick) in enumerate(plan, 1):
        if   slot == "표지": c = cover(meta)
        elif slot == "문제": c = prob(ex)
        elif slot == "감점": c = penalty(ex)
        elif slot == "착지": c = outro()
        else:
            c = argument_card(kind, slot, kick, k, steps); k += 1
        c["no"] = no
        cards.append({"no": no, **{x: y for x, y in c.items() if x != "no"}})
    return {
        "meta": {
            "series": "SERIES_NAME",
            "issue": "%d학년도 %s 문제 %d" % (meta.get("year", 0), meta.get("subject", ""),
                                             meta.get("no", 0)),
            "title": "%d학년도 · %s 문제 %d" % (meta.get("year", 0), meta.get("subject", ""),
                                               meta.get("no", 0)),
            "skeleton": "표지·문제·번역·환원·도구·실행·검증·감점·착지 (카드_구성_기준_v1). "
                        "장수는 고정값이 아니다 — 5~11장 범위에서 내용이 정한다",
            "source": "BRAND · SOURCE_PUBLICATION",
            "render": "_엔진/make.py build <문항> → 이 폴더의 out",
            "brand": "BRAND",
        },
        "cards": cards,
    }


def materials(ex):
    """카피 작성자가 볼 재료 한 장. 교재 해설에서 뽑은 것만 담는다."""
    m, g = ex.get("meta", {}), ex.get("glance", {})
    L = ["# 카피 재료 — %d학년도 %s 문제 %d\n" % (m.get("year", 0), m.get("subject", ""),
                                                m.get("no", 0)),
         "> `extractor`가 SOURCE_PUBLICATION에서 뽑은 것만 적었다. **여기 없는 사실은 쓰지 않는다.**\n",
         "## 한눈에", "- 주제: %s" % clean(g.get("topic")),
         "- 난도: %s" % clean(g.get("level")), "- 요약: %s" % clean(g.get("summary")),
         "\n## 출제 정보", "- 교육과정: %s" % m.get("curriculum", ""),
         "- 모집단위(%s): %s" % (m.get("session", ""), " · ".join(m.get("units", []))),
         "- 권장 시간 배분: %s (총 %s분)" % (m.get("time_plan_raw", ""), m.get("time_total", "")),
         "\n## 풀이 단계 (steps)"]
    for s in ex.get("steps", []):
        L.append("%d. **%s** — %s" % (s.get("n", 0), clean(s.get("title")), clean(s.get("goal"))))
    L.append("\n## 핵심 아이디어 (key_ideas)")
    L += ["- %s" % clean(k) for k in ex.get("key_ideas", [])]
    L.append("\n## 자주 하는 실수 (common_mistakes)")
    L += ["- %s" % clean(k) for k in ex.get("common_mistakes", [])]
    L.append("\n## 첫인상")
    L.append(clean(ex.get("first_impression")))
    L.append("\n---\n")
    L.append("### ⚠ 주의 — 추출 본문에는 수식이 빠져 있다")
    L.append("추출기는 KaTeX 조판을 수식으로 분리하므로 위 문장들에서 **수식 자리가 비어 있다**")
    L.append("(예: \"좌석 세 개를 고르는 **가지**\"). 카드에 넣을 때는 `crops/_인덱스.png`에서")
    L.append("해당 수식 크롭을 골라 이미지로 넣거나, 원문 PDF를 보고 다시 조판한다.")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("item_id", help="추출 JSON 이름 (예: 2017_수학_02)")
    ap.add_argument("--dir", default=None, help="만들 폴더 (기본: 03_카드뉴스/<과목><번호>)")
    ap.add_argument("--cards", type=int, default=9, help="카드 장수 (5~11)")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    exp = os.path.join(ROOT, "extractor", "out", a.item_id + ".json")
    if not os.path.exists(exp):
        sys.exit("추출 JSON이 없다: %s\n먼저 extractor/extract.py 를 돌린다." % exp)
    ex = json.load(open(exp, encoding="utf-8"))
    m = ex.get("meta", {})

    d = a.dir or os.path.join(OUT_ROOT, "%s%02d" % (m.get("subject", "문항"), m.get("no", 0)))
    d = os.path.abspath(d)
    if os.path.exists(os.path.join(d, "cards.json")) and not a.force:
        sys.exit("이미 있다: %s (덮어쓰려면 --force)" % d)
    os.makedirs(d, exist_ok=True)

    rel = lambda p: os.path.relpath(p, d)
    pdf = os.path.join(ROOT, "assets", "%d_%s" % (m.get("year", 0), m.get("subject", "")),
                       m.get("file", ""))
    item = {"id": a.item_id,
            "extract": rel(exp),
            "pdf": rel(pdf),
            "cards": "cards.json", "crops": "crops", "out": "cards",
            "preview": "_전체_%d장.png" % a.cards,
            "logo": rel(os.path.join(ROOT, "assets", "로고", "logo_bg.png")),
            "fonts": rel(os.path.join(OUT_ROOT, "수학01", "fonts"))}
    json.dump(item, open(os.path.join(d, "item.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    json.dump(build_cards(ex, a.cards),
              open(os.path.join(d, "cards.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    open(os.path.join(d, "재료.md"), "w", encoding="utf-8").write(materials(ex))

    print("문항 폴더 생성 → %s" % os.path.relpath(d, ROOT))
    print("  item.json · cards.json(초안 %d장) · 재료.md" % a.cards)
    print("다음: python3 _엔진/make.py crops %s" % os.path.relpath(d, OUT_ROOT))


if __name__ == "__main__":
    main()

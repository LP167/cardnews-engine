#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""기출 원문의 **인라인 수식** 자리를 다룬다.

  `extractor`는 문제 원문을 세그먼트로 쪼개 둔다 —
      [{"type":"text","t":"문제 3. 수열 "},
       {"type":"math","page":1,"rect":[...]},
       {"type":"text","t":"을 다음과 같이 정의하자."}]
  즉 **수식이 문장 어디에 박혀 있는지 좌표까지 안다.** 그래서 문제 카드는
  통째로 자동으로 만들 수 있다. 이게 없으면 원문에 ▣ 구멍이 뚫린 채로 남는다.

  crop 이름은 `q01`, `q02` … 로 **읽는 순서**를 따른다. scaffold(카피 초안)와
  autocrop(크롭 생성)이 같은 규칙으로 세므로 둘이 따로 돌아도 이름이 어긋나지 않는다.
"""
import re

PREFIX = "q"


def walk(ex):
    """problem_lines 를 읽는 순서로 훑으며 (줄번호, 세그먼트, 수식이면 이름)을 낸다."""
    n = 0
    for li, L in enumerate(ex.get("problem_lines", [])):
        for s in L.get("segs", []):
            if s.get("type") == "math":
                n += 1
                yield li, s, "%s%02d" % (PREFIX, n)
            else:
                yield li, s, None


def crops(ex):
    """{이름: {page, rect}} — autocrop 이 잘라야 할 인라인 수식."""
    out = {}
    for _, s, name in walk(ex):
        if name:
            out[name] = {"kind": "inline", "page": s["page"], "rect": list(s["rect"]),
                         "display": False, "peek": "본문 인라인 수식"}
    return out


def lines(ex):
    """[[세그먼트…]] — 줄 단위. 세그먼트는 {"t": 글자} 또는 {"img": 크롭이름}."""
    out = {}
    for li, s, name in walk(ex):
        row = out.setdefault(li, [])
        if name:
            row.append({"img": name})
        else:
            t = s.get("t", "")
            if t:
                row.append({"t": t})
    return [out[k] for k in sorted(out)]


def plain(segs):
    """세그먼트 줄을 사람이 읽을 수 있는 문자열로 (검사·로그용)."""
    return re.sub(r"\s+", " ", "".join(s.get("t", "▣") for s in segs)).strip()


def strip_head(segs, no):
    """맨 앞의 '문제 3.' 같은 머리표를 뗀다 — 카드에는 문항 번호를 따로 단다."""
    if segs and "t" in segs[0]:
        segs = list(segs)
        segs[0] = {"t": re.sub(r"^\s*문제\s*%d\s*[.．]\s*" % no, "", segs[0]["t"])}
        if not segs[0]["t"]:
            segs = segs[1:]
    return segs

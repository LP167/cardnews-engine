#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""추출 JSON → 카드뉴스 9장 구성안 (대표 피드백 2026-08-28 반영)

대표 피드백
  01 표지  : 대표가 지은 제목 대신 **몇 년도 어떤 문제**를 크게, 소제목은 **교육과정**
  02 문제  : 원문 그대로
  03 (신설): 풀이 전에 "혼자 풀어보세요" — **답변 권장 배분 시간**을 근거로
  04~06    : **핵심 아이디어 3개**를 각각 자세히 + 이 문제 어디에 썼는지
  07~08    : 감점 → **답**. 여기서 '답'은 수능식 정답이 아니라
             **구술면접에서 말하는 것 전체**(⑤ 면접 답변 시나리오)
  09 착지  : 11문항이 아니라 **2017~2026 10개년 전량** 해설을 강조

  python3 plan.py out/2017_수학_01.json
  python3 plan.py out/*.json --outdir plans
"""
import os, re, json, argparse

SERIES = {"from": 2017, "to": 2026, "years": 10}


def slice_lines(lines, start_pat, end_pat):
    """세그먼트 줄 목록에서 구간을 잘라낸다."""
    import re
    a = b = None
    for i, L in enumerate(lines):
        t = L["plain"]
        if a is None and re.search(start_pat, t):
            a = i + 1
        elif a is not None and re.search(end_pat, t):
            b = i
            break
    if a is None:
        return []
    return [L for L in lines[a:b] if L["plain"].strip()]


def seg_len(L):
    """세그먼트 줄의 시각 분량. 수식 한 덩어리를 글자 4개로 친다."""
    n = 0
    for sg in L["segs"]:
        n += len(sg["t"]) if sg["type"] == "text" else 4
    return n


def pick_ideas(d, n=3):
    """핵심 아이디어에서 n개를 고르고, 각각이 어느 Step에서 쓰였는지 붙인다."""
    ideas = d.get("key_ideas", [])[:]
    steps = d.get("steps", [])

    def where(idea):
        words = [w for w in re.findall(r"[가-힣]{2,}", idea) if len(w) >= 2]
        best, score = None, 0
        for s in steps:
            hay = s["title"] + " " + s.get("goal", "")
            k = sum(1 for w in words if w in hay)
            if k > score:
                best, score = s, k
        if best:
            return "Step %d · %s" % (best["n"], best["title"][:40])
        return ""

    out = []
    for i, t in enumerate(ideas[:n], 1):
        out.append({"n": i, "idea": t, "used_at": where(t)})
    return out


def solve_prompt(d):
    """'혼자 풀어보세요' 카드 — 권장 배분 시간을 근거로."""
    m = d["meta"]
    plan = m.get("time_plan", [])
    total = m.get("time_total")
    return {
        "total": total,
        "steps": plan,
        "raw": m.get("time_plan_raw", ""),
    }


def answer_cards(d, max_lines=6):
    """대표 정의: '답' = 구술에서 말하는 것 전체."""
    sc = d.get("answer_script", {})
    utt = sc.get("utterances", [])
    body = [u for u in utt if len(u) > 25][:max_lines]
    fu = sc.get("followups", [])[:1]
    return {"utterances": body, "followup": fu[0] if fu else None}


# 카드 장수는 고정하지 않는다. 내용 분량이 정한다. (사용자 지시 2026-08-29)
# 다만 인스타 캐러셀은 10장을 넘기면 완주율이 급격히 떨어진다.
# 1080x1350 카드 한 장이 편하게 담는 본문은 대략 500~550자다(33px 본문 기준).
# 목표 장수는 9~12장. 문제 원문은 재조판하므로 대개 한 장에 들어간다.
BUDGET = {"problem": 620, "answer": 520}
N_IDEAS = 3          # 대표 지시: 핵심 아이디어 3개


def chunk(items, budget, key=lambda x: x):
    """분량 예산에 맞춰 항목을 카드 단위로 묶는다."""
    out, cur, n = [], [], 0
    for it in items:
        L = len(key(it))
        if cur and n + L > budget:
            out.append(cur); cur, n = [], 0
        cur.append(it); n += L
    if cur:
        out.append(cur)
    return out


def build(d):
    m = d["meta"]
    cards = []
    no = [0]
    def add(c):
        no[0] += 1
        c["no"] = no[0]
        cards.append(c)

    # 표지 — 대표가 지은 제목이 아니라 '몇 년도 어떤 문제' + 교육과정
    add({"role": "표지",
         "head": ["%d학년도 UNIV" % m["year"], "%s 문제 %d" % (m["subject"], m["no"])],
         "sub": m.get("curriculum", ""),
         "sub_parts": m.get("curriculum_parts", []),
         "foot": "%s · %s" % (m.get("session", ""), " · ".join(m.get("units", [])[:3]))})

    # 문제 원문 — 길면 나눈다
    plines = [L for L in d.get("problem_lines", []) if L["plain"].strip()]
    for grp in chunk(plines, BUDGET["problem"], key=lambda L: L["plain"]):
        add({"role": "문제", "kick": "기출 문제 · 원문", "lines": grp})

    # 혼자 풀어보세요 — 권장 배분 시간 근거
    sp = solve_prompt(d)
    add({"role": "혼자풀기", "kick": "먼저 직접 풀어보세요",
         "head": ["실제 시험에서는", "%d분입니다" % sp["total"]] if sp["total"]
                 else ["먼저 직접", "풀어보세요"],
         "time_steps": sp["steps"], "time_raw": sp["raw"],
         "note": "여기서 멈추고 풀어보신 뒤 넘기시면 훨씬 남습니다."})

    # 핵심 아이디어 — 교재에 있는 만큼(3~4개) 쓴다
    ideas = pick_ideas(d, n=N_IDEAS)
    for it in ideas:
        add({"role": "핵심아이디어",
             "kick": "핵심 아이디어 %d / %d" % (it["n"], len(ideas)),
             "idea": it["idea"], "used_at": it["used_at"]})

    # 답 — 구술에서 말하는 것 전체. **세그먼트로 싣는다**(문자열은 수식이 빠진다).
    sl = d.get("script_lines", [])
    body = slice_lines(sl, r"답변\s*뼈대", r"예상\s*꼬리질문") or \
           [L for L in sl if len(L["plain"]) > 25][:8]
    groups = chunk(body, BUDGET["answer"], key=lambda L: "x" * seg_len(L))
    for k, g in enumerate(groups):
        add({"role": "답", "part": [k + 1, len(groups)],
             "kick": "답 — 이렇게 말합니다" + (" %d/%d" % (k + 1, len(groups)) if len(groups) > 1 else ""),
             "note": "구술면접의 답은 숫자가 아니라 말하는 것 전체입니다." if k == 0 else "",
             "lines": g})

    # 꼬리질문 한 개 — 답의 연장
    fu = d.get("answer_script", {}).get("followups", [])
    if fu:
        ql = slice_lines(d.get("script_lines", []), r"예상\s*꼬리질문", r"^$")
        add({"role": "꼬리질문", "kick": "이어지는 질문",
             "q": fu[0]["q"], "a": fu[0]["a"][:400],
             "lines": ql[:4]})

    # 감점
    p = d.get("penalty", {})
    add({"role": "감점", "kick": "이렇게 답하면 감점",
         "quote": p.get("quote", ""),
         "mistakes": d.get("common_mistakes", [])[:3]})

    # 마무리 — 10개년 전량
    add({"role": "마무리", "kick": "%d~%d학년도" % (SERIES["from"], SERIES["to"]),
         "head": ["%d개년 기출 전량을" % SERIES["years"], "이렇게 풀어놨습니다"],
         "body": "한 문항도 빠짐없이 원문 · 핵심 아이디어 · 단계별 풀이 · "
                 "면접 답변 시나리오 · 예상 꼬리질문 · 감점 포인트까지.",
         "cta": "팔로우하고 댓글에 “수학” 을 남겨 주시면 전체 목차를 보내 드립니다"})
    return {"meta": m, "cards": cards}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("jsons", nargs="+")
    ap.add_argument("--outdir", default="plans")
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    for p in a.jsons:
        d = json.load(open(p, encoding="utf-8"))
        plan = build(d)
        name = os.path.splitext(os.path.basename(p))[0]
        json.dump(plan, open(os.path.join(a.outdir, name + "_plan.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        m = plan["meta"]
        roles = [c["role"] for c in plan["cards"]]
        print("%-14s %2d장  %s"
              % (name, len(plan["cards"]),
                 " ".join("%s%s" % (r[:2], "") for r in roles)))

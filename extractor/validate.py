#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""추출 결과 검증 게이트 (교차검증 지적 §5.4 반영)

자동화에서 가장 위험한 건 틀린 결과가 정상처럼 다음 단계로 흘러가는 것이다.
실제로 Step 0개·아이디어 0개가 예외 없이 통과한 적이 있다.

3단계로 본다 —
  L1 스키마   : 필수 필드가 있는가
  L2 상식     : 개수가 말이 되는가
  L3 교차정합 : 필드끼리 앞뒤가 맞는가

  python3 validate.py out/*.json
  python3 validate.py out/*.json --min 0.80    # 이 점수 미만이면 exit 1
"""
import sys, os, re, json, argparse

# (키, 설명, 필수)
L1 = [("meta.year", "학년도", True), ("meta.subject", "과목", True),
      ("meta.no", "문항번호", True), ("meta.curriculum", "출제 범위", True),
      ("meta.time_plan", "권장 시간 배분", True),
      ("key_ideas", "핵심 아이디어", True), ("steps", "Step", True),
      ("answer_script", "면접 답변 시나리오", True), ("penalty", "감점", True),
      ("glance", "한눈에 보기", False), ("math", "수식 블록", True)]


def get(d, path):
    cur = d
    for k in path.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


def check(d):
    errs, warns = [], []

    # ── L1 스키마 ──
    for path, label, req in L1:
        v = get(d, path)
        empty = v is None or (isinstance(v, (list, dict, str)) and len(v) == 0)
        if empty:
            (errs if req else warns).append("L1 %s 없음(%s)" % (label, path))

    # ── L2 상식 ──
    ki = get(d, "key_ideas") or []
    st = get(d, "steps") or []
    utt = (get(d, "answer_script") or {}).get("utterances") or []
    fu = (get(d, "answer_script") or {}).get("followups") or []
    mb = get(d, "math") or []
    if len(ki) < 3: errs.append("L2 핵심 아이디어 %d개 (3개 미만)" % len(ki))
    if len(st) < 2: errs.append("L2 Step %d개 (2개 미만)" % len(st))
    if len(utt) < 3: errs.append("L2 발화 %d개 (3개 미만)" % len(utt))
    if len(fu) < 1: warns.append("L2 꼬리질문 없음")
    if len(mb) < 5: warns.append("L2 수식 블록 %d개 (비정상적으로 적음)" % len(mb))
    tt = get(d, "meta.time_total")
    if not tt or tt < 5 or tt > 90: errs.append("L2 권장 시간 %s분 (범위 밖)" % tt)

    # ── L3 교차정합 ──
    g = get(d, "glance") or {}
    for k, label in [("topic", "핵심 주제"), ("level", "난이도"), ("summary", "한 줄 요약")]:
        v = (g.get(k) or "").strip()
        if not v:
            warns.append("L3 한눈에보기 '%s' 비어 있음" % label)
        elif k == "topic" and re.search(r"(중상|최상|^중\s*:|^상\s*:|난이도)", v):
            errs.append("L3 '핵심 주제'에 난이도 내용이 섞임 → 표 파싱 어긋남")
    nums = [s.get("n") for s in st]
    if nums and len(set(nums)) != len(nums):
        errs.append("L3 Step 번호 중복 %s" % nums)
    for c in ki:
        pass
    ml = get(d, "script_lines") or []
    if utt and not ml:
        errs.append("L3 발화는 있는데 인라인 세그먼트(script_lines)가 없음")
    # 수식이 텍스트에서 빠졌는지: 세그먼트에 math가 하나도 없으면 의심
    if ml and not any(sg["type"] == "math" for L in ml for sg in L["segs"]):
        warns.append("L3 시나리오에 인라인 수식이 하나도 없음")

    n = len(errs) + len(warns)
    score = 1.0 if n == 0 else max(0.0, 1.0 - (0.18 * len(errs) + 0.05 * len(warns)))
    return errs, warns, round(score, 2)


def verdict(score):
    if score >= 0.95: return "자동처리"
    if score >= 0.80: return "검토큐"
    return "사람확인"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("jsons", nargs="+")
    ap.add_argument("--min", type=float, default=0.0)
    a = ap.parse_args()
    worst, rows = 1.0, []
    for p in sorted(a.jsons):
        d = json.load(open(p, encoding="utf-8"))
        e, w, sc = check(d)
        worst = min(worst, sc)
        rows.append((os.path.basename(p), sc, e, w))
    print("%-22s %6s  %-8s %s" % ("파일", "점수", "판정", "지적"))
    print("─" * 92)
    for name, sc, e, w in rows:
        first = (e + w)[0] if (e + w) else "—"
        print("%-22s %6.2f  %-8s %s" % (name, sc, verdict(sc), first[:52]))
        for x in (e + w)[1:]:
            print("%-22s %6s  %-8s %s" % ("", "", "", x[:52]))
    print("─" * 92)
    print("최저 점수 %.2f · 판정 %s" % (worst, verdict(worst)))
    if worst < a.min:
        sys.exit(1)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""카드뉴스 파이프라인 — 한 줄 명령.

  new     <문항id>      추출 JSON → 작업 폴더(item.json · cards.json 초안 · 재료.md)
  crops   <문항폴더>     추출 좌표로 수식·도형 크롭 전부 자동 생성 + 썸네일 색인
  check   <문항폴더>     발행 전 검사 (TODO · 크롭 존재 · 골드 한 자리 · 금지어)
  build   <문항폴더>     렌더 → PNG + 전체 미리보기
  verify  <문항폴더>     지금 렌더 결과가 기존 산출물과 바이트 단위로 같은지 (회귀)
  list                  문항 폴더 전부

예)
  python3 make.py new 2017_수학_02
  python3 make.py crops 수학02
  python3 make.py check 수학02 && python3 make.py build 수학02
"""
import os, re, sys, json, shutil, tempfile, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
CARD_ROOT = os.path.abspath(os.path.join(HERE, ".."))       # 03_카드뉴스/
sys.path.insert(0, HERE)
from engine.item import Item, sha

# DESIGN.md §Do's and Don'ts — 카드에 절대 못 들어가는 것
BANNED = [(r"\d+\s*만\s*원|\d{2,3},\d{3}\s*원", "가격"),
          (r"합격률|커트라인|컷트라인", "합격률·커트라인"),
          (r"마감\s*임박|선착순", "마감 임박"),
          (r"[\U0001F300-\U0001FAFF☀-➿]", "이모지"),
          (r"LEGACY_BRAND", "옛 브랜드명")]


def resolve(name):
    """문항 폴더 이름 또는 경로를 받는다."""
    for cand in (name, os.path.join(CARD_ROOT, name)):
        if os.path.exists(os.path.join(cand, "item.json")):
            return os.path.abspath(cand)
    sys.exit("문항 폴더를 못 찾겠다: %s  (`make.py list` 로 확인)" % name)


def cmd_list(_):
    print("문항 폴더 (%s)" % CARD_ROOT)
    for d in sorted(os.listdir(CARD_ROOT)):
        p = os.path.join(CARD_ROOT, d)
        if os.path.exists(os.path.join(p, "item.json")):
            it = Item(p)
            n = len(it.spec()["cards"])
            out = it.path("out")
            done = len([f for f in os.listdir(out) if f.endswith(".png")]) if os.path.isdir(out) else 0
            print("  %-12s %s  카드 %d장 · 렌더 %d장" % (d, it.id, n, done))


def cmd_new(args):
    subprocess.run([sys.executable, os.path.join(HERE, "scaffold.py")] + args, check=False)


def cmd_crops(args):
    d = resolve(args[0])
    subprocess.run([sys.executable, os.path.join(HERE, "autocrop.py"), d] + args[1:], check=False)


def cmd_check(args):
    it = Item(resolve(args[0]))
    spec = it.spec()
    cards = spec["cards"]
    crops = it.path("crops")
    have = {os.path.splitext(f)[0] for f in os.listdir(crops)} if os.path.isdir(crops) else set()
    mp = os.path.join(crops, "crops.json")
    man = json.load(open(mp, encoding="utf-8")).get("crops", {}) if os.path.exists(mp) else {}
    errs, warns = [], []
    from engine import render as R
    R.add_font_dir(it.path("fonts"))

    if not (5 <= len(cards) <= 11):
        warns.append("카드가 %d장이다. 권장 범위는 5~11장" % len(cards))

    for c in cards:
        tag = "%02d(%s)" % (c["no"], c.get("slot", c["type"]))
        blob = json.dumps(c, ensure_ascii=False)
        if "TODO" in blob:
            errs.append("%s 아직 TODO가 남아 있다" % tag)
        for k in ("img", "img2", "big_img"):
            if c.get(k) and c[k] != "TODO" and c[k] not in have:
                errs.append("%s %s=\"%s\" 크롭이 없다" % (tag, k, c[k]))
            elif c.get(k) and man.get(c[k], {}).get("suspect"):
                errs.append("%s %s=\"%s\" 는 지면을 통째로 자른 크롭이다 (한글 %d조각). "
                            "폰에서 본문이 6px가 된다" % (tag, k, c[k], man[c[k]]["suspect"]))
        g = c.get("gold")
        if g and g not in ("img", "img2", "big_img"):
            errs.append("%s gold=\"%s\" 는 이미지 키가 아니다" % (tag, g))
        if g and not c.get(g):
            errs.append("%s gold=\"%s\" 인데 그 자리에 이미지가 없다" % (tag, g))
        for pat, what in BANNED:
            if re.search(pat, blob):
                errs.append("%s 금지 표현: %s" % (tag, what))
        for key in ("_재료", "_목표"):
            if key in c:
                warns.append("%s 스캐폴드 힌트 %s 가 남아 있다 (지워도 렌더에는 영향 없음)" % (tag, key))

    # 실제로 그려 보고 내용이 지면을 넘치는지 잰다. 카피 길이는 사람이 눈으로
    # 못 가늠한다 — 이 프로젝트가 두 번 죽은 자리가 "폰에서 6px"였다.
    #
    # 임계값은 **확정된 기준본(수학01)의 실측치**에서 잡았다. 그 9장은 대표 확인을
    # 거친 판이므로 전부 정상이어야 한다 — 최소 364(감점) · 최대 1153(도구·렌즈 그림).
    # 기준을 여기보다 좁게 잡으면 통과해야 할 판이 걸린다.
    if not errs:
        try:
            import numpy as np
            rd = it.renderer()
            for c in cards:
                im = rd.card(c)
                a = np.asarray(im.convert("L")).astype(int)
                rows = np.where(a.max(axis=1) > 60)[0]
                rows = rows[(rows > 12) & (rows < 1250)]
                if not len(rows):
                    continue
                h = int(rows.max() - rows.min())
                tag = "%02d(%s)" % (c["no"], c.get("slot", c["type"]))
                if h > 1200:
                    errs.append("%s 내용이 지면을 넘친다 (%dpx / 한계 1200). 카피를 줄이거나 카드를 나눈다" % (tag, h))
                elif h > 1153:
                    warns.append("%s 기준본 최대(1153px)보다 빽빽하다 (%dpx). 폰에서 읽히는지 확인" % (tag, h))
                elif h < 340:
                    warns.append("%s 기준본 최소(364px)보다 성기다 (%dpx). 앞뒤 카드와 합칠지 본다" % (tag, h))
        except ImportError:
            warns.append("numpy 가 없어 지면 넘침 검사를 건너뛰었다")

    # 수식 크롭이 얼마나 줄어들어 얹히는지 잰다. 카드 폭에 맞추느라 지나치게 줄면
    # 폰에서 뭉갠다 — README_v3 가 "3.0px/pt면 뭉갠다"고 적어 둔 그 자리다.
    # 하한은 기준본 수학01의 실측 최저에서 잡았다: 수식 2.5 · 도형 1.7 px/pt.
    from PIL import Image as _Im
    LIM = {"prob": [("img", R.CW, 230)], "dark_img": [("img", R.CW - R.PAD * 2, 260)],
           "paper": [("img", R.CW, 900), ("img2", R.CW, 210), ("big_img", 600, 170)],
           "dark2": [("img", R.CW - R.PAD * 2, 150), ("img2", R.CW - R.PAD * 2, 520)],
           "paper2": [("img", R.CW, 132), ("img2", R.CW, 132)]}
    if not errs:
        rd2 = it.renderer()
        dpi = rd2.crops.dpi
        for c in cards:
            tag = "%02d(%s)" % (c["no"], c.get("slot", c["type"]))
            for key, mw, mh in LIM.get(c["type"], []):
                nm = c.get(key)
                if not nm or nm not in have:
                    continue
                src = _Im.open(rd2.crops.path(nm)).width
                ratio = rd2.img_for(c, key, mw, mh).width / src * (dpi / 72.0)
                floor = 1.7 if rd2.crops.is_figure(nm) else 2.5
                if ratio < floor:
                    errs.append("%s %s=\"%s\" 가 %.1fpx/pt 로 줄어든다 (하한 %.1f). "
                                "가장 넓은 공백에서 둘로 잘라 쌓는다 — item.json 의 crops_extra"
                                % (tag, key, nm, ratio, floor))

    # 세리프로 그리는 자리(헤드라인·인용)에 없는 글자가 있으면 두부(□)가 된다.
    # Noto Serif KR 에는 √ ≤ ≥ ∴ α β 가 없다 — DESIGN.md 「함정」.
    for c in cards:
        tag = "%02d(%s)" % (c["no"], c.get("slot", c["type"]))
        serif = " ".join(c.get("head", []) or []) + " " + (c.get("quote") or "")
        miss = R.missing_glyphs(serif, "NotoSerifKR-Regular")
        if miss:
            errs.append("%s 세리프에 없는 글자 %s — 두부(□)로 나온다. 헤드·인용에서 뺀다"
                        % (tag, " ".join(miss)))
        sans = " ".join(str(v) for k, v in c.items()
                        if k in ("body", "foot", "mid", "sub", "kick", "stem",
                                 "question", "after", "tail") and isinstance(v, str))
        miss = R.missing_glyphs(sans, "Regular")
        if miss:
            warns.append("%s 본문 폰트에 없는 글자 %s" % (tag, " ".join(miss)))

    golds = [c["no"] for c in cards if c.get("gold")]
    if not golds:
        warns.append("골드 강조가 한 자리도 없다. 어느 줄이 결론인지 안 보인다")
    if spec.get("meta", {}).get("brand") not in (None, "BRAND"):
        errs.append("meta.brand 가 BRAND가 아니다")

    for w in warns: print("  경고  %s" % w)
    for e in errs:  print("  오류  %s" % e)
    if errs:
        print("\n검사 실패 — 오류 %d건" % len(errs)); sys.exit(1)
    print("검사 통과 · 카드 %d장 · 골드 %s번" % (len(cards), ", ".join(map(str, golds)) or "없음"))


def cmd_build(args):
    it = Item(resolve(args[0]))
    it.build()


def cmd_verify(args):
    """엔진이 기존 산출물을 바이트 단위로 재현하는지. 회귀의 마지막 방어선이다."""
    it = Item(resolve(args[0]))
    cur = it.path("out")
    if not os.path.isdir(cur):
        sys.exit("비교할 기존 산출물이 없다: %s" % cur)
    tmp = tempfile.mkdtemp(prefix="cardnews_verify_")
    try:
        it.build(outdir=tmp, preview=False, quiet=True)
        ok = bad = miss = 0
        for f in sorted(os.listdir(tmp)):
            a, b = os.path.join(tmp, f), os.path.join(cur, f)
            if not os.path.exists(b):
                print("  없음  %s (기존 산출물에 해당 파일 없음)" % f); miss += 1
            elif sha(a) == sha(b):
                print("  일치  %s" % f); ok += 1
            else:
                print("  다름  %s" % f); bad += 1
        print("\n일치 %d · 다름 %d · 없음 %d" % (ok, bad, miss))
        sys.exit(1 if (bad or miss) else 0)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


CMDS = {"list": cmd_list, "new": cmd_new, "crops": cmd_crops,
        "check": cmd_check, "build": cmd_build, "verify": cmd_verify}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in CMDS:
        print(__doc__); sys.exit(0 if len(sys.argv) < 2 else 2)
    CMDS[sys.argv[1]](sys.argv[2:])

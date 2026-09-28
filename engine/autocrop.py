#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""수식·도형 크롭을 전부 자동 생성한다. 사람이 좌표를 찾지 않는다.

  이 프로젝트에서 손이 가장 많이 가던 자리가 크롭 좌표였다 — 문항마다 PDF를 열고
  눈으로 rect를 찾아 표를 다시 쓰는 일. PDF가 KaTeX 조판이라 수식 스팬을 폰트로
  가려낼 수 있고(`engine/mathcrop.py`), **사각형 안에 한글이 없는 덩어리만** 남기면
  그대로 카드에 얹을 수 있는 크롭이 된다.

산출물 (crops/)
  m01.png … mNN.png   수식 (읽는 순서)
  f01.png …           도형 (추출 JSON의 figures)
  crops.json          매니페스트 — 이름 → kind(math|figure) · page · rect · 픽셀크기
  _인덱스.png          썸네일 색인. **카피 쓸 때 이 한 장만 보면 된다**

쓰기
  python3 autocrop.py <문항폴더> [--dpi 400] [--pad 5]
"""
import os, sys, json, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine.item import Item
from engine import render as R
from engine import mathcrop
from engine import probsegs

try:
    import pymupdf
except ImportError:
    import fitz as pymupdf
from PIL import Image, ImageDraw


def cut(doc, spec, outdir, dpi):
    os.makedirs(outdir, exist_ok=True)
    for name, it in spec.items():
        pg = doc[it["page"] - 1]
        rect = pymupdf.Rect(*it["rect"]) & pg.rect        # 지면 밖으로 나가지 않게
        pm = pg.get_pixmap(clip=rect, dpi=dpi)
        pm.save(os.path.join(outdir, "%s.png" % name))
        it["px"] = [pm.width, pm.height]
    return spec


def index_sheet(spec, outdir, cols=5, cell=320):
    """썸네일 색인. 카피 작성자는 여기서 `m07` 처럼 이름만 골라 카드에 적는다."""
    names = list(spec.keys())
    if not names:
        return None
    rows = (len(names) + cols - 1) // cols
    pad, lab = 16, 34
    sheet = Image.new("RGB", (cols * (cell + pad) + pad,
                              rows * (cell + pad + lab) + pad), (24, 18, 20))
    d = ImageDraw.Draw(sheet)
    f, fs = R.F("Bold", 24), R.F("Regular", 20)
    for i, name in enumerate(names):
        im = Image.open(os.path.join(outdir, "%s.png" % name)).convert("RGB")
        r = min(cell / im.width, (cell - 40) / im.height, 1.0)
        im = im.resize((max(1, int(im.width * r)), max(1, int(im.height * r))), Image.LANCZOS)
        cx = pad + (i % cols) * (cell + pad)
        cy = pad + (i // cols) * (cell + pad + lab)
        box = Image.new("RGB", (cell, cell - 40), (245, 243, 239))
        box.paste(im, ((cell - im.width) // 2, ((cell - 40) - im.height) // 2))
        sheet.paste(box, (cx, cy))
        it = spec[name]
        kind = {"figure": "도형", "inline": "원문 인라인"}.get(
            it["kind"], "큰수식" if it.get("display") else "작은수식")
        d.text((cx, cy + cell - 34), "%s   p%d · %s" % (name, it["page"], kind),
               font=f, fill=(218, 186, 101))
        d.text((cx, cy + cell - 6), "%dx%d px" % tuple(it["px"]), font=fs, fill=(140, 130, 120))
    p = os.path.join(outdir, "_인덱스.png")
    sheet.save(p)
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("item", help="문항 폴더 (item.json 이 있는 곳)")
    ap.add_argument("--dpi", type=int, default=400)
    ap.add_argument("--pad", type=float, default=mathcrop.PAD)
    a = ap.parse_args()

    it = Item(a.item)
    pdf = it.path("pdf")
    if not pdf or not os.path.exists(pdf):
        sys.exit("소스 PDF가 없다: %s" % pdf)
    doc = pymupdf.open(pdf)

    ex = it.extract() or {}
    maths, dropped = mathcrop.find(doc, pad=a.pad)
    figs = mathcrop.figures(ex, doc)
    spec = {}
    for i, m in enumerate(maths, 1):
        spec["m%02d" % i] = m
    for i, g in enumerate(figs, 1):
        spec["f%02d" % i] = g
    # 기출 원문 속 인라인 수식 — 문제 카드를 통째로 자동 조판하기 위한 것.
    # 이름(q01…)은 scaffold 와 같은 규칙으로 센다.
    spec.update(probsegs.crops(ex))
    # 손으로 잡아 둔 크롭이 있으면 덮어쓴다 — 자동이 못 잡는 자리(한 줄을 둘로
    # 쪼개야 하는 긴 수식 등)를 위한 문. 없으면 전부 자동이다.
    for name, ov in (it.cfg.get("crops_extra") or {}).items():
        spec[name] = {"kind": ov.get("kind", "math"), "page": ov["page"],
                      "display": True, "rect": ov["rect"], "manual": True,
                      "peek": ov.get("peek", "")}

    outdir = it.path("crops")
    spec = cut(doc, spec, outdir, a.dpi)
    json.dump({"dpi": a.dpi, "pad": a.pad, "body_pt": mathcrop.body_pt(doc),
               "note": "autocrop.py 자동 생성. 사각형 안에 한글이 걸리는 덩어리는 버렸다. "
                       "q## 는 기출 원문 속 인라인 수식이고 body_pt 는 교재 본문 글자 크기다.",
               "crops": spec},
              open(os.path.join(outdir, "crops.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    idx = index_sheet(spec, outdir)

    cnt = lambda k: sum(1 for v in spec.values() if v["kind"] == k)
    print("크롭 %d개 (수식 %d · 도형 %d · 원문 인라인 %d) → %s"
          % (len(spec), cnt("math"), cnt("figure"), cnt("inline"),
             os.path.relpath(outdir, it.dir)))
    if dropped:
        print("  · 한글이 섞여 크롭 불가로 버린 덩어리 %d개" % dropped)
    for name, v in spec.items():
        if v.get("suspect"):
            print("  ⚠ %s 는 도형이 아니라 지면을 잘랐을 수 있다 (한글 %d조각 포함). "
                  "카드에 쓰기 전에 눈으로 확인한다" % (name, v["suspect"]))
    if idx:
        print("색인 → %s" % os.path.relpath(idx, it.dir))


if __name__ == "__main__":
    main()

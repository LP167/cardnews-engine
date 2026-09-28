#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""문항 하나(= 카드뉴스 한 편)의 작업 디렉터리를 다룬다.

문항 폴더에는 `item.json` 하나가 있고, 나머지 경로는 전부 거기서 나온다.
경로가 코드에 박히지 않으므로 문항을 늘려도 스크립트를 복사하지 않는다.
"""
import os, json, hashlib
from . import render as R

DEFAULTS = {
    "cards":   "cards.json",
    "crops":   "crops",
    "out":     "cards",
    "preview": "_전체_미리보기.png",
    "fonts":   "fonts",
    "logo":    "../../assets/로고/logo_bg.png",
}


class Item:
    def __init__(self, dirpath):
        self.dir = os.path.abspath(dirpath)
        p = os.path.join(self.dir, "item.json")
        if not os.path.exists(p):
            raise FileNotFoundError("item.json 이 없다: %s" % self.dir)
        self.cfg = dict(DEFAULTS)
        self.cfg.update(json.load(open(p, encoding="utf-8")))
        self.id = self.cfg.get("id", os.path.basename(self.dir))

    def path(self, key):
        v = self.cfg.get(key)
        return None if not v else os.path.normpath(os.path.join(self.dir, v))

    # ── 입력 ──────────────────────────────────────────
    def spec(self):
        return json.load(open(self.path("cards"), encoding="utf-8"))

    def extract(self):
        p = self.path("extract")
        return json.load(open(p, encoding="utf-8")) if p and os.path.exists(p) else None

    def renderer(self):
        R.add_font_dir(self.path("fonts"))
        crops = R.Crops(self.path("crops"))
        return R.Renderer(crops, self.path("logo"))

    # ── 렌더 ──────────────────────────────────────────
    def build(self, outdir=None, preview=True, quiet=False):
        spec  = self.spec()
        cards = spec["cards"]
        out   = outdir or self.path("out")
        os.makedirs(out, exist_ok=True)
        rd = self.renderer()
        paths, labels = [], []
        for c in cards:
            p = os.path.join(out, "%02d.png" % c["no"])
            rd.card(c).save(p)
            paths.append(p); labels.append("%02d  %s" % (c["no"], c["type"]))
            if not quiet:
                print("  %02d.png  %-9s %s" % (c["no"], c["type"], c.get("slot", "")))
        if preview and self.path("preview"):
            R.contact_sheet(paths, labels).save(self.path("preview"))
        if not quiet:
            print("완료 · %d장 → %s" % (len(cards), os.path.relpath(out, self.dir)))
        return paths


def sha(p):
    return hashlib.sha1(open(p, "rb").read()).hexdigest()

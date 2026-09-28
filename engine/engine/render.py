#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BRAND 카드뉴스 렌더 코어 — 문항에 종속되지 않는다.

  DESIGN.md v2.0 「지면 통일판」의 구현체다.
  · 지면은 잉크 하나. 상단 룰은 전 카드 골드
  · 강조는 골드 하나, 카드당 한 자리 (카드의 "gold" 필드가 지정한다)
  · 로고는 9장 전부 우하단 고정
  · 수식 크롭은 흑백 반전해 지면에 직접, 도형 크롭만 종이판 위에

수학01/render_samecolor.py + render_v3.py 를 문항 인자를 받도록 일반화한 것이며,
같은 입력에 대해 **바이트 단위로 같은 결과**를 내는 것이 이 모듈의 계약이다.
회귀 검증: `python3 _엔진/make.py verify 수학01`
"""
import os, re, json
from PIL import Image, ImageDraw, ImageFont, ImageOps

W, H = 1080, 1350

# ── 팔레트 (client brand site, sampled) ───────────────────────
INK       = (14, 8, 9)
INK_800   = (26, 16, 19)
GOLD      = (218, 186, 101)
GOLD_SOFT = (234, 215, 160)
GOLD_RULE = (60, 46, 30)
N100      = (245, 245, 245)
N300      = (212, 212, 212)
N400      = (163, 163, 163)
N500      = (115, 115, 115)
PAPER     = (245, 243, 239)
HL_A      = 150

# ── 그리드 (4px 기본 단위) ──────────────────────────────
M   = 84
CW  = W - M * 2
PAD = 26
SP  = {"xxs": 8, "xs": 16, "sm": 24, "md": 32, "lg": 48, "xl": 64, "xxl": 92, "sec": 96}
RAD = {"sm": 8, "md": 12, "lg": 16, "xl": 24}
TRK_DISPLAY = -1.8
TRK_KICKER  = 3.4


# ── 폰트 ────────────────────────────────────────────────
# 맥의 ~/Library/Fonts를 먼저 본다. 맥이 아닌 곳에서도 죽지 않도록 저장소 안의
# 사본까지 훑고, 없는 굵기는 가장 가까운 굵기로 대체한다.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
FONT_DIRS = [os.path.expanduser("~/Library/Fonts"),
             os.path.join(_HERE, "..", "fonts"),
             os.path.join(_ROOT, "03_카드뉴스", "수학01", "fonts"),
             os.path.join(_ROOT, "_아카이브_20260827", "02_카드뉴스_렌더",
                          "카드뉴스_01", "out", "fonts")]
NEAR = {"Thin": ["Thin", "Light", "Regular"], "Light": ["Light", "Regular"],
        "Regular": ["Regular", "Medium"], "Medium": ["Medium", "Regular", "SemiBold"],
        "SemiBold": ["SemiBold", "Bold", "Medium"], "Bold": ["Bold", "SemiBold", "ExtraBold"],
        "ExtraBold": ["ExtraBold", "Bold"], "Black": ["Black", "ExtraBold", "Bold"]}
_fc = {}

def add_font_dir(d):
    """문항 폴더의 fonts/ 를 탐색 경로 맨 앞(시스템 다음)에 끼운다."""
    if d and os.path.isdir(d) and d not in FONT_DIRS:
        FONT_DIRS.insert(1, d)

def F(name, size):
    k = (name, size)
    if k in _fc: return _fc[k]
    cands = ["Pretendard-%s" % w for w in NEAR[name]] if name in NEAR else [name]
    for stem in cands:
        for d in FONT_DIRS:
            for p in (os.path.join(d, stem + ".ttf"),
                      os.path.join(d, stem.split("-")[-1] + ".ttf")):
                if os.path.exists(p):
                    _fc[k] = ImageFont.truetype(p, size); return _fc[k]
    raise FileNotFoundError("폰트 없음: %s (탐색 %s)" % (name, FONT_DIRS))

def SERIF(size, bold=False):
    """디스플레이 기본은 Regular. Bold는 인용에만."""
    return F("NotoSerifKR-%s" % ("Bold" if bold else "Regular"), size)

def BODONI(size):
    return F("BodoniModa-Bold", size)


# ── 텍스트 ──────────────────────────────────────────────
def tw(d, t, f):
    return d.textbbox((0, 0), t, font=f)[2]

def dtext(d, xy, t, f, fill, trk=0):
    """자간을 적용해 그린다. PIL에는 letter-spacing이 없어 글자 단위로 그린다."""
    if not trk:
        d.text(xy, t, font=f, fill=fill); return
    x, y = xy
    for ch in t:
        d.text((x, y), ch, font=f, fill=fill)
        x += d.textlength(ch, font=f) + trk

def wrap(d, t, f, mx):
    out, cur = [], ""
    for wd in t.split(" "):
        c = (cur + " " + wd).strip()
        if tw(d, c, f) <= mx or not cur: cur = c
        else: out.append(cur); cur = wd
    if cur: out.append(cur)
    return out

TOK = re.compile(r"(\*\*.+?\*\*|==.+?==)")
def rich(d, x, y, text, size, col, hi, mx, lh):
    """**볼드** / ==하이라이트== 인라인 마크업."""
    for para in text.split("\n"):
        if not para.strip(): y += lh // 2; continue
        line, cx = [], 0
        def flush():
            nonlocal line, cx, y
            px = x
            for tx, st in line:
                f = F("Bold", size) if st else F("Regular", size)
                if st == 2:
                    d.rectangle([px, y + size * 0.92, px + tw(d, tx, f), y + size * 1.12],
                                fill=hi + (HL_A,))
                d.text((px, y), tx, font=f, fill=col if st == 0 else N100)
                px += tw(d, tx, f)
            y += lh; line, cx = [], 0
        for p in [q for q in TOK.split(para) if q]:
            st = 1 if p.startswith("**") else (2 if p.startswith("==") else 0)
            body = p[2:-2] if st else p
            f = F("Bold", size) if st else F("Regular", size)
            # 공백은 토막 '안'에서만 낸다. 토막 끝에 붙이면 마크업 경계마다
            # 군더더기 공백이 생기고 하이라이트 밑줄도 글자 밖으로 삐져나온다.
            ws = body.split(" ")
            for i, wd in enumerate(ws):
                wd_ = wd + ("" if i == len(ws) - 1 else " ")
                if not wd_: continue
                wpx = tw(d, wd_, f)
                if cx + wpx > mx and line: flush()
                line.append((wd_, st)); cx += wpx
        if line: flush()
    return y


# ── 크롭 ────────────────────────────────────────────────
class Crops:
    """문항의 crops/ 폴더 + 매니페스트(crops.json). 이름 → 종류(math|figure).

    종류를 코드가 아니라 데이터로 들고 있는 게 핵심이다. 예전 렌더러는
    FLAT/FIGURE 집합에 문제 1의 크롭 이름을 하드코딩해서 다음 문항으로 못 넘어갔다."""

    def __init__(self, dirpath, manifest=None):
        self.dir = dirpath
        self.kind, self.meta = {}, {}
        self.body_pt = 10.0       # 교재 본문 글자 크기 (인라인 수식 축척의 기준)
        self.dpi = 400
        p = manifest or os.path.join(dirpath, "crops.json")
        if os.path.exists(p):
            man = json.load(open(p, encoding="utf-8"))
            self.body_pt = man.get("body_pt") or 10.0
            self.dpi = man.get("dpi") or 400
            for name, meta in man.get("crops", {}).items():
                self.kind[name] = meta.get("kind", "math")
                self.meta[name] = meta

    def is_figure(self, name):
        return self.kind.get(name, "math") == "figure"

    def inline_scale(self, size):
        """교재에서 body_pt 였던 글자가 카드에서 size 픽셀이 되도록 하는 축척.
           크롭은 dpi 로 잘렸으므로 pt→px 환산을 되돌린다."""
        return (size / self.body_pt) * (72.0 / self.dpi)

    def path(self, name):
        return os.path.join(self.dir, "%s.png" % name)


def trim(img, bg, tol=12):
    """크롭에 남은 지면색 여백을 잘라낸다.
    이걸 안 하면 좌측 그리드에 붙여도 잉크가 안쪽으로 밀려 축이 어긋난다."""
    px = img.load(); w, h = img.size
    bc = lambda x: all(abs(px[x, y][i] - bg[i]) <= tol for y in range(0, h, 2) for i in range(3))
    br = lambda y: all(abs(px[x, y][i] - bg[i]) <= tol for x in range(0, w, 2) for i in range(3))
    L = 0
    while L < w - 1 and bc(L): L += 1
    R = w - 1
    while R > L and bc(R): R -= 1
    T = 0
    while T < h - 1 and br(T): T += 1
    B = h - 1
    while B > T and br(B): B -= 1
    return img.crop((L, T, R + 1, B + 1))


def fit(img, mw, mh):
    r = min(mw / img.width, mh / img.height, 1.0)
    return img.resize((max(1, int(img.width * r)), max(1, int(img.height * r))), Image.LANCZOS)


def paper_plate(im, box, radius=RAD["md"], pad=PAD):
    x, y, w, h = box
    plate = Image.new("RGB", (w + pad * 2, h + pad * 2), PAPER)
    m = Image.new("L", plate.size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, plate.width, plate.height], radius, fill=255)
    im.paste(plate, (x - pad, y - pad), m)


def rule(d, y, col, x0=M, x1=W - M, wd=2):
    d.rectangle([x0, y, x1, y + wd], fill=col)


def _center(fn):
    """내용 높이를 먼저 재고, 남는 공간의 가운데에서 시작하도록 오프셋을 준다.
    카드 높이가 1350으로 고정이라 위로 쏠리면 아래가 통째로 빈다."""
    probe = Image.new("RGB", (W, H), (0, 0, 0))
    end = fn(probe, ImageDraw.Draw(probe), SP["xxl"])
    block = end - SP["xxl"]
    return max(SP["xxl"], (H - block) // 2)


def _arrow(d, y, col, cx=None):
    cx = cx if cx is not None else M + 18
    d.polygon([(cx - 13, y), (cx + 13, y), (cx, y + 22)], fill=col)
    return y + 22


def _seg_words(segs):
    """세그먼트를 배치 단위로 쪼갠다 — 글자는 어절, 수식은 통째로 하나."""
    out = []
    for sg in segs:
        if "img" in sg:
            out.append({"img": sg["img"]}); continue
        ws = sg.get("t", "").split(" ")
        for i, w in enumerate(ws):
            w = w + ("" if i == len(ws) - 1 else " ")
            if w:
                out.append({"t": w})
    return out


# ── 렌더러 ──────────────────────────────────────────────
class Renderer:
    """한 문항을 그린다. 크롭 저장소와 로고를 들고 있다."""

    LOGO_H, LOGO_ALPHA, LOGO_BOT = 34, 0.72, 52

    def __init__(self, crops, logo_path=None):
        self.crops = crops
        self.logo_path = logo_path
        self._logo = None

    # ── 크롭 색 처리 ──────────────────────────────────
    def load_crop(self, name, bg=None):
        im = Image.open(self.crops.path(name)).convert("RGB")
        if bg is None:
            return im
        # 수식은 밝은 화소를 통째로 눌러도 된다(글자만 남는다).
        # 도형은 내부 채색이 의미를 가지므로 '거의 순백'만 누른다.
        thr = 247 if self.crops.is_figure(name) else 205
        px = im.load()
        for yy in range(im.height):
            for xx in range(im.width):
                r, g, b = px[xx, yy]
                if r > thr and g > thr and b > thr:
                    px[xx, yy] = bg
        return trim(im, bg)

    def ink_crop(self, name, fg=N100):
        """종이용 크롭의 흑백을 뒤집어 잉크 지면 위에 놓는다.
           화이트포인트를 순백(255)이 아니라 **종이색의 밝기(243)** 로 잡는 게 핵심이다.
           255로 두면 여백이 INK보다 살짝 밝게 남아 수식 자리에 네모가 비친다."""
        im = self.load_crop(name, PAPER).convert("L")
        return ImageOps.colorize(im, black=fg, white=INK,
                                 blackpoint=30, whitepoint=243).convert("RGB")

    def img_for(self, c, key, mw, mh):
        """도형이면 원본(종이판용), 수식이면 반전본.
           골드는 카드가 지정한 한 자리에만 — 카드의 "gold" 필드."""
        name = c[key]
        if self.crops.is_figure(name):
            return fit(self.load_crop(name, PAPER), mw, mh)
        fg = GOLD if c.get("gold") == key else (N300 if c.get("dim") else N100)
        return fit(self.ink_crop(name, fg), mw, mh)

    # 수식은 글자와 달라 붙여 놓으면 앞말과 엉킨다. 좌우로 조금 띄운다.
    INLINE_BEARING = 6

    def inline_img(self, name, size, fg, maxw=None):
        """본문 글자 크기에 맞춰 줄인 인라인 수식. trim 은 축척 뒤에 한다 —
           먼저 잘라내면 원본 pt 비율이 깨져 수식만 혼자 커진다."""
        im = self.ink_crop_raw(name, fg)
        sc = self.crops.inline_scale(size)
        w, h = max(1, round(im.width * sc)), max(1, round(im.height * sc))
        im = trim(im.resize((w, h), Image.LANCZOS), INK, tol=10)
        # 한 줄을 통째로 넘기는 수식은 줄바꿈으로 못 푼다. 폭에 맞춰 줄인다.
        if maxw and im.width > maxw:
            im = fit(im, maxw, im.height)
        return im

    def ink_crop_raw(self, name, fg):
        im = Image.open(self.crops.path(name)).convert("RGB")
        px = im.load()
        for yy in range(im.height):
            for xx in range(im.width):
                r, g, b = px[xx, yy]
                if r > 205 and g > 205 and b > 205:
                    px[xx, yy] = PAPER
        im = im.convert("L")
        return ImageOps.colorize(im, black=fg, white=INK,
                                 blackpoint=30, whitepoint=243).convert("RGB")

    def segs(self, canvas, d, x, y, segs, font, fill, maxw, lh, size):
        """글자 사이에 수식 크롭을 끼워 조판한다.

        기출 원문은 수식이 문장 한가운데 박혀 있다. 이걸 못 하면 문제 카드에
        ▣ 구멍이 남거나, 수식을 통째로 아래에 따로 떼어 놓아 원문이 아니게 된다.
        수식이 큰 줄은 줄높이를 그만큼 늘린다 — 고정 줄높이로 밀면 윗줄과 겹친다."""
        cache = {}
        line, cx = [], 0

        def flush(row, yy):
            hs = [it["im"].height for it in row if "im" in it]
            rowh = max([lh] + [h + 10 for h in hs])
            base = yy + (rowh - lh) // 2
            px = x
            for it in row:
                if "im" in it:
                    im = it["im"]
                    px += self.INLINE_BEARING
                    canvas.paste(im, (int(px), int(base + (lh - im.height) // 2 + size * 0.12)))
                    px += im.width + self.INLINE_BEARING
                else:
                    d.text((px, base), it["t"], font=font, fill=fill)
                    px += tw(d, it["t"], font)
            return yy + rowh

        for w in _seg_words(segs):
            if "img" in w:
                nm = w["img"]
                if nm not in cache:
                    cache[nm] = self.inline_img(nm, size, fill,
                                                maxw - self.INLINE_BEARING * 2)
                item, wpx = {"im": cache[nm]}, cache[nm].width + self.INLINE_BEARING * 2
            else:
                item, wpx = {"t": w["t"]}, tw(d, w["t"], font)
            if cx + wpx > maxw and line:
                y = flush(line, y); line, cx = [], 0
            line.append(item); cx += wpx
        if line:
            y = flush(line, y)
        return y

    # ── 로고 ──────────────────────────────────────────
    def logo(self):
        if self._logo is None:
            im = Image.open(self.logo_path).convert("RGBA")
            im = im.crop(im.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox())
            w = round(self.LOGO_H * im.width / im.height)
            im = im.resize((w, self.LOGO_H), Image.LANCZOS)
            im.putalpha(im.getchannel("A").point(lambda v: int(v * self.LOGO_ALPHA)))
            self._logo = im
        return self._logo

    def stamp(self, im):
        """9장 전부 같은 자리에 같은 크기로. 흔들리면 서명이 아니라 장식이 된다."""
        if not self.logo_path or not os.path.exists(self.logo_path):
            return im
        lg = self.logo()
        im.paste(lg, (W - M - lg.width, H - self.LOGO_BOT - lg.height), lg)
        return im

    # ── 아키타입 ──────────────────────────────────────
    # 이름은 지면이 아니라 **배치 형식**을 뜻한다 (DESIGN.md §Archetypes).
    def c_cover(self, c):
        im = Image.new("RGB", (W, H), INK); d = ImageDraw.Draw(im)
        d.rectangle([0, 0, W, 10], fill=GOLD)
        d.text((M - 8, 150), c["serif_num"], font=BODONI(210), fill=(42, 30, 22))

        def body(canvas, dd, y):
            dtext(dd, (M, y), c["eyebrow"], F("SemiBold", 28), GOLD, TRK_KICKER); y += SP["xl"]
            for ln in c["head"]:
                dtext(dd, (M, y), ln, SERIF(92), N100, TRK_DISPLAY); y += 118
            y += SP["sm"]
            rule(dd, y, GOLD_RULE, M, M + 236); y += SP["lg"]
            sf = F("Medium", 33)
            for para in c["sub"].split("\n"):
                for ln in wrap(dd, para, sf, CW):
                    dd.text((M, y), ln, font=sf, fill=GOLD_SOFT); y += 50
            y += SP["sm"]
            for ln in wrap(dd, c["foot"], F("Regular", 27), CW):
                dd.text((M, y), ln, font=F("Regular", 27), fill=N500); y += 40
            return y

        body(im, d, max(470, _center(body)))   # 워터마크 숫자와 겹치지 않게 하한
        return im

    def c_prob(self, c):
        im = Image.new("RGB", (W, H), INK); d = ImageDraw.Draw(im)
        d.rectangle([0, 0, W, 10], fill=GOLD)
        # 원문에 수식이 없는 문항도 있다(경우의 수·확률 계열). img 는 선택이다.
        # 블록 수식 높이 상한. 기준본(수학01)은 230이고, 원문이 짧은 문항은
        # 수식이 본문을 압도하므로 카드에서 낮춰 잡을 수 있게 열어 둔다.
        img = self.img_for(c, "img", CW, c.get("img_h", 230)) if c.get("img") else None
        bf, qf = F("Medium", 34), F("SemiBold", 34)
        # 문항 번호 폭만큼 질문을 들여쓴다. 상수("1-1. ")로 박아 두면 두 자리 문항
        # (10-2. · 11-2.)에서 번호와 질문 첫 글자가 겹쳐 찍힌다.
        # 네 글자 이하는 기준본과 같은 폭을 그대로 쓴다 — 01~09 산출물 회귀 방지.
        ind = int(d.textlength("1-1. " if len(c["qno"]) <= 4 else c["qno"] + " ",
                               font=F("Bold", 34)))

        # 원문에 수식이 문장 속에 박힌 문항은 *_segs 로 온다. 없으면 예전처럼 문자열.
        def para(canvas, dd, x, y, key, font, fill, maxw, size):
            if c.get(key + "_segs"):
                return self.segs(canvas, dd, x, y, c[key + "_segs"],
                                 font, fill, maxw, 52, size)
            for ln in wrap(dd, c.get(key, ""), font, maxw):
                dd.text((x, y), ln, font=font, fill=fill); y += 52
            return y

        def body(canvas, dd, y):
            dtext(dd, (M, y), c["kick"], F("Bold", 27), GOLD, TRK_KICKER); y += SP["xl"]
            y = para(canvas, dd, M, y, "stem", bf, N300, CW, 34)
            y += SP["sm"]
            if img is not None:
                canvas.paste(img, (M, y)); y += img.height + SP["sm"]
            if c.get("tail") or c.get("tail_segs"):
                y = para(canvas, dd, M, y, "tail", bf, N300, CW, 34)
            y += SP["md"]
            dd.rectangle([M, y, M + 72, y + 4], fill=GOLD); y += SP["md"]
            dd.text((M, y), c["qno"], font=F("Bold", 34), fill=GOLD)
            y = para(canvas, dd, M + ind, y, "question", qf, N100, CW - ind, 34)
            # 질문이 가리키는 [조건]처럼 뒤에 붙는 원문. 인용이므로 한 단계 낮춘다.
            if c.get("after") or c.get("after_segs"):
                y += SP["md"]
                y = para(canvas, dd, M, y, "after", bf, N300, CW, 34)
            return y

        body(im, d, _center(body))
        if c.get("foot"):
            d.text((M, H - SP["sec"] - 44), c["foot"], font=F("Regular", 27), fill=N500)
        return im

    def c_dark_img(self, c):
        """세리프 헤드 + 수식 한 장 + 본문. 수식은 판 없이 지면에 직접 얹는다 —
           판이 하나도 없어야 카드가 한 덩어리로 읽힌다."""
        im = Image.new("RGB", (W, H), INK); d = ImageDraw.Draw(im)
        d.rectangle([0, 0, W, 10], fill=GOLD)
        img = self.img_for(c, "img", CW - PAD * 2, 260)

        def body(canvas, dd, y):
            dtext(dd, (M, y), c["kick"], F("Bold", 27), GOLD, TRK_KICKER); y += SP["lg"]
            for ln in c["head"]:
                dtext(dd, (M, y), ln, SERIF(66), N100, TRK_DISPLAY); y += 88
            y += SP["lg"]
            canvas.paste(img, (M, y)); y += img.height + SP["xl"]
            return rich(dd, M, y, c["body"], 33, N300, GOLD, CW, 54)

        body(im, d, _center(body))
        return im

    def c_text(self, c):
        """수식 없이 논증만 있는 카드. 헤드 + 본문(+ 목록).

        모든 문항에 크롭할 수식이 넉넉한 게 아니다 — 경우의 수·확률 계열은 해설이
        문장 속 인라인 수식으로 쓰여 있어 잘라낼 덩어리가 거의 없다. 그런 카드를
        억지로 수식 카드로 만들면 못 읽는 크롭이 들어간다. 그때 이걸 쓴다."""
        im = Image.new("RGB", (W, H), INK); d = ImageDraw.Draw(im)
        d.rectangle([0, 0, W, 10], fill=GOLD)

        def body(canvas, dd, y):
            dtext(dd, (M, y), c["kick"], F("Bold", 27), GOLD, TRK_KICKER); y += SP["lg"]
            for ln in c.get("head", []):
                dtext(dd, (M, y), ln, SERIF(66), N100, TRK_DISPLAY); y += 88
            y += SP["lg"]
            y = rich(dd, M, y, c["body"], 33, N300, GOLD, CW, 54)
            # 목록은 골드 불릿으로 세운다. 이모지·기호는 쓰지 않는다.
            if c.get("list"):
                y += SP["md"]
                for row in c["list"]:
                    dd.rectangle([M, y + 18, M + 18, y + 22], fill=GOLD)
                    y = rich(dd, M + SP["lg"], y, row, 31, N300, GOLD, CW - SP["lg"], 50)
                    y += SP["xs"]
            if c.get("foot"):
                y += SP["md"]
                for para in c["foot"].split("\n"):
                    for ln in wrap(dd, para, F("Medium", 29), CW):
                        dd.text((M, y), ln, font=F("Medium", 29), fill=N400); y += 44
            return y

        body(im, d, _center(body))
        return im

    def c_paper(self, c):
        """수식 한 덩어리 + 꼬리. img2를 주면 두 줄로 쌓고, big_img는 답 자리다."""
        im = Image.new("RGB", (W, H), INK); d = ImageDraw.Draw(im)
        d.rectangle([0, 0, W, 10], fill=GOLD)

        big  = self.img_for(c, "big_img", 600, 170) if c.get("big_img") else None
        img2 = self.img_for(c, "img2", CW, 210) if c.get("img2") else None
        foot_lines = []
        if c.get("foot"):
            for para in c["foot"].split("\n"):
                foot_lines += wrap(d, para, F("Medium", 29), CW)
        reserve = (SP["lg"] + len(c.get("head", [])) * 82 + SP["lg"] * 2
                   + len(foot_lines) * 44
                   + ((img2.height + SP["sm"]) if img2 is not None else 0)
                   + ((big.height + SP["lg"]) if big is not None else 0) + SP["sec"] * 2)
        img = self.img_for(c, "img", CW,
                           min(210, H - reserve) if img2 is not None else H - reserve)

        def body(canvas, dd, y):
            dtext(dd, (M, y), c["kick"], F("Bold", 27), GOLD, TRK_KICKER); y += SP["lg"]
            for ln in c.get("head", []):
                dtext(dd, (M, y), ln, SERIF(62), N100, TRK_DISPLAY); y += 82
            y += SP["lg"]
            canvas.paste(img, (M, y)); y += img.height + (SP["sm"] if img2 is not None else SP["lg"])
            if img2 is not None:
                canvas.paste(img2, (M, y)); y += img2.height + SP["lg"]
            if big is not None:
                canvas.paste(big, (M, y))     # 답은 라벨 없이 수식만 놓는다
                y += big.height + SP["lg"]
            for ln in foot_lines:
                dd.text((M, y), ln, font=F("Medium", 29), fill=N400); y += 44
            return y

        body(im, d, _center(body))
        return im

    def c_dark2(self, c):
        """도구 → 결과. 위는 수식이라 뒤집어 얹고, 아래가 도형이면 종이판 위에 남긴다."""
        im = Image.new("RGB", (W, H), INK); d = ImageDraw.Draw(im)
        d.rectangle([0, 0, W, 10], fill=GOLD)
        a = self.img_for(c, "img",  CW - PAD * 2, 150)
        b = self.img_for(c, "img2", CW - PAD * 2, 520)
        b_fig = self.crops.is_figure(c["img2"])

        def body(canvas, dd, y):
            dtext(dd, (M, y), c["kick"], F("Bold", 27), GOLD, TRK_KICKER); y += SP["lg"]
            for ln in c["head"]:
                dtext(dd, (M, y), ln, SERIF(58), N100, TRK_DISPLAY); y += 76
            y += SP["lg"]
            canvas.paste(a, (M, y)); y += a.height + SP["sm"]
            y = _arrow(dd, y, GOLD_RULE, M + a.width // 2) + SP["sm"]
            if b_fig:
                y += PAD
                paper_plate(canvas, (M + PAD, y, b.width, b.height))
                canvas.paste(b, (M + PAD, y)); y += b.height + PAD + SP["lg"]
            else:
                canvas.paste(b, (M, y)); y += b.height + SP["lg"]
            return rich(dd, M, y, c["body"], 31, N300, GOLD, CW, 50)

        body(im, d, _center(body))
        return im

    def c_paper2(self, c):
        """수식 두 줄 + 사이의 이음매 문장 — 논증이 굴러가는 걸 보인다."""
        im = Image.new("RGB", (W, H), INK); d = ImageDraw.Draw(im)
        d.rectangle([0, 0, W, 10], fill=GOLD)
        a = self.img_for(c, "img",  CW, 132)
        b = self.img_for(c, "img2", CW, 132)
        mf, ff = F("Medium", 30), F("Medium", 29)

        def body(canvas, dd, y):
            dtext(dd, (M, y), c["kick"], F("Bold", 27), GOLD, TRK_KICKER); y += SP["lg"]
            for ln in c.get("head", []):
                dtext(dd, (M, y), ln, SERIF(62), N100, TRK_DISPLAY); y += 82
            y += SP["lg"]
            for ln in wrap(dd, c["mid"], mf, CW):
                dd.text((M, y), ln, font=mf, fill=N400); y += 46
            y += SP["md"]
            canvas.paste(a, (M, y)); y += a.height + SP["md"]
            y = _arrow(dd, y, GOLD_RULE) + SP["md"]
            canvas.paste(b, (M, y)); y += b.height + SP["lg"]
            for para in c["foot"].split("\n"):
                for ln in wrap(dd, para, ff, CW):
                    dd.text((M, y), ln, font=ff, fill=N300); y += 44
            return y

        body(im, d, _center(body))
        return im

    def c_dark_wine(self, c):
        """오답·감점. 이름은 물려받았지만 와인은 쓰지 않는다 — 골드 인용 바다."""
        im = Image.new("RGB", (W, H), INK); d = ImageDraw.Draw(im)
        d.rectangle([0, 0, W, 10], fill=GOLD)
        qf = SERIF(52, bold=True)
        lines = wrap(d, "“%s”" % c["quote"], qf, CW - SP["lg"])

        def body(canvas, dd, y):
            dtext(dd, (M, y), c["kick"], F("Bold", 27), GOLD, TRK_KICKER); y += SP["lg"]
            qy = y
            # 바는 인용 글자 높이에 맞춰 세운다 (줄간이 아니라 글자 기준)
            dd.rectangle([M, y + 10, M + 6, y + (len(lines) - 1) * 74 + 62], fill=GOLD)
            for ln in lines:
                dd.text((M + SP["lg"], qy), ln, font=qf, fill=N100); qy += 74
            y = qy + SP["lg"]
            rule(dd, y, GOLD_RULE); y += SP["lg"]
            return rich(dd, M, y, c["body"], 33, N300, GOLD, CW, 56)

        body(im, d, _center(body))
        return im

    def c_outro(self, c):
        im = Image.new("RGB", (W, H), INK); d = ImageDraw.Draw(im)
        d.rectangle([0, 0, W, 10], fill=GOLD)

        def body(canvas, dd, y):
            dtext(dd, (M, y), c["kick"], F("Bold", 27), GOLD, TRK_KICKER); y += SP["lg"]
            for ln in c["head"]:
                dtext(dd, (M, y), ln, SERIF(70), N100, TRK_DISPLAY); y += 92
            y += SP["md"]
            # 본문 31 — 32에서는 긴 줄이 콘텐츠 폭을 넘겨 어색하게 끊긴다.
            y = rich(dd, M, y, c["body"], 31, N300, GOLD, CW, 52)
            y += SP["lg"]
            bx = [M, y, W - M, y + 224]
            dd.rounded_rectangle(bx, RAD["lg"], fill=INK_800, outline=(64, 50, 30), width=2)
            ty = y + SP["lg"]
            for i, ln in enumerate(c["cta"]):
                f = F("Bold", 33) if i == 0 else F("SemiBold", 31)
                col = N100 if i == 0 else GOLD_SOFT
                for l2 in wrap(dd, ln, f, CW - SP["lg"] * 2):
                    dd.text((M + SP["lg"], ty), l2, font=f, fill=col); ty += 50
                ty += SP["xs"]
            y = bx[3] + SP["xl"]
            rule(dd, y, GOLD_RULE); y += SP["lg"]
            dd.text((M, y), c["brand"], font=F("SemiBold", 30), fill=GOLD)
            dd.text((M, y + 46), c.get("brand_sub",
                    "PRODUCT_LINE"),
                    font=F("Regular", 26), fill=N500)
            return y + 46 + 40

        body(im, d, _center(body))
        return im

    # ── 디스패치 ──────────────────────────────────────
    def card(self, c):
        fn = {"cover": self.c_cover, "prob": self.c_prob, "paper": self.c_paper,
              "dark_img": self.c_dark_img, "dark_wine": self.c_dark_wine,
              "outro": self.c_outro, "dark2": self.c_dark2, "paper2": self.c_paper2,
              "text": self.c_text}
        if c["type"] not in fn:
            raise KeyError("모르는 아키타입: %s (쓸 수 있는 것: %s)"
                           % (c["type"], ", ".join(sorted(fn))))
        return self.stamp(fn[c["type"]](c))


def font_path(name):
    """F() 와 같은 규칙으로 실제 파일 경로를 돌려준다 (글리프 검사용)."""
    cands = ["Pretendard-%s" % w for w in NEAR[name]] if name in NEAR else [name]
    for stem in cands:
        for d in FONT_DIRS:
            for p in (os.path.join(d, stem + ".ttf"),
                      os.path.join(d, stem.split("-")[-1] + ".ttf")):
                if os.path.exists(p):
                    return p
    return None


_cmap = {}
def missing_glyphs(text, font_name):
    """폰트에 없는 글자를 골라낸다.

    Noto Serif KR 에는 √ ≤ ≥ ∴ α β 가 없어 헤드라인·인용에 쓰면 두부(□)가 된다.
    DESIGN.md 가 경고하는 자리이고, 발행 전에 기계로 잡아야 하는 자리다."""
    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        return []
    p = font_path(font_name)
    if not p:
        return []
    if p not in _cmap:
        f = TTFont(p, fontNumber=0, lazy=True)
        cm = set()
        for t in f["cmap"].tables:
            cm |= set(t.cmap)
        f.close()
        _cmap[p] = cm
    cm = _cmap[p]
    return sorted({ch for ch in text
                   if ch.strip() and ord(ch) not in cm and not ch.isspace()})


def contact_sheet(paths, labels, bg=(24, 18, 20)):
    """전체 미리보기 한 장. 장수에 맞춰 폭이 늘어난다."""
    tw_, th_, gap = 300, 375, 20
    n = len(paths)
    sheet = Image.new("RGB", (tw_ * n + gap * (n + 1), th_ + gap * 2 + 40), bg)
    sd = ImageDraw.Draw(sheet)
    for i, (p, lab) in enumerate(zip(paths, labels)):
        t = Image.open(p).resize((tw_, th_), Image.LANCZOS)
        x = gap + i * (tw_ + gap)
        sheet.paste(t, (x, gap))
        sd.text((x, gap + th_ + 12), lab, font=F("Medium", 22), fill=(163, 163, 163))
    return sheet

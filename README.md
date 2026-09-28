# Card News Engine

A pipeline that turns a Korean university-entrance math problem (PDF, KaTeX-typeset)
into a publication-ready 9-card Instagram carousel (1080x1350) — with formulas cropped
from the source PDF, rescaled, and typeset **inline inside Korean sentences**.

Built solo with Claude Code over ~3 weeks for a live client account. 11 problems have
been produced end to end with it.

- **2,729 lines of Python** — extractor 1,075 / engine 1,654
- 11 problems x 9 cards = 99 cards rendered
- New problem to finished set in ~10 minutes, of which exactly one step is human

> **This repository is a sanitized mirror: code only.**
> No source PDFs, no publication text, no extracted content, no rendered cards, no
> client branding. Those belong to the client and are not mine to publish. Brand
> strings in the code are replaced with `BRAND` placeholders. The code is the artifact
> here; the output is not.

---

## The problem

Exam commentary is close to the worst possible input for a card carousel.

1. **Formulas cannot be re-typed.** Korean web fonts (Noto Serif KR) have no `√`.
   Every formula must ship as a cropped image of the original PDF.
2. **Formulas sit in the middle of sentences** — `수열 {aₙ} 을 다음과 같이 정의하자`.
   A crop wide enough to catch the formula drags Korean text in with it; a tighter one
   severs the formula. Either way the card is unreadable on a phone.
3. **Shrinking the A4 page to fit** renders at roughly 6px on a phone.
   This project died twice at exactly that shortcut.

So the engine's job is not "render a template". It is: *decide what can be cropped,
crop it, and set it back into the sentence at the right size.*

## Core idea: one crop criterion

The textbook is KaTeX-typeset, so math spans are identifiable **by font name**
(`^KaTeX`). That alone is useless for cropping — inline fragments merge into paragraphs.
The engine replaces it with a single rule:

> **A croppable formula is a rectangle that contains not one fragment of Korean body text.**

That one rule also decides the merge width. The engine first merges very wide (90pt):
sibling formulas standing side by side (`(I) ... (II)`) pass, because only whitespace
separates them, while in-sentence fragments catch Korean and fail. Whatever fails is
re-merged narrower (40 -> 13pt). If no width separates the Korean, **the formula is
discarded** rather than shipped broken.

**Validation.** On problem 1, of 8 crops a human had picked by hand, the engine
reproduced 6 at 80-94% bounding-box overlap. The two misses are places where the human
merged two lines into one block; the engine splits per line.

## Inline formula typesetting

The extractor keeps the original sentence as coordinate-bearing segments:

```json
[{"type":"text","t":"수열 "},
 {"type":"math","page":1,"rect":[...]},
 {"type":"text","t":"을 다음과 같이 정의하자"}]
```

`autocrop` cuts those positions as `q01`, `q02` ..., and the renderer **sets the crops
between the glyphs**. Crops are scaled from the textbook's body font size (`body_pt`,
recorded in the manifest) to the card's body size — without that conversion the formula
alone ends up larger or smaller than the sentence around it. Lines carrying a tall
formula get their leading increased to match.

All 11 problems are typeset this way. Without it, every source card has a hole in it.

## What is automatic and what is not

Written honestly, because this is the part that matters.

| Stage | Who | Note |
|---|---|---|
| PDF -> structured JSON | **automatic** | `extractor/extract.py`, 11/11 problems |
| Formula & figure **crop coordinates** | **automatic** | the criterion above |
| Cover card (year, number, curriculum, unit) | **automatic** | straight from extracted meta |
| Problem card (source text, inline formulas, conditions) | **automatic** | inline typesetting above |
| Penalty card (quotation + commentary) | **automatic** | from extracted `penalty` |
| Landing card (brand, CTA) | **automatic** | fixed template |
| **Argument cards (translate / reduce / tool / execute / verify)** | **human or LLM** | deliberately not automated |
| Page, emphasis, logo, layout | **automatic** | unchanged across problems |
| Caption | human | not automated yet |

**The argument cards are deliberately left to a human.** "In what order should this
problem's logic be shown" is editorial judgment, and the density of a single card is the
account's entire credibility asset. What the engine does instead is assemble a materials
file — every usable input pulled from the commentary (steps, key ideas, common mistakes,
first impression, time budget) — and enforce one rule: **nothing goes on a card that is
not in that file.**

## Regression contract: byte-level reproduction

The engine's contract is that it reproduces the hand-finalized 9-card reference set
**byte for byte**:

```bash
python3 engine/make.py verify <item>
```

Any change to the renderer must pass this before it ships. A carousel pipeline with no
regression test drifts silently in kerning and spacing until the account's visual
identity is gone. This is the cheapest possible guard against that.

## Usage

```bash
python3 engine/make.py new   2017_math_03   # 1. work folder + copy draft + materials file
python3 engine/make.py crops math03         # 2. all formula/figure crops + thumbnail index
#    3. fill the TODOs in cards.json  <- the human step
python3 engine/make.py check math03         # 4. pre-publication checks
python3 engine/make.py build math03         #    render -> cards/01..NN.png + full preview
```

One `item.json` per problem folder — **no path is hard-coded into the code**, so a
problem folder can be moved or copied without touching the engine.

## Layout

```
extractor/
  extract.py     PDF -> structured JSON (766 lines)
  plan.py        card composition plan
  validate.py    extraction checks
engine/
  make.py        CLI: new / crops / check / build / verify / list
  scaffold.py    work folder + copy draft generation
  autocrop.py    crop execution + thumbnail index
  engine/
    item.py      per-problem manifest (item.json) access
    mathcrop.py  the crop criterion -- the core of this repository
    probsegs.py  inline-formula naming rules
    render.py    renderer: page, emphasis, logo, inline typesetting (690 lines)
```

## Known limits

- `mathcrop.find` merges vertically at `GAP_Y = 8`, so a display formula with Korean
  text directly above or below is discarded as "a block containing Korean". Those are
  pinned by hand in `item.json` -> `crops_extra` (problems 7, 9, 10).
- Crops wider than 320pt hit the check's 2.5px/pt reduction and must be split in two.
- Usable formula count varies enormously per problem — 10 in problem 1, 4 in problem 2
  (combinatorics commentary is written as in-sentence inline math). Hence a `text`
  archetype carrying argument only, with no formula cards. Forcing formula cards
  produces unreadable crops.
- Captions are still written by hand.

## Stack

Python - PyMuPDF - Pillow - Claude Code (for building the engine, and for drafting
argument-card copy).

## License

MIT for the code in this repository. Source publications, exam material and client
branding are not included and are not covered by it.

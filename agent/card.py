"""
Print-ready signal card.

Takes the writer's card output and renders an A6 card, front and back, as HTML
sized in millimetres so it prints at true scale rather than "roughly card
sized". Crop marks are deliberately omitted — this goes to a local printer or a
print-on-demand service, both of which add their own.

WHY THIS EXISTS RATHER THAN A PDF LIBRARY
The card has to be editable five minutes before it goes to print, and a human
has to be able to read the source and see exactly what will appear. HTML with
millimetre units and a print stylesheet does that; a generated PDF does not.

WHAT GOES ON IT AND WHY
Front: one number and one line. The test is whether it works face-up on a desk,
glanced at while walking past. Anything more is a leaflet.
Back: the verbatim customer quote (their own, public, checkable), two lines of
context, the limitation in small print, and the sender. The limitation is on
the card rather than left for the follow-up because a figure sent to a senior
operator without its caveat invites exactly one reply, and it is not a friendly
one.
"""

from __future__ import annotations

import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out" / "cards"

FIELDS = ["FRONT_STAT", "FRONT_LINE", "BACK_QUOTE", "BACK_BODY", "BACK_SMALLPRINT"]


def parse_card(text: str) -> dict:
    """
    Pull the marked fields out of the writer's output.

    Returns only what was actually found. A missing field is left absent rather
    than filled with a placeholder — the renderer then omits that element, and
    the caller can see the card is incomplete instead of printing the word
    "None" on something going in the post.
    """
    out: dict[str, str] = {}
    for i, f in enumerate(FIELDS):
        nxt = FIELDS[i + 1] if i + 1 < len(FIELDS) else None
        pat = rf"{f}\s*:\s*(.*?)(?=\n\s*{nxt}\s*:|\Z)" if nxt else rf"{f}\s*:\s*(.*)"
        m = re.search(pat, text, re.S | re.I)
        if m:
            v = m.group(1).strip().strip('"“”')
            if v:
                out[f] = v
    return out


CARD_CSS = """
@page { size: 148mm 105mm; margin: 0 }
*{box-sizing:border-box}
body{margin:0;background:#8891a0;font-family:"Archivo",system-ui,sans-serif;
  -webkit-font-smoothing:antialiased}
.sheet{display:flex;flex-wrap:wrap;gap:8mm;padding:8mm;justify-content:center}
.face{width:148mm;height:105mm;background:#fff;color:#0d1f47;position:relative;
  overflow:hidden;box-shadow:0 2mm 6mm rgba(0,0,0,.25)}
.face.back{background:#0d1f47;color:#fff}
.pad{position:absolute;inset:10mm 11mm}

/* front */
.stat{font-family:"JetBrains Mono",monospace;font-size:31mm;line-height:.92;
  font-weight:600;letter-spacing:-.02em}
.rule{width:22mm;height:1.6mm;background:#eab308;margin:5mm 0 4.5mm}
.line{font-size:5.1mm;line-height:1.34;font-weight:500;max-width:112mm}
.src{position:absolute;left:11mm;right:11mm;bottom:8mm;
  font-family:"JetBrains Mono",monospace;font-size:2.5mm;letter-spacing:.09em;
  text-transform:uppercase;color:#7f93b4}

/* back */
.quote{font-size:4.3mm;line-height:1.42;font-style:italic;color:#fff}
.qmeta{font-family:"JetBrains Mono",monospace;font-size:2.5mm;letter-spacing:.08em;
  text-transform:uppercase;color:#7ec0f5;margin-top:2.5mm}
.body{font-size:3.7mm;line-height:1.46;color:#dbe4f5;margin-top:6mm;max-width:118mm}
.small{position:absolute;left:11mm;right:11mm;bottom:14mm;font-size:2.6mm;
  line-height:1.4;color:#8fa3c8;max-width:118mm}
.sign{position:absolute;left:11mm;right:11mm;bottom:8mm;display:flex;
  justify-content:space-between;gap:4mm;
  font-family:"JetBrains Mono",monospace;font-size:2.7mm;letter-spacing:.07em;
  text-transform:uppercase;color:#ffd24a}

.tag{position:absolute;top:10mm;right:11mm;font-family:"JetBrains Mono",monospace;
  font-size:2.5mm;letter-spacing:.1em;text-transform:uppercase;color:#7f93b4}
.face.back .tag{color:#6f82ab}
@media print{ body{background:#fff} .sheet{gap:0;padding:0}
  .face{box-shadow:none;page-break-after:always} }
"""


def render_card(prospect: str, fields: dict, sender: str, url: str) -> str:
    e = lambda k: html.escape(fields.get(k, ""))
    front_src = f"Source: public Google Play reviews, India &middot; {html.escape(prospect)}"
    quote = e("BACK_QUOTE")
    return f"""<!doctype html>
<html><head><meta charset="utf-8">
<title>Signal card — {html.escape(prospect)}</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600&family=JetBrains+Mono:wght@400;600&display=swap">
<style>{CARD_CSS}</style></head><body>
<div class="sheet">

  <div class="face front">
    <div class="pad">
      <div class="tag">{html.escape(prospect)}</div>
      <div class="stat">{e('FRONT_STAT')}</div>
      <div class="rule"></div>
      <div class="line">{e('FRONT_LINE')}</div>
    </div>
    <div class="src">{front_src}</div>
  </div>

  <div class="face back">
    <div class="pad">
      <div class="tag">one of your reviews</div>
      {f'<p class="quote">&ldquo;{quote}&rdquo;</p>' if quote else ''}
      {'<div class="qmeta">Google Play &middot; India &middot; verbatim</div>' if quote else ''}
      <p class="body">{e('BACK_BODY')}</p>
    </div>
    {f'<div class="small">{e("BACK_SMALLPRINT")}</div>' if fields.get('BACK_SMALLPRINT') else ''}
    <div class="sign"><span>{html.escape(sender)}</span><span>{html.escape(url)}</span></div>
  </div>

</div></body></html>"""


def write_card(prospect_id: str, prospect: str, raw: str,
               sender: str = "{sender}", url: str = "{url}") -> dict:
    """Render one card. Returns the path and which fields were missing."""
    fields = parse_card(raw)
    missing = [f for f in FIELDS if f not in fields]
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{prospect_id}.html"
    path.write_text(render_card(prospect, fields, sender, url))
    return {"path": str(path), "fields": fields, "missing": missing}

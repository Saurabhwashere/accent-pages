#!/usr/bin/env python3
"""accent-pages: make a landing-page hero twice, once in two quiet colours and once with one accent colour.

Commands (run from anywhere, pass the project folder):
  accent.py init   <folder>                 write a page.json to fill in
  accent.py check  <folder>                 check the palette (accent across the wheel, quiet field, readable ink)
  accent.py render <folder> [--n 2]         render the ACCENT page from page.json  -> <folder>/out/accent-<k>.png
  accent.py plain  <folder> <accent.png>    edit that render into the PLAIN page   -> <folder>/out/plain-<k>.png
  accent.py fix    <folder> <image.png> "<what to change>"   targeted edit of one render -> <folder>/out/<name>-fix<k>.png
  accent.py pair   <folder> <plain.png> <accent.png>         side-by-side card with swatches -> <folder>/out/pair.png

Needs: Python 3.9+, `pip install requests pillow`, and OPENAI_API_KEY (environment variable, or a .env file in the
folder or any parent: OPENAI_API_KEY=sk-...). Every render is one paid OpenAI image call.
Model: gpt-image-2.6-sunburst by default; set ACCENT_IMAGE_MODEL to use another image model.
"""
import argparse
import colorsys
import json
import math
import os
import sys
import time
from pathlib import Path

MODEL = os.environ.get('ACCENT_IMAGE_MODEL', 'gpt-image-2.6-sunburst')
SIZE = '1536x1024'
API = 'https://api.openai.com/v1/images'

TEMPLATE = {
    "brand": "Copperline",
    "what": "a hair colour salon in New York known for bold copper colour work",
    "layout": "split: the headline in two giant lines across the full width, the subject standing in front of the lower line",
    "subject": "a young woman with a glossy blunt bob and fringe, eyes closed, chin raised, plain off-white knit",
    "accent_on": "her hair is glossy copper-orange",
    "plain_as": "her hair is cool ash grey, almost silver",
    "background": "seamless matte studio paper in pale cool grey",
    "light": "hard on-camera flash, crisp highlights, a soft shadow on the paper",
    "headline": "STATEMENT COLOUR",
    "type": "tall ultra-condensed heavy sans in deep navy, each line spanning the full width",
    "ui": ["wordmark top-left: COPPERLINE", "nav: Colour, Cuts, Salons", "outline pill button top-right: Book a chair",
           "small captions: SoHo, New York / Colour from $180"],
    "ref": "",
    "palette": {"field": ["Studio Grey", "#E7EAEE"], "ink": ["Navy", "#141E5C"], "accent": ["Copper", "#F0661E"]}
}


def die(msg):
    print(f'ERROR: {msg}', file=sys.stderr)
    sys.exit(1)


# ------------------------------------------------------------------ colour maths
def hex_rgb(h):
    h = h.strip().lstrip('#')
    if len(h) != 6:
        die(f'"{h}" is not a 6-digit hex colour like #F0661E')
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def oklch(h):
    def lin(c):
        return c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in hex_rgb(h))
    l_ = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m_ = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s_ = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    L = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
    A = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    B = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_
    return L, math.hypot(A, B), math.degrees(math.atan2(B, A)) % 360


def contrast(h1, h2):
    def lum(h):
        return sum(w * (c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4)
                   for w, c in zip((.2126, .7152, .0722), hex_rgb(h)))
    a, b = sorted((lum(h1), lum(h2)), reverse=True)
    return (a + .05) / (b + .05)


def hue_gap(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)


# ------------------------------------------------------------------ project files
def load(folder):
    p = Path(folder) / 'page.json'
    if not p.exists():
        die(f'no page.json in {folder}. Run: accent.py init {folder}')
    try:
        page = json.loads(p.read_text(encoding='utf-8'))
    except json.JSONDecodeError as e:
        die(f'page.json is not valid JSON: {e}')
    need = ['brand', 'what', 'layout', 'subject', 'accent_on', 'plain_as', 'background', 'light', 'headline', 'type',
            'ui', 'palette']
    miss = [k for k in need if not page.get(k)]
    if miss:
        die(f'page.json is missing: {", ".join(miss)}')
    for k in ('field', 'ink', 'accent'):
        if k not in page['palette']:
            die(f'palette needs "{k}": ["Name", "#HEX"]')
    return page


def api_key(folder):
    if os.environ.get('OPENAI_API_KEY'):
        return os.environ['OPENAI_API_KEY']
    d = Path(folder).resolve()
    for cand in [d, *d.parents]:
        env = cand / '.env'
        if env.exists():
            for ln in env.read_text(encoding='utf-8').splitlines():
                if ln.strip().startswith('OPENAI_API_KEY='):
                    return ln.split('=', 1)[1].strip().strip('"\'')
    die('no OPENAI_API_KEY. Put OPENAI_API_KEY=sk-... in a .env file in your project folder, or set it in your shell.')


def next_path(out, stem):
    k = 1
    while (out / f'{stem}-{k}.png').exists():
        k += 1
    return out / f'{stem}-{k}.png'


def call(folder, prompt, src=None):
    key = api_key(folder)
    try:
        import requests
    except ImportError:
        die('missing package. Run: python3 -m pip install requests pillow')
    import base64
    headers = {'Authorization': f'Bearer {key}'}
    t0 = time.time()
    if src is None:
        r = requests.post(f'{API}/generations', headers=headers, timeout=(15, 300),
                          json={'model': MODEL, 'prompt': prompt, 'size': SIZE, 'quality': 'high', 'n': 1})
    else:
        with open(src, 'rb') as f:
            r = requests.post(f'{API}/edits', headers=headers, timeout=(15, 300),
                              data={'model': MODEL, 'prompt': prompt, 'size': SIZE, 'quality': 'high', 'n': '1'},
                              files={'image[]': (Path(src).name, f, 'image/jpeg' if Path(src).suffix.lower() in ('.jpg', '.jpeg') else 'image/png')})
    if r.status_code != 200:
        try:
            msg = r.json().get('error', {}).get('message', r.text)
        except ValueError:
            msg = r.text
        hint = ''
        if 'verif' in msg.lower():
            hint = '\nYour OpenAI organisation may need verifying for image models: platform.openai.com/settings/organization/general'
        elif r.status_code == 401:
            hint = '\nThe API key was rejected. Check OPENAI_API_KEY.'
        elif 'model' in msg.lower():
            hint = f'\nThe model "{MODEL}" is not available to you. Set ACCENT_IMAGE_MODEL to an image model you can use.'
        die(f'OpenAI {r.status_code}: {msg}{hint}')
    j = r.json()
    return base64.b64decode(j['data'][0]['b64_json']), round(time.time() - t0, 1), j.get('usage', {})


def save(path, png, prompt, src, secs, usage):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)
    path.with_suffix('.json').write_text(json.dumps({'model': MODEL, 'source': str(src) if src else None,
                                                     'seconds': secs, 'usage': usage, 'prompt': prompt}, indent=1),
                                         encoding='utf-8')
    print(f'saved {path}  ({secs}s)')


# ------------------------------------------------------------------ prompts
def accent_prompt(page, variation=''):
    p = page['palette']
    ui = '; '.join(page['ui'])
    ref = ("The attached screenshot is a design reference only. Match its level of craft, its kind of layout, the way its "
           "big type and its subject overlap, and its polish. Do not copy its brand, words, people, logo or colours.\n"
           if page.get('ref') else '')
    return ref + (
        f"A finished, award-level website hero for {page['brand']}, {page['what']}. Landscape desktop screenshot, "
        f"edge to edge, no browser frame, no device, no mockup.\n"
        f"Layout: {page['layout']}.\n"
        f"Subject: {page['subject']}. {page['accent_on']}. The subject is big and confident; let it break the frame.\n"
        f"Background: {page['background']}. Light: {page['light']}.\n"
        f"Headline, spelled exactly \"{page['headline']}\": {page['type']}.\n"
        f"Interface (small, crisp, readable, spelled exactly as written): {ui}. No other text anywhere.\n"
        f"Colour: the page is built from two quiet colours, {p['field'][0]} ({p['field'][1]}) and {p['ink'][0]} "
        f"({p['ink'][1]}). {p['accent'][0]} ({p['accent'][1]}) appears ONLY on the subject, as described, and nowhere "
        f"else on the page. Everything else stays in the two quiet colours.\n"
        f"Real photography, real materials, sharp type. No lorem ipsum, no watermark, no extra logos. {variation}"
    ).strip()


def plain_prompt(page):
    a = page['palette']['accent']
    return (
        "Edit this website hero. Change one thing and keep everything else pixel for pixel: same layout, same crop, "
        "same subject pose, same headline and small text with the same spelling, same type colours, same background "
        "and same light. Add no text.\n"
        f"The change: take the {a[0].lower()} colour out of the page. {page['plain_as']}, with the same shape, "
        f"texture, shine and shadows. After the edit nothing on the page is {a[0].lower()}; the page uses only "
        f"{page['palette']['field'][0].lower()} and {page['palette']['ink'][0].lower()} tones."
    )


def fix_prompt(change):
    return ("Edit this website hero. Keep everything exactly as it is (layout, subject, every word and its spelling, "
            "colours, background, light) and change only this: " + change + " Add no text.")


VARIATIONS = ['', 'Closer camera: the subject larger and cut by the frame edge.',
              'Lower camera looking slightly up at the subject.', 'The subject a little off centre, cut by one side.',
              'A small turn of the subject, caught mid-movement by the flash.']


# ------------------------------------------------------------------ commands
def cmd_init(a):
    d = Path(a.folder)
    d.mkdir(parents=True, exist_ok=True)
    p = d / 'page.json'
    if p.exists():
        die(f'{p} already exists; edit it instead')
    p.write_text(json.dumps(TEMPLATE, indent=1), encoding='utf-8')
    print(f'wrote {p}. Replace the example (Copperline) with your brand, then run: accent.py check {d}')


def cmd_check(a):
    page = load(a.folder)
    pal = page['palette']
    f, i, x = (pal[k][1] for k in ('field', 'ink', 'accent'))
    (_, cf, hf), (li, ci, hi), (lx, cx, hx) = oklch(f), oklch(i), oklch(x)
    rows, bad = [], 0

    def row(ok, text):
        nonlocal bad
        bad += not ok
        rows.append(('PASS ' if ok else 'FAIL ') + text)
    # a quiet colour with almost no chroma has no real hue, so it cannot clash
    for name, c, h in (('field', cf, hf), ('ink', ci, hi)):
        gap = hue_gap(hx, h)
        row(c < .03 or gap >= 100, f'accent vs {name}: {gap:.0f} deg apart on the wheel (want 100+; {name} chroma {c:.2f})')
    row(cf <= .55 * cx, f'field is quiet: chroma {cf:.2f} vs accent {cx:.2f} (field must be at most 55% of the accent)')
    row(ci <= .55 * cx or li < .4, f'ink is quiet: chroma {ci:.2f} vs accent {cx:.2f}, lightness {li:.2f} (a dark ink always passes)')
    row(cx >= .12, f'accent is bold enough: chroma {cx:.2f} (want 0.12+)')
    cr = contrast(f, i)
    row(cr >= 4.5, f'ink on field reads: contrast {cr:.1f}:1 (want 4.5+)')
    print('\n'.join(rows))
    print('palette OK' if not bad else f'{bad} problem(s): change the hex in page.json and check again')
    sys.exit(1 if bad else 0)


def cmd_render(a):
    page = load(a.folder)
    out = Path(a.folder) / 'out'
    ref = None
    if page.get('ref'):
        ref = Path(page['ref']) if Path(page['ref']).is_absolute() else Path(a.folder) / page['ref']
        if not ref.exists():
            die(f'ref image {ref} not found (page.json "ref" is relative to the project folder)')
    for k in range(a.n):
        prompt = accent_prompt(page, VARIATIONS[k % len(VARIATIONS)])
        png, secs, usage = call(a.folder, prompt, ref)
        save(next_path(out, 'accent'), png, prompt, ref, secs, usage)
    print('Next: open the renders, check every word is spelled right, pick one, then: accent.py plain <folder> <render>')


def cmd_plain(a):
    page = load(a.folder)
    src = Path(a.image)
    if not src.exists():
        die(f'{src} not found')
    prompt = plain_prompt(page)
    png, secs, usage = call(a.folder, prompt, src)
    save(next_path(Path(a.folder) / 'out', 'plain'), png, prompt, src, secs, usage)
    print('Next: compare it with the accent render (same layout and words?), then: accent.py pair <folder> <plain> <accent>')


def cmd_fix(a):
    load(a.folder)
    src = Path(a.image)
    if not src.exists():
        die(f'{src} not found')
    prompt = fix_prompt(a.change)
    png, secs, usage = call(a.folder, prompt, src)
    save(next_path(Path(a.folder) / 'out', f'{src.stem}-fix'), png, prompt, src, secs, usage)


def rendered_accent(img, planned):
    """the accent as it actually rendered: the median of pixels near the planned hue and saturated"""
    _, _, ph = oklch(planned)
    small = img.convert('RGB').resize((192, 128))
    hits = []
    px = small.tobytes()
    for r, g, b in zip(px[0::3], px[1::3], px[2::3]):
        hx = f'#{r:02X}{g:02X}{b:02X}'
        _, c, h = oklch(hx)
        if c > .1 and hue_gap(h, ph) < 35:
            hits.append((r, g, b))
    if len(hits) < 30:
        return None, 0
    # the lit half of the accent reads as "the colour"; the shadow half pulls it muddy
    hits.sort(key=lambda p: colorsys.rgb_to_hsv(*(v / 255 for v in p))[2])
    lit = hits[len(hits) // 2:]
    r, g, b = (sorted(c)[len(c) // 2] for c in zip(*lit))
    return f'#{r:02X}{g:02X}{b:02X}', round(100 * len(hits) / (192 * 128), 1)


def cmd_pair(a):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        die('missing package. Run: python3 -m pip install requests pillow')
    page = load(a.folder)
    pal = page['palette']
    plain, acc = Image.open(a.plain).convert('RGB'), Image.open(a.accent).convert('RGB')
    real, share = rendered_accent(acc, pal['accent'][1])
    if real:
        drift = hue_gap(oklch(real)[2], oklch(pal['accent'][1])[2])
        print(f'accent rendered as {real} ({share}% of the frame, {drift:.0f} deg from the planned {pal["accent"][1]})')
        if drift > 15:
            print('  the rendered accent drifted: the pair card shows the rendered hex, so your swatch matches the page')
    else:
        real = pal['accent'][1]
        print('could not find the accent on the render; using the planned hex')
    W, H, P = 1536, 1024, 40
    card = Image.new('RGB', (W * 2 + P * 3, H + P * 2 + 170), '#F4F2EE')
    card.paste(plain, (P, P))
    card.paste(acc, (W + P * 2, P))
    d = ImageDraw.Draw(card)

    def font(sz):
        for f in ('Inter.ttf', 'Arial.ttf', '/System/Library/Fonts/Helvetica.ttc', 'C:/Windows/Fonts/arial.ttf',
                  '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'):
            try:
                return ImageFont.truetype(f, sz)
            except OSError:
                pass
        return ImageFont.load_default()
    y = H + P + 30
    for x, (name, hx) in ((P, pal['field']), (P + 520, pal['ink']), (W + P * 2, (pal['accent'][0], real))):
        d.rectangle([x, y, x + 110, y + 110], fill=hx)
        d.text((x + 130, y + 18), name, fill='#111', font=font(40))
        d.text((x + 130, y + 68), hx.upper(), fill='#555', font=font(28))
    dest = Path(a.folder) / 'out' / 'pair.png'
    card.save(dest)
    print(f'saved {dest}')
    print(f'Swatches: {pal["field"][0]} {pal["field"][1]} · {pal["ink"][0]} {pal["ink"][1]} · {pal["accent"][0]} {real}')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name in ('init', 'check'):
        sub.add_parser(name).add_argument('folder')
    r = sub.add_parser('render'); r.add_argument('folder'); r.add_argument('--n', type=int, default=2)
    p = sub.add_parser('plain'); p.add_argument('folder'); p.add_argument('image')
    f = sub.add_parser('fix'); f.add_argument('folder'); f.add_argument('image'); f.add_argument('change')
    q = sub.add_parser('pair'); q.add_argument('folder'); q.add_argument('plain'); q.add_argument('accent')
    a = ap.parse_args()
    {'init': cmd_init, 'check': cmd_check, 'render': cmd_render, 'plain': cmd_plain, 'fix': cmd_fix, 'pair': cmd_pair}[a.cmd](a)


if __name__ == '__main__':
    main()

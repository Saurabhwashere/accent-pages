---
name: accent-pages
description: Design a landing-page hero twice, first in two quiet colours and then with one bold accent colour, so you can see how a single accent changes the way a page feels. Use when someone wants a hero mockup, a before/after colour comparison, help picking an accent colour for a brand, or "the accent colour trick" for a landing page.
---

# accent-pages

One page, two versions: **plain** (two quiet colours) and **accent** (the same page plus one colour from the far side of
the colour wheel, used only on the hero subject). The script is `scripts/accent.py` in this skill's folder (call it `S`).
Run `python3 S/scripts/accent.py --help` for every command and flag.

## Before the first render
- Needs Python 3.9+, `python3 -m pip install requests pillow`, and `OPENAI_API_KEY` in the shell or in a `.env` file in
  the project folder. Never print, echo or commit the key.
- Each render is one paid OpenAI image call. A finished pair is usually 3 to 4 calls (2 accent tries, 1 plain, maybe
  1 fix). Tell the user that before the first render.

## Workflow
1. **Brief.** Ask the user what the brand sells and who it is for, one question at a time. Invent the rest.
2. **Fill `page.json`.** `accent.py init <folder>` writes an example (Copperline, a hair salon). Replace every field:
   - `subject`: one striking object or person, big enough to break the frame. The accent lives on it and nowhere else.
   - `accent_on` / `plain_as`: the subject with the accent, and the same subject in a quiet neutral (silver, white, grey).
   - `headline`: 1 to 3 short words, tied to the subject. `type`: typeface style and colour (the ink colour).
   - `ui`: a real site's nav, button and 1 to 2 small captions, so it reads as a landing page, not a poster.
   - `palette`: `field` (the background), `ink` (type), `accent`. Two quiet colours, one loud one.
   - `ref` (optional, strongly recommended): path to a landing-page screenshot the user likes, e.g. from Pinterest.
     The render borrows its layout and craft, not its brand or colours. Without it, layouts come out plainer.
3. **Check.** `accent.py check <folder>` must print `palette OK`. It fails when the accent sits too close on the wheel
   to the quiet colours, the field is too saturated, or the ink is hard to read. Fix the hex, check again.
4. **Render the accent page.** `accent.py render <folder>` makes 2 tries in `out/`. Open each one and check:
   - every word, letter by letter: image models drop or merge letters in big headlines;
   - the accent appears only on the subject;
   - it reads as a website: nav, button, small text.
   Fix one problem per call: `accent.py fix <folder> <render> "<the one change>"`.
5. **Make the plain page.** `accent.py plain <folder> <chosen accent render>`. It edits that render, so layout and words
   stay put. Compare the two: same words, same layout, the accent gone. If it drifted, run `plain` again.
6. **Pair.** `accent.py pair <folder> <plain> <accent>` saves `out/pair.png` with swatches. Use the hexes it prints for
   anything downstream: they come from the render, not the plan.

## Taste rules
- The accent goes on the hero subject only: hair, a can, a lettuce, a sofa. Never on buttons, nav or small text.
- Quiet colours carry the page: a pale field and a dark ink. Name every colour with a plain word (Silver, Navy, Copper).
- If the plain version already looks exciting, the quiet colours are too loud. If the accent version does not jump,
  the accent is too close to the field on the wheel or too dull.
- Show the result as plain first, then accent: the change is the point.

---
name: plain-copy
description: Write user-facing copy that does not read as AI-generated. Use whenever writing or editing interface strings, headings, empty states, button labels, report prose, README text, or any other words a user will read in this project.
---

# Plain copy

Interface text in this project must read like a person wrote it. The list below
is derived from Wikipedia's "Signs of AI writing" field guide, narrowed to what
actually applies to product copy.

## Hard rules

1. **No em dashes.** Ever. Use a plain hyphen, a comma, a colon, or a full stop.
   This is a standing project rule and also the single most recognisable tell.
2. **No curly quotes or curly apostrophes** in source strings. Straight only.
3. **No emoji as decoration** in headings, labels, or bullets.
4. **Sentence case for headings**, never Title Case For Every Word.
5. **No bold for emphasis inside sentences.** Bold is for labels only.

## Words that are banned in UI copy

crucial, pivotal, vital, key (as adjective), robust, seamless, comprehensive,
leverage, utilize, delve, underscore, showcase, highlight (as verb), foster,
enhance, enrich, elevate, empower, curated, tailored, bespoke, vibrant, rich,
diverse array, testament, tapestry, landscape (figurative), journey (figurative),
unlock, supercharge, effortless, intuitive, powerful, cutting-edge, state-of-the-art,
meticulously, thoughtfully, carefully crafted, designed to, built to, serves as,
stands as, represents, reflects (figurative), Additionally (sentence-initial)

## Shapes to avoid

- **Participle tails.** "...sorted by score, ensuring the best results surface
  first." Cut everything after the comma, or make it its own sentence.
- **Rule of three.** "fast, simple, and reliable". Two is fine. Three reads as
  filler because it almost always is.
- **Negative parallelism.** "Not just a list, but a picture of your taste."
  "It's not X, it's Y." Say the thing directly.
- **Significance claims.** Do not tell the user that something is important,
  powerful, or meaningful. Show the number and let them decide.
- **Vague attribution.** "Studies show", "experts agree", "many users find".
- **Hedged padding.** "It's worth noting that", "It's important to remember".
- **Restating the obvious in a closing line.** No summary sentence at the end of
  a short block.

## What to do instead

- Prefer **is / has / does** over serves as / features / provides.
- Prefer the **concrete number** over the adjective. "70 swipes, 3 groups" beats
  "a rich picture of your taste".
- Say **what a thing does**, not what it signifies.
- Let short be short. A four-word empty state is better than a sentence.
- Contractions are fine. Fragments are fine. Dry is fine.

## Test before shipping a string

Read it aloud. If it sounds like a product landing page, a press release, or a
LinkedIn post, rewrite it. If you would not say it to someone sitting next to
you, do not put it on screen.

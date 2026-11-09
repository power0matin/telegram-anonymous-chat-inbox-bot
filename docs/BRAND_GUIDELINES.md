# WhisprLink Brand Guidelines

These guidelines keep the WhisprLink identity consistent across the README, documentation, GitHub settings, and any future website or bot profile. They describe the assets in [`assets/brand/`](../assets/brand/).

**Tagline:** Anonymous conversations, on your terms.
**Descriptor:** Random Chat · Anonymous Inbox · Private Messaging

## 1. Brand concept

WhisprLink is about two people talking without exposing who they are. The identity is built on that idea and nothing else: two voices, one message between them.

The brand should feel private, human, simple, and trustworthy, like an independent piece of software made with care rather than a corporate product. It avoids visual clichés such as shields, padlocks, masks, paper planes, speech bubbles with dots, and chain links.

## 2. The symbol

The symbol is a **W** made from three parts:

| Part | Meaning |
| --- | --- |
| **Left stroke** (a "V") | One participant's voice. |
| **Right stroke** (a "V") | The other participant's voice. |
| **Orange message shape** | The message, and the link between them. It replaces the middle vertex of the W, so the two voices connect through it rather than touching each other. |

The strokes carry no faces or figures, which keeps both participants anonymous. The message shape is a circle with a single square corner, the quietest possible reduction of a chat bubble. Its square corner points down and to the right, toward the other voice.

The gaps between the strokes and the message shape are deliberate negative space. They express discretion: the participants never meet directly, and the message is the only thing that travels between them.

### Construction

The symbol is drawn on a 128-unit square grid.

| Property | Value |
| --- | --- |
| Artwork bounds | 112 × 82 units, centred in the square |
| Stroke weight | 16 units, round caps and joins |
| Stroke angle | About 21° from vertical, identical on every arm |
| Message shape | 24 × 24 units, three corners rounded at 12 units, square corner at bottom right |
| Gap, strokes to message shape | About 5–6 units |
| Symmetry | The strokes are mirror images. Only the message shape's square corner breaks the symmetry. |

At small sizes the message shape reads as an orange dot and the fine inner stroke ends soften, but the W silhouette and the single accent remain recognisable.

### Wordmark and lockup

The wordmark is **WhisprLink**, written as one word with capital W and L, in Inter SemiBold (weight 600) with letter-spacing of −0.01 em. In the horizontal lockup the symbol is scaled to 0.75, sits one gap of 28 units from the wordmark, and is centred on the capital height of the text.

## 3. Colour

Deep charcoal is the foundation. Orange is the accent and appears once per composition, as the message shape.

| Role | Colour | Hex | Notes |
| --- | --- | --- | --- |
| Primary | Deep charcoal green | `#18211F` | Symbol, wordmark, dark backgrounds, body text. |
| Brand accent | Warm vivid orange | `#E56B45` | The message shape. Buttons and highlights, used sparingly. |
| Light background | Warm ivory | `#F4F2EA` | Light backgrounds, and the symbol and wordmark on charcoal. |
| White surface | Soft white | `#FFFFFF` | Cards and panels. |
| Secondary text | Muted gray-green | `#77817B` | Captions and supporting text. |
| Border | Soft gray | `#D8DDD7` | Dividers, outlines, and secondary text on charcoal. |
| Accent hover | Deep orange | `#C95534` | Hover and pressed states for orange UI elements. Not part of the logo. |

**Do not use purple, violet, lavender, or indigo**, and avoid gradients, glows, and glass effects.

### Contrast reference

Ratios use the WCAG 2.x formula.

| Combination | Ratio | Guidance |
| --- | --- | --- |
| Charcoal on ivory | 14.7:1 | Preferred for all text and the symbol. |
| Charcoal on white | 16.5:1 | Preferred for all text and the symbol. |
| Ivory on charcoal | 14.7:1 | Preferred for all text on dark. |
| Soft gray `#D8DDD7` on charcoal | 11.9:1 | Secondary text on dark. |
| Orange on charcoal | 5.1:1 | Fine for the message shape and large text. |
| Charcoal on orange | 5.1:1 | Use this for text on orange buttons. |
| Orange on ivory | 2.9:1 | Below 3:1. Fine for the logo's message shape, **not for text or thin lines.** |
| White on orange | 3.2:1 | Large or bold text only. Prefer charcoal on orange. |
| Deep orange on ivory | 3.9:1 | For orange text on light backgrounds use `#C95534`, and only at large sizes. |
| Muted `#77817B` on ivory | 3.6:1 | Large text and non-essential captions only. |
| Muted `#77817B` on white | 4.0:1 | Large text and captions only. |
| Muted `#77817B` on charcoal | 4.1:1 | Large text only. |

## 4. Logo files

All files are in `assets/brand/`. None contain raster images, embedded fonts, or external resources.

| File | Purpose |
| --- | --- |
| `whisprlink-icon.svg` | Symbol only, 128 × 128, transparent background. For favicons, avatars, and app icons. The ink colour switches to ivory when the viewer prefers a dark colour scheme. |
| `whisprlink-logo.svg` | Horizontal lockup, adapts to the viewer's light or dark colour scheme. Default choice where you cannot choose between the light and dark files. |
| `whisprlink-logo-light.svg` | Lockup fixed for light backgrounds (charcoal and orange). |
| `whisprlink-logo-dark.svg` | Lockup fixed for dark backgrounds (ivory and orange). |
| `whisprlink-monochrome.svg` | Single-colour lockup. Uses the CSS `color` property and defaults to charcoal. For print, stamps, embossing, and one-colour contexts. |
| `whisprlink-social-preview.svg` | 1280 × 640 GitHub social preview, the editable source. |
| `whisprlink-social-preview.png` | PNG export of the social preview, for upload to GitHub. |

The adaptive files (`whisprlink-icon.svg` and `whisprlink-logo.svg`) follow the operating system or browser colour preference. This may not match a theme chosen inside GitHub, so the README uses the fixed light and dark files inside a `<picture>` element instead.

## 5. Light and dark usage

- **On light backgrounds** use `whisprlink-logo-light.svg`: charcoal symbol and wordmark with the orange message shape.
- **On dark backgrounds** use `whisprlink-logo-dark.svg`: ivory symbol and wordmark with the same orange message shape.
- **On one-colour backgrounds or in print** use `whisprlink-monochrome.svg` in charcoal, white, or ivory. All gaps are preserved so the W stays legible without the orange.
- **On an orange background** use the monochrome file in charcoal. Never place the full-colour logo on orange, because the message shape would disappear.

### Appropriate backgrounds

| Background | File | Notes |
| --- | --- | --- |
| Ivory `#F4F2EA` | Light | Primary light surface. |
| White `#FFFFFF` | Light | |
| Charcoal `#18211F` | Dark | Primary dark surface, used by the social preview. |
| Soft gray `#D8DDD7` | Monochrome (charcoal) | The full-colour logo has too little contrast here. |
| Orange `#E56B45` | Monochrome (charcoal) | |
| Photographs | Monochrome | Only over calm, evenly lit areas with strong contrast. |

## 6. Clear space

Keep an empty margin around the symbol or lockup on every side equal to **one quarter of the symbol's width** (28 units on the 128-unit grid, or about 21 px in the 434 px lockup). Keep other logos, text, and edges out of this margin.

The SVG files include only a few pixels of padding so the strokes are not clipped. Provide the clear space in your layout.

## 7. Minimum sizes

| Asset | Digital | Print (recommended) |
| --- | --- | --- |
| Symbol (`whisprlink-icon.svg`) | 16 px. Use 24 px or larger where the message shape needs to read as more than a dot. | 8 mm |
| Horizontal lockup | 120 px wide. Below this, use the symbol alone. | 30 mm wide |

The symbol was checked at 16, 24, 32, 48, and 64 px. Print minimums are recommendations and have not been proofed on paper.

## 8. Incorrect usage

Do not:

- Recolour the symbol, especially with purple, violet, lavender, or indigo.
- Colour the strokes orange or the message shape charcoal in the full-colour logo.
- Use the light-background logo on dark or mid-tone backgrounds, or the dark-background logo on light ones.
- Place the full-colour logo on orange, or on photographs and patterns that reduce contrast.
- Stretch, squash, rotate, skew, or mirror the symbol. Mirroring moves the message shape's square corner.
- Separate the message shape from the strokes, resize it, or move it.
- Add outlines, drop shadows, glows, gradients, bevels, or glass effects.
- Redraw the wordmark in a different typeface, change its weight, or change its capitalisation (write **WhisprLink**, never "Whisprlink" or "whisprlink" in the logo).
- Put the symbol inside a speech bubble, shield, padlock, or other container.
- Use the deep orange `#C95534` as a logo colour. It is for UI hover states.
- Crowd the logo inside its clear space.

## 9. Typography

The wordmark is live text, not outlines, so the SVG files do not embed a font. Each file specifies this font stack, in this order:

```
Inter, 'Segoe UI', system-ui, -apple-system, 'Helvetica Neue', Arial, sans-serif
```

Inter is the intended face. If it is not installed, the next available system sans-serif is used, and the lockup stays correct because the text is left-aligned beside the symbol. Letter widths will differ slightly between fonts.

For anything where exact letterforms matter (print, merchandise, app store graphics, social images), open the SVG in a vector editor with Inter SemiBold installed and convert the wordmark to outlines first. The social preview PNG was exported with Inter.

| Use | Recommendation |
| --- | --- |
| Wordmark | Inter SemiBold (600), letter-spacing −0.01 em |
| Headings | Inter SemiBold (600) |
| Body text | Inter Regular (400), or the system sans-serif stack above |
| Code and identifiers | A system monospace stack, for example `ui-monospace, SFMono-Regular, Menlo, Consolas, monospace` |
| Persian text | A Persian-capable sans-serif such as Vazirmatn, falling back to the system font. Inter has no Persian glyphs. |

Inter and Vazirmatn are open-source fonts (SIL Open Font License). If you ever bundle them, follow that license.

## 10. GitHub social preview

Upload `assets/brand/whisprlink-social-preview.png` under **Settings → General → Social preview**. GitHub requires a raster image, so the SVG stays as the editable source. If you change the SVG, re-export the PNG at 1280 × 640.

## 11. Design tokens

This repository has no frontend, website, or design system, so there is no token file. The colours and type stack above are the single source of truth. If a website or app is added later, create tokens from this document at that point.

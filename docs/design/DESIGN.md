---
name: Tabi Talk
colors:
  surface: '#f6faff'
  surface-dim: '#cfdce8'
  surface-bright: '#f6faff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#ebf5ff'
  surface-container: '#e3effc'
  surface-container-high: '#ddeaf6'
  surface-container-highest: '#d7e4f0'
  on-surface: '#111d26'
  on-surface-variant: '#424653'
  inverse-surface: '#26323b'
  inverse-on-surface: '#e5f2ff'
  outline: '#737784'
  outline-variant: '#c3c6d5'
  surface-tint: '#1459c3'
  primary: '#004eb3'
  on-primary: '#ffffff'
  primary-container: '#2b67d1'
  on-primary-container: '#e9edff'
  inverse-primary: '#b0c6ff'
  secondary: '#4a6632'
  on-secondary: '#ffffff'
  secondary-container: '#c8eaa8'
  on-secondary-container: '#4e6b36'
  tertiary: '#38586a'
  on-tertiary: '#ffffff'
  tertiary-container: '#507083'
  on-tertiary-container: '#def1ff'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#d9e2ff'
  primary-fixed-dim: '#b0c6ff'
  on-primary-fixed: '#001944'
  on-primary-fixed-variant: '#00429a'
  secondary-fixed: '#cbedab'
  secondary-fixed-dim: '#b0d191'
  on-secondary-fixed: '#0c2000'
  on-secondary-fixed-variant: '#334e1c'
  tertiary-fixed: '#c6e7fd'
  tertiary-fixed-dim: '#aacbe0'
  on-tertiary-fixed: '#001e2c'
  on-tertiary-fixed-variant: '#2a4a5c'
  background: '#f6faff'
  on-background: '#111d26'
  surface-variant: '#d7e4f0'
typography:
  display-lg:
    fontFamily: Jua
    fontSize: 30px
    fontWeight: '400'
    lineHeight: 38px
  headline-lg:
    fontFamily: Jua
    fontSize: 24px
    fontWeight: '400'
    lineHeight: 32px
  headline-md:
    fontFamily: Jua
    fontSize: 20px
    fontWeight: '400'
    lineHeight: 28px
  headline-sm:
    fontFamily: Jua
    fontSize: 18px
    fontWeight: '400'
    lineHeight: 24px
  body-lg:
    fontFamily: Gowun Dodum
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-md:
    fontFamily: Gowun Dodum
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 21px
  body-sm:
    fontFamily: Gowun Dodum
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 17px
  label-lg:
    fontFamily: Gowun Dodum
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 18px
  label-md:
    fontFamily: Gowun Dodum
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
  label-sm:
    fontFamily: Gowun Dodum
    fontSize: 11px
    fontWeight: '400'
    lineHeight: 14px
rounded:
  sm: 0.5rem
  DEFAULT: 1rem
  md: 1.5rem
  lg: 2rem
  xl: 3rem
  full: 9999px
spacing:
  gutter: 0.75rem
  margin: 1.25rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 0.75rem
  space-lg: 1.25rem
  space-xl: 1.75rem
---

## Brand & Style
This design system establishes a gentle, minimal, and welcoming travel companion tailored for Korean independent travelers exploring Japan. The visual language evokes the tranquility of a quiet neighborhood cafe or a breezy morning in Kamakura: uncluttered, softly illuminated, and effortlessly intuitive. 

Rather than overwhelming the user with hyper-dense itineraries or cluttered maps, the interface breathes through generous negative space, cloud-soft pastels, and tactile, pill-shaped interactions. It balances conversational intimacy with clear utility. Visual weight is kept featherlight: sharp borders, harsh contrasts, and stark outlines are entirely absent. In their place, organic surface contrast and subtle, tinted ambient light define structure and sequence.

## Colors
The palette is derived from natural Japanese landscapes and soft stationery tones, anchored by deep legible ink rather than stark black.

### Palette Architecture
- **Base Canvas (`#F5FAF6`):** An airy pale mint-white tint that removes screen glare and establishes a soothing atmosphere.
- **Card & Sheet Surfaces (`#FFFFFF`):** Pure white floats atop the canvas to produce subtle, natural depth without borders.
- **Primary Indigo (`#2B67D1`):** Applied deliberately to focal actions, selected states, bottom-bar active indicators, and digital stamp seals. Always pairs with pure white text (`#FFFFFF`).
- **Culinary Sage (`#E6F5D8` base, `#C8EAA8` active/emphasis):** Denotes gourmet dining, street food discoveries, cafes, and dietary filters.
- **Transit & Horizon Blue (`#E3F1FB` base, `#BFE0F6` active/emphasis):** Used for user chat bubbles, landmarks, transit notices, and contextual neighborhood tags.
- **Typography & Details:** Primary text is Deep Ink (`#1E2A33`), providing high legibility while maintaining a soft printed feel. Secondary and auxiliary details use Muted Slate (`#56636C`).

## Typography
Typography bridges expressive warmth with clear, sustained readability across Korean and Japanese naming conventions.

- **Display & Headlines (`Jua`):** A rounded, hand-crafted sans-serif with friendly proportions. Used exclusively for screen headers, place names, conversational greetings, and section breaks. It gives the product its distinctive, approachable character without descending into juvenile forms.
- **Body & Labels (`Gowun Dodum`):** A warm, humanist Korean typeface with refined proportions and organic stroke terminals. It renders dense travel tips, operational hours, addresses, and chat text with pristine clarity and eye comfort.

Korean typographic spacing rules require a slightly tighter letter spacing for headlines (`-0.02em`) and relaxed line heights on body copy to maintain legibility when mixed with Japanese kanji or katakana place names.

## Layout & Spacing
The layout philosophy centers on an airy, mobile-first canvas optimized for single-handed use on a standard 390x844 viewport.

- **Screen Grid & Margins:** A flexible single-column layout flanked by fixed `1.25rem` (20px) outer canvas margins. Element clusters conform to an 8pt spatial baseline with sub-steps of 4px.
- **Vertical Flow:** Conversational threads and recommendation feeds stack with generous vertical separations (`space-lg` between distinct message clusters, `space-sm` between conversational bursts).
- **Safe Areas:** Generous padding at the bottom of the viewport (`min-height: 84px`) accommodates floating prompt bars and the mobile home indicator without obscuring conversation logs.

## Elevation & Depth
Depth is strictly featherweight. The system rejects multi-layered drop shadows, dark directional casts, and hard stroke borders.

- **The Ambient Veil:** All elevated elements (floating cards, tooltips, sheets) utilize exactly one unified soft shadow:
  `box-shadow: 0 6px 20px rgba(30, 42, 51, 0.07);`
- **Surface Contrast:** Depth is primarily established through surface tinting. The `#F5FAF6` background provides a tinted base that lets `#FFFFFF` cards visually lift without needing heavy borders or sharp contrast.
- **Conversational Hierarchy:** System and guide recommendations sit on `#FFFFFF` elevated cards; user messages rest flush on `#E3F1FB` capsules without shadows.

## Shapes
Shapes are soft, continuous, and friendly, removing all sharp vertices from the user's field of view.

- **Full Pill (`border-radius: 9999px`):** Applied uniformly to action buttons, search bars, text input fields, quick-reply tags, and segmented pills.
- **Content Cards:** Molded with a consistent `24px` radius on all four corners.
- **Modal Sheets & Overlays:** Bottom sheets feature a `28px` radius on top-left and top-right corners, with zero radius at the bottom edge.
- **Conversational Bubbles:** User bubbles feature an asymmetric radius (`20px` all around, collapsing to `6px` at the bottom-right tail). System messages follow the reverse geometry (`6px` at bottom-left).

## Components

### Buttons
- **Primary Action:** Pill-shaped, background `#2B67D1`, text `#FFFFFF` (`Jua`, 16px). Height is 52px for primary CTAs. Ambient shadow applied. Active state slightly scales down to `0.98`.
- **Secondary / Category Pill:** Background `#E6F5D8` (food) or `#E3F1FB` (sights). Deep Ink text (`#1E2A33`), borderless, height 40px, full pill shape.

### Input Fields & Search Bars
- Pill-shaped container (`border-radius: 9999px`) in pure `#FFFFFF`.
- Ambient shadow applied (`0 6px 20px rgba(30, 42, 51, 0.07)`). Zero stroke or border.
- Placeholder text in `#56636C`. Deep Ink user text with an embedded primary blue submit button at the trailing edge.

### Chips & Filter Tags
- Height 34px, fully pill-shaped.
- **Unselected:** Transparent or `#FFFFFF` with muted text.
- **Selected (Food):** `#C8EAA8` background, `#1E2A33` text.
- **Selected (Transit/Sight):** `#BFE0F6` background, `#1E2A33` text.

### Cards & Recommendations
- Background `#FFFFFF`, corner radius `24px`, padding `1.25rem`.
- One ambient shadow, no borders.
- Imagery inside cards conforms to an internal `16px` radius. Tag pills float inside the card with `#F5FAF6` or pastel category tints.

### Bottom Sheets
- White surface `#FFFFFF` with `28px` top radius and ambient shadow cast upwards.
- Includes a muted pill drag indicator (36px wide, 4px thick, color `#E3F1FB` or tint-neutral) centered at 8px from the top.

### Selection Controls (Checkboxes & Radios)
- Fully rounded circular glyphs (22px).
- Inactive state is a soft `#E3F1FB` solid circle without harsh borders.
- Active state fills with `#2B67D1` containing a 2px rounded white check icon.

### Iconography Style
- Exclusively 2px stroke weight, rounded line terminals (`stroke-linecap: round`, `stroke-linejoin: round`).
- Pure single-color strokes matching the accompanying text tone (`#1E2A33` or `#2B67D1`).
- Strictly geometric and minimal; no emojis, complex multi-color assets, or radial burst decorations.
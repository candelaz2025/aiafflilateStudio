# Design System: AI Studio Pro & Affiliate Auto Studio
**Project ID:** `affiliate-auto-studio-v7`  
**Version:** 7.10.0  
**Design Philosophy:** Metric Flow (Clean Light) + Highfield Obsidian (Deep Cosmic Dark)

---

## 1. Visual Theme & Atmosphere

AI Studio Pro is an enterprise-grade AI video generation and affiliate marketing automation platform. Its visual aesthetic combines high-density productivity tooling with the refined, cinematic feel of modern creative studios (Popcont & Highfield).

- **Highfield Obsidian Dark Mode (`[data-theme="dark"]`):** The primary operating environment. Uses deep space void backgrounds (`#090D16`), layered with rich obsidian surfaces (`#111827`), translucent glassmorphic navigation bars (`backdrop-filter: blur(16px)`), and controlled radial ambient glows (`rgba(37, 99, 235, 0.15)` and `rgba(16, 185, 129, 0.12)`).
- **Metric Flow Light Mode (`:root`):** A razor-sharp, distraction-free daylight interface built on slate canvases (`#F8FAFC`), crisp white elevated cards (`#FFFFFF`), and refined structural borders (`#E2E8F0`).
- **Atmosphere Keywords:** *Cinematic, High-Precision, Glassmorphic, Fluid, Focused, Futuristic yet Functional.*

---

## 2. Color Palette & Functional Roles

Every color in the system serves an unambiguous role, balancing high-contrast readability with subtle neon energy.

| Role | Descriptive Name | Hex Code (Light / Dark) | CSS Variable | Functional Usage |
| :--- | :--- | :--- | :--- | :--- |
| **Primary Brand** | Electric Cobalt Blue | `#2563EB` / `#3B82F6` | `--color-primary` | Primary actions, CTA buttons, active sidebar tabs, selection highlights |
| **Primary Subtle**| Soft Sky Tint | `#EFF6FF` / `rgba(59,130,246,0.15)` | `--color-primary-subtle` | Active badge backgrounds, highlight pill containers |
| **Secondary** | Emerald Matrix Green | `#10B981` / `#34D399` | `--color-secondary` | Connected channels, online bots, high-converting commissions, verified checks |
| **Warning / Notice**| Sunburst Amber | `#F59E0B` / `#FBBF24` | `--color-tertiary` | Pending jobs, rate-limit warnings, draft states, moderate commissions |
| **Destructive** | Crimson Flare | `#EF4444` / `#F87171` | `--color-danger` | Disconnect channels, cancel actions, error notifications, delete items |
| **Canvas Deep** | Highfield Obsidian Void | `#F8FAFC` / `#090D16` | `--color-bg` | Main app background canvas, radial light source parent |
| **Elevated Surface**| Obsidian Slate | `#FFFFFF` / `#111827` | `--color-surface` | Primary content cards, sidebar panels, modals, data tables |
| **Subtle Container**| Midnight Muted Slate | `#F1F5F9` / `#182334` | `--color-surface-subtle` | Input backgrounds, code preview blocks, inactive channel cards |
| **Border Structural**| Cold Slate Hairline | `#E2E8F0` / `#1E293B` | `--color-border` | Card outlines, dividers, table row borders |
| **Text Main** | Pure Titanium / Midnight | `#0F172A` / `#F8FAFC` | `--color-text-main` | Headers, primary titles, emphasized metrics |
| **Text Muted** | Cool Slate Grey | `#64748B` / `#94A3B8` | `--color-text-muted` | Descriptive subheadings, timestamps, secondary parameters |
| **Text Subtle** | Steely Dust | `#94A3B8` / `#64748B` | `--color-text-subtle` | Placeholders, inactive state icons, footnote disclaimers |

---

## 3. Typography Rules

The typography system uses a tri-font hierarchy to ensure maximum clarity across international Latin characters, natural Thai scripts, and technical numerical metrics.

1. **Primary Interface:** `Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif`  
   - Used for headers, dashboard analytics, cards, and interactive controls.
   - Letter-spacing: `-0.015em` on headings for optical tightness; `0` on body copy.
2. **Thai Script Typography:** `Prompt, sans-serif`  
   - Handled seamlessly through modern web fallback. Provides clean, modern loopless letterforms ideal for digital creator interfaces.
3. **Monospace & Telemetry:** `'IBM Plex Mono', 'SFMono-Regular', Consolas, monospace`  
   - Exclusively applied to API keys, token hashes, model token counters, prices (฿), timestamps, and pill badges (`.mono`).

### Type Scale

| Level | Size | Weight | Line Height | CSS / Usage |
| :--- | :--- | :--- | :--- | :--- |
| **Display 1** | `28px` - `36px` | 800 (Extrabold) | `1.2` | Hero headlines, landing titles |
| **Heading 1** | `22px` - `24px` | 800 (Extrabold) | `1.25` | Page titles (`.page-title`), major view headers |
| **Heading 2** | `17px` - `18px` | 700 (Bold) | `1.35` | Card titles, section headers, modal titles |
| **Heading 3** | `14px` - `15px` | 600 (Semibold) | `1.4` | Subsections, item titles, channel names |
| **Body Large**| `14px` | 400 (Regular) / 500 | `1.5` | Lead paragraphs, modal descriptions |
| **Body Regular**| `13px` | 400 (Regular) | `1.5` | Standard body copy, inputs, table cell data |
| **Caption / Small**| `11px` - `12px` | 500 (Medium) | `1.4` | Helper hints, channel metadata, timestamps |
| **Micro Badge**| `10px` | 700 (Bold) | `1.0` | Chips, status pills, model aspect tags |

---

## 4. Component Stylings & Tokens

### 4.1 Buttons (`.btn`)
- **Geometry:** Subtly rounded rectangular (`border-radius: 10px / var(--radius-md)`), height `38px` (default) or `30px` (small `.btn-sm`).
- **Primary (`.btn-primary`):** Electric blue solid fill (`var(--color-primary)`), white text, subtle elevation (`box-shadow: 0 1px 2px rgba(0,0,0,0.05)`). On hover: deepens color, smooth translateY(-1px) translation.
- **Secondary (`.btn-secondary`):** Translucent sky/slate tint with a 1px border matching `--color-primary-border`.
- **Ghost (`.btn-ghost`):** Zero fill, transparent border, subtle hover highlight (`var(--color-surface-subtle)`).
- **Danger (`.btn-danger`):** Crimson flare background with soft glow on hover.

### 4.2 Cards & Containers (`.mf-card`)
- **Geometry:** `border-radius: 14px / var(--radius-lg)`.
- **Fill:** Solid `--color-surface` with 1px border `--color-border`.
- **Lighting & Glow:** In dark mode, cards feature a 1px top highlight `rgba(255,255,255,0.06)` simulating overhead studio key lighting.
- **Padding:** Compact `16px` or standard `20px` to maintain high data density.

### 4.3 Chips & Status Pills (`.chip`, `.hero-status-pill`)
- **Geometry:** Full pill shape (`border-radius: 9999px / var(--radius-full)`).
- **Typography:** `10px` - `11px`, `font-weight: 700`, monospace font family.
- **Variants:**
  - `.chip-primary`: Sky blue tint with electric blue border.
  - `.chip-success`: Emerald green tint with glowing dot indicator (`.status-dot-pulse`).
  - `.chip-warning`: Sunburst amber tint.
  - `.chip-muted`: Slate tint for disconnected or inactive entities.

### 4.4 Form Controls & Inputs (`.form-input`, `.form-select`, `.form-textarea`)
- **Geometry:** `border-radius: 10px`, height `38px` (inputs).
- **Background:** `var(--color-surface-subtle)` or `var(--color-surface)` depending on context.
- **Borders:** 1px solid `var(--color-border)`.
- **Focus State:** 2px ring in `var(--color-primary)` with subtle ambient glow (`0 0 0 3px rgba(37,99,235,0.2)`).

### 4.5 9:16 Smartphone Mockup Player (`#mockup-phone`)
- **Aspect Ratio:** Fixed vertical mobile viewport 9:16 (typically `280px` × `498px` or `320px` × `568px`).
- **Chassis:** Outer metallic bezel border (`#1E293B`), dynamic notch/island header, glass sheen reflection.
- **Real-time Canvas:** Live HTML5 2D canvas displaying dynamic hooks, avatars, audio waveforms, and conversion stickers.

### 4.6 Auto-Post Switches (`.switch-label`)
- **Track:** Capsule `36px` × `20px`, smooth transition `var(--trans-fast)`.
- **Thumb:** White circle `16px`, smooth translateX on active state with green glow.

---

## 5. Layout & Spatial Geometry

- **Base Unit:** 4px / 8px grid system (`4px`, `8px`, `12px`, `16px`, `20px`, `24px`, `32px`, `48px`).
- **App Shell Structure:**
  - **Sidebar:** Left rail `240px` wide (collapses to `72px` icon-only mode).
  - **Topbar Navigation:** Fixed `64px` header with blurred backdrop (`rgba(9, 13, 22, 0.85)`).
  - **Main Viewport:** Fluid container with max-width `1440px`, centered padding `24px`.
- **Grid Layouts:**
  - Channel cards: `grid-template-columns: repeat(auto-fit, minmax(320px, 1fr))`.
  - Feature cards: `grid-template-columns: repeat(3, 1fr)` on desktop, collapsing to 1 column on mobile (`< 768px`).
  - Calendar planner: 7-column responsive CSS grid with time-block cards.

---

## 6. Depth, Elevation & Glassmorphism

```
Level 0: Deep Canvas (#090D16)
Level 1: Subtle Well (#182334 / border: #162032)
Level 2: Standard Card Surface (#111827 / border: #1E293B / shadow-sm)
Level 3: Floating Dropdown & Popover (backdrop-filter: blur(12px) / shadow-md)
Level 4: Modal Dialog Backdrop (rgba(0,0,0,0.7) blur(8px) + Card / shadow-xl)
```

---

## 7. Machine-Readable Tokens Export

The complete token definitions are maintained in:
- **W3C Format:** [`design-tokens.json`](file:///Users/candelaz/Desktop/AIStudio/design-tokens.json)
- **CSS Custom Properties:** [`static/tokens.css`](file:///Users/candelaz/Desktop/AIStudio/static/tokens.css) & [`static/styles.css`](file:///Users/candelaz/Desktop/AIStudio/static/styles.css)

# Hibiscus — visual style (app mapping)

The look of Hibiscus (web app and these docs) comes from the **Hibiscus design
system**, kept in the private repository `github.com/Bigkatoan/hibiscus-assets`. Its style guide
(`docs/style-guide.md` there) is the single source of truth for the palette, the mascot, the icons,
typography, the pixel unit and motion. This page only records how the app maps onto it.

Short version of the rules: a friendly **robot garden** in original pixel art drawn from code;
**1 art pixel = 2 CSS px everywhere** (no per-use scaling); **Nunito** for all text (system
monospace only for logs and code); colour 16×16 sprites for navigation and features, 8×8 `PxIcon`
glyphs for buttons and inline icons (no third-party icon sets, no emoji); day = parchment with wood
frames, night = indigo with flat indigo frames and hard shadows; one looping mascot per screen plus
the sidebar garden; everything stops under `prefers-reduced-motion`.

## How the assets get here
```bash
git -C ~/hibiscus-assets pull --ff-only
~/hibiscus-assets/tools/sync.sh frontend --favicon
```
This refreshes `frontend/public/pixel/` (sprites, `anim/` strips, `sprites.json`),
`frontend/public/icons/` (glyph SVGs), `frontend/public/fonts/` (Nunito + OFL),
`frontend/public/favicon.*` and `frontend/src/hibiscus/` (`PixelAnim.tsx`, `*.gen.ts`, CSS, `VERSION`).
**Never edit those copies**: change hibiscus-assets, rebuild, re-sync. Brand images in
`assets/brand/` are recomposed from the synced files with `tools/brand.py`. All of these are
covered by [ASSETS-LICENSE](https://github.com/Bigkatoan/Hibiscus/blob/main/ASSETS-LICENSE), not by
the AGPL.

The app imports only `fonts.css` and `motion.css` from the design system; its shadcn/Tailwind tokens
(`frontend/src/index.css`) carry the same colours as `tokens.css`, and
`frontend/src/lib/pixelTheme.test.ts` checks index.css, `pixelTheme.ts` and the synced `tokens.css`
against each other and against WCAG 2.1 AA.

## Mascot moods (`<Mascot mood>` → synced `<Hibi>`)
Hibi is a small robot arm holding a hibiscus (hero 48×48 art = 96 px, mini 24×24 = 48 px).

| App state | Mood |
|---|---|
| Empty list, welcome, default | `idle` |
| Login, onboarding | `wave` |
| Run preparing / running / exporting | `working` |
| Run succeeded | `happy` |
| Run queued / pausing / paused | `sleep` |
| Run failed, crash screen, 404, error | `sad` |
| Run cancelling / cancelled | `idle` |

Mapping in code: `frontend/src/lib/hibi.ts` (runs). Hibiscus Station has its own mapping in
[its repository](https://github.com/Bigkatoan/hibiscus-station).

## Feature icons (16×16 colour sprites, animate on hover via `.px-hover`)
| Feature | Sprite |
|---|---|
| Brand / home | `hibiscus_sparkle` |
| Datasets, recording | `icon_dataset` (seed bag) |
| Upload | `icon_upload` (crate + arrow) |
| Training runs, train step | `icon_train` (sprouting pot) |
| Models, run a policy | `icon_model` (hibiscus basket) |
| GPUs & queue | `icon_gpu` (chip) |
| Workspace settings | `icon_gear` |
| Robot / port | `icon_robot_arm`, `icon_plug` |
| Calibration | `icon_calibrate`, illustration `arm_home` |
| Cameras | `icon_camera` |
| Teleoperation | `icon_teleop` (joystick) |
| Emergency stop | `icon_estop` / `icon_estop_pressed`, frame `ui_button_estop` |
| Motor temperature banners | `icon_thermo_ok` / `_hot` / `_critical` |

Status chips use glyphs: `spinner` (busy, `.px-spin`), `pending` (queued), `check` (done),
`warning` (failed), `pause`; inline temperatures use `thermo`.

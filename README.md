# wallplay

Play with your Windows desktop from the terminal — recolour and filter your wallpaper, drop stickers, sticky notes, clocks and widgets onto it, arrange or animate your real desktop icons with physics and mouse reactions, or run a live interactive layer *behind* your icons.

Everything is **non-destructive**: on first run `wallplay` backs up your original wallpaper and icon positions so `wallplay restore` always puts your desktop back the way it was.

## Quick start

```powershell
.\.venv\Scripts\wallplay          # interactive studio shell
# or run one-liners directly:
.\.venv\Scripts\wallplay aurora
.\.venv\Scripts\wallplay add clock at=center
.\.venv\Scripts\wallplay add note "Ship the feature 🚀" at=top-right angle=-4
.\.venv\Scripts\wallplay icons heart
.\.venv\Scripts\wallplay icons flee 8
.\.venv\Scripts\wallplay live fireflies
.\.venv\Scripts\wallplay restore  # put original wallpaper & icon layout back
```

## Highlights

- **Bases & colours** — `solid`, `gradient`, `aurora`, `image <path>`, `original`
- **Stackable filters** — `tint`, `hue`, `duotone`, `saturate`, `bright`, `contrast`, `gray`, `sepia`, `invert`, `blur`, `pixelate`, `posterize`, `vignette`, `neon`, `glitch`, `dream`, `cartoon`, `sketch`, `mirror`, `flip`, `surprise`
- **Wallpaper layers & widgets** — `add text`, `add sticker`, `add shape`, `add note`, `add clock`, `add date`, `add calendar`, `add quote`, `add greeting`, `add sysinfo`, `add countdown`, `add image`, plus `layers`, `edit`, `remove`, `front`, `watch`
- **Desktop icon playground** — shapes (`circle`, `heart`, `spiral`, `wave`, `star`, `grid`, `line`, `diagonal`, `square`, `triangle`, `infinity`, `smile`, `scatter`) and live physics/mouse animations (`dance`, `orbit`, `gravity`, `follow`, `flee`, `magnet`, `rain`)
- **Live interactive wallpaper** (behind your icons) — `live snow`, `live fireflies`, `live bubbles`, `live matrix`, `live starfield`, `live fireworks`, `live rain`, `live pet [cat|dog|fox|dino|unicorn|...]`, `live stop`
- **Windows theme & accent** — `theme dark|light|toggle|glass on|off|bars on|off`, `accent <color|match|auto|random>`

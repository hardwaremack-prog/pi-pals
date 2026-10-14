# 🐣 Pi Pals

**Cute little figurines with a whole Raspberry Pi computer hiding inside.**

Pi Pals are seasonal characters — a chick, a dino, a piggy, a pumpkin, a snowman and more — each with a Raspberry Pi Zero 2 W tucked inside. Turn one on and it makes its own Wi‑Fi network, so you can connect from a phone or laptop and use its desktop over VNC. No router needed. A glowing heart on its chest beats to show how much battery is left.

They're something you'd actually want to carry around: a pocket coding lab, a desk buddy, an offline file-sharing hub, or a gift.

> **Status:** concept / design stage. "Pi Pals" is a working name.

<p align="center">
  <a href="docs/Pi-Pals-Concept.pdf"><img src="docs/screenshots/cover.png" width="420" alt="Pi Pals concept brief cover"></a>
</p>

📄 **[Read the full concept brief (PDF, 9 pages)](docs/Pi-Pals-Concept.pdf)**

---

## Meet the Pals

| Pal | Season |
|---|---|
| 🐥 **Pip the Chick** | Spring |
| 🦕 **Dot the Dino** | Any time |
| 🐷 **Penny the Piggy** | Any time |
| ☀️ **Sunny** | Summer |
| 🎃 **Gourdy the Pumpkin** | Fall |
| 🦃 **Gobbles the Turkey** | Thanksgiving |
| ⛄ **Flurry the Snowman** | Winter |
| 🐰 **Hop the Bunny** | Easter |

All original characters — no licensed ones.

## What's inside

Everything fits in a shell about the size of a **large orange** (roughly 90–100 mm tall — the Pi board alone is 65 mm wide).

- **Raspberry Pi Zero 2 W** — the brain (snappier over VNC than the original Zero W)
- **Battery board** — a PiSugar for the easy build, or a LiPo + charger/boost board + **MAX17048** fuel gauge for the budget build. Either reports battery % to the software.
- **Lithium cells** — one, or two matched protected cells **in parallel** for longer runtime (a few hours per ~1200 mAh with Wi‑Fi broadcasting)
- **One smart RGB LED** (WS2812B / "NeoPixel") behind a translucent heart
- **Power switch + USB‑C charging port** hidden under the base
- **Hidden vents** — the Zero 2 W gets warm in a sealed shell
- **Plastic or vinyl shell** — metallic paint or metal blocks Wi‑Fi

### Rough cost per unit

| Build | Cost |
|---|---|
| Easy build (PiSugar) | ~$60–75 |
| Budget build (LiPo + fuel gauge) | ~$38–49 |

## Software

```
  Phone / laptop ──Wi‑Fi──► Pal's own hotspot (NetworkManager)
                                   │
                                   ├──► VNC desktop (wayvnc, headless)
                                   ├──► My shell + task manager (shows battery %)
                                   └──► Heartbeat LED service
```

- **Hotspot:** NetworkManager starts a Wi‑Fi access point at boot with one `nmcli` command.
- **VNC:** wayvnc with a virtual display, so it works with no screen attached.
- **My shell & task manager** come preinstalled and show the battery level in the prompt, the login banner and the task manager.

## The heartbeat light

One multicolour LED glows through a translucent heart and pulses like a heartbeat:

| Battery | Colour | Beat |
|---|---|---|
| Healthy | 🟢 Green | Slow |
| Getting low | 🟡 Yellow | Medium |
| Low | 🔴 Red | Fast |

Plus a rainbow "wave" effect for fun.

**Wiring (3 wires):** 5V → pin 2 · Ground → pin 6 · Data → pin 19 through one small resistor. Needs SPI turned on in `raspi-config`. The LED is rated for 5V and the Pi's data line is 3.3V — most work fine, but if it flickers, add a cheap diode on the 5V wire.

## Unboxing

Flip the switch → the heart glows → join the Pal's Wi‑Fi → open VNC → you're on its desktop.

## Concept brief

The [concept PDF](docs/Pi-Pals-Concept.pdf) covers the idea, character lineup, hardware cutaway and costs, the heartbeat light, how the software fits together, shell and task-manager mockups, the unboxing flow, and a roadmap with price ideas.

![All pages of the Pi Pals concept brief](docs/screenshots/all-pages.png)

| Meet the lineup | A cutaway of Pip |
|---|---|
| ![Character lineup](docs/screenshots/characters.png) | ![Hardware cutaway](docs/screenshots/cutaway.png) |
| **The heartbeat light** | **What you see once connected** |
| ![Heartbeat light](docs/screenshots/heartbeat.png) | ![Software mockups](docs/screenshots/software.png) |

## Software in this repo

| File | What it does |
|---|---|
| [`software/pal-heartbeat.py`](software/pal-heartbeat.py) | Drives the heartbeat LED from the battery level. Smart LED by default; `--led rgb` for the older four-leg kind; `--demo` to cycle through the beats. |
| [`software/pal-heartbeat.service`](software/pal-heartbeat.service) | systemd service so the heartbeat starts at boot. Install notes are at the top of the file. |

## Things to sort out before selling

- **Lithium battery shipping rules**
- **Radio certification** for a device with Wi‑Fi
- **Age labeling** — clearly marked *not for small kids*, since it has a lithium battery
- Generic characters only, no licensed ones

---

*Part of the things I'm making :) — see also [PiMesh](https://github.com/hardwaremack-prog/PiMesh), [rpi-task-manager](https://github.com/hardwaremack-prog/rpi-task-manager) and [Pedal Power Station](https://github.com/hardwaremack-prog/pedal-power-station).*

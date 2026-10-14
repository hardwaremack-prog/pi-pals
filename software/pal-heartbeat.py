#!/usr/bin/env python3
"""
pal-heartbeat: makes the Pi Pal's RGB LED beat like a heart.

  Green, slow beat   battery above 50%   (healthy)
  Yellow, medium     20-50%
  Red, fast beat     below 20%           (charge me)
  Slow breathing     plugged in and charging
  Rainbow            `touch /run/pal/wave` (the "find my Pal" command)

Battery level is read from /run/pal/battery (a number 0-100) and charging state
from /run/pal/charging ("1" or "0"). Those files are written by pal-batteryd.

Wiring: one smart multicolour LED (WS2812B / "NeoPixel"), three wires:
  5V             (pin 2)                 -> LED 5V
  GND            (pin 6)                 -> LED GND
  GPIO10 / MOSI  (pin 19) -> 330 ohm     -> LED DIN
  Turn on SPI first:  sudo raspi-config  ->  Interface Options  ->  SPI
  Install:            sudo pip3 install --break-system-packages adafruit-circuitpython-neopixel-spi

Usage:
  pal-heartbeat.py               normal mode
  pal-heartbeat.py --demo        cycle through every state (good for testing the shell)
  pal-heartbeat.py --level 35    pretend the battery is at 35%
  pal-heartbeat.py --led rgb     use a plain 4-leg RGB LED on GPIO17/27/22 instead
  pal-heartbeat.py --anode       (with --led rgb) for a common-anode LED
"""
import argparse, math, os, time

BATTERY_FILE = "/run/pal/battery"
CHARGING_FILE = "/run/pal/charging"
WAVE_FILE = "/run/pal/wave"

PINS = {"red": 17, "green": 27, "blue": 22}
FPS = 50
BASE_GLOW = 0.06          # never fully dark between beats, so it always looks alive
GAMMA = 2.2               # eyes see brightness non-linearly; this makes fades look smooth

# Colour of each state as (r, g, b) 0-1. Green LEDs are much brighter than red,
# so "yellow" uses less green than you'd expect. Tune these on the real shell.
COLOURS = {
    "healthy": (0.00, 0.85, 0.25),
    "medium":  (1.00, 0.45, 0.00),
    "low":     (1.00, 0.00, 0.02),
    "unknown": (0.60, 0.60, 0.60),
}
# Beats per minute for each state: calm when full, worried when empty.
BPM = {"healthy": 54, "medium": 70, "low": 96, "critical": 120, "unknown": 40}


def heartbeat(t, bpm):
    """Brightness 0-1 at time t: a strong 'lub', a softer 'dub', then rest."""
    phase = (t % (60.0 / bpm))
    lub = math.exp(-((phase - 0.10) / 0.045) ** 2)
    dub = 0.55 * math.exp(-((phase - 0.32) / 0.055) ** 2)
    return BASE_GLOW + (1 - BASE_GLOW) * min(1.0, lub + dub)


def breathing(t, period=4.0):
    """Slow, smooth in-and-out glow used while charging."""
    return BASE_GLOW + (1 - BASE_GLOW) * (0.5 - 0.5 * math.cos(2 * math.pi * t / period))


def rainbow(t):
    h = (t * 0.5) % 1.0
    return tuple(max(0.0, min(1.0, abs((h * 6 + o) % 6 - 3) - 1)) for o in (0, 4, 2))


def read_file(path, default=None):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


def battery_state(forced_level=None):
    """Returns (state, level, charging)."""
    raw = forced_level if forced_level is not None else read_file(BATTERY_FILE)
    charging = read_file(CHARGING_FILE, "0") == "1"
    try:
        level = float(raw)
    except (TypeError, ValueError):
        return "unknown", None, charging
    if level > 50:
        state = "healthy"
    elif level >= 20:
        state = "medium"
    elif level >= 8:
        state = "low"
    else:
        state = "critical"
    return state, level, charging


def frame(t, state, charging):
    """What colour and brightness the LED should be right now."""
    colour = COLOURS["low" if state == "critical" else state]
    if charging:
        if state == "healthy" and frame.level is not None and frame.level >= 99:
            return COLOURS["healthy"], 0.5           # full: steady green
        return colour, breathing(t)
    return colour, heartbeat(t, BPM[state])
frame.level = None


class PixelLed:
    """One WS2812B/SK6812 smart LED on the SPI data pin (GPIO10, pin 19)."""
    def __init__(self):
        try:
            import board, neopixel_spi
            self.px = neopixel_spi.NeoPixel_SPI(board.SPI(), 1, auto_write=False,
                                                pixel_order=neopixel_spi.GRB)
        except Exception as e:
            print(f"No smart LED available ({e}); printing instead of lighting the LED.")
            self.px = None

    def show(self, rgb, brightness):
        value = tuple((c * brightness) ** GAMMA for c in rgb)
        if self.px is not None:
            self.px[0] = tuple(int(v * 255) for v in value)
            self.px.show()
        else:
            bar = "#" * int(brightness * 30)
            print(f"\r({value[0]:.2f},{value[1]:.2f},{value[2]:.2f}) {bar:<30}", end="", flush=True)

    def off(self):
        if self.px is not None:
            self.px.fill((0, 0, 0))
            self.px.show()


class Led:
    """Plain 4-leg RGB LED on three GPIO pins (the older wiring)."""
    def __init__(self, common_anode=False):
        try:
            from gpiozero import RGBLED
            self.led = RGBLED(PINS["red"], PINS["green"], PINS["blue"],
                              active_high=not common_anode, pwm=True)
        except Exception as e:                        # lets you test on a laptop
            print(f"No GPIO available ({e}); printing instead of lighting the LED.")
            self.led = None

    def show(self, rgb, brightness):
        value = tuple((c * brightness) ** GAMMA for c in rgb)
        if self.led:
            self.led.color = value
        else:
            bar = "#" * int(brightness * 30)
            print(f"\r({value[0]:.2f},{value[1]:.2f},{value[2]:.2f}) {bar:<30}", end="", flush=True)

    def off(self):
        if self.led:
            self.led.off()


def main():
    ap = argparse.ArgumentParser(description="Heartbeat LED for a Pi Pal")
    ap.add_argument("--demo", action="store_true", help="cycle through all states")
    ap.add_argument("--level", type=float, help="pretend battery level (0-100)")
    ap.add_argument("--led", choices=["pixel", "rgb"], default="pixel",
                    help="pixel = one smart LED (default), rgb = plain 4-leg RGB LED")
    ap.add_argument("--anode", action="store_true", help="common-anode LED (with --led rgb)")
    args = ap.parse_args()

    led = PixelLed() if args.led == "pixel" else Led(args.anode)
    demo = [(85, False), (35, False), (12, False), (5, False), (60, True)]
    start = time.monotonic()
    state, level, charging = "unknown", None, False
    last_check = -10.0
    wave_until = 0.0

    try:
        while True:
            t = time.monotonic() - start

            if t - last_check >= 2.0:                 # re-read the battery every 2 s
                last_check = t
                if args.demo:
                    lvl, chg = demo[int(t // 8) % len(demo)]
                    state, level, charging = battery_state(lvl)
                    charging = chg
                else:
                    state, level, charging = battery_state(args.level)
                frame.level = level
                if os.path.exists(WAVE_FILE):         # `pal wave` touches this file
                    wave_until = t + 3.0
                    try:
                        os.remove(WAVE_FILE)
                    except OSError:
                        pass

            if t < wave_until:
                led.show(rainbow(t), 1.0)
            else:
                rgb, brightness = frame(t, state, charging)
                led.show(rgb, brightness)

            time.sleep(1.0 / FPS)
    except KeyboardInterrupt:
        pass
    finally:
        led.off()


if __name__ == "__main__":
    main()

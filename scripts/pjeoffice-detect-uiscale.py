#!/usr/bin/env python3
# pjeoffice-detect-uiscale.py — emit Java sun.java2d.uiScale for PJeOffice Pro
#
# Java Swing pre-HiDPI (Metal L&F) renders at fixed 96dpi unless told otherwise.
# On modern Linux (Wayland + fractional scaling + high-DPI panels) this leaves
# the PJeOffice window minuscule. The fix is to pass a `-Dsun.java2d.uiScale=N`
# matching the effective DPI the user sees.
#
# Detection chain (worst → best):
#   1. Fallback: 1.0
#   2. Xft.dpi from XSettings (XWayland)
#   3. EDID physical size + native resolution (per connected monitor)
#   4. xrandr *logical* DPI (preferred on X11 — already nets out desktop scale)
#
# Formula:
#     uiScale = max(per_monitor_dpi) / 96.0
#
# Why xrandr-logical wins over raw EDID on X11:
# the EDID path reads the panel's NATIVE pixel grid (e.g. 3840x2160). But
# when the desktop already scales that output down (xrandr --scale, XFCE
# display scaling), the user interacts with a LOGICAL grid (e.g. 2560x1440).
# Scaling Java to the native DPI on top of a desktop that already scaled the
# panel double-counts and produces a huge window. xrandr reports the logical
# resolution, so logical_px / physical_size gives the DPI the user actually
# perceives — no double scaling. We only fall back to raw EDID when xrandr
# is unavailable (e.g. a pure-Wayland session with no XWayland).
#
# We still take max() across monitors: over-scaling a low-DPI panel is
# visually tolerable, but under-scaling a high-DPI one makes PJeOffice's
# tiny (~302x300 logical px) main window unusable.
#
# Override: set PJEOFFICE_UI_SCALE in env to any number (e.g. 1.5, 2, 2.5)
# to bypass detection. Useful for users who don't like the default sizing.
#
# Result rounded to a Java-friendly step (1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0).
# Floor is 1.5 (smaller than that the window is unusable on any laptop).
# Prints the chosen scale on stdout. On any error prints "1.5".

from __future__ import annotations
import os
import re
import subprocess
import sys


def round_to_step(x: float) -> float:
    steps = [1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 3.0]
    return min(steps, key=lambda s: abs(s - x))


def edid_scales() -> dict[str, float]:
    """Return {connector_name: native_dpi_scale} for each connected output."""
    out: dict[str, float] = {}
    drm = "/sys/class/drm"
    if not os.path.isdir(drm):
        return out
    for entry in sorted(os.listdir(drm)):
        base = os.path.join(drm, entry)
        edid = os.path.join(base, "edid")
        status_f = os.path.join(base, "status")
        modes_f = os.path.join(base, "modes")
        if not (os.path.isfile(edid) and os.path.isfile(status_f) and os.path.isfile(modes_f)):
            continue
        try:
            if open(status_f).read().strip() != "connected":
                continue
            mode = (open(modes_f).read().splitlines() or ["0x0"])[0]
            if "x" not in mode:
                continue
            w_str, h_str = mode.split("x")[:2]
            w = int(w_str)
            with open(edid, "rb") as f:
                edid_bytes = f.read()
            if len(edid_bytes) < 24 or w == 0:
                continue
            h_cm = edid_bytes[21]
            if h_cm == 0:
                continue
            dpi = w / (h_cm * 0.3937)
            connector = entry.split("-", 1)[1] if "-" in entry else entry
            out[connector] = dpi / 96.0
        except (OSError, ValueError):
            continue
    return out


def xrandr_logical_scales() -> dict[str, float]:
    """Return {connector: logical_dpi/96} from `xrandr --query`.

    Unlike raw EDID, this uses the *logical* resolution xrandr reports, which
    already nets out any desktop-level output scaling (xrandr --scale, XFCE/X11
    display scaling). On a panel the desktop scaled down, EDID sees the native
    pixel grid and over-scales; xrandr sees the logical grid the user actually
    interacts with. Only available when an X server (real or XWayland) is up.
    """
    out: dict[str, float] = {}
    try:
        proc = subprocess.run(
            ["xrandr", "--query"], capture_output=True, text=True, timeout=2,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return out
    # e.g. "DP-1 connected primary 2560x1440+0+0 (...) 600mm x 340mm"
    line_re = re.compile(
        r"^(\S+)\s+connected\b.*?\s(\d+)x(\d+)\+\d+\+\d+.*?\s(\d+)mm\s+x\s+(\d+)mm"
    )
    for line in proc.stdout.splitlines():
        m = line_re.match(line)
        if not m:
            continue
        connector = m.group(1)
        w = int(m.group(2))
        w_mm = int(m.group(4))
        if w == 0 or w_mm == 0:
            continue
        dpi = w / (w_mm / 25.4)
        out[connector] = dpi / 96.0
    return out


def mutter_scales() -> tuple[dict[str, float], bool]:
    """Return ({connector: logical_scale}, has_any) via Mutter DBus.

    `has_any` is False when the call fails (no GNOME, no Mutter, error).
    """
    try:
        proc = subprocess.run(
            [
                "gdbus", "call", "--session",
                "--dest", "org.gnome.Mutter.DisplayConfig",
                "--object-path", "/org/gnome/Mutter/DisplayConfig",
                "--method", "org.gnome.Mutter.DisplayConfig.GetCurrentState",
            ],
            capture_output=True, text=True, timeout=4,
        )
        if proc.returncode != 0:
            return {}, False
        text = proc.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {}, False

    # The reply contains a "logical monitors" array of tuples shaped like:
    #   (x, y, scale, transform, primary, [(connector, vendor, ...)], {})
    # We extract the (scale, connector) pairs by regex — robust enough since
    # the gdbus output is one long line of variants.
    out: dict[str, float] = {}
    # gdbus prints the first element of a variant array with an explicit
    # type prefix (e.g. `uint32 0`) and subsequent ones without — accept both.
    pattern = re.compile(
        r"\(\s*-?\d+,\s*-?\d+,\s*([0-9]+\.[0-9]+),\s*(?:uint32\s+)?\d+,\s*(?:true|false),\s*\[\(\s*'([^']+)'"
    )
    for m in pattern.finditer(text):
        scale = float(m.group(1))
        connector = m.group(2)
        out[connector] = scale
    return out, True


def xwayland_native_scaling_on() -> bool:
    try:
        proc = subprocess.run(
            ["gsettings", "get", "org.gnome.mutter", "experimental-features"],
            capture_output=True, text=True, timeout=2,
        )
        return "xwayland-native-scaling" in proc.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def xft_dpi_scale() -> float | None:
    try:
        proc = subprocess.run(
            ["xrdb", "-query"], capture_output=True, text=True, timeout=2,
        )
        for line in proc.stdout.splitlines():
            if line.startswith("Xft.dpi"):
                dpi = float(line.split()[-1])
                if dpi > 0:
                    return dpi / 96.0
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        pass
    return None


FLOOR_SCALE = 1.5


def main() -> int:
    # Manual override — power users / testers / unusual setups
    override = os.environ.get("PJEOFFICE_UI_SCALE", "").strip()
    if override:
        try:
            value = float(override)
            if value > 0:
                final = round_to_step(value)
                sys.stderr.write(
                    f"pjeoffice-detect-uiscale: env override "
                    f"PJEOFFICE_UI_SCALE={override} → {final}\n"
                )
                print(f"{final}")
                return 0
        except ValueError:
            sys.stderr.write(
                f"pjeoffice-detect-uiscale: bad PJEOFFICE_UI_SCALE={override!r}, "
                "falling back to detection\n"
            )

    session = os.environ.get("XDG_SESSION_TYPE", "").lower()
    xrandr = xrandr_logical_scales()
    edid = edid_scales()
    mutter, _ = mutter_scales()  # logged for observability only
    native_scaling = xwayland_native_scaling_on()

    chosen: float | None = None
    why = "fallback"

    # Preferred on X11: logical DPI from xrandr already accounts for any
    # desktop output scaling, so it never double-counts the way raw EDID does.
    # Skip it on a pure-Wayland session (xrandr there reflects XWayland, which
    # may not expose per-monitor scale) and fall through to EDID/mutter.
    if xrandr and session != "wayland":
        chosen = max(xrandr.values())
        picked = max(xrandr, key=xrandr.get)
        why = f"xrandr-logical (max from {picked})"

    # Use the highest panel DPI on the system. Multi-monitor users care
    # about whichever screen has the most demanding pixel density —
    # over-scaling a low-DPI panel is visually fine, under-scaling a
    # high-DPI panel makes PJeOffice unusable.
    if chosen is None and edid:
        chosen = max(edid.values())
        picked = max(edid, key=edid.get)
        why = f"edid (max from {picked}, native_scaling={native_scaling})"

    # Otherwise fall back to Xft.dpi (XSettings — only set under X11/XSettings)
    if chosen is None:
        x = xft_dpi_scale()
        if x is not None and x >= 1.0:
            chosen = x
            why = "xft.dpi"

    if chosen is None:
        chosen = FLOOR_SCALE
        why = "fallback"

    # Floor: don't go below FLOOR_SCALE — the PJeOffice base window is
    # already tiny by design.
    if chosen < FLOOR_SCALE:
        chosen = FLOOR_SCALE
        why += " (floored)"

    final = round_to_step(chosen)
    if final < FLOOR_SCALE:
        final = FLOOR_SCALE

    sys.stderr.write(
        f"pjeoffice-detect-uiscale: raw={chosen:.3f} final={final} "
        f"why={why} xrandr={xrandr} edid={edid} mutter={mutter} "
        f"native={native_scaling} session={session or '?'}\n"
    )
    print(f"{final}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # pragma: no cover — never block PJeOffice startup
        sys.stderr.write(f"pjeoffice-detect-uiscale: error {exc!r}, using {FLOOR_SCALE}\n")
        print(f"{FLOOR_SCALE}")
        sys.exit(0)

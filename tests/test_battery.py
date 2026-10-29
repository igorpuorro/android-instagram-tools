#!/usr/bin/env python3
"""Battery watch (DEVELOPMENT.md 4.15) on a simulated phone and clock -- no phone needed.

Run: uv run tests/test_battery.py
"""
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import feed_autoplay as fa  # noqa: E402

failures = []
lines = []
fa.log = lambda *a: lines.append(" ".join(map(str, a)))
fa.bell = lambda: lines.append("BELL")


def dumpsys(level, status=3, ac=False, usb=False, wireless=False, temp=310):
    """`dumpsys battery` as Android 11 (Samsung) prints it, trimmed."""
    return (f"Current Battery Service state:\n  AC powered: {str(ac).lower()}\n"
            f"  USB powered: {str(usb).lower()}\n  Wireless powered: {str(wireless).lower()}\n"
            f"  Max charging current: 0\n  status: {status}\n  health: 2\n  present: true\n"
            f"  level: {level}\n  scale: 100\n  voltage: 3912\n  temperature: {temp}\n"
            f"  technology: Li-ion\n  mSecPlugTypeSummary: 0\n")


class Phone:
    def __init__(self):
        self.out = dumpsys(64)

    def shell(self, cmd):
        assert cmd == "dumpsys battery", cmd
        if self.out is None:
            raise RuntimeError("device offline")
        return types.SimpleNamespace(output=self.out)


class Clock:
    def __init__(self):
        self.now = 1000.0

    def time(self):
        return self.now


def check(name, got, want):
    if got != want:
        failures.append(f"{name}: got {got!r}, want {want!r}")


# --- reading and describing -----------------------------------------------------------------
phone = Phone()
check("discharging", fa.read_battery(phone),
      {"level": 64, "status": "discharging", "plugged": None, "temp": 31.0})
check("describe discharging", fa.describe_battery(fa.read_battery(phone)), "64% · discharging · 31 °C")
phone.out = dumpsys(88, status=2, usb=True, temp=302)
check("describe charging USB", fa.describe_battery(fa.read_battery(phone)), "88% · charging (USB) · 30 °C")
phone.out = dumpsys(100, status=5, ac=True)
check("describe full AC", fa.describe_battery(fa.read_battery(phone)), "100% · full (AC) · 31 °C")
phone.out = dumpsys(85, status=4, wireless=True)
check("not charging, wireless", fa.read_battery(phone)["status"] + " " + fa.read_battery(phone)["plugged"],
      "not charging wireless")
phone.out = None
check("unreadable", fa.read_battery(phone), None)
check("describe unreadable", fa.describe_battery(None), "unknown")

# --- warnings and the stop (default: warn from 20 %, stop at 10 %) ---------------------------
clock = Clock()
fa.time = types.SimpleNamespace(time=clock.time)
phone = Phone()
b = fa.Battery(lambda: phone)


def at(level, **kw):
    """The phone at `level`, 2 minutes later; returns check()'s answer."""
    phone.out = dumpsys(level, **kw)
    clock.now += fa.Battery.EVERY
    return b.check()


lines.clear()
check("64 %: nothing", (at(64), lines), (None, []))
check("21 %: nothing", (at(21), lines), (None, []))
check("20 %: warning", (at(20), lines[-2:]), (None, ["BELL", "⚠ phone battery 20% and not charging -- stopping at 10%"]))
n = len(lines)
check("19 %: no repeat yet", (at(19), lines[n:]), (None, []))
check("17 %: repeated", (at(17), lines[-1]), (None, "⚠ phone battery 17% and not charging -- stopping at 10%"))
phone.out = dumpsys(5)
check("checked at most every 2 min", b.check(), None)
check("10 %: stop", at(10), "phone battery 10% and not charging")

# on the charger: no warnings, no stop; plug events logged; warnings start over afterwards
phone = Phone()
b = fa.Battery(lambda: phone)
lines.clear()
at(30)
check("plugged at 9 %: no stop", at(9, status=2, usb=True), None)
check("plug event", lines[-1], "🔌 phone on the charger: battery 9% · charging (USB) · 31 °C")
at(40, status=2, usb=True)
check("unplugged at 40 %", (at(40), lines[-1]), (None, "🔌 phone unplugged: battery 40% · discharging · 31 °C"))
check("after charging: warns again at 20 %", (at(20), lines[-1]),
      (None, "⚠ phone battery 20% and not charging -- stopping at 10%"))
check("forced check works between intervals", (phone.__setattr__("out", dumpsys(8)), b.check(force=True))[1],
      "phone battery 8% and not charging")

# --battery-stop 0: warnings only, from 20 %
phone = Phone()
b = fa.Battery(lambda: phone, stop=0)
lines.clear()
check("stop 0, 20 %: warning", (at(20), lines[-1]), (None, "⚠ phone battery 20% and not charging"))
check("stop 0, 2 %: still no stop", at(2), None)
# --battery-stop 30: warnings from 40 %
b = fa.Battery(lambda: phone, stop=30)
lines.clear()
check("stop 30, 41 %: nothing", (at(41), lines), (None, []))
check("stop 30, 40 %: warning", at(40) is None and lines[-1].startswith("⚠ phone battery 40%"), True)
check("stop 30, 30 %: stop", at(30), "phone battery 30% and not charging")

# heat: warn once at 42 °C (again only after cooling below 40), stop at 45 °C even charging
phone = Phone()
b = fa.Battery(lambda: phone)
lines.clear()
check("42 °C: warning", (at(80, temp=420), lines[-1]), (None, "⚠ phone battery hot: 42 °C (stopping at 45 °C)"))
n = len(lines)
check("43 °C: no repeat", (at(80, temp=430), lines[n:]), (None, []))
at(80, temp=390)
check("cooled, 42 °C again: warning", (at(80, temp=420), lines[-1]),
      (None, "⚠ phone battery hot: 42 °C (stopping at 45 °C)"))
check("45 °C on the charger: stop", at(80, status=2, ac=True, temp=450), "phone battery at 45 °C")

# a phone that can't be read: no stop, no crash
phone.out = None
check("unreadable: carries on", at(50), None)

# --battery-stop values
for value, ok in (("0", True), ("10", True), ("90", True), ("-1", False), ("91", False), ("x", False)):
    try:
        fa.battery_percent(value)
        got = True
    except Exception:
        got = False
    check(f"--battery-stop {value}", got, ok)

if failures:
    print(f"{len(failures)} FAILED:")
    for f in failures:
        print("  " + f)
    sys.exit(1)
print("all battery checks passed")

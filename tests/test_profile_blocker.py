#!/usr/bin/env python3
"""profile_blocker's list parsing, results file and profile screens -- no phone needed.

Screens are shaped like the ones recorded on Instagram 452 (made-up account and texts).

Run: uv run tests/test_profile_blocker.py
"""
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import profile_blocker as pb  # noqa: E402

RID = "com.instagram.android:id/"
failures = []


def check(what, got, want):
    if got != want:
        failures.append(f"{what}: got {got!r}, want {want!r}")


def node(rid="", text="", desc="", pkg="com.instagram.android"):
    return (f'<node text="{text}" resource-id="{rid and RID + rid}" package="{pkg}" '
            f'content-desc="{desc}" clickable="true" bounds="[0,0][100,100]" />')


def screen(*ns):
    return "<hierarchy>" + "".join(ns) + "</hierarchy>"


# ---- the list ------------------------------------------------------------------------------
names, bad = pb.parse_profiles([
    "# comment", "", "chef.marco", "@Chef.Marco  # same account, other case",
    "https://www.instagram.com/daily_news/?hl=en", "instagram.com/bakery_42", "not a name!",
])
check("names", names, ["chef.marco", "daily_news", "bakery_42"])
check("bad lines", bad, [(7, "not a name!")])

# ---- results file: the latest outcome per profile decides ------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    log = Path(tmp) / "blocked-profiles.txt"
    log.write_text("t\tchef.marco\tblocked\n"
                   "t\tdaily_news\tblocked\nt\tdaily_news\tunblocked\n"
                   "t\tbakery_42\tnot found\n"
                   "t\tsunny.days\talready blocked\n", encoding="utf-8")
    check("done for block", pb.done_before("block", log), {"chef.marco", "sunny.days"})
    check("done for unblock", pb.done_before("unblock", log), {"daily_news"})
    check("missing file", pb.done_before("block", Path(tmp) / "none.txt"), set())

# ---- profile screens -------------------------------------------------------------------------
title = node("action_bar_title", text="chef.marco", desc="chef.marco")
check("profile", pb.profile_state(screen(title, node("profile_header_follow_button", text="Follow")),
                                  "chef.marco"), "profile")
check("blocked", pb.profile_state(screen(title, node("profile_header_follow_button", text="Unblock")),
                                  "Chef.Marco"), "blocked")
check("pt-BR blocked", pb.profile_state(screen(title, node(text="Desbloquear")), "chef.marco"), "blocked")
check("not found", pb.profile_state(screen(node("no_found_text", text="User not found")), "chef.marco"),
      "not found")
check("other profile", pb.profile_state(screen(node("action_bar_title", text="daily_news"),
                                               node(text="Follow")), "chef.marco"), "other")
check("name only in system UI", pb.profile_state(screen(node(text="chef.marco", pkg="com.android.systemui")),
                                                 "chef.marco"), "other")
pt_title = node("action_bar_title", text="chef.marco", desc="chef.marco")
check("pt-BR profile", pb.profile_state(screen(pt_title, node("profile_header_follow_button", text="Seguir")),
                                        "chef.marco"), "profile")
check("pt-BR not found", pb.profile_state(screen(node("no_found_text", text="Usuário não encontrado")),
                                          "chef.marco"), "not found")
check("pt-BR options", bool(re.fullmatch(pb.exact("options"), "Opções")), True)
check("pt-BR unblock", bool(re.fullmatch(pb.exact("unblock"), "Desbloquear")), True)
check("menu item regex", [t for t in ("Block", "Unblock", "Block and Report", "Bloquear", "Desbloquear", "Bloquear e denunciar")
                          if re.fullmatch(pb.exact("block"), t)], ["Block", "Bloquear"])

for f in failures:
    print("FAIL", f)
print(f"{'all checks passed' if not failures else f'{len(failures)} check(s) failed'}")
sys.exit(1 if failures else 0)

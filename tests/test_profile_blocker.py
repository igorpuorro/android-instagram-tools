#!/usr/bin/env python3
"""profile_blocker's list parsing, results file and screen checks -- no phone needed.

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

# ---- texts ----------------------------------------------------------------------------------
check("pt-BR options", bool(re.fullmatch(pb.exact("options"), "Opções")), True)
check("pt-BR unblock", bool(re.fullmatch(pb.exact("unblock"), "Desbloquear")), True)
check("menu item regex", [t for t in ("Block", "Unblock", "Block and Report", "Bloquear", "Desbloquear", "Bloquear e denunciar")
                          if re.fullmatch(pb.exact("block"), t)], ["Block", "Bloquear"])

# ---- blocked accounts list and its search (+) ------------------------------------------------
def row(user, full, button, top):
    b = f"[0,{top}][1080,{top + 204}]"
    return (f'<node text="" resource-id="{RID}blocked_list_container" package="com.instagram.android" '
            f'content-desc="" clickable="true" bounds="{b}">'
            + node("blocked_list_username", text=user) + node("blocked_list_subtitle", text=full)
            + f'<node text="{button}" resource-id="{RID}unblock_button" package="com.instagram.android" '
              f'content-desc="" clickable="true" bounds="[777,{top + 57}][1035,{top + 147}]" />'
            + "</node>")


results = screen(node("search_bar_real_field", text="chef.marco", desc="Pesquisar"),
                 row("chef.marco", "Marco", "Bloquear", 246), row("chef.marco79", "chef.marco", "Bloquear", 450))
check("rows", [r[:2] for r in pb.list_rows(results)], [("chef.marco", "Bloquear"), ("chef.marco79", "Bloquear")])
check("row button bounds", pb.list_rows(results)[1][2], (777, 507, 1035, 597))
check("search is not the list", pb.on_blocked_list(results), False)
blocked = screen(node("action_bar_title", text="Contas bloqueadas", desc="Contas bloqueadas"),
                 node(desc="Adicionar"), row("chef.marco", "Inclui outras contas", "Desbloquear", 245))
check("blocked list", pb.on_blocked_list(blocked), True)
check("blocked list en", pb.on_blocked_list(screen(node("action_bar_title", text="Blocked accounts"),
                                                   node(desc="Add"))), True)
check("other screen", pb.on_blocked_list(screen(node("action_bar_title", text="chef.marco"),
                                                node(desc="Opções"))), False)
sheet = results.replace("</hierarchy>", node("igds_headline_headline", text="Bloquear chef.marco?") + "</hierarchy>")
check("question for the name", pb.block_question(sheet, "chef.marco"), True)
check("question for another name", pb.block_question(sheet, "chef.marco79"), False)
check("no question before the sheet", pb.block_question(results, "chef.marco"), False)
check("question en", pb.block_question(screen(node("igds_headline_headline", text="Block chef.marco?")),
                                       "Chef.Marco"), True)

check("blocking progress", pb.blocking(screen(node("message", text="Bloqueando..."))), True)
check("blocking progress en", pb.blocking(screen(node("message", text="Blocking..."))), True)
check("no progress", pb.blocking(blocked), False)

dialog = screen(node("igds_alert_dialog_headline", text="Unblock The New York Times (nytimes)?"),
                node("igds_alert_dialog_primary_button", text="Unblock"))
check("unblock question", pb.unblock_question(dialog, "nytimes"), True)
check("unblock question other name", pb.unblock_question(dialog, "nytimes_fan79"), False)
check("unblock question pt-BR", pb.unblock_question(screen(node("igds_alert_dialog_headline",
                                                                 text="Desbloquear chef.marco?")), "chef.marco"), True)
check("unblock question no dialog", pb.unblock_question(blocked, "chef.marco"), False)

for f in failures:
    print("FAIL", f)
print(f"{'all checks passed' if not failures else f'{len(failures)} check(s) failed'}")
sys.exit(1 if failures else 0)

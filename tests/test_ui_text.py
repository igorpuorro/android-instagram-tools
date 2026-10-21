#!/usr/bin/env python3
"""Language checks for feed_autoplay's text matching (DEVELOPMENT.md 4.12) -- no phone needed.

English expectations are the behaviour of the code before pt-BR was added (verified by a
differential test, 89 checks, 0 differences): if one of them fails, English matching changed.
pt-BR expectations come from texts recorded on Instagram 451. Examples use made-up accounts.

Run: uv run tests/test_ui_text.py
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import feed_autoplay as fa  # noqa: E402

fa.log = lambda *a: None
RID = "com.instagram.android:id/"
failures = []


class FakeDevice:
    def __init__(self, xml=""):
        self.xml = xml

    def window_size(self):
        return 1080, 2340

    def dump_hierarchy(self):
        return self.xml


def player(xml="", **args):
    return fa.Player(FakeDevice(xml), argparse.Namespace(**args), None)


def node(rid, desc="", text="", bounds="[0,500][1080,640]"):
    return (f'<node index="0" text="{text}" resource-id="{RID}{rid}" class="x" '
            f'package="com.instagram.android" content-desc="{desc}" selected="false" bounds="{bounds}" />')


def check(name, got, want):
    if got != want:
        failures.append(f"{name}: got {got!r}, want {want!r}")


SUGGESTED_EN = node("secondary_label", "Suggested for you", bounds="[128,520][758,600]")
SUGGESTED_PT = node("secondary_label", "Sugestões para você", bounds="[128,520][758,600]")
FOLLOW_BTN = node("inline_follow_button", "Follow Chef Marco", "Follow", bounds="[758,520][965,600]")

# --- feed: which headers are video posts, ads, suggestions ---------------------------------
for header, extra, want_all, want_followed in [
    ("chef.marco posted a video 2 hours ago", "", True, True),
    ("chef.marco posted a video in Lisbon, Portugal on 1 day ago", "", True, True),
    ("news.channel posted a video 7 October", "", True, True),
    ("news.channel posted a video October 7", "", True, True),   # US English date
    ("garden_tales posted a photo 3 hours ago", "", False, False),
    ("brand.store posted a video 2 hours ago Sponsored", "", False, False),
    ("chef.marco posted a video 2 hours ago", SUGGESTED_EN, True, False),
    ("chef.marco posted a video 2 hours ago", FOLLOW_BTN, True, False),
    ("chef.marco postou um video em Há 7 horas", "", True, True),
    ("chef.marco postou um video em há 15 minutos", "", True, True),
    ("chef.marco postou um video em Lisboa em Há 5 horas", "", True, True),
    ("chef.marco postou um video em 10 de outubro", "", True, True),
    ("garden_tales postou uma foto em Há 3 horas", "", False, False),
    ("brand.store postou um video em Há 2 horas Patrocinado", "", False, False),
    ("chef.marco postou um video em Há 7 horas", SUGGESTED_PT, True, False),
    ("chef.marco postou um video em Há 7 horas", FOLLOW_BTN.replace("Follow", "Seguir"), True, False),
]:
    xml = "<hierarchy>" + node("row_feed_profile_header", header) + extra + "</hierarchy>"
    check(f"feed (all) {header!r}", player(xml, play="all").find_video_header() is not None, want_all)
    check(f"feed (followed) {header!r}", player(xml, play="followed").find_video_header() is not None,
          want_followed)

# --- post identity: relative time labels -----------------------------------------------------
for header, want_prefix, want_tol in [
    ("a posted a video 5 hours ago", "a posted a video", 66.0),
    ("a posted a video 1 minute ago", "a posted a video", 3),
    ("a posted a video in X on 3 weeks ago", "a posted a video in X", 11088.0),
    ("a postou um video em Há 7 horas", "a postou um video", 66.0),
    ("a postou um video em há 15 minutos", "a postou um video", 3),
    ("a postou um video em Lisboa em Há 2 dias", "a postou um video em Lisboa", 1584.0),
    ("a postou um video em 10 de outubro", "a postou um video em 10 de outubro", 0),   # absolute
]:
    prefix, posted, tol = player().post_id(header)
    check(f"post_id {header!r}", (prefix, round(tol, 1)), (want_prefix, round(want_tol, 1)))
p = player()
p.remember("y postou um video em há 23 minutos")
check("dedupe: same pt-BR post, label moved on", p.is_seen("y postou um video em há 25 minutos"), True)
check("dedupe: other pt-BR post", p.is_seen("y postou um video em Há 2 horas"), False)

# --- player: followed / suggested / collaboration --------------------------------------------
for author, extra, want in [
    ("chef.marco", "", True),
    ("chef.marco", node("inline_follow_button", "Follow Chef Marco"), False),
    ("chef.marco", '<node text="Followed by ana and 13 others" />', False),
    ("news.channel and 2 others", node("inline_follow_button", "Follow X"), True),
    ("chef.marco and cityfoodtour", node("inline_follow_button", "Follow X"), True),
    ("chef.marco", node("inline_follow_button", "Seguir Chef Marco"), False),
    ("chef.marco", '<node text="Seguido por ana e outras 2 pessoas" />', False),
    ("chef.marco e mais 2", node("inline_follow_button", "Seguir X"), True),
    ("chef.marco e cityfoodtour", node("inline_follow_button", "Seguir X"), True),
]:
    xml = f'<node text="{author}" resource-id="{RID}clips_author_username" />' + extra
    check(f"player followed {author!r} {extra[:40]!r}", player(xml).player_author_followed(), want)

# --- exact counts ------------------------------------------------------------------------------
for kind, text, want in [
    ("like", "The like number is 22759. View likes", 22759),
    ("like", "The like number is 1,204. View likes", 1204),
    ("like", "Like number is 5424. View likes", 5424),            # US English
    ("like", "Like number is 18.5K. View likes", None),
    ("like", "The like number is 18.5K. View likes", None),
    ("repost", "Reposted 6592 times", 6592),
    ("repost", "Reposted 1 time", 1),
    ("save", "Save number is 39", 39),
    ("save", "Save number is 1.2M", None),
    ("like", "O número de curtidas é 180. Ver curtidas", 180),
    ("like", "O número de curtidas é 2.118. Ver curtidas", 2118),
    ("like", "O número de curtidas é 1,2 mil. Ver curtidas", None),
    ("repost", "Repostado 49 vezes", 49),
    ("repost", "Repostado 1 vez", 1),
    ("save", "O número de salvamentos é 19.103", 19103),
]:
    check(f"count {kind} {text!r}", player(f'<node content-desc="{text}" />').exact_count(kind), want)


# --- like state from the label (feed path: no icon check) ------------------------------------
class Button:
    def __init__(self, desc, selected):
        self.info = {"contentDescription": desc, "selected": selected, "bounds": {}}


for desc, selected, want in [("Like", False, False), ("Like", True, True), ("Liked", False, True),
                             ("Curtir", False, False), ("Curtir", True, True), ("Curtido", False, True)]:
    check(f"is_liked {desc}/{selected}", player().is_liked(Button(desc, selected), check_icon=False), want)

# --- 2x hints, share sheet, refusal, Home tab, snackbars --------------------------------------
for text, locked, unlocked in [
    ("Slide down to lock 2X speed", False, True),
    ("Slide down to lock 2x speed", False, True),
    ("Slide down for normal speed", True, False),
    ("Press edge to fast-forward", False, False),
    ("Deslize para baixo para ativar a velocidade 2x", False, True),
    ("Deslize para baixo para voltar à velocidade normal", True, False),
]:
    xml = f'text="{text}"'
    check(f"2x hint {text!r}", (fa.has_any(xml, "speed_locked"), fa.has_any(xml, "speed_unlocked")),
          (locked, unlocked))
for desc, want in [("Copy link", True), ("Copiar link", True), ("Share", False), ("Compartilhar", False)]:
    check(f"share sheet {desc!r}", player(f'<node content-desc="{desc}" />').share_sheet_open(), want)
for text, want in [("Unable to repost", True), ("Try again later", True), ("Não foi possível repostar", True),
                   ("Reposted", False), ("Repostado", False), ("Salvo", False)]:
    check(f"refusal {text!r}", bool(re.fullmatch(fa.REFUSED, text)), want)
for desc, want in [("Home", True), ("Página inicial", True), ("Reels", False), ("home", False)]:
    check(f"home tab {desc!r}", bool(re.fullmatch(fa.HOME_TAB, desc)), want)
for key, en, pt in [("copied", "Copied", "Copiado"), ("reposted", "Reposted", "Repostado"),
                    ("copy_link", "Copy link", "Copiar link")]:
    check(f"UI_TEXT[{key}]", (en in fa.UI_TEXT[key], pt in fa.UI_TEXT[key]), (True, True))

if failures:
    print(f"{len(failures)} FAILED:")
    for f in failures:
        print("  " + f)
    sys.exit(1)
print("all language checks passed")

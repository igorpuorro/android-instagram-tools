#!/usr/bin/env python3
"""Example --comment-script for feed_autoplay: a greeting for the time of day, picked at random.

feed_autoplay runs it before each comment and posts what it prints. The video comes in
environment variables:
  IG_AUTHOR    the account, as the player shows it (e.g. chef.marco)
  IG_POST      the post's header (e.g. "chef.marco posted a video 2 hours ago")
  IG_FOLLOWED  1 = you follow the account, 0 = not
  IG_TEST      1 on the trial run when feed_autoplay starts (nothing is posted)
Print nothing to leave a video without a comment.

Try it: python examples/comment_greeting.py
Use it: uv run feed_autoplay.py --comment followed --comment-script examples/comment_greeting.py
"""
import os
import random
import time

GREETINGS = {
    "morning": ["Bom dia! ☀️", "Bom dia, ótimo vídeo! 🇧🇷", "Que manhã boa com esse vídeo! ☕"],
    "afternoon": ["Boa tarde! 👏", "Boa tarde, muito bom! 🇧🇷", "Excelente, boa tarde! 🙌"],
    "night": ["Boa noite! 🌙", "Boa noite, adorei! 🇧🇷", "Ótimo vídeo, boa noite! ✨"],
}

hour = time.localtime().tm_hour
period = "morning" if 5 <= hour < 12 else "afternoon" if 12 <= hour < 18 else "night"
text = random.choice(GREETINGS[period])

author = os.environ.get("IG_AUTHOR", "")
if os.environ.get("IG_FOLLOWED") == "1" and author and " " not in author:
    text = f"@{author} {text}"  # name the accounts you follow (a co-authored post has spaces)

print(text)

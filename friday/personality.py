"""
friday/personality.py
---------------------
Cross-cutting tone helpers: varied wake-word acknowledgements and a
time-of-day greeting. No state; safe to call from any thread.
"""

import datetime
import random

WAKE_ACKS = [
    "Yes boss",
    "I'm listening sir",
    "At your service",
    "Standing by",
    "Go ahead boss",
    "Boss?",
    "How can I help",
    "Right here sir",
]


def wake_ack() -> str:
    """Random short acknowledgement phrase for the wake-word response."""
    return random.choice(WAKE_ACKS)


def greet_for_time_of_day(now: datetime.datetime | None = None) -> str:
    """
    Return a time-of-day greeting.

      05:00 - 11:59 -> "Good morning sir"
      12:00 - 16:59 -> "Good afternoon boss"
      17:00 - 21:59 -> "Good evening sir"
      22:00 - 04:59 -> "You're up late boss"
    """
    now = now or datetime.datetime.now()
    h = now.hour
    if 5 <= h < 12:
        return "Good morning sir"
    if 12 <= h < 17:
        return "Good afternoon boss"
    if 17 <= h < 22:
        return "Good evening sir"
    return "You're up late boss"

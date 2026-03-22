"""
Single source of truth for the main menu.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 HOW TO ADD A NEW BUTTON
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Edit exactly TWO files:

 1. This file (buttons.py) — add one MenuButton:
      MYFEATURE = MenuButton("My Feature", row=1)
    Then append it to ALL:
      ALL: list[MenuButton] = [..., MYFEATURE]

    MAIN_MENU, USER_TEXT, and menu_fallbacks() update automatically.

 2. The command file (e.g. bot/commands/myfeature.py) — add one entry point:
      from bot.commands.common import BTN_MYFEATURE   # auto-exported
      ...
      entry_points=[
          CommandHandler("myfeature", myfeature_start),
          MessageHandler(filters.Text([BTN_MYFEATURE]), myfeature_start),
      ]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Fallback actions (what happens when a button is tapped mid-flow):
  CANCEL_SILENT  — end the flow, say nothing (default)
  CANCEL_MESSAGE — end the flow, reply "Cancelled."
  SHOW_INFO      — end the flow, show the info/help message
"""

from dataclasses import dataclass
from enum import Enum, auto


class FallbackAction(Enum):
    CANCEL_SILENT  = auto()
    CANCEL_MESSAGE = auto()
    SHOW_INFO      = auto()


@dataclass(frozen=True)
class MenuButton:
    label: str
    row: int
    fallback: FallbackAction = FallbackAction.CANCEL_SILENT


# ── Menu definition ───────────────────────────────────────────────────────────
SPEAK     = MenuButton("🎙 Speak",     row=0)
VOICEOVER = MenuButton("🎤 Voiceover", row=0)
SONG      = MenuButton("🎵 Song",      row=0)
SETTINGS  = MenuButton("⚙️ Settings",  row=1)
INFO      = MenuButton("ℹ️ Info",      row=1, fallback=FallbackAction.SHOW_INFO)
CREDITS   = MenuButton("💳 Credits",   row=1)
CANCEL    = MenuButton("❌ Cancel",    row=2, fallback=FallbackAction.CANCEL_MESSAGE)

# Ordered list used to build rows — order within a row matches definition order above
ALL: list[MenuButton] = [SPEAK, VOICEOVER, SONG, SETTINGS, INFO, CREDITS, CANCEL]

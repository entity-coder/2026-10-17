"""
RepairDesk — repair shop job-card tracker.

Run:  python main.py
Build a Windows .exe: run build_exe.bat on a Windows PC (see README).
"""

import customtkinter as ctk

from db import DB
from ui import App, APP_NAME


def main():
    db = DB()
    # Theme follows the saved setting (dark default), toggle lives in Settings.
    ctk.set_appearance_mode(db.get_setting("theme", "dark"))
    ctk.set_default_color_theme("blue")
    app = App(db)
    app.mainloop()


if __name__ == "__main__":
    main()

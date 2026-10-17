"""
RepairDesk — repair-shop job-card tracker.
ui.py: the whole CustomTkinter interface.

Screens (sidebar switches between them):
  Dashboard — stat cards (in progress / delivered today / pending payments),
              jobs due soon, active jobs list.
  Jobs      — search (phone / job ID / name), status filter chips,
              job cards with one-click status advance.
  Backup    — one-click backup, restore from zip, open data folder.
  Settings  — shop name (printed on receipts), light/dark theme.
"""

import os
import sys
import subprocess
import tkinter.messagebox as msgbox

import customtkinter as ctk

from db import DB, STATUSES, ACTIVE_STATUSES
from printing import generate_receipt
from backup import make_backup, restore_backup, data_dir

APP_NAME = "RepairDesk"
APP_VERSION = "1.0"


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def open_file(path: str) -> None:
    """Open a file with the OS default app (used for receipt PDFs)."""
    if sys.platform.startswith("win"):
        os.startfile(path)  # noqa: S606 - local file path
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def money(x: float) -> str:
    return f"Rs. {x:,.2f}"


STATUS_COLORS = {
    "Received": ("#8b5cf6", "#a78bfa"),
    "Diagnosing": ("#f59e0b", "#fbbf24"),
    "In Repair": ("#3b82f6", "#60a5fa"),
    "Ready": ("#10b981", "#34d399"),
    "Delivered": ("#6b7280", "#9ca3af"),
}


class JobDialog(ctk.CTkToplevel):
    """Add / edit a job card. Calls on_save(job_id) when done."""

    def __init__(self, master, db: DB, job: dict | None, on_save):
        super().__init__(master)
        self.db = db
        self.job = job
        self.on_save = on_save
        self.title("Edit job" if job else "New job")
        self.geometry("520x640")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        body = ctk.CTkScrollableFrame(self)
        body.pack(fill="both", expand=True, padx=12, pady=12)

        self.entries: dict[str, ctk.CTkEntry | ctk.CTkTextbox] = {}

        def field(label: str, key: str, default: str = "", height: int = 32):
            ctk.CTkLabel(body, text=label, anchor="w").pack(fill="x", pady=(10, 2))
            if height > 60:
                w = ctk.CTkTextbox(body, height=height)
                w.insert("1.0", default)
            else:
                w = ctk.CTkEntry(body, height=height)
                w.insert(0, default)
            w.pack(fill="x")
            self.entries[key] = w

        j = job or {}
        field("Customer name *", "customer_name", j.get("customer_name", ""))
        field("Phone *", "phone", j.get("phone", ""))
        field("Device *  (e.g. Redmi Note 12, Dell Inspiron 15)", "device", j.get("device", ""))
        field("Reported issue", "issue", j.get("issue", ""), height=80)
        field("Accessories left with shop  (charger, case, ...)", "accessories", j.get("accessories", ""))
        field("Estimated cost (Rs.)", "estimated_cost", str(j.get("estimated_cost", "")))
        field("Promised return date  (YYYY-MM-DD, optional)", "promised_at", j.get("promised_at", ""))
        field("Notes", "notes", j.get("notes", ""), height=80)

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=12, pady=(0, 12))
        ctk.CTkButton(btns, text="Cancel", fg_color="gray", command=self.destroy).pack(
            side="left", expand=True, fill="x", padx=(0, 6)
        )
        ctk.CTkButton(btns, text="Save job", command=self._save).pack(
            side="left", expand=True, fill="x", padx=(6, 0)
        )
        self.bind("<Return>", lambda _e: self._save())
        self.bind("<Escape>", lambda _e: self.destroy())

    def _value(self, key: str) -> str:
        w = self.entries[key]
        return w.get("1.0", "end").strip() if isinstance(w, ctk.CTkTextbox) else w.get().strip()

    def _save(self) -> None:
        name, phone, device = (
            self._value("customer_name"),
            self._value("phone"),
            self._value("device"),
        )
        if not name or not phone or not device:
            msgbox.showerror("Missing details", "Customer name, phone and device are required.")
            return
        cost_text = self._value("estimated_cost").replace(",", "")
        try:
            cost = float(cost_text) if cost_text else 0.0
        except ValueError:
            msgbox.showerror("Bad cost", "Estimated cost must be a number.")
            return
        data = {
            "customer_name": name,
            "phone": phone,
            "device": device,
            "issue": self._value("issue"),
            "accessories": self._value("accessories"),
            "estimated_cost": cost,
            "promised_at": self._value("promised_at"),
            "notes": self._value("notes"),
        }
        if self.job:
            self.db.update_job(self.job["id"], **data)
            job_id = self.job["id"]
        else:
            job_id = self.db.add_job(**data)
        self.destroy()
        self.on_save(job_id)


class PaymentDialog(ctk.CTkToplevel):
    """Record a payment against a job."""

    def __init__(self, master, db: DB, job: dict, on_done):
        super().__init__(master)
        self.db, self.job, self.on_done = db, job, on_done
        self.title(f"Record payment — {job['job_code']}")
        self.geometry("380x320")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        totals = db.totals_for_job(job["id"])
        ctk.CTkLabel(self, text=f"Due: {money(totals['due'])}", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(16, 8))

        frm = ctk.CTkFrame(self, fg_color="transparent")
        frm.pack(fill="both", expand=True, padx=16)
        ctk.CTkLabel(frm, text="Amount (Rs.)", anchor="w").pack(fill="x")
        self.amount = ctk.CTkEntry(frm)
        self.amount.pack(fill="x", pady=(2, 10))
        ctk.CTkLabel(frm, text="Mode", anchor="w").pack(fill="x")
        self.mode = ctk.CTkOptionMenu(frm, values=["Cash", "UPI", "Card", "Bank transfer"])
        self.mode.pack(fill="x", pady=(2, 10))
        ctk.CTkLabel(frm, text="Note (optional)", anchor="w").pack(fill="x")
        self.note = ctk.CTkEntry(frm)
        self.note.pack(fill="x", pady=(2, 10))

        ctk.CTkButton(frm, text="Save payment", command=self._save).pack(fill="x", pady=8)
        self.bind("<Return>", lambda _e: self._save())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.amount.focus()

    def _save(self) -> None:
        try:
            amount = float(self.amount.get().replace(",", ""))
        except ValueError:
            msgbox.showerror("Bad amount", "Enter a number for the amount.")
            return
        if amount <= 0:
            msgbox.showerror("Bad amount", "Amount must be positive.")
            return
        try:
            self.db.add_payment(self.job["id"], amount, self.mode.get(), self.note.get().strip())
        except ValueError as e:
            msgbox.showerror("Bad amount", str(e))
            return
        self.destroy()
        self.on_done()


class PrintDialog(ctk.CTkToplevel):
    """Choose paper size for the receipt, then generate + open the PDF."""

    def __init__(self, master, db: DB, job: dict):
        super().__init__(master)
        self.db, self.job = db, job
        self.title(f"Print receipt — {job['job_code']}")
        self.geometry("360x230")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        ctk.CTkLabel(self, text="Receipt paper size", font=ctk.CTkFont(size=15, weight="bold")).pack(pady=(18, 6))
        self.paper = ctk.CTkOptionMenu(self, values=["A4", "80mm (thermal)"])
        self.paper.pack(pady=8)
        ctk.CTkLabel(self, text="The PDF opens in your viewer —\nprint it from there.", justify="center").pack(pady=6)
        ctk.CTkButton(self, text="Generate receipt", command=self._go).pack(pady=10)

    def _go(self) -> None:
        paper = "80mm" if self.paper.get().startswith("80") else "A4"
        shop = self.db.get_setting("shop_name", APP_NAME)
        totals = self.db.totals_for_job(self.job["id"])
        payments = self.db.payments_for_job(self.job["id"])
        path = generate_receipt(self.job, totals, shop, payments, paper=paper)
        self.destroy()
        open_file(path)


# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------
class App(ctk.CTk):
    def __init__(self, db: DB):
        super().__init__()
        self.db = db
        self.title(f"{APP_NAME} {APP_VERSION} — repair shop job tracker")
        self.geometry("1180x760")
        self.minsize(980, 620)

        # ---- sidebar -----------------------------------------------------
        side = ctk.CTkFrame(self, width=190, corner_radius=0)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)

        ctk.CTkLabel(side, text=APP_NAME, font=ctk.CTkFont(size=22, weight="bold")).pack(pady=(18, 4))
        ctk.CTkLabel(side, text="job cards for repair shops", font=ctk.CTkFont(size=11)).pack(pady=(0, 18))

        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        for name in ("Dashboard", "Jobs", "Backup", "Settings"):
            b = ctk.CTkButton(
                side, text=name, anchor="w", fg_color="transparent",
                text_color=("gray10", "gray90"),
                command=lambda n=name: self.show(n),
            )
            b.pack(fill="x", padx=10, pady=4)
            self.nav_buttons[name] = b

        ctk.CTkButton(side, text="+ New job", command=lambda: self._job_dialog(None)).pack(
            fill="x", padx=10, pady=(18, 4)
        )
        ctk.CTkLabel(side, text=APP_VERSION, font=ctk.CTkFont(size=10)).pack(side="bottom", pady=12)

        # ---- pages -------------------------------------------------------
        self.main = ctk.CTkFrame(self, fg_color="transparent")
        self.main.pack(side="left", fill="both", expand=True, padx=14, pady=14)
        self.page: ctk.CTkFrame | None = None

        self.show("Dashboard")

    # ---- navigation ------------------------------------------------------
    def show(self, name: str) -> None:
        for n, b in self.nav_buttons.items():
            b.configure(fg_color=("gray75", "gray25") if n == name else "transparent")
        if self.page:
            self.page.destroy()
        self.page = ctk.CTkFrame(self.main, fg_color="transparent")
        self.page.pack(fill="both", expand=True)
        {"Dashboard": self._dashboard, "Jobs": self._jobs,
         "Backup": self._backup_page, "Settings": self._settings}[name]()

    def refresh(self) -> None:
        current = next(n for n, b in self.nav_buttons.items()
                       if str(b.cget("fg_color")) != "transparent")
        self.show(current)

    # ---- dashboard -------------------------------------------------------
    def _stat_card(self, parent, title: str, value: str, accent: str):
        card = ctk.CTkFrame(parent)
        card.pack(side="left", expand=True, fill="both", padx=6)
        ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=12)).pack(pady=(12, 2))
        ctk.CTkLabel(card, text=value, font=ctk.CTkFont(size=24, weight="bold"),
                     text_color=accent).pack(pady=(0, 12))

    def _dashboard(self) -> None:
        d = self.db.dashboard()
        ctk.CTkLabel(self.page, text="Dashboard", font=ctk.CTkFont(size=20, weight="bold")).pack(anchor="w", pady=(0, 10))

        cards = ctk.CTkFrame(self.page, fg_color="transparent")
        cards.pack(fill="x", pady=(0, 12))
        self._stat_card(cards, "Jobs in progress", str(d["in_progress"]), "#3b82f6")
        self._stat_card(cards, "Delivered today", str(d["delivered_today"]), "#10b981")
        self._stat_card(cards, "Pending payments", money(d["pending_payments"]), "#f59e0b")

        if d["due_soon"]:
            ctk.CTkLabel(self.page, text="Due / overdue (promised date)", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(4, 4))
            for job in d["due_soon"][:8]:
                self._job_row(self.page, job, show_due=True)

        ctk.CTkLabel(self.page, text="Active jobs", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(10, 4))
        scroll = ctk.CTkScrollableFrame(self.page)
        scroll.pack(fill="both", expand=True)
        for job in d["active"]:
            self._job_row(scroll, job)
        if not d["active"]:
            ctk.CTkLabel(scroll, text="No active jobs. Click “+ New job” to add one.").pack(pady=20)

    # ---- jobs list -------------------------------------------------------
    def _jobs(self) -> None:
        header = ctk.CTkFrame(self.page, fg_color="transparent")
        header.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(header, text="Jobs", font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkButton(header, text="+ New job", width=110,
                      command=lambda: self._job_dialog(None)).pack(side="right")

        tools = ctk.CTkFrame(self.page, fg_color="transparent")
        tools.pack(fill="x", pady=(0, 8))
        self.search_var = ctk.StringVar()
        search = ctk.CTkEntry(tools, textvariable=self.search_var, width=320,
                              placeholder_text="Search phone / job ID / name / device…")
        search.pack(side="left", padx=(0, 10))
        search.bind("<KeyRelease>", lambda _e: self._reload_jobs())
        self.status_filter = ctk.CTkOptionMenu(
            tools, values=["All"] + STATUSES, command=lambda _v: self._reload_jobs()
        )
        self.status_filter.pack(side="left")

        self.jobs_scroll = ctk.CTkScrollableFrame(self.page)
        self.jobs_scroll.pack(fill="both", expand=True)
        self._reload_jobs()

    def _reload_jobs(self) -> None:
        for w in self.jobs_scroll.winfo_children():
            w.destroy()
        jobs = self.db.list_jobs(status=self.status_filter.get(),
                                 query=self.search_var.get())
        for job in jobs:
            self._job_row(self.jobs_scroll, job)
        if not jobs:
            ctk.CTkLabel(self.jobs_scroll, text="No jobs match.").pack(pady=20)

    # ---- one job row (used by dashboard + jobs list) ----------------------
    def _job_row(self, parent, job: dict, show_due: bool = False) -> None:
        totals = self.db.totals_for_job(job["id"])
        card = ctk.CTkFrame(parent)
        card.pack(fill="x", pady=4, padx=2)

        left = ctk.CTkFrame(card, fg_color="transparent")
        left.pack(side="left", fill="both", expand=True, padx=10, pady=8)
        ctk.CTkLabel(left,
                     text=f"{job['job_code']}  ·  {job['customer_name']}  ·  {job['phone']}",
                     font=ctk.CTkFont(size=13, weight="bold"), anchor="w").pack(fill="x")
        ctk.CTkLabel(left, text=f"{job['device']} — {job['issue'][:60]}",
                     anchor="w").pack(fill="x")
        due_text = ""
        if show_due and job["promised_at"]:
            due_text = f"  ·  promised {job['promised_at']}"
        ctk.CTkLabel(left,
                     text=f"Due: {money(totals['due'])}{due_text}",
                     font=ctk.CTkFont(size=12)).pack(fill="x", anchor="w")

        color = STATUS_COLORS.get(job["status"], ("gray", "gray"))
        badge = ctk.CTkLabel(card, text=job["status"], text_color=color[1],
                             font=ctk.CTkFont(size=12, weight="bold"), width=90)
        badge.pack(side="left", padx=6)

        right = ctk.CTkFrame(card, fg_color="transparent")
        right.pack(side="right", padx=10, pady=8)
        ctk.CTkButton(right, text="Open", width=70,
                      command=lambda j=job: self._open_job(j["id"])).pack(side="left", padx=2)
        # One-click advance to the next pipeline stage.
        idx = STATUSES.index(job["status"])
        if idx < len(STATUSES) - 1:
            nxt = STATUSES[idx + 1]
            ctk.CTkButton(right, text=f"→ {nxt}", width=120,
                          command=lambda jid=job["id"], s=nxt: self._advance(jid, s)).pack(side="left", padx=2)

    def _advance(self, job_id: int, status: str) -> None:
        self.db.set_status(job_id, status)
        self.refresh()

    # ---- job detail ------------------------------------------------------
    def _open_job(self, job_id: int) -> None:
        job = self.db.get_job(job_id)
        if not job:
            return
        win = ctk.CTkToplevel(self)
        win.title(f"{job['job_code']} — {job['customer_name']}")
        win.geometry("640x720")
        win.transient(self)

        def rebuild():
            win.destroy()
            self._open_job(job_id)

        ctk.CTkLabel(win, text=f"{job['job_code']}  ·  {job['customer_name']}",
                     font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(14, 2))
        ctk.CTkLabel(win, text=f"{job['phone']}  ·  {job['device']}").pack(pady=(0, 10))

        # status pipeline buttons
        pipe = ctk.CTkFrame(win, fg_color="transparent")
        pipe.pack(fill="x", padx=12)
        for s in STATUSES:
            active = s == job["status"]
            ctk.CTkButton(
                pipe, text=s, width=105,
                fg_color=STATUS_COLORS[s][0] if active else "gray",
                command=lambda st=s: (self.db.set_status(job_id, st), rebuild()),
            ).pack(side="left", padx=3)

        body = ctk.CTkScrollableFrame(win)
        body.pack(fill="both", expand=True, padx=12, pady=10)

        totals = self.db.totals_for_job(job_id)
        info = (
            f"Issue: {job['issue'] or '-'}\n"
            f"Accessories: {job['accessories'] or '-'}\n"
            f"Received: {job['received_at'][:16]}   "
            f"Promised: {job['promised_at'] or '-'}\n"
            f"Delivered: {job['delivered_at'][:16] if job['delivered_at'] else '-'}\n"
            f"Notes: {job['notes'] or '-'}"
        )
        ctk.CTkLabel(body, text=info, justify="left", anchor="w").pack(fill="x", pady=4)

        ctk.CTkLabel(body, text=f"Estimate {money(totals['estimated'])}  ·  "
                                f"Paid {money(totals['advance'])}  ·  "
                                f"Due {money(totals['due'])}",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", pady=(8, 4))

        ctk.CTkLabel(body, text="Payments", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", pady=(6, 2))
        for p in self.db.payments_for_job(job_id):
            ctk.CTkLabel(body, text=f"{p['paid_at'][:10]}  {p['mode']}  {money(float(p['amount']))}"
                                   + (f"  ({p['note']})" if p["note"] else ""),
                         anchor="w").pack(fill="x")

        btns = ctk.CTkFrame(win, fg_color="transparent")
        btns.pack(fill="x", padx=12, pady=(0, 12))
        ctk.CTkButton(btns, text="Record payment", width=140,
                      command=lambda: PaymentDialog(self, self.db, job, rebuild)).pack(side="left", padx=3)
        ctk.CTkButton(btns, text="Print receipt", width=120,
                      command=lambda: PrintDialog(self, self.db, job)).pack(side="left", padx=3)
        ctk.CTkButton(btns, text="Edit", width=80,
                      command=lambda: self._job_dialog(job, on_save=lambda _jid: rebuild())).pack(side="left", padx=3)
        ctk.CTkButton(btns, text="Delete", width=80, fg_color="#dc2626",
                      command=lambda: self._delete_job(job_id, win)).pack(side="left", padx=3)

    def _delete_job(self, job_id: int, win) -> None:
        if msgbox.askyesno("Delete job", "Delete this job and its payments? This cannot be undone."):
            self.db.delete_job(job_id)
            win.destroy()
            self.refresh()

    def _job_dialog(self, job: dict | None, on_save=None) -> None:
        JobDialog(self, self.db, job, on_save=on_save or (lambda _jid: self.refresh()))

    # ---- backup page -----------------------------------------------------
    def _backup_page(self) -> None:
        ctk.CTkLabel(self.page, text="Backup", font=ctk.CTkFont(size=20, weight="bold")).pack(anchor="w", pady=(0, 10))
        ctk.CTkLabel(self.page, wraplength=700, justify="left",
                     text="Backups are timestamped zips of your database and receipts. "
                          "Keep a copy on a pen drive or another PC.").pack(anchor="w", pady=(0, 10))
        ctk.CTkButton(self.page, text="Create backup now", width=200, command=self._do_backup).pack(anchor="w", pady=6)
        ctk.CTkButton(self.page, text="Restore from backup…", width=200, command=self._do_restore).pack(anchor="w", pady=6)
        ctk.CTkButton(self.page, text="Open data folder", width=200,
                      command=lambda: open_file(data_dir())).pack(anchor="w", pady=6)
        self.backup_msg = ctk.CTkLabel(self.page, text="", anchor="w")
        self.backup_msg.pack(anchor="w", pady=10)

    def _do_backup(self) -> None:
        try:
            path = make_backup()
            self.backup_msg.configure(text=f"Backup saved:\n{path}", text_color="green")
        except Exception as e:  # keep the app alive; show the error
            self.backup_msg.configure(text=f"Backup failed: {e}", text_color="red")

    def _do_restore(self) -> None:
        from tkinter import filedialog
        path = filedialog.askopenfilename(title="Choose a RepairDesk backup zip",
                                          filetypes=[("ZIP files", "*.zip")])
        if not path:
            return
        if not msgbox.askyesno("Restore", "Replace current data with this backup?\nA safety copy is kept first."):
            return
        try:
            restore_backup(path)
            self.backup_msg.configure(text="Restored. Restart the app to reload.", text_color="green")
        except Exception as e:
            self.backup_msg.configure(text=f"Restore failed: {e}", text_color="red")

    # ---- settings --------------------------------------------------------
    def _settings(self) -> None:
        ctk.CTkLabel(self.page, text="Settings", font=ctk.CTkFont(size=20, weight="bold")).pack(anchor="w", pady=(0, 10))

        ctk.CTkLabel(self.page, text="Shop name (printed on receipts)", anchor="w").pack(anchor="w", pady=(6, 2))
        name_entry = ctk.CTkEntry(self.page, width=320)
        name_entry.insert(0, self.db.get_setting("shop_name", APP_NAME))
        name_entry.pack(anchor="w", pady=(0, 8))

        ctk.CTkLabel(self.page, text="Theme", anchor="w").pack(anchor="w", pady=(6, 2))
        theme = ctk.CTkOptionMenu(self.page, values=["dark", "light"],
                                 command=lambda v: ctk.set_appearance_mode(v))
        theme.set(self.db.get_setting("theme", "dark"))
        theme.pack(anchor="w", pady=(0, 8))

        def save():
            self.db.set_setting("shop_name", name_entry.get().strip() or APP_NAME)
            self.db.set_setting("theme", theme.get())
            ctk.set_appearance_mode(theme.get())
            msgbox.showinfo("Settings", "Saved.")

        ctk.CTkButton(self.page, text="Save settings", width=200, command=save).pack(anchor="w", pady=10)

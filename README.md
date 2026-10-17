# RepairDesk — repair shop job-card tracker

A desktop app for mobile/laptop repair shops: log every repair as a **job card**,
track it through a status pipeline, record payments, and print a receipt for the
customer. Fully offline — your data lives in a single SQLite file on the shop PC.

## Features

- **Job cards** — customer name/phone, device, reported issue, accessories left
  with the shop, estimated cost, promised return date, notes. Job IDs are
  human-friendly (`RD-0001`, `RD-0002`, …).
- **Status pipeline** — `Received → Diagnosing → In Repair → Ready → Delivered`,
  with color badges and one-click advance from the list, or a full pipeline
  switcher in the job detail view. Delivering stamps the delivery date/time.
- **Search & filter** — instant search across phone, job ID, customer name and
  device; filter chips per status.
- **Printable receipts** — A4 receipt for the customer's record, or a compact
  **80mm thermal slip** for receipt printers. Shop name from Settings is printed
  on top; the receipt shows estimate, advance paid and balance due.
- **Payment tracking** — record advance/part payments (Cash/UPI/Card/Bank
  transfer); due amount = estimated cost − payments, never negative.
- **Dashboard** — jobs in progress, deliveries made today, total pending
  payments, jobs promised today or overdue, and the active job list.
- **Backup & restore** — one-click timestamped `.zip` backup of the database +
  receipts, and restore with an automatic safety copy first.
- **Settings** — shop name and light/dark theme (persisted).

## How to run

**On the shop PC (Windows):** double-click `build_exe.bat` once — it installs
the packages and builds `dist\RepairDesk.exe`. After that just run the `.exe`
(no Python needed).

**From source (any OS with Python 3.10+):**

```bash
pip install -r requirements.txt
python main.py
```

Note: a Windows `.exe` can only be built on Windows — `build_exe.bat` will not
work on Linux or Mac, but `python main.py` runs anywhere tkinter works.

## Project layout

| File | What it does |
|---|---|
| `main.py` | Entry point: loads theme, launches the app |
| `db.py` | SQLite layer: jobs, payments, settings, dashboard stats |
| `ui.py` | All CustomTkinter screens: Dashboard, Jobs, Backup, Settings, dialogs |
| `printing.py` | Receipt PDFs (A4 + 80mm thermal) via reportlab |
| `backup.py` | Timestamped zip backups + restore with safety copy |
| `requirements.txt` | `customtkinter`, `reportlab` |

Data is stored in `repairdesk_data/` next to the app (database + receipts).
The app is offline-first — no account, no internet needed.

## Interview notes

**What this project is:** RepairDesk is a single-purpose business tool for
small repair shops — it replaces the paper job-card register. Every repair is
one row in SQLite ("job"), and the UI is organized around the shop's real
workflow: take the device → diagnose → repair → call the customer → collect
payment → hand it over.

**Why CustomTkinter + SQLite (key decisions):**
- *CustomTkinter* over a web app: a shop PC is often a single shared machine
  with flaky internet. A desktop app starts instantly, works fully offline, and
  printing a receipt is trivial (just open the PDF). No server to host or pay
  for, which matters for a tool meant to be sold to small shops.
- *SQLite* over a client-server database: one file = zero setup, zero admin.
  Backup is literally copying the file (I zip it with the receipts). Concurrency
  isn't a concern — one operator uses it at a time.
- *reportlab* for receipts: receipts must be pixel-precise printable documents,
  and reportlab gives direct control over page geometry (especially the 80mm
  thermal format), unlike an HTML-to-PDF pipeline that needs a browser engine.

**Trade-offs / limitations (be honest about these):**
- No multi-user or sync: data lives on one PC. If the shop has two counters,
  they'd need separate databases — a cloud sync layer would be the next big
  feature, but it changes the cost model (hosting) and the offline-first promise.
- Payment due is computed as `max(0, estimated − payments)` — if a technician
  lowers the estimate below what's already paid, the "overpaid" amount isn't
  tracked as a refund. Intentional simplification for v1.
- Status timestamps: I only persist `received_at` and `delivered_at`. The
  intermediate stages (Diagnosing/In Repair/Ready) are current-state only —
  there's no audit log of when a job entered each stage. Fine for a small shop,
  a limitation for SLA reporting.
- The UI isn't unit-tested (tkinter GUIs are hard to test headlessly); the
  database and money-math layer is the part with deterministic logic, and that's
  where I kept the code dependency-free and testable.

**How I'd extend it:**
- SMS/WhatsApp "your device is ready" notification per job (biggest real-world
  win for a repair shop).
- Spare-parts inventory: deduct a part when a job uses it, link part cost to
  the job's estimate.
- Simple analytics: average repair time per device type, revenue per week —
  the data is already there, it's just new queries on top.
- Customer lookup by phone with repeat-customer history.

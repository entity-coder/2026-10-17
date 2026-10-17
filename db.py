"""
RepairDesk — repair-shop job-card tracker.
db.py: SQLite persistence layer (offline-first, single-file database).

Tables:
  jobs     — one row per repair job card.
  payments — partial/advance payments recorded against a job.
  settings — simple key/value store (shop name, theme, ...).
"""

import os
import sqlite3
from datetime import date, datetime


# Status pipeline in display order. Jobs move left -> right; they can be
# moved back (e.g. Ready -> In Repair) if a device comes back with issues.
STATUSES = ["Received", "Diagnosing", "In Repair", "Ready", "Delivered"]

# Jobs still needing work.
ACTIVE_STATUSES = ["Received", "Diagnosing", "In Repair", "Ready"]


def _today_iso() -> str:
    return date.today().isoformat()


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


class DB:
    def __init__(self, path: str | None = None):
        """If no path is given, use repairdesk.db next to the data folder."""
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "repairdesk_data")
        os.makedirs(base, exist_ok=True)
        self.path = path or os.path.join(base, "repairdesk.db")
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._migrate()

    # ------------------------------------------------------------------ schema
    def _migrate(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                job_code       TEXT UNIQUE,
                customer_name  TEXT NOT NULL DEFAULT '',
                phone          TEXT NOT NULL DEFAULT '',
                device         TEXT NOT NULL DEFAULT '',
                issue          TEXT DEFAULT '',
                accessories    TEXT DEFAULT '',
                estimated_cost REAL NOT NULL DEFAULT 0,
                status         TEXT NOT NULL DEFAULT 'Received',
                received_at    TEXT NOT NULL,
                promised_at    TEXT DEFAULT '',
                delivered_at   TEXT DEFAULT '',
                notes          TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS payments (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id  INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                amount  REAL NOT NULL DEFAULT 0,
                mode    TEXT DEFAULT 'Cash',
                paid_at TEXT NOT NULL,
                note    TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT ''
            );
            """
        )
        self.conn.commit()

    # ------------------------------------------------------------------ settings
    def get_setting(self, key: str, default: str = "") -> str:
        row = self.conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self.conn.commit()

    # ------------------------------------------------------------------ jobs
    def _next_job_code(self) -> str:
        """Human-friendly job codes: RD-0001, RD-0002, ..."""
        row = self.conn.execute("SELECT MAX(id) AS m FROM jobs").fetchone()
        return f"RD-{(row['m'] or 0) + 1:04d}"

    def add_job(
        self,
        customer_name: str,
        phone: str,
        device: str,
        issue: str = "",
        accessories: str = "",
        estimated_cost: float = 0.0,
        promised_at: str = "",
        notes: str = "",
    ) -> int:
        job_code = self._next_job_code()
        cur = self.conn.execute(
            """
            INSERT INTO jobs (job_code, customer_name, phone, device, issue,
                              accessories, estimated_cost, status, received_at,
                              promised_at, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'Received', ?, ?, ?)
            """,
            (
                job_code,
                customer_name.strip(),
                phone.strip(),
                device.strip(),
                issue.strip(),
                accessories.strip(),
                float(estimated_cost or 0),
                _now_iso(),
                promised_at.strip(),
                notes.strip(),
            ),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_job(self, job_id: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None

    def update_job(self, job_id: int, **fields) -> None:
        allowed = {
            "customer_name", "phone", "device", "issue", "accessories",
            "estimated_cost", "promised_at", "notes",
        }
        sets, vals = [], []
        for k, v in fields.items():
            if k in allowed:
                sets.append(f"{k} = ?")
                vals.append(v.strip() if isinstance(v, str) else float(v or 0) if k == "estimated_cost" else v)
        if not sets:
            return
        vals.append(job_id)
        self.conn.execute(f"UPDATE jobs SET {', '.join(sets)} WHERE id = ?", vals)
        self.conn.commit()

    def set_status(self, job_id: int, status: str) -> None:
        if status not in STATUSES:
            raise ValueError(f"unknown status: {status}")
        if status == "Delivered":
            self.conn.execute(
                "UPDATE jobs SET status = ?, delivered_at = ? WHERE id = ?",
                (status, _now_iso(), job_id),
            )
        else:
            # Leaving Delivered back to an earlier stage clears the delivery stamp.
            self.conn.execute(
                "UPDATE jobs SET status = ?, delivered_at = '' WHERE id = ?",
                (status, job_id),
            )
        self.conn.commit()

    def delete_job(self, job_id: int) -> None:
        self.conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        self.conn.commit()

    def list_jobs(self, status: str = "", query: str = "") -> list[dict]:
        """All jobs, newest first. Optional exact-status filter and free-text
        search across job code, customer name, phone and device."""
        sql = "SELECT * FROM jobs"
        clauses, params = [], []
        if status and status != "All":
            clauses.append("status = ?")
            params.append(status)
        if query:
            q = f"%{query.strip()}%"
            clauses.append(
                "(job_code LIKE ? OR customer_name LIKE ? OR phone LIKE ? OR device LIKE ?)"
            )
            params.extend([q, q, q, q])
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY id DESC"
        return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    # ------------------------------------------------------------------ payments
    def add_payment(
        self, job_id: int, amount: float, mode: str = "Cash", note: str = ""
    ) -> None:
        amount = float(amount or 0)
        if amount <= 0:
            raise ValueError("payment amount must be positive")
        self.conn.execute(
            "INSERT INTO payments (job_id, amount, mode, paid_at, note) "
            "VALUES (?, ?, ?, ?, ?)",
            (job_id, amount, mode, _now_iso(), note.strip()),
        )
        self.conn.commit()

    def payments_for_job(self, job_id: int) -> list[dict]:
        return [
            dict(r)
            for r in self.conn.execute(
                "SELECT * FROM payments WHERE job_id = ? ORDER BY id DESC",
                (job_id,),
            ).fetchall()
        ]

    def totals_for_job(self, job_id: int) -> dict:
        """advance = sum of recorded payments; due = estimated - advance (>= 0)."""
        job = self.get_job(job_id)
        if not job:
            return {"estimated": 0.0, "advance": 0.0, "due": 0.0}
        advance = self.conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS s FROM payments WHERE job_id = ?",
            (job_id,),
        ).fetchone()["s"]
        estimated = float(job["estimated_cost"] or 0)
        due = max(0.0, estimated - float(advance))
        return {"estimated": estimated, "advance": float(advance), "due": due}

    # ------------------------------------------------------------------ dashboard
    def dashboard(self) -> dict:
        """Numbers for the dashboard cards."""
        today = _today_iso()
        in_progress = self.conn.execute(
            f"SELECT COUNT(*) AS c FROM jobs WHERE status IN "
            f"({','.join('?' for _ in ACTIVE_STATUSES)})",
            ACTIVE_STATUSES,
        ).fetchone()["c"]
        delivered_today = self.conn.execute(
            "SELECT COUNT(*) AS c FROM jobs WHERE status = 'Delivered' "
            "AND substr(delivered_at, 1, 10) = ?",
            (today,),
        ).fetchone()["c"]
        # Pending payments = estimated - advance, summed over non-delivered jobs.
        pending_payments = self.conn.execute(
            """
            SELECT COALESCE(SUM(j.estimated_cost - COALESCE(p.paid, 0)), 0) AS s
            FROM jobs j
            LEFT JOIN (SELECT job_id, SUM(amount) AS paid FROM payments GROUP BY job_id) p
              ON p.job_id = j.id
            WHERE j.status != 'Delivered'
              AND j.estimated_cost > COALESCE(p.paid, 0)
            """
        ).fetchone()["s"]
        # Jobs promised today or overdue and still active.
        due_soon = [
            dict(r)
            for r in self.conn.execute(
                f"SELECT * FROM jobs WHERE promised_at != '' AND promised_at <= ? "
                f"AND status IN ({','.join('?' for _ in ACTIVE_STATUSES)}) "
                f"ORDER BY promised_at",
                (today, *ACTIVE_STATUSES),
            ).fetchall()
        ]
        # Active jobs newest first (dashboard list).
        active = [
            dict(r)
            for r in self.conn.execute(
                f"SELECT * FROM jobs WHERE status IN "
                f"({','.join('?' for _ in ACTIVE_STATUSES)}) ORDER BY id DESC",
                ACTIVE_STATUSES,
            ).fetchall()
        ]
        return {
            "in_progress": in_progress,
            "delivered_today": delivered_today,
            "pending_payments": float(pending_payments or 0),
            "due_soon": due_soon,
            "active": active,
        }

    def close(self) -> None:
        self.conn.close()

"""
db.py — NeonDB connection module
=================================
GST Smart Planner | IT Maverick Solutions

Sabhi Python scripts yahi module import karte hain DB operations ke liye.
Connection string .env ya environment variable se aata hai.

Usage:
    from db import get_conn, save_invoices, get_last_invoice_number

Install:
    pip install psycopg2-binary python-dotenv --break-system-packages
"""

import os
import json
from datetime import date
from pathlib import Path
from dotenv import load_dotenv

def _load_env():
    """
    Next.js .env.local format mein kuch lines hoti hain jo standard
    python-dotenv parse nahi kar pata (multi-line JSON strings, etc.)
    Isliye override=False ke saath load karte hain — jo variables already
    process.env mein hain (Next.js ne inject kiye) unhe preserve karte hain,
    sirf missing ones .env.local se add karte hain.
    """
    # When called from Next.js spawn, env vars already injected by Node
    # So DATABASE_URL etc. already in os.environ — no need to parse file
    if os.environ.get("DATABASE_URL"):
        return  # Already set by Next.js / system env

    # Local terminal run — try loading from file
    for env_file in [
        Path(__file__).parent.parent / ".env.local",
        Path(__file__).parent.parent / ".env",
        Path(".env.local"),
        Path(".env"),
    ]:
        if env_file.exists():
            load_dotenv(env_file, override=False)
            if os.environ.get("DATABASE_URL"):
                return

_load_env()

try:
    import psycopg2
    from psycopg2.extras import execute_values, RealDictCursor
except ImportError:
    raise SystemExit("Install psycopg2:  pip install psycopg2-binary --break-system-packages")

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise SystemExit("DATABASE_URL environment variable nahi mila. .env file check karo.")


# ─────────────────────────────────────────────
# CONNECTION
# ─────────────────────────────────────────────

def get_conn():
    """NeonDB se connection leta hai."""
    return psycopg2.connect(DATABASE_URL, sslmode="require")


# ─────────────────────────────────────────────
# INVOICE OPERATIONS
# ─────────────────────────────────────────────

def get_last_invoice_number(supplier_gstin: str, series: str) -> str | None:
    """
    DB se us series ka last invoice number nikalta hai.
    invoice_engine.py aur b2c_generator.py dono isko use karte hain
    taaki next invoice number auto-detect ho sake.

    Returns: "ME260034" jaisa string, ya None agar koi invoice nahi mila.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT invoice_no FROM invoices
                WHERE supplier_gstin = %s AND series = %s AND is_cancelled = FALSE
                ORDER BY invoice_no DESC
                LIMIT 1
            """, (supplier_gstin, series))
            row = cur.fetchone()
            return row[0] if row else None


def save_invoices(rows: list[dict], fp: str, supplier_gstin: str) -> int:
    """
    Invoice rows DB mein save karta hai.
    Duplicate invoice_no pe skip karta hai (ON CONFLICT DO NOTHING).

    `rows` format (invoice_engine.py ya b2c_generator.py ka output):
    {
        invoice_no, date (datetime.date), gstin (party, B2B only),
        receiver (party name), qty_1l, qty_500ml, taxable, tax_total,
        invoice_value, category, rate, is_intra
    }
    Returns: number of rows inserted.
    """
    if not rows:
        return 0

    def row_to_tuple(r):
        inv_type = _map_invoice_type(r.get("category", "B2B"), r.get("rate", 0))
        series   = r["invoice_no"][:2]  # "ME" or "CM"
        cgst = samt = igst = 0.0
        tax = r.get("tax_total", r.get("tax", 0))
        if r.get("is_intra", True):
            cgst = round(tax / 2, 2)
            samt = round(tax - cgst, 2)
        else:
            igst = tax

        inv_date = r["date"] if isinstance(r["date"], date) else r["date"]

        return (
            fp,
            supplier_gstin,
            r["invoice_no"],
            inv_date,
            inv_type,
            series,
            r.get("gstin") or r.get("party_gstin"),       # party GSTIN (B2B only)
            r.get("receiver") or r.get("party_name"),      # party name
            r.get("pos", "10"),
            r.get("taxable", 0),
            r.get("rate", r.get("gst_rate", 0)),
            cgst,
            samt,
            igst,
            r.get("invoice_value", 0),
            r.get("qty_1l", 0),
            r.get("qty_500ml", 0),
            r.get("hsn_code", "151499"),
        )

    data = [row_to_tuple(r) for r in rows]

    sql = """
        INSERT INTO invoices (
            fp, supplier_gstin, invoice_no, invoice_date,
            invoice_type, series,
            party_gstin, party_name, place_of_supply,
            taxable_value, gst_rate,
            cgst_amount, sgst_amount, igst_amount,
            invoice_value, qty_1l, qty_500ml, hsn_code
        ) VALUES %s
        ON CONFLICT (invoice_no) DO NOTHING
    """

    with get_conn() as conn:
        with conn.cursor() as cur:
            execute_values(cur, sql, data)
        conn.commit()
        return len(data)


def _map_invoice_type(category: str, rate: float) -> str:
    """category string ko DB enum mein map karta hai."""
    cat = category.upper()
    if "EXEMPT" in cat:
        return "EXEMPT"
    if "B2C" in cat or "CASH" in cat:
        return f"B2C_{int(rate)}"
    return "B2B"


def mark_json_exported(fp: str, supplier_gstin: str) -> int:
    """GSTR-1 JSON generate hone ke baad invoices flag karta hai."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE invoices
                SET json_exported = TRUE, json_export_at = NOW()
                WHERE fp = %s AND supplier_gstin = %s AND is_cancelled = FALSE
            """, (fp, supplier_gstin))
            count = cur.rowcount
        conn.commit()
        return count


# ─────────────────────────────────────────────
# MONTHLY SUMMARY
# ─────────────────────────────────────────────

def check_month_generated(fp: str, supplier_gstin: str, invoice_type: str = None) -> dict:
    """
    Checks if invoices already exist in DB for a given month + supplier.
    Returns dict with:
      - exists: bool
      - count: int (number of invoices found)
      - series: list of invoice series found (e.g. ['ME', 'CM'])
      - invoice_from: first invoice no
      - invoice_to: last invoice no

    Use this BEFORE generating to prevent duplicate data.
    invoice_type: 'B2B' | 'B2C_5' | 'B2C_18' | 'EXEMPT' | None (all)
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            query = """
                SELECT
                    COUNT(*) as count,
                    array_agg(DISTINCT series) as series,
                    MIN(invoice_no) as invoice_from,
                    MAX(invoice_no) as invoice_to
                FROM invoices
                WHERE fp = %s AND supplier_gstin = %s AND is_cancelled = FALSE
            """
            params = [fp, supplier_gstin]
            if invoice_type:
                query += " AND invoice_type = %s"
                params.append(invoice_type)

            cur.execute(query, params)
            row = cur.fetchone()
            count = row[0] if row else 0
            return {
                "exists":       count > 0,
                "count":        count,
                "series":       row[1] if row and row[1] else [],
                "invoice_from": row[2] if row else None,
                "invoice_to":   row[3] if row else None,
            }


def delete_month_invoices(fp: str, supplier_gstin: str, invoice_type: str = None) -> int:
    """
    Deletes invoices for a month (for re-generation).
    Returns count of deleted rows.
    Use with caution — only if user explicitly confirms regeneration.
    invoice_type: 'B2B' | None (all B2B) etc.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            query = "DELETE FROM invoices WHERE fp = %s AND supplier_gstin = %s"
            params = [fp, supplier_gstin]
            if invoice_type:
                query += " AND invoice_type = %s"
                params.append(invoice_type)
            cur.execute(query, params)
            count = cur.rowcount
        conn.commit()
        return count



    """
    Monthly summary view se data nikalta hai.
    Sales Records screen aur dashboard ke liye.
    """
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM monthly_summary
                WHERE fp = %s AND supplier_gstin = %s
            """, (fp, supplier_gstin))
            row = cur.fetchone()
            return dict(row) if row else None


def get_b2b_sales_records(fp: str, supplier_gstin: str) -> list[dict]:
    """
    B2B-SALES-RECORDS view — ERP entry ke liye.
    Sales Records screen + CSV export ke liye.
    """
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM b2b_sales_records
                WHERE fp = %s
                ORDER BY invoice_date, invoice_no
            """, (fp,))
            return [dict(r) for r in cur.fetchall()]


def get_invoices_for_month(fp: str, supplier_gstin: str) -> list[dict]:
    """Poore month ke saare invoices — JSON generator ke liye."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM invoices
                WHERE fp = %s AND supplier_gstin = %s AND is_cancelled = FALSE
                ORDER BY series, invoice_no
            """, (fp, supplier_gstin))
            return [dict(r) for r in cur.fetchall()]


# ─────────────────────────────────────────────
# PARTY OPERATIONS
# ─────────────────────────────────────────────

def get_parties(supplier_gstin: str) -> list[dict]:
    """Active parties list — B2B Planner screen ke liye."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT gstin, trade_name, state_code
                FROM parties
                WHERE is_active = TRUE
                ORDER BY trade_name
            """)
            return [dict(r) for r in cur.fetchall()]


def upsert_party(gstin: str, trade_name: str, state_code: str = "10"):
    """Party add ya update karta hai."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO parties (gstin, trade_name, state_code)
                VALUES (%s, %s, %s)
                ON CONFLICT (gstin) DO UPDATE
                SET trade_name = EXCLUDED.trade_name,
                    state_code = EXCLUDED.state_code,
                    updated_at = NOW()
            """, (gstin, trade_name, state_code))
        conn.commit()


# ─────────────────────────────────────────────
# MONTHLY TARGETS
# ─────────────────────────────────────────────

def save_monthly_targets(fp: str, supplier_gstin: str, targets: dict):
    """
    FY2026-27 sheet se read kiye targets DB mein save karta hai.
    targets dict: {taxable_5pct, taxable_18pct, exempt_registered,
                   exempt_unregistered, b2b_5pct, b2c_5pct, ...}
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO monthly_targets (
                    gstin, fp,
                    taxable_5pct, taxable_18pct,
                    exempt_registered, exempt_unregistered,
                    b2b_5pct, b2c_5pct, b2b_18pct, b2c_18pct,
                    updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (gstin, fp) DO UPDATE SET
                    taxable_5pct        = EXCLUDED.taxable_5pct,
                    taxable_18pct       = EXCLUDED.taxable_18pct,
                    exempt_registered   = EXCLUDED.exempt_registered,
                    exempt_unregistered = EXCLUDED.exempt_unregistered,
                    b2b_5pct            = EXCLUDED.b2b_5pct,
                    b2c_5pct            = EXCLUDED.b2c_5pct,
                    b2b_18pct           = EXCLUDED.b2b_18pct,
                    b2c_18pct           = EXCLUDED.b2c_18pct,
                    updated_at          = NOW()
            """, (
                supplier_gstin, fp,
                targets.get("taxable_5pct", 0),
                targets.get("taxable_18pct", 0),
                targets.get("exempt_registered", 0),
                targets.get("exempt_unregistered", 0),
                targets.get("b2b_5pct", 0),
                targets.get("b2c_5pct", 0),
                targets.get("b2b_18pct", 0),
                targets.get("b2c_18pct", 0),
            ))
        conn.commit()


# ─────────────────────────────────────────────
# FILING RECORD
# ─────────────────────────────────────────────

def save_filing_record(fp: str, supplier_gstin: str, json_filename: str, summary: dict):
    """GSTR-1 generate hone ke baad filing record save karta hai."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO gst_filings (
                    fp, supplier_gstin, filing_type, status,
                    json_filename,
                    total_b2b, total_b2c, total_exempt, total_turnover, total_gst,
                    updated_at
                ) VALUES (%s, %s, 'GSTR1', 'generated', %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (fp, supplier_gstin, filing_type) DO UPDATE SET
                    status        = 'generated',
                    json_filename = EXCLUDED.json_filename,
                    total_b2b     = EXCLUDED.total_b2b,
                    total_b2c     = EXCLUDED.total_b2c,
                    total_exempt  = EXCLUDED.total_exempt,
                    total_turnover = EXCLUDED.total_turnover,
                    total_gst     = EXCLUDED.total_gst,
                    updated_at    = NOW()
            """, (
                fp, supplier_gstin, json_filename,
                summary.get("b2b_taxable", 0),
                summary.get("b2c_taxable", 0),
                summary.get("exempt_taxable", 0),
                summary.get("total_taxable", 0),
                summary.get("total_gst", 0),
            ))
        conn.commit()


# ─────────────────────────────────────────────
# QUICK TEST
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("NeonDB connection test...")
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT version()")
                print("✓ Connected:", cur.fetchone()[0][:40])
                cur.execute("SELECT COUNT(*) FROM parties")
                print("✓ Parties in DB:", cur.fetchone()[0])
    except Exception as e:
        print("✗ Connection failed:", e)

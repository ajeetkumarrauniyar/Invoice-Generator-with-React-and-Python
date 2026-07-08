"""
b2c_generator.py  —  v1.0
===========================
GST Smart Planner | IT Maverick Solutions | Muskan Enterprises

WHAT THIS DOES:
  Reads the month's B2C targets DIRECTLY from your existing "FY2026-27"
  sheet (Sales Planning Sheet section) — no new sheet needed. Generates
  CASH-counter invoices (5%, 18%, and Exempt) under a single shared "CM"
  invoice series, and produces the CSVs needed for the B2CS + EXEMP
  sections of your GSTR-1 JSON.

WHERE THE TARGETS COME FROM (FY2026-27 sheet, Sales Planning Sheet):
  Column D  = 5% Taxable Portion  (whole month)
  Column E  = 18% Taxable Portion (whole month)
  Column M  = B2B Sales @5%   (you enter this manually)
  Column N  = B2C Sales @5%   (formula: =D-M, already in your sheet)
  Column O  = B2B Sales @18%  (blank for now — not tracked yet)
  Column P  = B2C Sales @18%  (blank for now — treated as = E, since O is blank)
  Column G  = Exempt - Registered    (22% share)
  Column H  = Exempt - Unregistered  (78% share)

  IMPORTANT: Once you start tracking B2B@18% (column O), this script will
  automatically use (E - O) instead of the full E value — no code change
  needed, it just reads whatever is in the sheet.

INVOICE NUMBERING:
  All cash invoices (5% + 18% + Exempt) share ONE "CM" series, continuing
  sequentially — matching your Invoice Planning sheet's CM260001-style
  numbering. Auto-detects the next number from a "CM_LEDGER" sheet if
  present, otherwise you give a --start-invoice the first time.

PLACE OF SUPPLY:
  All cash sales assumed Intra-State (Bihar) — matches your sheet's
  "IntraState Supplies" header. If you ever have inter-state cash sales,
  flag it and this will need a small extension.

USAGE:
    python3 b2c_generator.py <workbook_path> <MMYYYY> --start-invoice CM260001

EXAMPLE:
    python3 b2c_generator.py GST_Monthwise_Ratewise_Bifurcation.xlsx 042026 --start-invoice CM260001

OUTPUT:
    b2cs_rows.csv          → paste into your b2cs.csv / B2CS JSON section
    exemp_row.csv          → paste into your exemp.csv / EXEMP JSON section
    cash_sales_records.csv → invoice-level detail, for ERP entry + your
                              own Invoice Planning sheet reference
"""

import sys
import os
import csv
import re
import random
import calendar
import argparse
import datetime
from pathlib import Path

try:
    import openpyxl
except ImportError:
    sys.exit("Install openpyxl first:  pip install openpyxl --break-system-packages")

# DB integration — optional
try:
    from db import get_last_invoice_number, save_invoices, save_monthly_targets
    DB_AVAILABLE = True
except Exception:
    DB_AVAILABLE = False

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
PLANNING_SHEET  = "FY2026-27"
PLANNING_HEADER_ROW = 45   # sub-header row (rate values live in row 45 for GST%, data from row 46)
PLANNING_DATA_START = 46

COL_MONTH   = 1   # A
COL_5_TAXABLE  = 4   # D
COL_18_TAXABLE = 5   # E
COL_EXEMPT_REG   = 7   # G
COL_EXEMPT_UNREG = 8   # H
COL_B2B_5   = 13  # M
COL_B2C_5   = 14  # N
COL_B2B_18  = 15  # O
COL_B2C_18  = 16  # P

INVOICE_CAP = 50000
SUPPLIER_STATE = "10"   # Bihar
POS_NAME = "10-Bihar"
CM_PATTERN = re.compile(r"^([A-Za-z]+)(\d+)$")


# ─────────────────────────────────────────────
# 1. READ TARGETS FROM FY2026-27 SHEET
# ─────────────────────────────────────────────

def read_month_targets(wb, month_yyyymm):
    if PLANNING_SHEET not in wb.sheetnames:
        sys.exit(f"ERROR: Sheet '{PLANNING_SHEET}' not found in workbook.")
    ws = wb[PLANNING_SHEET]

    mm, yyyy = int(month_yyyymm[:2]), int(month_yyyymm[2:])

    for r in range(PLANNING_DATA_START, ws.max_row + 1):
        cell_val = ws.cell(row=r, column=COL_MONTH).value
        if isinstance(cell_val, datetime.datetime):
            if cell_val.month == mm and cell_val.year == yyyy:
                taxable_5 = ws.cell(row=r, column=COL_5_TAXABLE).value or 0
                taxable_18 = ws.cell(row=r, column=COL_18_TAXABLE).value or 0
                b2b_5 = ws.cell(row=r, column=COL_B2B_5).value or 0
                b2c_5 = ws.cell(row=r, column=COL_B2C_5).value
                b2b_18 = ws.cell(row=r, column=COL_B2B_18).value or 0
                b2c_18 = ws.cell(row=r, column=COL_B2C_18).value
                exempt_reg = ws.cell(row=r, column=COL_EXEMPT_REG).value or 0
                exempt_unreg = ws.cell(row=r, column=COL_EXEMPT_UNREG).value or 0

                # Use the sheet's own B2C value if present; else derive it
                target_5 = b2c_5 if b2c_5 is not None else (taxable_5 - b2b_5)
                target_18 = b2c_18 if b2c_18 is not None else (taxable_18 - b2b_18)

                return {
                    "row": r,
                    "b2c_5": round(target_5, 2),
                    "b2c_18": round(target_18, 2),
                    "exempt_registered": round(exempt_reg, 2),
                    "exempt_unregistered": round(exempt_unreg, 2),
                }
    sys.exit(f"ERROR: No row found in '{PLANNING_SHEET}' for month {month_yyyymm}.")


# ─────────────────────────────────────────────
# 2. INVOICE NUMBER HANDLING (shared CM series)
# ─────────────────────────────────────────────

def generate_invoice_numbers(start_no, count):
    m = CM_PATTERN.match(start_no)
    if not m:
        sys.exit(f"ERROR: --start-invoice '{start_no}' doesn't match pattern like CM260001")
    prefix, digits = m.group(1), m.group(2)
    width = len(digits)
    start_num = int(digits)
    return [f"{prefix}{str(start_num + k).zfill(width)}" for k in range(count)]


# ─────────────────────────────────────────────
# 3. SPLIT A TAXABLE-RATE BUCKET INTO INVOICES
# ─────────────────────────────────────────────

def split_taxable_bucket(taxable_target, gst_rate, cap=INVOICE_CAP, spread=0.6):
    """
    Given a TAXABLE VALUE target (tax-exclusive) and a GST rate, generates
    a list of invoice values (tax-INCLUSIVE, matching how the counter bill
    is actually written), each under `cap`, summing back to exactly the
    taxable target.
    """
    if taxable_target <= 0:
        return []

    invoice_inclusive_total = round(taxable_target * (1 + gst_rate / 100), 2)
    avg_invoice = 38000  # comfortable margin under the 50k cap
    n = max(1, -(-int(invoice_inclusive_total) // avg_invoice))  # ceil division

    weights = [random.uniform(1 - spread, 1 + spread) for _ in range(n)]
    scale = invoice_inclusive_total / sum(weights)
    values = [round(w * scale, 2) for w in weights]

    drift = round(invoice_inclusive_total - sum(values), 2)
    values[-1] = round(values[-1] + drift, 2)

    # Rebalance anything over cap
    for _ in range(2000):
        over_idx = max(range(len(values)), key=lambda i: values[i])
        if values[over_idx] < cap:
            break
        under_idx = min(range(len(values)), key=lambda i: values[i])
        move = round(values[over_idx] - (cap - 500), 2)
        values[over_idx] -= move
        values[under_idx] += move

    return values


def split_exempt_bucket(exempt_target, cap=INVOICE_CAP, spread=0.6):
    """Exempt invoices — no tax component, invoice value = taxable value."""
    if exempt_target <= 0:
        return []
    n = max(1, -(-int(exempt_target) // 38000))
    weights = [random.uniform(1 - spread, 1 + spread) for _ in range(n)]
    scale = exempt_target / sum(weights)
    values = [round(w * scale, 2) for w in weights]
    drift = round(exempt_target - sum(values), 2)
    values[-1] = round(values[-1] + drift, 2)

    for _ in range(2000):
        over_idx = max(range(len(values)), key=lambda i: values[i])
        if values[over_idx] < cap:
            break
        under_idx = min(range(len(values)), key=lambda i: values[i])
        move = round(values[over_idx] - (cap - 500), 2)
        values[over_idx] -= move
        values[under_idx] += move

    return values


def random_increasing_dates(month_yyyymm, count):
    mm, yyyy = int(month_yyyymm[:2]), int(month_yyyymm[2:])
    days_in_month = calendar.monthrange(yyyy, mm)[1]
    if count <= days_in_month:
        days = sorted(random.sample(range(1, days_in_month + 1), count))
    else:
        days = sorted(random.choices(range(1, days_in_month + 1), k=count))
    return [datetime.date(yyyy, mm, d) for d in days]


# ─────────────────────────────────────────────
# 4. MAIN GENERATION
# ─────────────────────────────────────────────

def build_all_invoices(targets, month, start_invoice):
    warnings = []
    all_rows = []

    buckets = [
        ("5", targets["b2c_5"], 5),
        ("18", targets["b2c_18"], 18),
    ]

    taxable_invoice_values = {}
    for label, target, rate in buckets:
        values = split_taxable_bucket(target, rate)
        taxable_invoice_values[label] = values

    exempt_total = targets["exempt_registered"] + targets["exempt_unregistered"]
    exempt_values = split_exempt_bucket(exempt_total)

    total_invoices = sum(len(v) for v in taxable_invoice_values.values()) + len(exempt_values)
    if total_invoices == 0:
        warnings.append("No B2C or Exempt targets found for this month — nothing generated.")
        return [], warnings, {}

    invoice_numbers = generate_invoice_numbers(start_invoice, total_invoices)
    dates = random_increasing_dates(month, total_invoices)

    cursor = 0
    bucket_summary = {}

    for label, rate in (("5", 5), ("18", 18)):
        values = taxable_invoice_values[label]
        if not values:
            continue
        bucket_taxable_sum = 0.0
        computed = []
        for v in values:
            taxable = round(v / (1 + rate / 100), 2)
            tax = round(v - taxable, 2)
            computed.append({"invoice_no": None, "date": None, "taxable": taxable, "tax": tax, "invoice_value": v})
            bucket_taxable_sum += taxable

        # Absorb any penny-level rounding drift into the last invoice's taxable value
        target_val = targets[f"b2c_{label}"]
        drift = round(target_val - bucket_taxable_sum, 2)
        if drift != 0:
            computed[-1]["taxable"] = round(computed[-1]["taxable"] + drift, 2)
            bucket_taxable_sum = round(bucket_taxable_sum + drift, 2)

        for c in computed:
            all_rows.append({
                "invoice_no": invoice_numbers[cursor],
                "date": dates[cursor],
                "category": f"B2C_{label}%",
                "rate": rate,
                "taxable": c["taxable"],
                "tax": c["tax"],
                "invoice_value": c["invoice_value"],
            })
            cursor += 1
        bucket_summary[f"b2c_{label}"] = {
            "count": len(values),
            "taxable_sum": bucket_taxable_sum,
            "target": targets[f"b2c_{label}"],
        }

    exempt_taxable_sum = 0.0
    for v in exempt_values:
        all_rows.append({
            "invoice_no": invoice_numbers[cursor],
            "date": dates[cursor],
            "category": "EXEMPT",
            "rate": 0,
            "taxable": v,
            "tax": 0.0,
            "invoice_value": v,
        })
        exempt_taxable_sum += v
        cursor += 1
    bucket_summary["exempt"] = {"count": len(exempt_values), "taxable_sum": round(exempt_taxable_sum, 2), "target": exempt_total}

    return all_rows, warnings, bucket_summary


# ─────────────────────────────────────────────
# 5. OUTPUT WRITERS
# ─────────────────────────────────────────────

def write_b2cs_csv(bucket_summary, out_path):
    """CONSOLIDATED by rate+state — this is the actual B2CS JSON structure:
    one row per rate, NOT invoice-wise."""
    cols = ["Type", "Place Of Supply", "Rate", "Applicable % of Tax Rate",
            "Taxable Value", "Cess Amount", "E-Commerce GSTIN"]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for label, rate in (("5", 5), ("18", 18)):
            info = bucket_summary.get(f"b2c_{label}")
            if info and info["taxable_sum"] > 0:
                w.writerow(["INTRA", POS_NAME, rate, "", f'{info["taxable_sum"]:.2f}', "0.00", ""])


def write_exemp_csv(targets, out_path):
    """EXEMP JSON — exactly 4 fixed rows, only 2 non-zero here since your
    business is Intra-State only."""
    cols = ["Description", "Nil Rated", "Exempted", "Non-GST Supplies"]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerow(["Inter-State supplies to registered persons", "0.00", "0.00", "0.00"])
        w.writerow(["Intra-State supplies to registered persons", "0.00", f'{targets["exempt_registered"]:.2f}', "0.00"])
        w.writerow(["Inter-State supplies to unregistered persons", "0.00", "0.00", "0.00"])
        w.writerow(["Intra-State supplies to unregistered persons", "0.00", f'{targets["exempt_unregistered"]:.2f}', "0.00"])


def write_hsn_b2c_csv(bucket_summary, targets, hsn_5, hsn_18, hsn_exempt, out_path):
    """
    HSN(B2C) summary — one row per rate bucket (5%, 18%, Exempt).

    NOTE: Quantity/UQC are NOT tracked here — b2c_generator.py works purely
    off rupee targets (from the FY2026-27 sheet), not product quantities.
    Total Quantity is left as 0 / UQC blank until a Product Master is built
    to link amounts back to actual units sold.
    """
    cols = ["HSN", "Description", "UQC", "Total Quantity", "Total Value", "Rate",
            "Taxable Value", "Integrated Tax Amount", "Central Tax Amount",
            "State/UT Tax Amount", "Cess Amount"]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)

        for label, rate, hsn in (("5", 5, hsn_5), ("18", 18, hsn_18)):
            info = bucket_summary.get(f"b2c_{label}")
            if info and info["taxable_sum"] > 0:
                taxable = info["taxable_sum"]
                tax = round(taxable * rate / 100, 2)
                camt = round(tax / 2, 2)
                samt = round(tax - camt, 2)
                total_val = round(taxable + tax, 2)
                w.writerow([hsn, "", "", 0, f"{total_val:.2f}", rate,
                            f"{taxable:.2f}", "0.00", f"{camt:.2f}", f"{samt:.2f}", "0.00"])

        exempt_info = bucket_summary.get("exempt")
        if exempt_info and exempt_info["taxable_sum"] > 0:
            taxable = exempt_info["taxable_sum"]
            w.writerow([hsn_exempt, "", "", 0, f"{taxable:.2f}", 0,
                        f"{taxable:.2f}", "0.00", "0.00", "0.00", "0.00"])


def write_cash_records_csv(all_rows, out_path):
    cols = ["Sl", "Invoice No.", "Invoice Date", "Category", "Rate",
            "Taxable Value (₹)", "GST (₹)", "Invoice Value (₹)"]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for i, r in enumerate(all_rows, start=1):
            w.writerow([
                i, r["invoice_no"], r["date"].strftime("%Y-%m-%d"), r["category"],
                r["rate"], f'{r["taxable"]:.2f}', f'{r["tax"]:.2f}', f'{r["invoice_value"]:.2f}',
            ])



    cols = ["Sl", "Invoice No.", "Invoice Date", "Category", "Rate",
            "Taxable Value (₹)", "GST (₹)", "Invoice Value (₹)"]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for i, r in enumerate(all_rows, start=1):
            w.writerow([
                i, r["invoice_no"], r["date"].strftime("%Y-%m-%d"), r["category"],
                r["rate"], f'{r["taxable"]:.2f}', f'{r["tax"]:.2f}', f'{r["invoice_value"]:.2f}',
            ])


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="B2C + Exempt invoice generator")
    # Legacy positional (local Excel mode)
    p.add_argument("workbook",   nargs="?", default=None)
    p.add_argument("month_pos",  nargs="?", default=None)
    # Named args (Sheets / web mode)
    p.add_argument("--month",        default=None)
    p.add_argument("--gstin",        default=None)
    p.add_argument("--sheet-id",     default=None, help="Google Sheets spreadsheet ID")
    p.add_argument("--start-invoice", default=None)
    p.add_argument("--hsn5",         default="151499")
    p.add_argument("--hsn18",        default="TBD")
    p.add_argument("--hsn-exempt",   default="1005")
    p.add_argument("--outdir",       default="b2c_output")
    args = p.parse_args()

    month     = args.month or args.month_pos
    if not month:
        sys.exit("ERROR: month is required (e.g. 042026 or --month 042026)")

    sheet_id   = args.sheet_id or os.environ.get("SHEET_ID")
    use_sheets = bool(sheet_id)
    outdir     = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # ── SHEETS MODE ──────────────────────────────────────────
    if use_sheets:
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'db'))
            from sheets import SheetsClient
        except ImportError as e:
            sys.exit(f"Sheets import failed: {e}")

        client = SheetsClient()
        supplier_gstin, _ = client.read_supplier_info(sheet_id)
        if args.gstin: supplier_gstin = args.gstin
        if not supplier_gstin:
            sys.exit("ERROR: GSTIN not found in sheet M1 and --gstin not given")

        targets = client.read_month_targets(sheet_id, month)

        # Auto-detect CM start
        start_invoice = args.start_invoice
        if not start_invoice and DB_AVAILABLE:
            last = get_last_invoice_number(supplier_gstin, "CM")
            if last:
                m = CM_PATTERN.match(last)
                if m:
                    next_num = int(m.group(2)) + 1
                    start_invoice = f"{m.group(1)}{str(next_num).zfill(len(m.group(2)))}"
        if not start_invoice:
            start_invoice = client.read_last_invoice_number(sheet_id, "CM") or "CM260001"

    else:
        # ── LOCAL EXCEL MODE ─────────────────────────────────
        if not args.workbook:
            sys.exit("ERROR: workbook path required in local mode")
        wb_path = Path(args.workbook)
        if not wb_path.exists():
            sys.exit(f"File not found: {wb_path}")
        wb = openpyxl.load_workbook(str(wb_path), data_only=True)

        supplier_gstin = args.gstin
        if not supplier_gstin and "FY2026-27" in wb.sheetnames:
            val = wb["FY2026-27"]["M1"].value
            if val: supplier_gstin = str(val).strip()
        if not supplier_gstin:
            supplier_gstin = "10FLZPK2273L1ZL"

        start_invoice = args.start_invoice
        if not start_invoice and DB_AVAILABLE:
            last = get_last_invoice_number(supplier_gstin, "CM")
            if last:
                m = CM_PATTERN.match(last)
                if m:
                    next_num = int(m.group(2)) + 1
                    start_invoice = f"{m.group(1)}{str(next_num).zfill(len(m.group(2)))}"
                    print(f"  (CM start auto-detected from DB: last={last}, next={start_invoice})")
        if not start_invoice:
            start_invoice = "CM260001"
            print(f"  (No DB / no --start-invoice given — defaulting to {start_invoice})")

        targets = read_month_targets(wb, month)

    print(f"\n{'='*60}")
    print(f"  B2C + Exempt Invoice Generator  |  IT Maverick Solutions")
    print(f"{'='*60}")
    print(f"  Mode                 : {'Google Sheets ✓' if use_sheets else 'Local Excel'}")
    print(f"  GSTIN                : {supplier_gstin}")
    print(f"  Period               : {month[:2]}/{month[2:]}  (sheet row {targets['row']})")
    print(f"  B2C @5%  Target      : ₹{targets['b2c_5']:,.2f}")
    print(f"  B2C @18% Target      : ₹{targets['b2c_18']:,.2f}")
    print(f"  Exempt (Registered)  : ₹{targets['exempt_registered']:,.2f}")
    print(f"  Exempt (Unregistered): ₹{targets['exempt_unregistered']:,.2f}")
    if DB_AVAILABLE:
        print(f"  DB                   : NeonDB connected ✓")
    print(f"{'='*60}\n")

    all_rows, warnings, summary = build_all_invoices(targets, month, start_invoice)

    if not all_rows:
        print("Nothing to generate.")
        for w in warnings: print(" -", w)
        return

    for key, info in summary.items():
        diff = info["taxable_sum"] - info["target"]
        print(f"  {key:<10} → {info['count']:>3} invoices   "
              f"Target ₹{info['target']:>12,.2f}   Achieved ₹{info['taxable_sum']:>12,.2f}   "
              f"(diff ₹{diff:.2f})")

    print(f"\n  Total invoices: {len(all_rows)}")
    print(f"  Invoice range : {all_rows[0]['invoice_no']} → {all_rows[-1]['invoice_no']}")
    print(f"  Max invoice value: ₹{max(r['invoice_value'] for r in all_rows):,.2f}")

    write_b2cs_csv(summary, outdir / "b2cs_rows.csv")
    write_exemp_csv(targets, outdir / "exemp_row.csv")
    write_cash_records_csv(all_rows, outdir / "cash_sales_records.csv")
    write_hsn_b2c_csv(summary, targets, args.hsn5, args.hsn18, args.hsn_exempt, outdir / "hsn_b2c_rows.csv")

    if summary.get("b2c_18", {}).get("taxable_sum", 0) > 0 and args.hsn18 == "TBD":
        warnings.append(
            "18% bucket has sales but --hsn18 wasn't given — HSN written as 'TBD'. "
            "Re-run with --hsn18 <code> before filing."
        )

    # DB save
    if DB_AVAILABLE:
        try:
            save_monthly_targets(month, supplier_gstin, {
                "taxable_5pct": targets["b2c_5"], "taxable_18pct": targets["b2c_18"],
                "exempt_registered": targets["exempt_registered"],
                "exempt_unregistered": targets["exempt_unregistered"],
                "b2c_5pct": targets["b2c_5"], "b2c_18pct": targets["b2c_18"],
            })
            for r in all_rows: r["is_intra"] = True
            inserted = save_invoices(all_rows, month, supplier_gstin)
            print(f"  ✓ NeonDB: {inserted} invoice rows saved")
        except Exception as e:
            print(f"  ⚠ NeonDB save failed: {e} (CSVs still written)")

    if warnings:
        print(f"\n  ⚠ Warnings:")
        for w in warnings: print(f"  - {w}")

    print(f"\n  ✓ Files written to {outdir}/")
    print(f"    - b2cs_rows.csv, exemp_row.csv, hsn_b2c_rows.csv, cash_sales_records.csv")
    print(f"\n  NEXT: Invoice Planning — EXEMPTED range {all_rows[0]['invoice_no']} to {all_rows[-1]['invoice_no']}, COUNT = {len(all_rows)}")
    print(f"{'='*60}\n")

    wb_path = Path(args.workbook)
    if not wb_path.exists():
        sys.exit(f"File not found: {wb_path}")

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    wb = openpyxl.load_workbook(str(wb_path), data_only=True)

    # Supplier GSTIN workbook se
    supplier_gstin = None
    if "FY2026-27" in wb.sheetnames:
        val = wb["FY2026-27"]["M1"].value
        if val:
            supplier_gstin = str(val).strip()
    if not supplier_gstin:
        supplier_gstin = "10FLZPK2273L1ZL"

    # CM start invoice — DB se auto-detect, ya argument se, ya default
    start_invoice = args.start_invoice
    if not start_invoice and DB_AVAILABLE:
        last = get_last_invoice_number(supplier_gstin, "CM")
        if last:
            m = CM_PATTERN.match(last)
            if m:
                prefix, digits = m.group(1), m.group(2)
                next_num = int(digits) + 1
                start_invoice = f"{prefix}{str(next_num).zfill(len(digits))}"
                print(f"  (CM start auto-detected from DB: last={last}, next={start_invoice})")
    if not start_invoice:
        start_invoice = "CM260001"
        print(f"  (No DB / no --start-invoice given — defaulting to {start_invoice})")

        targets = read_month_targets(wb, month)

    print(f"\n{'='*60}")
    print(f"  B2C + Exempt Invoice Generator  |  IT Maverick Solutions")
    print(f"{'='*60}")
    print(f"  Mode                 : {'Google Sheets ✓' if use_sheets else 'Local Excel'}")
    print(f"  GSTIN                : {supplier_gstin}")
    print(f"  Period               : {month[:2]}/{month[2:]}  (sheet row {targets['row']})")
    print(f"  B2C @5%  Target      : ₹{targets['b2c_5']:,.2f}")
    print(f"  B2C @18% Target      : ₹{targets['b2c_18']:,.2f}")
    print(f"  Exempt (Registered)  : ₹{targets['exempt_registered']:,.2f}")
    print(f"  Exempt (Unregistered): ₹{targets['exempt_unregistered']:,.2f}")
    if DB_AVAILABLE:
        print(f"  DB                   : NeonDB connected ✓")
    print(f"{'='*60}\n")

    all_rows, warnings, summary = build_all_invoices(targets, month, start_invoice)

    if not all_rows:
        print("Nothing to generate.")
        for w in warnings:
            print(" -", w)
        return

    for key, info in summary.items():
        diff = info["taxable_sum"] - info["target"]
        print(f"  {key:<10} → {info['count']:>3} invoices   "
              f"Target ₹{info['target']:>12,.2f}   Achieved ₹{info['taxable_sum']:>12,.2f}   "
              f"(diff ₹{diff:.2f})")

    print(f"\n  Total invoices: {len(all_rows)}")
    print(f"  Invoice range : {all_rows[0]['invoice_no']} → {all_rows[-1]['invoice_no']}")
    print(f"  Max invoice value: ₹{max(r['invoice_value'] for r in all_rows):,.2f}")

    write_b2cs_csv(summary, outdir / "b2cs_rows.csv")
    write_exemp_csv(targets, outdir / "exemp_row.csv")
    write_cash_records_csv(all_rows, outdir / "cash_sales_records.csv")
    write_hsn_b2c_csv(summary, targets, args.hsn5, args.hsn18, args.hsn_exempt, outdir / "hsn_b2c_rows.csv")

    if summary.get("b2c_18", {}).get("taxable_sum", 0) > 0 and args.hsn18 == "TBD":
        warnings.append(
            "18% bucket has sales but --hsn18 wasn't given — HSN written as 'TBD'. "
            "Re-run with --hsn18 <code> before filing."
        )

    # DB mein save karo
    if DB_AVAILABLE:
        try:
            # Targets save karo
            save_monthly_targets(month, supplier_gstin, {
                "taxable_5pct": targets["b2c_5"],
                "taxable_18pct": targets["b2c_18"],
                "exempt_registered": targets["exempt_registered"],
                "exempt_unregistered": targets["exempt_unregistered"],
                "b2c_5pct": targets["b2c_5"],
                "b2c_18pct": targets["b2c_18"],
            })
            # Rows prepare karo DB ke liye
            for r in all_rows:
                r["is_intra"] = True  # sab intra-state
            inserted = save_invoices(all_rows, month, supplier_gstin)
            print(f"  ✓ NeonDB: {inserted} invoice rows saved")
        except Exception as e:
            print(f"  ⚠ NeonDB save failed: {e} (CSVs still written)")

    if warnings:
        print(f"\n  ⚠ Warnings:")
        for w in warnings:
            print(f"  - {w}")

    print(f"\n  ✓ Files written to {outdir}/")
    print(f"    - b2cs_rows.csv          → B2CS section of GSTR-1 JSON")
    print(f"    - exemp_row.csv          → EXEMP section of GSTR-1 JSON")
    print(f"    - hsn_b2c_rows.csv       → HSN(B2C) section of GSTR-1 JSON")
    print(f"    - cash_sales_records.csv → invoice-level detail (ERP entry)")
    print(f"\n  NEXT: For your Invoice Planning sheet, EXEMPTED INVOICE range is")
    print(f"        {all_rows[0]['invoice_no']} to {all_rows[-1]['invoice_no']}, COUNT = {len(all_rows)}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()

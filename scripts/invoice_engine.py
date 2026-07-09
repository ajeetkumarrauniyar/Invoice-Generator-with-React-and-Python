"""
invoice_engine.py  —  v2.0
============================
GST Smart Planner | IT Maverick Solutions | Muskan Enterprises

WHAT CHANGED FROM b2b_planner.py (v1):
  ✓ Batch mode: reads ALL parties from a "B2B_PARTIES" sheet in your workbook
    (GSTIN, Party, Target) — one run handles the whole month.
  ✓ Invoice numbering is AUTO-DETECTED by scanning your B2B-SALES-RECORDS
    sheet for the highest existing invoice number — you never type it.
  ✓ Exact ₹0.00 diff — a small round-off adjustment (a few rupees, standard
    invoicing practice) is applied to each party's last invoice so the
    total matches your target exactly. (Mathematically, ₹2000/₹2020
    combinations only land on multiples of ₹20 — see note below.)
  ✓ Natural variation — invoice values, carton splits, and dates now vary
    realistically instead of clustering close together.
  ✓ Writes DIRECTLY into GSTR1-B2B and GSTR1-HSN-B2B sheets (clears old
    data, writes fresh — these sheets represent ONE filing month).
  ✓ Writes to a NEW file by default (never touches your live workbook
    unless you pass --inplace). Review the _UPDATED file, then replace
    your master.

WHAT'S DELIBERATELY NOT AUTOMATED:
  B2B-SALES-RECORDS is NOT auto-written. Its summary section format
  changes by hand every month (different layout in April vs May in your
  actual file) — auto-editing it risks corrupting your historical ledger.
  Instead, this script outputs a clean CSV (sales_records_addition.csv)
  with the new invoice rows — paste those into your ledger yourself,
  wherever your current month's block goes.

REQUIRED SETUP (one-time):
  Add a sheet named "B2B_PARTIES" to your workbook with these columns
  starting at row 2 (row 1 = headers):

      GSTIN              | Party              | Target
      10CABPK9941H1ZV    | ASHA ENTERPRISES   | 488324
      10ATYPJ1834A1Z2    | BHUMI ENTERPRISES  | 320840

  That's the ONLY manual data entry each month.

USAGE:
    python3 invoice_engine.py <workbook_path> <MMYYYY> [--outfile PATH] [--inplace]

EXAMPLE:
    python3 invoice_engine.py GST_Monthwise_Ratewise_Bifurcation.xlsx 062026

OUTPUT:
    <workbook>_UPDATED.xlsx           ← GSTR1-B2B & HSN-B2B freshly populated
    sales_records_addition.csv        ← paste into B2B-SALES-RECORDS manually
"""

import sys
import os
import re
import csv
import random
import calendar
import argparse
import datetime
from pathlib import Path
from collections import defaultdict

try:
    import openpyxl
except ImportError:
    sys.exit("Install openpyxl first:  pip install openpyxl --break-system-packages")

# DB integration — optional (graceful fallback agar .env nahi mila)
try:
    from db import get_last_invoice_number, save_invoices, upsert_party
    DB_AVAILABLE = True
except Exception:
    DB_AVAILABLE = False

# ─────────────────────────────────────────────
# CONFIG (from your workbook)
# ─────────────────────────────────────────────
PARTIES_SHEET   = "B2B_PARTIES"
B2B_SHEET       = "GSTR1-B2B"
HSN_SHEET       = "GSTR1-HSN-B2B"
RECORDS_SHEET   = "B2B-SALES-RECORDS"

B2B_HEADER_ROW  = 4
B2B_DATA_START  = 5
HSN_HEADER_ROW  = 4
HSN_DATA_START  = 5

RATE_1L         = 2000
RATE_500ML      = 2020
GST_RATE        = 5
DEFAULT_HSN     = "151499"
DEFAULT_UQC     = "CTN"
INVOICE_CAP     = 50000
SUPPLIER_STATE  = "10"   # Bihar

POS_NAMES = {
    "10": "10-Bihar", "09": "09-Uttar Pradesh", "19": "19-West Bengal",
    "20": "20-Jharkhand", "07": "07-Delhi",
}

INVOICE_NO_PATTERN = re.compile(r"^([A-Za-z]+)(\d+)$")


# ─────────────────────────────────────────────
# 1. READ PARTIES
# ─────────────────────────────────────────────

def read_parties(wb):
    if PARTIES_SHEET not in wb.sheetnames:
        sys.exit(
            f"\nERROR: Sheet '{PARTIES_SHEET}' not found.\n\n"
            f"Add a sheet named '{PARTIES_SHEET}' with columns:\n"
            f"  Row 1 (headers): GSTIN | Party | Target\n"
            f"  Row 2 onwards:   your party data\n\n"
            f"Example:\n"
            f"  10CABPK9941H1ZV | ASHA ENTERPRISES  | 488324\n"
            f"  10ATYPJ1834A1Z2 | BHUMI ENTERPRISES | 320840\n"
        )
    ws = wb[PARTIES_SHEET]
    parties = []
    r = 2
    while True:
        gstin = ws.cell(row=r, column=1).value
        party = ws.cell(row=r, column=2).value
        target = ws.cell(row=r, column=3).value
        if gstin is None and party is None and target is None:
            break
        if gstin and party and target:
            parties.append({
                "gstin": str(gstin).strip(),
                "party": str(party).strip(),
                "target": float(target),
            })
        r += 1
    if not parties:
        sys.exit(f"ERROR: '{PARTIES_SHEET}' sheet has no data rows (row 2 onwards).")
    return parties


# ─────────────────────────────────────────────
# 2. AUTO-DETECT NEXT INVOICE NUMBER
# ─────────────────────────────────────────────

def detect_next_invoice_number(wb, supplier_gstin=None):
    """
    Next ME invoice number auto-detect karta hai.
    Priority:
      1. NeonDB (agar available hai) — most reliable, har mahine sahi rahega
      2. B2B-SALES-RECORDS sheet scan — fallback agar DB nahi mila
    """
    if DB_AVAILABLE and supplier_gstin:
        last = get_last_invoice_number(supplier_gstin, "ME")
        if last:
            m = INVOICE_NO_PATTERN.match(last)
            if m:
                prefix, digits = m.group(1), m.group(2)
                next_num = int(digits) + 1
                print(f"  (Invoice number auto-detected from DB: last={last})")
                return f"{prefix}{str(next_num).zfill(len(digits))}"

    # Fallback: Excel sheet scan
    if RECORDS_SHEET not in wb.sheetnames:
        return "ME260001"
    ws = wb[RECORDS_SHEET]
    best = None
    for row in ws.iter_rows():
        for cell in row:
            if cell.value is None or not isinstance(cell.value, str):
                continue
            m = INVOICE_NO_PATTERN.match(cell.value.strip())
            if m:
                prefix, digits = m.group(1), m.group(2)
                num = int(digits)
                if best is None or num > best[0]:
                    best = (num, prefix, len(digits))

    if best is None:
        return "ME260001"
    num, prefix, width = best
    return f"{prefix}{str(num + 1).zfill(width)}"


def generate_invoice_numbers(start_no, count):
    m = INVOICE_NO_PATTERN.match(start_no)
    prefix, digits = m.group(1), m.group(2)
    width = len(digits)
    start_num = int(digits)
    return [f"{prefix}{str(start_num + k).zfill(width)}" for k in range(count)]


# ─────────────────────────────────────────────
# 3. CARTON ALLOCATION ENGINE
# ─────────────────────────────────────────────

def find_aggregate_cartons(target, rate1, rate2):
    """Total (qty_1l, qty_500ml) across all of a party's invoices that best
    matches the target. Bigger search space than a single invoice → very close."""
    best = None
    max_q1 = int(target // rate1) + 2
    for q1 in range(0, max_q1 + 1):
        remaining = target - q1 * rate1
        if remaining < 0:
            break
        for q2 in (int(remaining / rate2), round(remaining / rate2), int(remaining / rate2) + 1):
            if q2 < 0:
                continue
            achieved = q1 * rate1 + q2 * rate2
            diff = abs(achieved - target)
            if best is None or diff < best[2]:
                best = (q1, q2, diff, achieved)
    return best


def split_int_total(total, n, spread=0.5):
    """Splits an integer total into n non-negative parts with NATURAL
    variation — wider spread than a near-equal split, so invoice values
    don't cluster together."""
    if total == 0:
        return [0] * n
    weights = [random.uniform(1 - spread, 1 + spread) for _ in range(n)]
    scale = total / sum(weights)
    parts = [round(w * scale) for w in weights]
    parts = [max(0, p) for p in parts]

    drift = total - sum(parts)
    idxs = list(range(n))
    random.shuffle(idxs)
    i = 0
    while drift != 0:
        idx = idxs[i % n]
        if drift > 0:
            parts[idx] += 1
            drift -= 1
        elif parts[idx] > 0:
            parts[idx] -= 1
            drift += 1
        i += 1
    return parts


def rebalance_for_cap(q1_parts, q2_parts, rate1, rate2, cap, max_iterations=3000):
    def value(i):
        return q1_parts[i] * rate1 + q2_parts[i] * rate2

    for _ in range(max_iterations):
        values = [value(i) for i in range(len(q1_parts))]
        over_idx = max(range(len(values)), key=lambda i: values[i])
        if values[over_idx] < cap:
            break
        under_idx = min(range(len(values)), key=lambda i: values[i])
        if q1_parts[over_idx] > 0:
            q1_parts[over_idx] -= 1
            q1_parts[under_idx] += 1
        elif q2_parts[over_idx] > 0:
            q2_parts[over_idx] -= 1
            q2_parts[under_idx] += 1
        else:
            break
    return q1_parts, q2_parts


def random_increasing_dates(month_yyyymm, count):
    """Random days within the month, sorted ascending — NOT evenly spaced."""
    mm, yyyy = int(month_yyyymm[:2]), int(month_yyyymm[2:])
    days_in_month = calendar.monthrange(yyyy, mm)[1]
    if count <= days_in_month:
        days = sorted(random.sample(range(1, days_in_month + 1), count))
    else:
        days = sorted(random.choices(range(1, days_in_month + 1), k=count))
    return [datetime.date(yyyy, mm, d) for d in days]


# ─────────────────────────────────────────────
# 4. PLAN ONE PARTY'S INVOICES
# ─────────────────────────────────────────────

def plan_party_invoices(party, invoice_numbers, month, warnings):
    gstin, name, target_taxable = party["gstin"], party["party"], party["target"]
    pos = POS_NAMES.get(gstin[:2], f"{gstin[:2]}-Unknown")
    is_intra = gstin[:2] == SUPPLIER_STATE
    n = len(invoice_numbers)

    # ── IMPORTANT: `target` is the TAXABLE value (tax-EXCLUSIVE), as entered
    # in the Sales Planning Sheet's "B2B Sales @5%" column.
    # Carton rates (₹2000 / ₹2020) are the tax-INCLUSIVE per-carton price,
    # so we allocate cartons to hit an INVOICE-VALUE target = taxable × 1.05.
    # The ₹50,000 e-way-bill cap applies to the INVOICE value (tax-inclusive).
    target_invoice_value = round(target_taxable * (1 + GST_RATE / 100), 2)

    total_q1, total_q2, agg_diff, agg_achieved = find_aggregate_cartons(
        target_invoice_value, RATE_1L, RATE_500ML
    )

    q1_parts = split_int_total(total_q1, n)
    q2_parts = split_int_total(total_q2, n)
    q1_parts, q2_parts = rebalance_for_cap(q1_parts, q2_parts, RATE_1L, RATE_500ML, INVOICE_CAP)

    dates = random_increasing_dates(month, n)

    rows = []
    running_taxable = 0.0
    for idx in range(n):
        q1, q2 = q1_parts[idx], q2_parts[idx]
        invoice_value = q1 * RATE_1L + q2 * RATE_500ML
        taxable = round(invoice_value / (1 + GST_RATE / 100), 2)
        tax_total = round(invoice_value - taxable, 2)
        rows.append({
            "invoice_no": invoice_numbers[idx], "date": dates[idx],
            "gstin": gstin, "receiver": name, "qty_1l": q1, "qty_500ml": q2,
            "invoice_value": invoice_value, "taxable": taxable, "tax_total": tax_total,
            "pos": pos, "is_intra": is_intra,
        })
        running_taxable += taxable

    # ── Round-off adjustment: force the TAXABLE total to EXACTLY match the
    # entered target (which is a taxable-value figure). ₹2000/₹2020 carton
    # combos only land on multiples of ₹20, so a small rupee-level round-off
    # on the last invoice's taxable value reconciles against the target —
    # same idea as the "Round Off" line on any commercial invoice.
    final_diff = round(target_taxable - running_taxable, 2)
    if final_diff != 0:
        last = rows[-1]
        last["taxable"] = round(last["taxable"] + final_diff, 2)
        # Recompute that invoice's value + tax from the adjusted taxable
        last["invoice_value"] = round(last["taxable"] * (1 + GST_RATE / 100), 2)
        last["tax_total"] = round(last["invoice_value"] - last["taxable"], 2)
        if abs(final_diff) > 20:
            warnings.append(
                f"{name}: round-off of ₹{final_diff:.2f} applied to last invoice "
                f"{last['invoice_no']} taxable value — larger than usual, review."
            )

    # Cap check on INVOICE value (tax-inclusive)
    for r in rows:
        if r["invoice_value"] >= INVOICE_CAP:
            warnings.append(
                f"{name}: invoice {r['invoice_no']} = ₹{r['invoice_value']:,.2f} "
                f"(tax-incl) — at/over ₹50,000 cap"
            )

    return rows


# ─────────────────────────────────────────────
# 5. WRITE INTO GSTR1-B2B / GSTR1-HSN-B2B SHEETS
# ─────────────────────────────────────────────

def clear_data_rows(ws, header_row, data_start, ncols, max_scan=5000):
    r = data_start
    cleared = 0
    while r < data_start + max_scan:
        vals = [ws.cell(row=r, column=c).value for c in range(1, ncols + 1)]
        if all(v is None for v in vals):
            break
        for c in range(1, ncols + 1):
            ws.cell(row=r, column=c).value = None
        cleared += 1
        r += 1
    return cleared


def write_gstr1_b2b(ws, all_rows):
    B2B_COLS = 13
    cleared = clear_data_rows(ws, B2B_HEADER_ROW, B2B_DATA_START, B2B_COLS)
    r = B2B_DATA_START
    for row in all_rows:
        ws.cell(row=r, column=1).value = row["gstin"]
        ws.cell(row=r, column=2).value = row["receiver"]
        ws.cell(row=r, column=3).value = row["invoice_no"]
        ws.cell(row=r, column=4).value = row["date"].strftime("%d-%b-%Y")
        ws.cell(row=r, column=5).value = row["invoice_value"]
        ws.cell(row=r, column=6).value = row["pos"]
        ws.cell(row=r, column=7).value = "N"
        ws.cell(row=r, column=8).value = ""
        ws.cell(row=r, column=9).value = "Regular B2B"
        ws.cell(row=r, column=10).value = ""
        ws.cell(row=r, column=11).value = GST_RATE
        ws.cell(row=r, column=12).value = row["taxable"]
        ws.cell(row=r, column=13).value = 0.00
        r += 1
    return cleared, r - B2B_DATA_START


def write_hsn_b2b(ws, all_rows):
    HSN_COLS = 11
    cleared = clear_data_rows(ws, HSN_HEADER_ROW, HSN_DATA_START, HSN_COLS)

    total_qty = sum(r["qty_1l"] + r["qty_500ml"] for r in all_rows)
    taxable_sum = sum(r["taxable"] for r in all_rows)
    tax_sum = sum(r["tax_total"] for r in all_rows)
    intra_taxable = sum(r["taxable"] for r in all_rows if r["is_intra"])
    intra_tax = sum(r["tax_total"] for r in all_rows if r["is_intra"])
    inter_tax = sum(r["tax_total"] for r in all_rows if not r["is_intra"])

    camt = round(intra_tax / 2, 2)
    samt = round(intra_tax - camt, 2)
    iamt = round(inter_tax, 2)

    row_num = HSN_DATA_START
    ws.cell(row=row_num, column=1).value = DEFAULT_HSN
    ws.cell(row=row_num, column=2).value = ""
    ws.cell(row=row_num, column=3).value = DEFAULT_UQC
    ws.cell(row=row_num, column=4).value = total_qty
    ws.cell(row=row_num, column=5).value = round(taxable_sum + tax_sum, 2)
    ws.cell(row=row_num, column=6).value = GST_RATE
    ws.cell(row=row_num, column=7).value = round(taxable_sum, 2)
    ws.cell(row=row_num, column=8).value = iamt
    ws.cell(row=row_num, column=9).value = camt
    ws.cell(row=row_num, column=10).value = samt
    ws.cell(row=row_num, column=11).value = 0.00

    return cleared, 1


def write_sales_records_csv(all_rows, out_path):
    cols = [
        "Sl", "Invoice No.", "Invoice Date", "GSTIN", "Receiver Name",
        "1 Ltr CTN", "500ml CTN", "Taxable Value (₹)", "GST @5% (₹)", "Invoice Value (₹)",
    ]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for i, r in enumerate(all_rows, start=1):
            w.writerow([
                i, r["invoice_no"], r["date"].strftime("%Y-%m-%d"), r["gstin"], r["receiver"],
                r["qty_1l"], r["qty_500ml"], f'{r["taxable"]:.2f}',
                f'{r["tax_total"]:.2f}', f'{r["invoice_value"]:.2f}',
            ])


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="B2B Invoice Engine — batch, auto-numbered, writes into Excel or Sheets")
    # Legacy positional args (local Excel mode)
    p.add_argument("workbook", nargs="?", default=None, help="Path to Excel workbook (local mode)")
    p.add_argument("month_pos", nargs="?", default=None, help="MMYYYY positional (local mode)")
    # New named args (Sheets / web mode)
    p.add_argument("--month",    default=None, help="MMYYYY e.g. 062026")
    p.add_argument("--gstin",    default=None, help="Supplier GSTIN (overrides sheet M1)")
    p.add_argument("--sheet-id", default=None, help="Google Sheets spreadsheet ID")
    p.add_argument("--outfile",  default=None, help="Output xlsx path (local mode only)")
    p.add_argument("--inplace",  action="store_true")
    args = p.parse_args()

    # Resolve month from positional or named arg
    month = args.month or args.month_pos
    if not month:
        sys.exit("ERROR: month is required (e.g. 062026 or --month 062026)")

    sheet_id  = args.sheet_id or os.environ.get("SHEET_ID")
    use_sheets = bool(sheet_id)

    # ── SHEETS MODE ─────────────────────────────────────────
    if use_sheets:
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'db'))
            from sheets import SheetsClient
        except ImportError as e:
            sys.exit(f"Sheets import failed: {e}\nInstall: pip install google-auth google-auth-httplib2 google-api-python-client --break-system-packages")

        client = SheetsClient()
        supplier_gstin, trade_name = client.read_supplier_info(sheet_id)
        if args.gstin:
            supplier_gstin = args.gstin
        if not supplier_gstin:
            sys.exit("ERROR: GSTIN not found in sheet M1 and --gstin not given")

        parties = client.read_b2b_parties(sheet_id)
        if not parties:
            sys.exit(f"ERROR: No parties found in B2B_PARTIES sheet of spreadsheet {sheet_id}")

        # Auto-detect next invoice number: DB first, then Sheets scan
        next_invoice = None
        if DB_AVAILABLE:
            try:
                last = get_last_invoice_number(supplier_gstin, "ME")
                if last:
                    import re as _re
                    m = _re.match(r"^([A-Za-z]+)(\d+)$", last)
                    if m:
                        next_invoice = f"{m.group(1)}{str(int(m.group(2))+1).zfill(len(m.group(2)))}"
            except Exception:
                pass
        if not next_invoice:
            next_invoice = client.read_last_invoice_number(sheet_id, "ME") or "ME260001"

        print(f"\n{'='*60}")
        print(f"  B2B Invoice Engine  |  IT Maverick Solutions")
        print(f"{'='*60}")
        print(f"  Mode            : Google Sheets ✓")
        print(f"  GSTIN           : {supplier_gstin}  ({trade_name})")
        print(f"  Period          : {month[:2]}/{month[2:]}")
        print(f"  Parties         : {len(parties)}")
        print(f"  Next Invoice No : {next_invoice}")
        if DB_AVAILABLE:
            print(f"  DB              : NeonDB connected ✓")
        print(f"{'='*60}\n")

        warnings = []
        all_rows = []
        invoice_cursor = next_invoice

        for party in parties:
            n_invoices = max(1, -(-int(party["target"]) // 36000))  # divide taxable target; 36000 taxable x 1.05 = 37800 invoice value, safely under 50k
            invoice_numbers = generate_invoice_numbers(invoice_cursor, n_invoices)
            rows = plan_party_invoices(party, invoice_numbers, month, warnings)
            all_rows.extend(rows)
            achieved = sum(r["invoice_value"] for r in rows)
            print(f"  {party['party']:<30} Target ₹{party['target']:>12,.2f}  "
                  f"→ {n_invoices} invoices  Achieved ₹{achieved:>12,.2f}  "
                  f"(diff ₹{achieved - party['target']:.2f})")
            if DB_AVAILABLE:
                try: upsert_party(party["gstin"], party["party"])
                except Exception as e: warnings.append(f"DB upsert: {e}")
            invoice_cursor = generate_invoice_numbers(invoice_numbers[-1], 2)[1]

        print(f"\n  Total invoices generated: {len(all_rows)}")

        # Write back to Sheets (only GSTR1-B2B & HSN — the GST filing sheets)
        b2b_count = client.write_b2b_invoices(sheet_id, all_rows)
        print(f"  ✓ GSTR1-B2B sheet updated: {b2b_count} rows")
        client.write_hsn_b2b(sheet_id, all_rows)
        print(f"  ✓ GSTR1-HSN-B2B sheet updated")

        # NOTE: B2B-SALES-RECORDS sheet is no longer written — that data now
        # lives in NeonDB. View/export it anytime via the Reports page
        # (queries the DB live, ERP-ready format).

        # DB save
        if DB_AVAILABLE:
            try:
                for r in all_rows:
                    r["supplier_gstin"] = supplier_gstin
                    r["pos"] = str(r.get("pos", "10")).split("-")[0]
                inserted = save_invoices(all_rows, month, supplier_gstin)
                print(f"  ✓ NeonDB: {inserted} invoice rows saved")
            except Exception as e:
                print(f"  ⚠ NeonDB save failed: {e}")

        if warnings:
            print(f"\n  ⚠ {len(warnings)} WARNINGS:")
            for w in warnings: print(f"  - {w}")
        else:
            print("\n  ✓ No warnings.")
        print(f"\n{'='*60}\n")
        return

    # ── LOCAL EXCEL MODE (unchanged) ────────────────────────
    if not args.workbook:
        sys.exit("ERROR: workbook path required in local mode (or use --sheet-id for Sheets mode)")

    wb_path = Path(args.workbook)
    if not wb_path.exists():
        sys.exit(f"File not found: {wb_path}")

    out_path = Path(args.outfile) if args.outfile else wb_path.with_name(wb_path.stem + "_UPDATED" + wb_path.suffix)
    wb = openpyxl.load_workbook(str(wb_path), data_only=False)

    supplier_gstin = args.gstin
    if not supplier_gstin and "FY2026-27" in wb.sheetnames:
        val = wb["FY2026-27"]["M1"].value
        if val: supplier_gstin = str(val).strip()
    if not supplier_gstin:
        supplier_gstin = "10FLZPK2273L1ZL"

    parties = read_parties(wb)
    next_invoice = detect_next_invoice_number(wb, supplier_gstin)

    print(f"\n{'='*60}")
    print(f"  B2B Invoice Engine  |  IT Maverick Solutions")
    print(f"{'='*60}")
    print(f"  GSTIN           : {supplier_gstin}")
    print(f"  Period          : {month[:2]}/{month[2:]}")
    print(f"  Parties         : {len(parties)}")
    print(f"  Next Invoice No : {next_invoice}  (auto-detected)")
    if DB_AVAILABLE:
        print(f"  DB              : NeonDB connected ✓")
    else:
        print(f"  DB              : not connected (CSV fallback)")
    print(f"{'='*60}\n")

    warnings = []
    all_rows = []
    invoice_cursor = next_invoice

    for party in parties:
        n_invoices = max(1, -(-int(party["target"]) // 36000))  # divide taxable target; 36000 taxable x 1.05 = 37800 invoice value, safely under 50k
        invoice_numbers = generate_invoice_numbers(invoice_cursor, n_invoices)
        rows = plan_party_invoices(party, invoice_numbers, month, warnings)
        all_rows.extend(rows)
        achieved = sum(r["invoice_value"] for r in rows)
        print(f"  {party['party']:<30} Target ₹{party['target']:>12,.2f}  "
              f"→ {n_invoices} invoices  Achieved ₹{achieved:>12,.2f}  "
              f"(diff ₹{achieved - party['target']:.2f})")
        if DB_AVAILABLE:
            try: upsert_party(party["gstin"], party["party"])
            except Exception as e: warnings.append(f"DB party upsert failed for {party['gstin']}: {e}")
        invoice_cursor = generate_invoice_numbers(invoice_numbers[-1], 2)[1]

    print(f"\n  Total invoices generated: {len(all_rows)}")

    write_gstr1_b2b(wb[B2B_SHEET], all_rows)
    write_hsn_b2b(wb[HSN_SHEET], all_rows)
    wb.save(str(out_path))

    records_csv = wb_path.parent / "sales_records_addition.csv"
    write_sales_records_csv(all_rows, records_csv)

    if DB_AVAILABLE:
        try:
            for r in all_rows:
                r["supplier_gstin"] = supplier_gstin
                r["pos"] = r.get("pos", "10").split("-")[0]
            inserted = save_invoices(all_rows, month, supplier_gstin)
            print(f"  ✓ NeonDB: {inserted} invoice rows saved")
        except Exception as e:
            print(f"  ⚠ NeonDB save failed: {e} (CSV still written)")

    print(f"\n  ✓ {B2B_SHEET} & {HSN_SHEET} updated → {out_path}")
    print(f"  ✓ Sales-record rows written → {records_csv}")
    if not DB_AVAILABLE:
        print(f"    (paste these into B2B-SALES-RECORDS manually)")

    if warnings:
        print(f"\n  ⚠ {len(warnings)} WARNINGS:")
        for w in warnings:
            print(f"  - {w}")
    else:
        print("\n  ✓ No warnings — every party hit its target exactly, all invoices under cap.")

    print(f"\n{'='*60}")
    print("  NEXT: review Sheets, then run gstr1_generator.py.")
    print(f"{'='*60}\n")
    return  # ← Sheets mode ends here, do NOT fall through to local Excel block

    # ── LOCAL EXCEL MODE (only reached when --sheet-id not given) ────
    wb_path = Path(args.workbook)
    if not wb_path.exists():
        sys.exit(f"File not found: {wb_path}")

    out_path = Path(args.outfile) if args.outfile else wb_path.with_name(wb_path.stem + "_UPDATED" + wb_path.suffix)

    wb = openpyxl.load_workbook(str(wb_path), data_only=False)

    # Supplier GSTIN workbook se read karo (M1 cell — Executive Dashboard)
    supplier_gstin = None
    if "FY2026-27" in wb.sheetnames:
        val = wb["FY2026-27"]["M1"].value
        if val:
            supplier_gstin = str(val).strip()
    if not supplier_gstin:
        supplier_gstin = "10FLZPK2273L1ZL"  # hardcoded fallback

    parties = read_parties(wb)
    next_invoice = detect_next_invoice_number(wb, supplier_gstin)

    print(f"\n{'='*60}")
    print(f"  B2B Invoice Engine  |  IT Maverick Solutions")
    print(f"{'='*60}")
    print(f"  GSTIN           : {supplier_gstin}")
    print(f"  Period          : {month[:2]}/{month[2:]}")
    print(f"  Parties         : {len(parties)}")
    print(f"  Next Invoice No : {next_invoice}  (auto-detected)")
    if DB_AVAILABLE:
        print(f"  DB              : NeonDB connected ✓")
    else:
        print(f"  DB              : not connected (CSV fallback)")
    print(f"{'='*60}\n")

    warnings = []
    all_rows = []
    invoice_cursor = next_invoice

    for party in parties:
        n_invoices = max(1, -(-int(party["target"]) // 36000))  # divide taxable target; 36000 taxable x 1.05 = 37800 invoice value, safely under 50k
        invoice_numbers = generate_invoice_numbers(invoice_cursor, n_invoices)
        rows = plan_party_invoices(party, invoice_numbers, month, warnings)
        all_rows.extend(rows)

        achieved = sum(r["invoice_value"] for r in rows)
        print(f"  {party['party']:<30} Target ₹{party['target']:>12,.2f}  "
              f"→ {n_invoices} invoices  Achieved ₹{achieved:>12,.2f}  "
              f"(diff ₹{achieved - party['target']:.2f})")

        # DB mein party upsert karo
        if DB_AVAILABLE:
            try:
                upsert_party(party["gstin"], party["party"])
            except Exception as e:
                warnings.append(f"DB party upsert failed for {party['gstin']}: {e}")

        invoice_cursor = generate_invoice_numbers(invoice_numbers[-1], 2)[1]

    print(f"\n  Total invoices generated: {len(all_rows)}")

    write_gstr1_b2b(wb[B2B_SHEET], all_rows)
    write_hsn_b2b(wb[HSN_SHEET], all_rows)
    wb.save(str(out_path))

    records_csv = wb_path.parent / "sales_records_addition.csv"
    write_sales_records_csv(all_rows, records_csv)

    # DB mein save karo
    if DB_AVAILABLE:
        try:
            # rows mein supplier_gstin aur is_intra add karo
            for r in all_rows:
                r["supplier_gstin"] = supplier_gstin
                r["pos"] = r.get("pos", "10").split("-")[0]
            inserted = save_invoices(all_rows, month, supplier_gstin)
            print(f"  ✓ NeonDB: {inserted} invoice rows saved")
        except Exception as e:
            print(f"  ⚠ NeonDB save failed: {e} (CSV still written)")

    print(f"\n  ✓ {B2B_SHEET} & {HSN_SHEET} updated → {out_path}")
    print(f"  ✓ Sales-record rows written → {records_csv}")
    if not DB_AVAILABLE:
        print(f"    (paste these into B2B-SALES-RECORDS manually)")

    if warnings:
        print(f"\n  ⚠ {len(warnings)} WARNINGS:")
        for w in warnings:
            print(f"  - {w}")
    else:
        print("\n  ✓ No warnings — every party hit its target exactly, all invoices under cap.")

    print(f"\n{'='*60}")
    print("  NEXT: review the _UPDATED file, then run gstr1_generator.py on it.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()

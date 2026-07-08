"""
gstr1_generator.py  —  v3.0  FINAL
====================================
GST Smart Planner | IT Maverick Solutions

Reads directly from your working Excel (GST_Monthwise_Ratewise_Bifurcation.xlsx)
and produces a GSTR-1 JSON that the GST portal accepts for DIRECT UPLOAD.

Schema confirmed from REAL successfully-uploaded JSON:
  - returns_06072026_R1_10FLZPK2273L1ZL_offline.json  ← this actually uploaded OK

CONFIRMED top-level keys (from the real working upload):
  { gstin, fp, version, hash, b2b, hsn }
  NOTE: gt, cur_gt, doc_issue are NOT in the working upload schema — removed.

KEY FIXES vs previous versions:
  ✓ version = "GST3.2.4"  (confirmed from working upload — was "GST2.2" before)
  ✓ hash = "hash"          (literal string — portal replaces this)
  ✓ gt / cur_gt REMOVED    (not present in working upload JSON)
  ✓ doc_issue REMOVED      (not present in working upload JSON — only in template)
  ✓ Self-GSTIN invoices SKIPPED with warning (error RET191314 = portal rejects these)
  ✓ GSTIN trailing spaces stripped (your sheet has "10ATYPJ1834A1Z2   ")
  ✓ Date: Excel serial (46145.0) -> "DD-MM-YYYY" format
  ✓ Rate: 0.05 fraction -> 5.0 percentage (your HSN sheet stores as fraction)
  ✓ Place of Supply: "Bihar" -> "10" (2-digit code confirmed)
  ✓ inv_typ: "Regular" -> "R" (short code)
  ✓ iamt omitted for intra-state; camt/samt omitted for inter-state
  ✓ hsn: iamt always present (even as 0) — confirmed from working upload
  ✓ hsn structure: object with hsn_b2b[] / hsn_b2c[] arrays

Usage:
    python gstr1_generator.py <xlsx_path> <MMYYYY> [output_json_path]

Example — for May 2026 return:
    python gstr1_generator.py GST_Monthwise_Ratewise_Bifurcation.xlsx 052026

Output file (if not specified): gstr1_<MMYYYY>_<GSTIN>.json
"""

import sys
import re
import json
import datetime
from pathlib import Path
from collections import defaultdict

try:
    import openpyxl
except ImportError:
    sys.exit("Install openpyxl first:  pip install openpyxl --break-system-packages")

# DB integration — optional
try:
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'db'))
    from db import save_filing_record, mark_json_exported, get_conn
    DB_AVAILABLE = True
except Exception:
    DB_AVAILABLE = False
    get_conn = None

# ─────────────────────────────────────────────
# SHEET CONFIG  (your workbook's exact layout)
# ─────────────────────────────────────────────
B2B_SHEET        = "GSTR1-B2B"
HSN_SHEET        = "GSTR1-HSN-B2B"
B2B_HEADER_ROW   = 4   # row 4 has column names
B2B_DATA_START   = 5   # row 5 is first data row
HSN_HEADER_ROW   = 4
HSN_DATA_START   = 5

# Supplier GSTIN — DEFAULT/FALLBACK only. The actual value is auto-read
# from the FY2026-27 sheet's Executive Dashboard (cell M1 = GSTIN,
# M2 = Trade Name) each time the script runs. This constant is only used
# if that sheet/cell can't be found.
SUPPLIER_GSTIN   = "10FLZPK2273L1ZL"
SUPPLIER_STATE   = "10"   # Bihar

PLANNING_SHEET = "FY2026-27"
GSTIN_CELL = "M1"
TRADE_NAME_CELL = "M2"


def read_supplier_info(wb, warnings):
    """Reads GSTIN + Trade Name from the Executive Dashboard (FY2026-27
    sheet, cells M1/M2) so you never have to update a hardcoded value if
    you ever change GSTIN or file for a different entity."""
    if PLANNING_SHEET not in wb.sheetnames:
        warnings.append(f"Sheet '{PLANNING_SHEET}' not found — using hardcoded GSTIN {SUPPLIER_GSTIN}")
        return SUPPLIER_GSTIN, None
    ws = wb[PLANNING_SHEET]
    gstin = ws[GSTIN_CELL].value
    trade_name = ws[TRADE_NAME_CELL].value
    if not gstin:
        warnings.append(f"{PLANNING_SHEET}!{GSTIN_CELL} is blank — using hardcoded GSTIN {SUPPLIER_GSTIN}")
        return SUPPLIER_GSTIN, trade_name
    return str(gstin).strip(), (str(trade_name).strip() if trade_name else None)

# ─────────────────────────────────────────────
# LOOKUP TABLES
# ─────────────────────────────────────────────

# Place of Supply: state name/code -> 2-digit JSON code
POS_MAP = {
    "01": "01", "jammu & kashmir": "01", "jammu and kashmir": "01",
    "02": "02", "himachal pradesh": "02",
    "03": "03", "punjab": "03",
    "04": "04", "chandigarh": "04",
    "05": "05", "uttarakhand": "05",
    "06": "06", "haryana": "06",
    "07": "07", "delhi": "07",
    "08": "08", "rajasthan": "08",
    "09": "09", "uttar pradesh": "09",
    "10": "10", "bihar": "10",
    "11": "11", "sikkim": "11",
    "12": "12", "arunachal pradesh": "12",
    "13": "13", "nagaland": "13",
    "14": "14", "manipur": "14",
    "15": "15", "mizoram": "15",
    "16": "16", "tripura": "16",
    "17": "17", "meghalaya": "17",
    "18": "18", "assam": "18",
    "19": "19", "west bengal": "19",
    "20": "20", "jharkhand": "20",
    "21": "21", "odisha": "21",
    "22": "22", "chhattisgarh": "22",
    "23": "23", "madhya pradesh": "23",
    "24": "24", "gujarat": "24",
    "25": "25", "daman & diu": "25",
    "26": "26", "dadra & nagar haveli": "26",
    "27": "27", "maharashtra": "27",
    "29": "29", "karnataka": "29",
    "30": "30", "goa": "30",
    "31": "31", "lakshadweep": "31",
    "32": "32", "kerala": "32",
    "33": "33", "tamil nadu": "33",
    "34": "34", "puducherry": "34",
    "35": "35", "andaman & nicobar islands": "35",
    "36": "36", "telangana": "36",
    "37": "37", "andhra pradesh": "37",
    "38": "38", "ladakh": "38",
    "97": "97", "other territory": "97",
    "99": "99", "centre jurisdiction": "99",
}

INV_TYPE_MAP = {
    "regular":                                    "R",
    "regular b2b":                                "R",
    "deemed exp":                                 "DE",
    "deemed export":                              "DE",
    "sez supplies with payment":                  "SEWP",
    "sez wp":                                     "SEWP",
    "sez supplies without payment":               "SEWOP",
    "sez wop":                                    "SEWOP",
    "intra-state supplies attracting igst":       "CBW",
}

# Excel date serial origin
EXCEL_EPOCH = datetime.date(1899, 12, 30)


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def clean(v):
    """Strip and stringify any cell value."""
    if v is None:
        return ""
    return str(v).strip()


def to_float(v, default=0.0):
    """Convert cell value to float, stripping ₹ and commas."""
    if v is None:
        return default
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace("₹", "").replace(",", "").strip()
    if not s or s in ("-", "N/A"):
        return default
    try:
        return float(s)
    except ValueError:
        return default


def excel_date_to_str(v, row_num, warnings):
    """
    Converts Excel serial date (46145.0) or datetime object to DD-MM-YYYY.
    Your sheet stores dates as Excel serials (floats like 46145.0).
    """
    if v is None:
        warnings.append(f"Row {row_num}: Invoice date is blank")
        return ""
    if isinstance(v, datetime.datetime):
        return v.strftime("%d-%m-%Y")
    if isinstance(v, datetime.date):
        return v.strftime("%d-%m-%Y")
    # Try Excel serial
    try:
        serial = int(float(str(v)))
        d = EXCEL_EPOCH + datetime.timedelta(days=serial)
        return d.strftime("%d-%m-%Y")
    except (ValueError, TypeError):
        pass
    # Try text formats
    for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(str(v).strip(), fmt).strftime("%d-%m-%Y")
        except ValueError:
            continue
    warnings.append(f"Row {row_num}: Cannot parse date '{v}' — left as-is")
    return str(v).strip()


def map_pos(pos_raw, row_num, warnings):
    """Map Place of Supply to 2-digit code."""
    if not pos_raw:
        warnings.append(f"Row {row_num}: Place of Supply blank, defaulting to '10' (Bihar)")
        return "10"
    pos_str = str(pos_raw).strip()
    # Already "10-Bihar" or "10-" format
    if "-" in pos_str:
        code = pos_str.split("-")[0].strip()
        if code.isdigit():
            return code.zfill(2)
    # Bare number
    if pos_str.isdigit():
        return pos_str.zfill(2)
    # Name lookup
    key = pos_str.lower()
    code = POS_MAP.get(key)
    if code:
        return code
    warnings.append(f"Row {row_num}: Unknown Place of Supply '{pos_raw}', defaulting to '10' (Bihar)")
    return "10"


def map_inv_type(raw, row_num, warnings):
    code = INV_TYPE_MAP.get(raw.strip().lower())
    if not code:
        warnings.append(f"Row {row_num}: Unknown Invoice Type '{raw}', defaulting to 'R' (Regular)")
        return "R"
    return code


def read_sheet_rows(ws, header_row, data_start, ncols):
    """Read rows from sheet, stop at first fully-empty row."""
    headers = [clean(ws.cell(row=header_row, column=c).value) for c in range(1, ncols + 1)]
    rows = []
    r = data_start
    while True:
        vals = [ws.cell(row=r, column=c).value for c in range(1, ncols + 1)]
        if all(v is None for v in vals):
            break
        rows.append(dict(zip(headers, vals)))
        r += 1
    return rows


# ─────────────────────────────────────────────
# CORE BUILDERS
# ─────────────────────────────────────────────

def build_b2b(ws, warnings, all_invoice_numbers=None):
    """
    Reads GSTR1-B2B sheet and builds the b2b[] JSON array.

    Confirmed JSON structure (from real filed return):
    b2b: [
      {
        ctin: "...",
        inv: [
          {
            inum, idt, val, pos, rchrg, inv_typ,
            itms: [ { num, itm_det: { rt, txval, camt, samt, csamt } } ]
            // iamt present for inter-state; camt/samt present for intra-state
          }
        ]
      }
    ]
    Note: cfs, flag, cflag etc. are NOT included — these appear only in
    already-processed/downloaded JSONs, not in fresh-upload input files.

    `all_invoice_numbers` (if a list is passed in) gets EVERY invoice number
    seen in the sheet, including ones later skipped from the JSON (e.g.
    self-GSTIN rows) — needed so the DOCS section still counts documents
    that were physically issued, even if excluded from the B2B upload.
    """
    B2B_COLS = [
        "GSTIN/UIN of Recipient", "Receiver Name", "Invoice Number",
        "Invoice date", "Invoice Value", "Place Of Supply", "Reverse Charge",
        "Applicable % of Tax Rate", "Invoice Type", "E-Commerce GSTIN",
        "Rate", "Taxable Value", "Cess Amount",
    ]
    rows = read_sheet_rows(ws, B2B_HEADER_ROW, B2B_DATA_START, len(B2B_COLS))

    by_gstin = defaultdict(list)

    for i, row in enumerate(rows, start=B2B_DATA_START):
        gstin = clean(row.get("GSTIN/UIN of Recipient", ""))
        inv_no = clean(row.get("Invoice Number", ""))

        if not gstin:
            warnings.append(f"B2B Row {i}: GSTIN blank — skipped")
            continue
        if not inv_no:
            warnings.append(f"B2B Row {i}: Invoice Number blank — skipped")
            continue

        # Record this invoice number for DOCS purposes REGARDLESS of whether
        # it ends up skipped below — it was still physically issued.
        if all_invoice_numbers is not None:
            all_invoice_numbers.append(inv_no)

        # Skip self-GSTIN — portal returns error RET191314 for these
        # (confirmed from error report: "GSTIN you entered is same as counter Party GSTIN")
        if gstin == SUPPLIER_GSTIN:
            warnings.append(
                f"B2B Row {i}: Invoice {inv_no} SKIPPED — recipient GSTIN = supplier GSTIN "
                f"({SUPPLIER_GSTIN}). Portal rejects these (error RET191314). "
                f"Fix the GSTIN in your sheet before filing."
            )
            continue

        pos_code = map_pos(row.get("Place Of Supply"), i, warnings)
        idt      = excel_date_to_str(row.get("Invoice date"), i, warnings)
        inv_typ  = map_inv_type(clean(row.get("Invoice Type", "Regular")), i, warnings)
        rchrg    = clean(row.get("Reverse Charge", "N")) or "N"

        rate     = to_float(row.get("Rate"))
        # Rate stored as fraction in your sheet (0.05 = 5%) — convert if needed
        if 0 < rate < 1:
            rate = round(rate * 100, 2)
            warnings.append(f"B2B Row {i}: Rate was fraction ({rate/100}) — converted to {rate}%")

        txval    = to_float(row.get("Taxable Value"))
        inv_val  = to_float(row.get("Invoice Value"))
        cess     = to_float(row.get("Cess Amount"))
        total_tax = round(rate / 100 * txval, 2)

        itm_det = {"rt": rate, "txval": txval, "csamt": cess}

        if pos_code == SUPPLIER_STATE:
            # Intra-state → CGST + SGST, NO iamt
            camt = round(total_tax / 2, 2)
            samt = round(total_tax - camt, 2)
            itm_det["camt"] = camt
            itm_det["samt"] = samt
        else:
            # Inter-state → IGST only, NO camt/samt
            itm_det["iamt"] = total_tax

        invoice = {
            "inum": inv_no,
            "idt":  idt,
            "val":  inv_val,
            "pos":  pos_code,
            "rchrg": rchrg,
            "inv_typ": inv_typ,
            "itms": [{"num": 1, "itm_det": itm_det}],
        }
        by_gstin[gstin].append(invoice)

    b2b_list = []
    for gstin, invoices in by_gstin.items():
        b2b_list.append({"ctin": gstin, "inv": invoices})

    return b2b_list


def build_hsn(ws, warnings):
    """
    Reads GSTR1-HSN-B2B sheet and builds the hsn{} JSON object.

    Confirmed structure (from real filed return):
    hsn: {
      hsn_b2b: [
        { num, hsn_sc, desc, uqc, qty, txval, rt, camt, samt, csamt }
        // iamt present only if non-zero
      ],
      hsn_b2c: []
    }
    Note: Total Value ("val") field is NOT in the real JSON — omitted here.
    """
    HSN_COLS = [
        "HSN", "Description", "UQC", "Total Quantity", "Total Value",
        "Rate", "Taxable Value", "Integrated Tax Amount",
        "Central Tax Amount", "State/UT Tax Amount", "Cess Amount",
    ]
    rows = read_sheet_rows(ws, HSN_HEADER_ROW, HSN_DATA_START, len(HSN_COLS))

    items = []
    for i, row in enumerate(rows, start=HSN_DATA_START):
        hsn = clean(row.get("HSN", "")).replace(".0", "")
        if not hsn:
            warnings.append(f"HSN Row {i}: HSN code blank — skipped")
            continue

        rate = to_float(row.get("Rate"))
        if 0 < rate < 1:
            rate = round(rate * 100, 2)  # 0.05 -> 5.0

        iamt  = to_float(row.get("Integrated Tax Amount"))
        camt  = to_float(row.get("Central Tax Amount"))
        samt  = to_float(row.get("State/UT Tax Amount"))
        csamt = to_float(row.get("Cess Amount"))
        txval = to_float(row.get("Taxable Value"))
        qty   = to_float(row.get("Total Quantity"))
        uqc   = clean(row.get("UQC", ""))
        desc  = clean(row.get("Description", ""))

        # iamt always present (even as 0) — confirmed from working upload JSON
        item = {
            "num":    len(items) + 1,
            "hsn_sc": hsn,
            "desc":   desc,
            "uqc":    uqc,
            "qty":    qty,
            "rt":     rate,
            "txval":  txval,
            "iamt":   iamt,
            "camt":   camt,
            "samt":   samt,
            "csamt":  csamt,
        }

        items.append(item)

    return {"hsn_b2b": items, "hsn_b2c": []}


def build_b2cs(csv_path, warnings):
    """
    Reads b2cs_rows.csv (from b2c_generator.py) and builds the b2cs[] array.

    CONFIRMED structure (from the real working-upload JSON):
      [{ sply_ty, pos, typ, txval, rt, iamt, camt, samt, csamt }]
      sply_ty = "INTRA" or "INTER" (based on Place of Supply vs supplier state)
      typ     = "OE" (Other than E-commerce) — hardcoded since these are
                counter cash sales, not through an e-commerce operator.
    """
    import csv as csv_module
    entries = []
    if not csv_path or not Path(csv_path).exists():
        return entries

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv_module.DictReader(f)
        for i, row in enumerate(reader, start=2):
            pos_raw = clean(row.get("Place Of Supply", ""))
            pos_code = map_pos(pos_raw, i, warnings)
            sply_ty = "INTRA" if pos_code == SUPPLIER_STATE else "INTER"

            rate = to_float(row.get("Rate"))
            txval = to_float(row.get("Taxable Value"))
            cess = to_float(row.get("Cess Amount"))
            total_tax = round(rate / 100 * txval, 2)

            entry = {"sply_ty": sply_ty, "pos": pos_code, "typ": "OE", "txval": txval, "rt": rate}
            if sply_ty == "INTRA":
                camt = round(total_tax / 2, 2)
                samt = round(total_tax - camt, 2)
                entry.update({"iamt": 0.0, "camt": camt, "samt": samt})
            else:
                entry.update({"iamt": total_tax, "camt": 0.0, "samt": 0.0})
            entry["csamt"] = cess
            entries.append(entry)
    return entries


NIL_SPLY_TY_MAP = {
    "inter-state supplies to registered persons":   "INTRB2B",
    "intra-state supplies to registered persons":   "INTRAB2B",
    "inter-state supplies to unregistered persons": "INTRB2C",
    "intra-state supplies to unregistered persons":  "INTRAB2C",
}
NIL_ORDER = ["INTRB2B", "INTRAB2B", "INTRB2C", "INTRAB2C"]


def build_nil(csv_path, warnings):
    """
    Reads exemp_row.csv (from b2c_generator.py) and builds the nil{} object.

    CONFIRMED structure (from the real working-upload JSON):
      { "inv": [
          { sply_ty, expt_amt, nil_amt, ngsup_amt },   × 4 fixed categories
      ]}
    sply_ty codes: INTRB2B / INTRAB2B / INTRB2C / INTRAB2C — always all 4
    present (even as zero), matching what the portal expects.
    """
    import csv as csv_module
    by_type = {t: {"sply_ty": t, "expt_amt": 0.0, "nil_amt": 0.0, "ngsup_amt": 0.0} for t in NIL_ORDER}

    if not csv_path or not Path(csv_path).exists():
        return {"inv": list(by_type.values())}

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv_module.DictReader(f)
        for row in reader:
            desc = clean(row.get("Description", "")).lower()
            sply_ty = NIL_SPLY_TY_MAP.get(desc)
            if not sply_ty:
                warnings.append(f"EXEMP row: unrecognized description '{row.get('Description')}' — skipped")
                continue
            by_type[sply_ty]["nil_amt"] = to_float(row.get("Nil Rated"))
            by_type[sply_ty]["expt_amt"] = to_float(row.get("Exempted"))
            by_type[sply_ty]["ngsup_amt"] = to_float(row.get("Non-GST Supplies"))

    return {"inv": [by_type[t] for t in NIL_ORDER]}


def build_hsn_b2c(csv_path, warnings):
    """
    Reads hsn_b2c_rows.csv (from b2c_generator.py) and builds the
    hsn_b2c[] array — same field structure as hsn_b2b, confirmed from
    the working upload JSON.
    """
    import csv as csv_module
    items = []
    if not csv_path or not Path(csv_path).exists():
        return items

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv_module.DictReader(f)
        for row in reader:
            hsn = clean(row.get("HSN", "")).replace(".0", "")
            if not hsn:
                continue
            rate = to_float(row.get("Rate"))
            iamt = to_float(row.get("Integrated Tax Amount"))
            camt = to_float(row.get("Central Tax Amount"))
            samt = to_float(row.get("State/UT Tax Amount"))
            csamt = to_float(row.get("Cess Amount"))
            txval = to_float(row.get("Taxable Value"))
            qty = to_float(row.get("Total Quantity"))
            uqc = clean(row.get("UQC", ""))
            desc = clean(row.get("Description", ""))

            if hsn == "TBD":
                warnings.append(
                    "HSN(B2C) row has placeholder HSN code 'TBD' — re-run "
                    "b2c_generator.py with --hsn18 <code> before filing."
                )

            items.append({
                "num": len(items) + 1, "hsn_sc": hsn, "desc": desc, "uqc": uqc,
                "qty": qty, "rt": rate, "txval": txval,
                "iamt": iamt, "camt": camt, "samt": samt, "csamt": csamt,
            })
    return items


DOC_NUMBER_PATTERN = re.compile(r"^([A-Za-z]+)(\d+)$")


def build_docs(all_b2b_invoice_numbers, cash_records_path, warnings):
    """
    Builds the doc_issue{} section — CONFIRMED present in a real
    successfully-uploaded JSON (offline.json had this exact structure):

      { "doc_det": [
          { "doc_num": 1, "doc_typ": "Invoices for outward supply",
            "docs": [
              { "num": 1, "from": "ME260001", "to": "ME260020",
                "totnum": 20, "cancel": 0, "net_issue": 20 },
              { "num": 2, "from": "CM260001", "to": "CM260034",
                "totnum": 34, "cancel": 0, "net_issue": 34 },
            ]}
      ]}

    Each invoice series (grouped by letter-prefix, e.g. "ME", "CM") gets
    its own entry. Uses ALL invoice numbers physically issued (including
    ones later excluded from the B2B upload for GST-validity reasons,
    e.g. self-GSTIN rows) — document count reflects what was actually
    printed/issued, not what made it into the tax return.

    NOTE: 'cancel' is always 0 — this script doesn't track cancelled
    invoices. If you've cancelled any, adjust the JSON manually before
    filing.
    """
    import csv as csv_module
    series = defaultdict(list)  # prefix -> [(numeric_value, formatted_number), ...]

    for inv_no in all_b2b_invoice_numbers:
        m = DOC_NUMBER_PATTERN.match(inv_no)
        if m:
            series[m.group(1)].append((int(m.group(2)), inv_no))

    if cash_records_path and Path(cash_records_path).exists():
        with open(cash_records_path, newline="", encoding="utf-8") as f:
            reader = csv_module.DictReader(f)
            for row in reader:
                inv_no = clean(row.get("Invoice No.", ""))
                m = DOC_NUMBER_PATTERN.match(inv_no)
                if m:
                    series[m.group(1)].append((int(m.group(2)), inv_no))

    if not series:
        return None

    docs_list = []
    for i, (prefix, entries) in enumerate(sorted(series.items()), start=1):
        entries.sort(key=lambda x: x[0])
        from_no = entries[0][1]
        to_no = entries[-1][1]
        count = len(entries)
        expected_span = entries[-1][0] - entries[0][0] + 1
        if count != expected_span:
            warnings.append(
                f"DOCS: series '{prefix}' has {count} rows but spans "
                f"{expected_span} numbers ({from_no}-{to_no}) — some numbers "
                f"in between are missing from your sheet (not just GST-excluded)."
            )
        docs_list.append({
            "num": i, "from": from_no, "to": to_no,
            "totnum": expected_span, "cancel": 0, "net_issue": expected_span,
        })

    return {"doc_det": [{"doc_num": 1, "doc_typ": "Invoices for outward supply", "docs": docs_list}]}


def _build_b2b_from_db(fp, supplier_gstin, warnings):
    """
    Reads B2B invoices from NeonDB invoices table and builds
    the b2b[] array + hsn{hsn_b2b[]} + all_invoice_numbers list.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT invoice_no, invoice_date, invoice_value, place_of_supply,
                       party_gstin, party_name, gst_rate, taxable_value,
                       cgst_amount, sgst_amount, igst_amount, qty_1l, qty_500ml,
                       hsn_code
                FROM invoices
                WHERE fp = %s AND supplier_gstin = %s
                  AND invoice_type = 'B2B' AND is_cancelled = FALSE
                ORDER BY party_gstin, invoice_date, invoice_no
            """, (fp, supplier_gstin))
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]
            invoices = [dict(zip(cols, r)) for r in rows]

    if not invoices:
        warnings.append(f"No B2B invoices found in DB for {fp} / {supplier_gstin}")
        return [], {"hsn_b2b": [], "hsn_b2c": []}, []

    all_invoice_numbers = [r["invoice_no"] for r in invoices]

    # Group by party GSTIN
    from collections import defaultdict as _dd
    by_party = _dd(list)
    for r in invoices:
        by_party[r["party_gstin"]].append(r)

    b2b = []
    for party_gstin, party_invoices in by_party.items():
        inv_list = []
        for r in party_invoices:
            pos = str(r["place_of_supply"]).zfill(2) if r["place_of_supply"] else SUPPLIER_STATE
            rate  = float(r["gst_rate"]  or 0)
            txval = float(r["taxable_value"] or 0)
            camt  = float(r["cgst_amount"] or 0)
            samt  = float(r["sgst_amount"] or 0)
            iamt  = float(r["igst_amount"] or 0)

            inv_date = r["invoice_date"]
            if hasattr(inv_date, "strftime"):
                idt = inv_date.strftime("%d-%m-%Y")
            else:
                idt = str(inv_date)

            itm_det = {"rt": rate, "txval": txval, "csamt": 0.0}
            if pos == SUPPLIER_STATE:
                itm_det["camt"] = camt
                itm_det["samt"] = samt
            else:
                itm_det["iamt"] = iamt

            if r["invoice_no"].startswith(("ME", "me")):
                self_skip = (party_gstin == supplier_gstin)
                if self_skip:
                    warnings.append(f"Skipping self-GSTIN invoice {r['invoice_no']} (RET191314)")
                    continue

            inv_list.append({
                "inum": r["invoice_no"],
                "idt":  idt,
                "val":  float(r["invoice_value"] or 0),
                "pos":  pos,
                "rchrg": "N",
                "inv_typ": "R",
                "itms": [{"num": 1, "itm_det": itm_det}],
            })

        if inv_list:
            b2b.append({"ctin": party_gstin, "inv": inv_list})

    # Build HSN B2B summary from same data
    total_qty   = sum((r.get("qty_1l") or 0) + (r.get("qty_500ml") or 0) for r in invoices)
    taxable_sum = sum(float(r["taxable_value"] or 0) for r in invoices)
    cgst_sum    = sum(float(r["cgst_amount"] or 0) for r in invoices)
    sgst_sum    = sum(float(r["sgst_amount"] or 0) for r in invoices)
    igst_sum    = sum(float(r["igst_amount"] or 0) for r in invoices)
    gst_rate    = float(invoices[0]["gst_rate"] or 5) if invoices else 5
    hsn_code    = invoices[0].get("hsn_code") or "151499" if invoices else "151499"

    hsn_b2b = [{
        "num": 1, "hsn_sc": str(hsn_code), "desc": "", "uqc": "CTN",
        "qty": total_qty, "rt": gst_rate,
        "txval": round(taxable_sum, 2),
        "iamt": round(igst_sum, 2),
        "camt": round(cgst_sum, 2),
        "samt": round(sgst_sum, 2),
        "csamt": 0.0,
    }]

    return b2b, {"hsn_b2b": hsn_b2b, "hsn_b2c": []}, all_invoice_numbers


def _build_b2b_from_sheets(client, sheet_id, warnings):
    """Read B2B data from Google Sheets (fallback when DB not available)."""
    rows_data = client._get(sheet_id, f"GSTR1-B2B!A5:M500")
    all_invoice_numbers = []
    by_party = {}
    for row in rows_data:
        if len(row) < 12 or not row[0]:
            continue
        party_gstin = str(row[0]).strip()
        inv_no      = str(row[2]).strip()
        if not inv_no:
            continue
        all_invoice_numbers.append(inv_no)
        pos_raw = str(row[5]).strip()
        pos = pos_raw.split("-")[0].strip().zfill(2) if "-" in pos_raw else pos_raw.zfill(2)
        rate    = float(row[10] or 0)
        txval   = float(row[11] or 0)
        total_tax = round(rate / 100 * txval, 2)
        itm_det = {"rt": rate, "txval": txval, "csamt": 0.0}
        if pos == SUPPLIER_STATE:
            camt = round(total_tax / 2, 2)
            itm_det["camt"] = camt
            itm_det["samt"] = round(total_tax - camt, 2)
        else:
            itm_det["iamt"] = total_tax

        inv = {"inum": inv_no, "idt": str(row[3]).strip(),
               "val": float(row[4] or 0), "pos": pos,
               "rchrg": "N", "inv_typ": "R",
               "itms": [{"num": 1, "itm_det": itm_det}]}
        by_party.setdefault(party_gstin, []).append(inv)

    b2b = [{"ctin": g, "inv": invs} for g, invs in by_party.items()]

    # HSN from sheet
    hsn_rows = client._get(sheet_id, f"GSTR1-HSN-B2B!A5:K100")
    hsn_b2b = []
    for i, row in enumerate(hsn_rows):
        if not row or not row[0]: continue
        hsn_b2b.append({
            "num": i+1, "hsn_sc": str(row[0]).strip(), "desc": str(row[1] or ""),
            "uqc": str(row[2] or "CTN"), "qty": float(row[3] or 0),
            "rt": float(row[5] or 0), "txval": float(row[6] or 0),
            "iamt": float(row[7] or 0), "camt": float(row[8] or 0),
            "samt": float(row[9] or 0), "csamt": float(row[10] or 0),
        })
    return b2b, {"hsn_b2b": hsn_b2b, "hsn_b2c": []}, all_invoice_numbers


def _build_b2c_from_db(fp, supplier_gstin, warnings):
    """Reads B2C + Exempt invoices from DB and builds b2cs[] + nil{}."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            # B2CS — consolidated by rate
            cur.execute("""
                SELECT invoice_type, gst_rate,
                       SUM(taxable_value) AS taxable_sum,
                       SUM(cgst_amount)   AS cgst_sum,
                       SUM(sgst_amount)   AS sgst_sum,
                       SUM(igst_amount)   AS igst_sum
                FROM invoices
                WHERE fp = %s AND supplier_gstin = %s
                  AND invoice_type IN ('B2C_5','B2C_18') AND is_cancelled = FALSE
                GROUP BY invoice_type, gst_rate
            """, (fp, supplier_gstin))
            b2c_rows = cur.fetchall()

            # Exempt totals
            cur.execute("""
                SELECT SUM(taxable_value)
                FROM invoices
                WHERE fp = %s AND supplier_gstin = %s
                  AND invoice_type = 'EXEMPT' AND is_cancelled = FALSE
            """, (fp, supplier_gstin))
            exempt_row = cur.fetchone()

    b2cs = []
    for row in b2c_rows:
        inv_type, rate, txval, cgst, sgst, igst = row
        rate = float(rate or 0); txval = float(txval or 0)
        cgst = float(cgst or 0); sgst = float(sgst or 0); igst = float(igst or 0)
        entry = {"sply_ty": "INTRA", "pos": SUPPLIER_STATE, "typ": "OE",
                 "txval": round(txval, 2), "rt": rate,
                 "iamt": round(igst, 2), "camt": round(cgst, 2),
                 "samt": round(sgst, 2), "csamt": 0.0}
        b2cs.append(entry)

    # Exempt — split registered/unregistered from monthly_targets
    exempt_total = float(exempt_row[0] or 0) if exempt_row and exempt_row[0] else 0
    # Get split from monthly_targets if available
    expt_reg = expt_unreg = 0.0
    if DB_AVAILABLE:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT exempt_registered, exempt_unregistered
                        FROM monthly_targets WHERE fp = %s AND gstin = %s
                    """, (fp, supplier_gstin))
                    t = cur.fetchone()
                    if t:
                        expt_reg   = float(t[0] or 0)
                        expt_unreg = float(t[1] or 0)
        except Exception:
            # Fallback: 22/78 split as per your sheet default
            expt_reg   = round(exempt_total * 0.22, 2)
            expt_unreg = round(exempt_total - expt_reg, 2)

    nil_obj = {"inv": [
        {"sply_ty": "INTRB2B",  "expt_amt": 0.0,       "nil_amt": 0.0, "ngsup_amt": 0.0},
        {"sply_ty": "INTRAB2B", "expt_amt": expt_reg,   "nil_amt": 0.0, "ngsup_amt": 0.0},
        {"sply_ty": "INTRB2C",  "expt_amt": 0.0,        "nil_amt": 0.0, "ngsup_amt": 0.0},
        {"sply_ty": "INTRAB2C", "expt_amt": expt_unreg, "nil_amt": 0.0, "ngsup_amt": 0.0},
    ]}
    return b2cs, nil_obj


def _build_hsn_b2c_from_db(fp, supplier_gstin):
    """Builds HSN B2C summary from DB."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT invoice_type, gst_rate, hsn_code,
                       SUM(taxable_value) AS txval,
                       SUM(cgst_amount) AS camt, SUM(sgst_amount) AS samt,
                       SUM(igst_amount) AS iamt
                FROM invoices
                WHERE fp = %s AND supplier_gstin = %s
                  AND invoice_type IN ('B2C_5','B2C_18','EXEMPT') AND is_cancelled = FALSE
                GROUP BY invoice_type, gst_rate, hsn_code
            """, (fp, supplier_gstin))
            rows = cur.fetchall()

    items = []
    for i, (inv_type, rate, hsn, txval, camt, samt, iamt) in enumerate(rows):
        items.append({
            "num": i+1, "hsn_sc": str(hsn or "151499"), "desc": "", "uqc": "",
            "qty": 0, "rt": float(rate or 0),
            "txval": round(float(txval or 0), 2),
            "iamt": round(float(iamt or 0), 2),
            "camt": round(float(camt or 0), 2),
            "samt": round(float(samt or 0), 2),
            "csamt": 0.0,
        })
    return items


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    import argparse as _ap
    p = _ap.ArgumentParser(description="GSTR-1 JSON Generator")

    # Positional — optional now (only needed for local Excel mode)
    p.add_argument("xlsx_path", nargs="?", default=None,
                   help="Path to Excel workbook (local mode). Omit when using --sheet-id.")
    p.add_argument("fp_pos",    nargs="?", default=None,
                   help="Tax period MMYYYY (positional). Use --month instead for web mode.")

    # Named args (web / Sheets mode)
    p.add_argument("--month",        default=None, help="Tax period MMYYYY e.g. 052026")
    p.add_argument("--gstin",        default=None, help="Supplier GSTIN (overrides sheet/DB)")
    p.add_argument("--sheet-id",     default=None, help="Google Sheets spreadsheet ID")
    p.add_argument("--out",          default=None, help="Output JSON path")

    # B2C CSV overrides (only used in local Excel mode or when CSVs already exist)
    p.add_argument("--b2cs",         default=None)
    p.add_argument("--exemp",        default=None)
    p.add_argument("--hsn-b2c",      default=None)
    p.add_argument("--cash-records", default=None)

    args = p.parse_args()

    fp       = args.month or args.fp_pos
    sheet_id = args.sheet_id or os.environ.get("SHEET_ID")

    if not fp:
        sys.exit("ERROR: tax period required (e.g. --month 052026 or positional MMYYYY)")

    warnings             = []
    all_b2b_invoice_numbers = []
    use_sheets           = bool(sheet_id)
    use_db               = DB_AVAILABLE

    # ── RESOLVE GSTIN ───────────────────────────────────────
    global SUPPLIER_GSTIN, SUPPLIER_STATE

    if args.gstin:
        SUPPLIER_GSTIN = args.gstin.strip()
    elif use_db:
        # Try to get GSTIN from DB companies table
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT gstin FROM companies WHERE is_active = TRUE LIMIT 1")
                    row = cur.fetchone()
                    if row: SUPPLIER_GSTIN = row[0]
        except Exception:
            pass

    SUPPLIER_STATE = SUPPLIER_GSTIN[:2] if SUPPLIER_GSTIN else "10"

    out_path = Path(args.out) if args.out else Path(f"gstr1_{fp}_{SUPPLIER_GSTIN}.json")

    print(f"\n{'='*55}")
    print(f"  GSTR-1 JSON Generator  |  IT Maverick Solutions")
    print(f"{'='*55}")
    print(f"  GSTIN     : {SUPPLIER_GSTIN}")
    print(f"  Period    : {fp[:2]}/{fp[2:]}   ({fp})")
    print(f"  Mode      : {'Google Sheets + DB' if use_sheets else ('DB' if use_db else 'Local Excel')}")
    print(f"{'='*55}\n")

    b2b  = []
    hsn  = {"hsn_b2b": [], "hsn_b2c": []}
    b2cs = []
    nil_obj  = {"inv": [{"sply_ty": t, "expt_amt": 0.0, "nil_amt": 0.0, "ngsup_amt": 0.0}
                        for t in NIL_ORDER]}

    # ── B2B + HSN from DB (preferred) ──────────────────────
    if use_db:
        try:
            b2b, hsn, all_b2b_invoice_numbers = _build_b2b_from_db(fp, SUPPLIER_GSTIN, warnings)
            total_invoices = sum(len(e["inv"]) for e in b2b)
            print(f"  ✓ B2B   : {len(b2b)} recipients, {total_invoices} invoices  (from DB)")
            print(f"  ✓ HSN   : {len(hsn['hsn_b2b'])} rows  (computed from DB)")
        except Exception as e:
            warnings.append(f"DB B2B read failed: {e} — falling back to Excel/Sheet")
            use_db = False

    # ── B2B + HSN fallback: Excel or Google Sheets ─────────
    if not use_db:
        if use_sheets:
            try:
                from sheets import SheetsClient
                client = SheetsClient()
                # Read GSTIN if not already set
                if not args.gstin:
                    gstin_sheet, trade_name = client.read_supplier_info(sheet_id)
                    if gstin_sheet: SUPPLIER_GSTIN = gstin_sheet
                b2b, hsn, all_b2b_invoice_numbers = _build_b2b_from_sheets(client, sheet_id, warnings)
                print(f"  ✓ B2B   : {len(b2b)} recipients (from Sheets)")
            except Exception as e:
                sys.exit(f"ERROR reading from Google Sheets: {e}")
        elif args.xlsx_path:
            wb_path = Path(args.xlsx_path)
            if not wb_path.exists():
                sys.exit(f"File not found: {wb_path}")
            wb = openpyxl.load_workbook(str(wb_path), data_only=True)
            b2b  = build_b2b(wb[B2B_SHEET], warnings, all_invoice_numbers=all_b2b_invoice_numbers)
            hsn  = build_hsn(wb[HSN_SHEET], warnings)
            if not SUPPLIER_GSTIN:
                SUPPLIER_GSTIN, _ = read_supplier_info(wb, warnings)
            total_invoices = sum(len(e["inv"]) for e in b2b)
            print(f"  ✓ B2B   : {len(b2b)} recipients, {total_invoices} invoices  (from Excel)")
            print(f"  ✓ HSN   : {len(hsn['hsn_b2b'])} rows  (from Excel)")
        else:
            sys.exit("ERROR: No data source available. Provide --sheet-id, xlsx_path, or NeonDB connection.")

    # ── B2CS + EXEMP + HSN-B2C from DB ─────────────────────
    if DB_AVAILABLE:
        try:
            b2cs, nil_obj = _build_b2c_from_db(fp, SUPPLIER_GSTIN, warnings)
            print(f"  ✓ B2CS  : {len(b2cs)} rows  (from DB)")
            nonzero = sum(1 for e in nil_obj["inv"] if e["expt_amt"] or e["nil_amt"])
            print(f"  ✓ EXEMP : {nonzero} of 4 categories non-zero  (from DB)")
        except Exception as e:
            warnings.append(f"DB B2C read failed: {e} — using CSV files if provided")
            b2cs    = build_b2cs(args.b2cs, warnings) if args.b2cs else []
            nil_obj = build_nil(args.exemp, warnings)
    else:
        b2cs    = build_b2cs(args.b2cs, warnings) if args.b2cs else []
        nil_obj = build_nil(args.exemp, warnings)

    # HSN-B2C from DB
    if DB_AVAILABLE:
        try:
            hsn["hsn_b2c"] = _build_hsn_b2c_from_db(fp, SUPPLIER_GSTIN)
            print(f"  ✓ HSN-B2C: {len(hsn['hsn_b2c'])} rows  (from DB)")
        except Exception:
            if args.hsn_b2c:
                hsn["hsn_b2c"] = build_hsn_b2c(args.hsn_b2c, warnings)
    elif args.hsn_b2c:
        hsn["hsn_b2c"] = build_hsn_b2c(args.hsn_b2c, warnings)

    # ── DOCS ────────────────────────────────────────────────
    doc_issue = build_docs(all_b2b_invoice_numbers, args.cash_records, warnings)
    if doc_issue:
        print(f"  ✓ DOCS  : {len(doc_issue['doc_det'][0]['docs'])} invoice series")

    # ── FINAL PAYLOAD ───────────────────────────────────────
    payload = {
        "gstin":   SUPPLIER_GSTIN,
        "fp":      fp,
        "version": "GST3.2.4",
        "hash":    "hash",
        "b2b":     b2b,
        "hsn":     hsn,
    }
    if b2cs:       payload["b2cs"]      = b2cs
    if nil_obj:    payload["nil"]       = nil_obj
    if doc_issue:  payload["doc_issue"] = doc_issue

    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    total_txval   = sum(inv["itms"][0]["itm_det"]["txval"] for e in b2b for inv in e["inv"])
    b2cs_total    = sum(e["txval"] for e in b2cs)
    exempt_total  = sum(e["expt_amt"] + e["nil_amt"] + e["ngsup_amt"] for e in nil_obj["inv"])

    print(f"\n  ✓ JSON written → {out_path}")
    print(f"  ✓ B2B Taxable   : ₹{total_txval:,.2f}")
    print(f"  ✓ B2C Taxable   : ₹{b2cs_total:,.2f}")
    print(f"  ✓ Exempt/Nil    : ₹{exempt_total:,.2f}")

    if DB_AVAILABLE:
        try:
            save_filing_record(fp, SUPPLIER_GSTIN, out_path.name, {
                "b2b_taxable": total_txval, "b2c_taxable": b2cs_total,
                "exempt_taxable": exempt_total,
                "total_taxable": total_txval + b2cs_total + exempt_total,
                "total_gst": sum(
                    inv["itms"][0]["itm_det"].get("camt", 0) +
                    inv["itms"][0]["itm_det"].get("samt", 0) +
                    inv["itms"][0]["itm_det"].get("iamt", 0)
                    for e in b2b for inv in e["inv"]
                ),
            })
            mark_json_exported(fp, SUPPLIER_GSTIN)
            print(f"  ✓ NeonDB: filing record saved")
        except Exception as e:
            print(f"  ⚠ NeonDB filing record failed: {e}")

    if warnings:
        print(f"\n{'─'*55}")
        print(f"  ⚠  {len(warnings)} WARNINGS:")
        print(f"{'─'*55}")
        for w in warnings: print(f"  - {w}")
    else:
        print("\n  ✓ No warnings.")

    print(f"\n{'='*55}")
    print("  Upload → GST Portal → GSTR-1 → Import JSON")
    print(f"{'='*55}\n")

    xlsx_path = Path(sys.argv[1])
    fp = sys.argv[2].strip()

    # Parse remaining args: positional output path + optional --b2cs / --exemp flags
    rest = sys.argv[3:]
    out_path = None
    b2cs_path = None
    exemp_path = None
    hsn_b2c_path = None
    cash_records_path = None
    i = 0
    while i < len(rest):
        if rest[i] == "--b2cs":
            b2cs_path = rest[i + 1]
            i += 2
        elif rest[i] == "--exemp":
            exemp_path = rest[i + 1]
            i += 2
        elif rest[i] == "--hsn-b2c":
            hsn_b2c_path = rest[i + 1]
            i += 2
        elif rest[i] == "--cash-records":
            cash_records_path = rest[i + 1]
            i += 2
        else:
            out_path = rest[i]
            i += 1

    if not xlsx_path.exists():
        sys.exit(f"File not found: {xlsx_path}")

    wb = openpyxl.load_workbook(str(xlsx_path), data_only=True)
    warnings = []
    all_b2b_invoice_numbers = []

    global SUPPLIER_GSTIN, SUPPLIER_STATE
    SUPPLIER_GSTIN, trade_name = read_supplier_info(wb, warnings)
    SUPPLIER_STATE = SUPPLIER_GSTIN[:2]

    out_path = Path(out_path) if out_path else Path(f"gstr1_{fp}_{SUPPLIER_GSTIN}.json")

    print(f"\n{'='*55}")
    print(f"  GSTR-1 JSON Generator  |  IT Maverick Solutions")
    print(f"{'='*55}")
    print(f"  GSTIN     : {SUPPLIER_GSTIN}")
    if trade_name:
        print(f"  Trade Name: {trade_name}")
    print(f"  Period    : {fp[:2]}/{fp[2:]}   ({fp})")
    print(f"  Source    : {xlsx_path.name}")
    print(f"{'='*55}\n")

    # ── B2B
    if B2B_SHEET not in wb.sheetnames:
        sys.exit(f"ERROR: Sheet '{B2B_SHEET}' not found in workbook.")
    b2b = build_b2b(wb[B2B_SHEET], warnings, all_invoice_numbers=all_b2b_invoice_numbers)
    total_invoices = sum(len(e["inv"]) for e in b2b)
    print(f"  ✓ B2B   : {len(b2b)} recipients, {total_invoices} invoices")

    # ── HSN
    if HSN_SHEET not in wb.sheetnames:
        sys.exit(f"ERROR: Sheet '{HSN_SHEET}' not found in workbook.")
    hsn = build_hsn(wb[HSN_SHEET], warnings)
    print(f"  ✓ HSN   : {len(hsn['hsn_b2b'])} rows")

    # ── B2CS (optional — only if you pass --b2cs)
    b2cs = build_b2cs(b2cs_path, warnings)
    if b2cs_path:
        print(f"  ✓ B2CS  : {len(b2cs)} rows  (from {b2cs_path})")

    # ── EXEMP / nil (optional — only if you pass --exemp)
    nil_obj = build_nil(exemp_path, warnings)
    if exemp_path:
        nonzero = sum(1 for e in nil_obj["inv"] if e["expt_amt"] or e["nil_amt"] or e["ngsup_amt"])
        print(f"  ✓ EXEMP : {nonzero} of 4 categories non-zero  (from {exemp_path})")

    # ── HSN(B2C) (optional — only if you pass --hsn-b2c)
    if hsn_b2c_path:
        hsn["hsn_b2c"] = build_hsn_b2c(hsn_b2c_path, warnings)
        print(f"  ✓ HSN-B2C: {len(hsn['hsn_b2c'])} rows  (from {hsn_b2c_path})")

    # ── DOCS (auto-built from B2B invoice numbers + cash records, if given)
    doc_issue = build_docs(all_b2b_invoice_numbers, cash_records_path, warnings)
    if doc_issue:
        series_count = len(doc_issue["doc_det"][0]["docs"])
        print(f"  ✓ DOCS  : {series_count} invoice series detected")

    # ── Final payload  (keys confirmed from real working upload JSON)
    payload = {
        "gstin":   SUPPLIER_GSTIN,
        "fp":      fp,
        "version": "GST3.2.4",
        "hash":    "hash",
        "b2b":     b2b,
        "hsn":     hsn,
    }
    if b2cs_path:
        payload["b2cs"] = b2cs
    if exemp_path:
        payload["nil"] = nil_obj
    if doc_issue:
        payload["doc_issue"] = doc_issue

    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    total_txval = sum(
        inv["itms"][0]["itm_det"]["txval"]
        for e in b2b for inv in e["inv"]
    )
    b2cs_total = sum(e["txval"] for e in b2cs) if b2cs_path else 0
    exempt_total = sum(e["expt_amt"] + e["nil_amt"] + e["ngsup_amt"] for e in nil_obj["inv"]) if exemp_path else 0

    print(f"\n  ✓ JSON written → {out_path}")
    print(f"  ✓ B2B Total Taxable Value : ₹{total_txval:,.2f}")
    if b2cs_path:
        print(f"  ✓ B2CS Total Taxable Value: ₹{b2cs_total:,.2f}")
    if exemp_path:
        print(f"  ✓ Exempt/Nil Total        : ₹{exempt_total:,.2f}")

    # DB mein filing record save karo
    if DB_AVAILABLE:
        try:
            summary = {
                "b2b_taxable": total_txval,
                "b2c_taxable": b2cs_total,
                "exempt_taxable": exempt_total,
                "total_taxable": total_txval + b2cs_total + exempt_total,
                "total_gst": sum(
                    inv["itms"][0]["itm_det"].get("camt", 0) +
                    inv["itms"][0]["itm_det"].get("samt", 0) +
                    inv["itms"][0]["itm_det"].get("iamt", 0)
                    for e in b2b for inv in e["inv"]
                ),
            }
            save_filing_record(fp, SUPPLIER_GSTIN, out_path.name, summary)
            mark_json_exported(fp, SUPPLIER_GSTIN)
            print(f"  ✓ NeonDB: filing record saved, invoices marked as exported")
        except Exception as e:
            print(f"  ⚠ NeonDB save failed: {e}")

    if warnings:
        print(f"\n{'─'*55}")
        print(f"  ⚠  {len(warnings)} WARNINGS (review before uploading):")
        print(f"{'─'*55}")
        for w in warnings:
            print(f"  - {w}")
    else:
        print("\n  ✓ No warnings — data looks clean.")

    print(f"\n{'='*55}")
    print("  NEXT STEP: Upload this JSON to GST Portal:")
    print("  Services → Returns → Returns Dashboard →")
    print("  GSTR-1 → Import JSON")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()

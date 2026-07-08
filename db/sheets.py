"""
sheets.py — Google Sheets Integration
======================================
GST Smart Planner | IT Maverick Solutions

Har company ki Google Sheet se data padhta hai aur likhta hai.
Service account credentials .env.local se aate hain.

Install:
    pip install google-auth google-auth-httplib2 google-api-python-client --break-system-packages

Usage:
    from sheets import SheetsClient
    client = SheetsClient()
    targets = client.read_month_targets(spreadsheet_id, "042026")
    client.write_b2b_invoices(spreadsheet_id, rows)
"""

import os
import json
import datetime
from pathlib import Path
from dotenv import load_dotenv

def _load_env():
    # When called from Next.js spawn, GOOGLE_SERVICE_ACCOUNT_JSON already in env
    if os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON") or os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE"):
        return
    for env_file in [
        Path(__file__).parent.parent / ".env.local",
        Path(__file__).parent.parent / ".env",
        Path(".env.local"),
        Path(".env"),
    ]:
        if env_file.exists():
            load_dotenv(env_file, override=False)
            if os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON") or os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE"):
                return

_load_env()

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError:
    raise SystemExit(
        "Install Google API client:\n"
        "pip install google-auth google-auth-httplib2 google-api-python-client --break-system-packages"
    )

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Sheet names (same across all company sheets)
PLANNING_SHEET   = "FY2026-27"
B2B_SHEET        = "GSTR1-B2B"
HSN_B2B_SHEET    = "GSTR1-HSN-B2B"
RECORDS_SHEET    = "B2B-SALES-RECORDS"
PARTIES_SHEET    = "B2B_PARTIES"

# FY2026-27 sheet layout (confirmed from Muskan sheet)
PLANNING_DATA_START_ROW = 46   # April 2026 = row 46
COL_MONTH        = 1   # A
COL_5_TAXABLE    = 4   # D
COL_18_TAXABLE   = 5   # E
COL_EXEMPT_REG   = 7   # G
COL_EXEMPT_UNREG = 8   # H
COL_B2B_5        = 13  # M
COL_B2C_5        = 14  # N (formula =D-M)
COL_B2B_18       = 15  # O
COL_B2C_18       = 16  # P (formula =E-O)
GSTIN_CELL       = "M1"
TRADE_NAME_CELL  = "M2"

# B2B sheet layout
B2B_HEADER_ROW   = 4
B2B_DATA_START   = 5
B2B_NCOLS        = 13

# HSN sheet layout
HSN_HEADER_ROW   = 4
HSN_DATA_START   = 5
HSN_NCOLS        = 11

GST_RATE         = 5
RATE_1L          = 2000
RATE_500ML       = 2020


class SheetsClient:
    def __init__(self):
        self._service = None

    def _get_service(self):
        if self._service:
            return self._service

        # Load credentials from env (stored as JSON string) or file path
        creds_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
        creds_file = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE")

        if creds_json:
            info = json.loads(creds_json)
            creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
        elif creds_file:
            creds = service_account.Credentials.from_service_account_file(creds_file, scopes=SCOPES)
        else:
            raise SystemExit(
                "Google credentials not found.\n"
                "Set GOOGLE_SERVICE_ACCOUNT_JSON (JSON string) or\n"
                "GOOGLE_SERVICE_ACCOUNT_FILE (path to .json file) in .env.local"
            )

        self._service = build("sheets", "v4", credentials=creds)
        return self._service

    def _get(self, spreadsheet_id, range_):
        try:
            result = self._get_service().spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=range_,
                valueRenderOption="UNFORMATTED_VALUE",
                dateTimeRenderOption="SERIAL_NUMBER",
            ).execute()
            return result.get("values", [])
        except HttpError as e:
            raise RuntimeError(f"Sheets API GET error ({range_}): {e}")

    def _update(self, spreadsheet_id, range_, values):
        try:
            self._get_service().spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=range_,
                valueInputOption="USER_ENTERED",
                body={"values": values},
            ).execute()
        except HttpError as e:
            raise RuntimeError(f"Sheets API UPDATE error ({range_}): {e}")

    def _clear(self, spreadsheet_id, range_):
        try:
            self._get_service().spreadsheets().values().clear(
                spreadsheetId=spreadsheet_id,
                range=range_,
            ).execute()
        except HttpError as e:
            raise RuntimeError(f"Sheets API CLEAR error ({range_}): {e}")

    # ─────────────────────────────────────────────
    # READ SUPPLIER INFO
    # ─────────────────────────────────────────────

    def read_supplier_info(self, spreadsheet_id):
        """M1 = GSTIN, M2 = Trade Name from Executive Dashboard."""
        rows = self._get(spreadsheet_id, f"{PLANNING_SHEET}!M1:M2")
        gstin      = rows[0][0] if rows and rows[0] else None
        trade_name = rows[1][0] if len(rows) > 1 and rows[1] else None
        return (str(gstin).strip() if gstin else None,
                str(trade_name).strip() if trade_name else None)

    # ─────────────────────────────────────────────
    # READ MONTHLY TARGETS
    # ─────────────────────────────────────────────

    def read_month_targets(self, spreadsheet_id, fp):
        """
        Reads the Sales Planning Sheet row for a given month.
        fp: "042026" format
        Returns dict with b2c_5, b2c_18, exempt_registered, exempt_unregistered, row
        """
        mm = int(fp[:2])
        yyyy = int(fp[2:])

        # Read A:P from row 46 onwards (data section)
        rows = self._get(spreadsheet_id, f"{PLANNING_SHEET}!A{PLANNING_DATA_START_ROW}:P200")

        for i, row in enumerate(rows):
            if not row:
                continue
            cell = row[0]  # Column A — month value

            # Excel serial date or datetime
            match_month = False
            if isinstance(cell, (int, float)):
                from datetime import date
                excel_epoch = date(1899, 12, 30)
                d = excel_epoch + datetime.timedelta(days=int(cell))
                match_month = (d.month == mm and d.year == yyyy)
            elif isinstance(cell, str) and cell:
                # e.g. "Apr-2026"
                try:
                    d = datetime.datetime.strptime(cell.strip(), "%b-%Y")
                    match_month = (d.month == mm and d.year == yyyy)
                except ValueError:
                    pass

            if not match_month:
                continue

            def col(idx, default=0):
                try:
                    v = row[idx - 1]
                    return float(v) if v not in (None, "", " ") else default
                except (IndexError, ValueError, TypeError):
                    return default

            taxable_5  = col(COL_5_TAXABLE)
            taxable_18 = col(COL_18_TAXABLE)
            b2b_5      = col(COL_B2B_5)
            b2c_5_cell = col(COL_B2C_5)
            b2b_18     = col(COL_B2B_18)
            b2c_18_cell = col(COL_B2C_18)
            exempt_reg   = col(COL_EXEMPT_REG)
            exempt_unreg = col(COL_EXEMPT_UNREG)

            # Use sheet's own B2C value if non-zero, else derive
            b2c_5  = b2c_5_cell  if b2c_5_cell  else round(taxable_5  - b2b_5,  2)
            b2c_18 = b2c_18_cell if b2c_18_cell else round(taxable_18 - b2b_18, 2)

            return {
                "row":                 PLANNING_DATA_START_ROW + i,
                "b2c_5":               round(b2c_5, 2),
                "b2c_18":              round(b2c_18, 2),
                "exempt_registered":   round(exempt_reg, 2),
                "exempt_unregistered": round(exempt_unreg, 2),
                "b2b_5":               round(b2b_5, 2),
                "b2b_18":              round(b2b_18, 2),
                "taxable_5":           round(taxable_5, 2),
                "taxable_18":          round(taxable_18, 2),
            }

        raise ValueError(f"Month {fp} not found in sheet '{PLANNING_SHEET}'")

    # ─────────────────────────────────────────────
    # READ B2B PARTIES
    # ─────────────────────────────────────────────

    def read_b2b_parties(self, spreadsheet_id):
        """Reads B2B_PARTIES sheet: GSTIN | Party | Target"""
        rows = self._get(spreadsheet_id, f"{PARTIES_SHEET}!A2:C100")
        parties = []
        for row in rows:
            if len(row) < 3 or not row[0]:
                continue
            try:
                parties.append({
                    "gstin":  str(row[0]).strip(),
                    "party":  str(row[1]).strip(),
                    "target": float(row[2]),
                })
            except (ValueError, TypeError):
                continue
        return parties

    # ─────────────────────────────────────────────
    # READ LAST INVOICE NUMBER
    # ─────────────────────────────────────────────

    def read_last_invoice_number(self, spreadsheet_id, series="ME"):
        """Scans B2B-SALES-RECORDS for the highest invoice number in given series."""
        import re
        pattern = re.compile(rf"^({re.escape(series)})(\d+)$")
        rows = self._get(spreadsheet_id, f"{RECORDS_SHEET}!A1:J500")
        best = None
        for row in rows:
            for cell in row:
                if not isinstance(cell, str):
                    continue
                m = pattern.match(cell.strip())
                if m:
                    num = int(m.group(2))
                    if best is None or num > best[0]:
                        best = (num, m.group(1), len(m.group(2)))
        if best is None:
            return None
        num, prefix, width = best
        return f"{prefix}{str(num + 1).zfill(width)}"

    # ─────────────────────────────────────────────
    # WRITE B2B INVOICES → GSTR1-B2B SHEET
    # ─────────────────────────────────────────────

    def write_b2b_invoices(self, spreadsheet_id, rows):
        """
        Clears GSTR1-B2B data rows and writes fresh invoice data.
        rows: list of invoice dicts from invoice_engine.py
        """
        # Clear existing data (rows 5 onwards)
        self._clear(spreadsheet_id, f"{B2B_SHEET}!A{B2B_DATA_START}:M500")

        supplier_gstin = self.read_supplier_info(spreadsheet_id)[0] or ""
        supplier_state = supplier_gstin[:2] if supplier_gstin else "10"

        values = []
        for r in rows:
            pos_raw = r.get("pos", "10")
            pos_code = pos_raw.split("-")[0].strip() if "-" in str(pos_raw) else str(pos_raw)
            pos_name = _pos_name(pos_code)
            inv_date = r["date"].strftime("%d-%b-%Y") if hasattr(r["date"], "strftime") else str(r["date"])
            values.append([
                r.get("gstin", r.get("party_gstin", "")),
                r.get("receiver", r.get("party_name", "")),
                r["invoice_no"],
                inv_date,
                r["invoice_value"],
                pos_name,
                "N",            # Reverse Charge
                "",             # Applicable %
                "Regular B2B",  # Invoice Type
                "",             # E-Commerce GSTIN
                GST_RATE,
                r["taxable"],
                0,              # Cess
            ])

        if values:
            self._update(spreadsheet_id, f"{B2B_SHEET}!A{B2B_DATA_START}", values)
        return len(values)

    # ─────────────────────────────────────────────
    # WRITE HSN B2B → GSTR1-HSN-B2B SHEET
    # ─────────────────────────────────────────────

    def write_hsn_b2b(self, spreadsheet_id, rows):
        """Clears and writes HSN-B2B summary row."""
        self._clear(spreadsheet_id, f"{HSN_B2B_SHEET}!A{HSN_DATA_START}:K100")

        total_qty    = sum(r.get("qty_1l", 0) + r.get("qty_500ml", 0) for r in rows)
        taxable_sum  = sum(r["taxable"] for r in rows)
        tax_sum      = sum(r["tax_total"] for r in rows)
        total_val    = round(taxable_sum + tax_sum, 2)
        camt         = round(tax_sum / 2, 2)
        samt         = round(tax_sum - camt, 2)

        self._update(spreadsheet_id, f"{HSN_B2B_SHEET}!A{HSN_DATA_START}", [[
            "151499", "", "CTN", total_qty, total_val,
            GST_RATE, round(taxable_sum, 2), 0, camt, samt, 0
        ]])
        return 1

    # ─────────────────────────────────────────────
    # APPEND SALES RECORDS → B2B-SALES-RECORDS
    # ─────────────────────────────────────────────

    def append_sales_records(self, spreadsheet_id, rows, month_label):
        """
        Appends new invoice rows to B2B-SALES-RECORDS sheet.
        Finds the first empty row after existing data and appends there.
        Does NOT restructure the existing sheet — safe for month-by-month use.
        """
        existing = self._get(spreadsheet_id, f"{RECORDS_SHEET}!A1:J1000")
        # Find first completely empty row
        first_empty = len(existing) + 1

        # Add a month header row first
        header = [[month_label, "", "", "", "", "", "", "", "", ""]]
        self._update(spreadsheet_id, f"{RECORDS_SHEET}!A{first_empty}", header)

        # Column headers
        col_header = [["Sl", "Invoice No.", "Invoice Date", "GSTIN", "Receiver Name",
                        "1 Ltr CTN", "500ml CTN", "Taxable Value (₹)", "GST @5% (₹)", "Invoice Value (₹)"]]
        self._update(spreadsheet_id, f"{RECORDS_SHEET}!A{first_empty + 1}", col_header)

        # Data rows
        data = []
        for i, r in enumerate(rows, start=1):
            inv_date = r["date"].strftime("%Y-%m-%d") if hasattr(r["date"], "strftime") else str(r["date"])
            data.append([
                i,
                r["invoice_no"],
                inv_date,
                r.get("gstin", r.get("party_gstin", "")),
                r.get("receiver", r.get("party_name", "")),
                r.get("qty_1l", 0),
                r.get("qty_500ml", 0),
                round(r["taxable"], 2),
                round(r["tax_total"], 2),
                round(r["invoice_value"], 2),
            ])

        if data:
            self._update(spreadsheet_id, f"{RECORDS_SHEET}!A{first_empty + 2}", data)

        return len(data)


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

_POS_MAP = {
    "01": "01-Jammu & Kashmir", "02": "02-Himachal Pradesh", "03": "03-Punjab",
    "04": "04-Chandigarh", "05": "05-Uttarakhand", "06": "06-Haryana",
    "07": "07-Delhi", "08": "08-Rajasthan", "09": "09-Uttar Pradesh",
    "10": "10-Bihar", "11": "11-Sikkim", "12": "12-Arunachal Pradesh",
    "13": "13-Nagaland", "14": "14-Manipur", "15": "15-Mizoram",
    "16": "16-Tripura", "17": "17-Meghalaya", "18": "18-Assam",
    "19": "19-West Bengal", "20": "20-Jharkhand", "21": "21-Odisha",
    "22": "22-Chhattisgarh", "23": "23-Madhya Pradesh", "24": "24-Gujarat",
    "27": "27-Maharashtra", "29": "29-Karnataka", "30": "30-Goa",
    "32": "32-Kerala", "33": "33-Tamil Nadu", "36": "36-Telangana",
    "37": "37-Andhra Pradesh",
}

def _pos_name(code):
    return _POS_MAP.get(str(code).zfill(2), f"{code}-Unknown")


# ─────────────────────────────────────────────
# QUICK TEST
# ─────────────────────────────────────────────

if __name__ == "__main__":
    MUSKAN_ID = "1WqkmGy2SMphg_YnhK0uNr0_802SjCj51t_0BakLeTJY"

    print("Testing Sheets connection...")
    client = SheetsClient()

    gstin, name = client.read_supplier_info(MUSKAN_ID)
    print(f"  GSTIN: {gstin}")
    print(f"  Name : {name}")

    targets = client.read_month_targets(MUSKAN_ID, "042026")
    print(f"  Apr-2026 B2C@5%   : ₹{targets['b2c_5']:,.2f}")
    print(f"  Apr-2026 Exempt   : ₹{targets['exempt_registered'] + targets['exempt_unregistered']:,.2f}")

    parties = client.read_b2b_parties(MUSKAN_ID)
    print(f"  B2B Parties: {[p['party'] for p in parties]}")

    print("\n✓ All tests passed")

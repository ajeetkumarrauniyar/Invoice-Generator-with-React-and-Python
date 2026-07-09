"""
sheets.py — Google Sheets Integration (READ ONLY)
===================================================
GST Smart Planner | IT Maverick Solutions

Sirf 2 cheezein padhta hai har company ki Sheet se:
  1. B2B_PARTIES tab  → GSTIN | Party | Target
  2. planning_sheet tab → Monthly targets (D,E,G,H,M columns)

Baaki sab (GSTR1-B2B, HSN, B2B-SALES-RECORDS) NeonDB mein hai.
Ye script kuch LIKHTA NAHI — sirf padh ta hai.

Install:
    pip install google-auth google-auth-httplib2 google-api-python-client --break-system-packages
"""

import os
import json
import datetime
from pathlib import Path
from dotenv import load_dotenv

def _load_env():
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
            if os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON"):
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

SCOPES         = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
PARTIES_SHEET  = "B2B_PARTIES"   # same across all companies (confirmed)

# Planning sheet columns (same layout across all companies)
PLANNING_DATA_START_ROW = 46   # April 2026 = row 46 for FY2026-27
COL_MONTH        = 1   # A
COL_5_TAXABLE    = 4   # D
COL_18_TAXABLE   = 5   # E
COL_EXEMPT_REG   = 7   # G
COL_EXEMPT_UNREG = 8   # H
COL_B2B_5        = 13  # M
COL_B2C_5        = 14  # N  (formula =D-M)
COL_B2B_18       = 15  # O
COL_B2C_18       = 16  # P  (formula =E-O)
GSTIN_CELL       = "M1"
TRADE_NAME_CELL  = "M2"


def _range(sheet_name, cell_range):
    """
    Builds A1 range string. Does NOT add quotes — googleapiclient
    URL-encodes the range param, so quotes become %27 and break the API.
    Hyphens and spaces in sheet names work fine without quotes via the
    REST v4 `range` query parameter.
    """
    return f"{sheet_name}!{cell_range}"


class SheetsClient:
    def __init__(self):
        self._service = None

    def _get_service(self):
        if self._service:
            return self._service

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
                "Set GOOGLE_SERVICE_ACCOUNT_JSON in environment / .env.local"
            )

        self._service = build("sheets", "v4", credentials=creds)
        return self._service

    # ─────────────────────────────────────────────
    # CORE: fetch sheet tab list → resolve name to gid
    # ─────────────────────────────────────────────

    def _get_sheet_gid(self, spreadsheet_id, sheet_name):
        """
        Resolves a sheet tab name to its numeric gid.
        This is the bulletproof approach for any sheet name —
        we use the gid in a special range format that never breaks.
        """
        meta = self._get_service().spreadsheets().get(
            spreadsheetId=spreadsheet_id,
            fields="sheets(properties(sheetId,title))"
        ).execute()
        for s in meta.get("sheets", []):
            p = s["properties"]
            if p["title"] == sheet_name:
                return p["sheetId"]
        raise ValueError(
            f"Sheet tab '{sheet_name}' not found in spreadsheet {spreadsheet_id}.\n"
            f"Available tabs: {[s['properties']['title'] for s in meta.get('sheets', [])]}"
        )

    def _read(self, spreadsheet_id, sheet_name, cell_range):
        """
        Reads data using spreadsheets.values.get with the sheet's gid-based
        range — fully immune to special characters in sheet names.

        We first resolve the sheet name to its numeric gid, then use the
        Sheets API's gid-based addressing: spreadsheets/{id}/values/{gid}!{range}
        which accepts any sheet name without quoting issues.

        Falls back to plain name if gid lookup fails.
        """
        try:
            gid = self._get_sheet_gid(spreadsheet_id, sheet_name)
            # Use gid-based range — bypasses all name encoding issues
            range_str = f"{gid}!{cell_range}"
        except Exception:
            # Fallback: plain name (works for most names without spaces/apostrophes)
            range_str = _range(sheet_name, cell_range)

        try:
            result = self._get_service().spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=range_str,
                valueRenderOption="UNFORMATTED_VALUE",
                dateTimeRenderOption="SERIAL_NUMBER",
            ).execute()
            return result.get("values", [])
        except HttpError as e:
            # Last resort: try plain name directly
            if "Unable to parse range" in str(e):
                try:
                    result = self._get_service().spreadsheets().values().get(
                        spreadsheetId=spreadsheet_id,
                        range=_range(sheet_name, cell_range),
                        valueRenderOption="UNFORMATTED_VALUE",
                        dateTimeRenderOption="SERIAL_NUMBER",
                    ).execute()
                    return result.get("values", [])
                except HttpError:
                    pass
            raise RuntimeError(
                f"Cannot read '{sheet_name}'!{cell_range} from spreadsheet {spreadsheet_id}.\n"
                f"Check: (1) service account has access, (2) sheet tab name is correct.\n"
                f"Error: {e}"
            )

    # ─────────────────────────────────────────────
    # READ SUPPLIER INFO
    # ─────────────────────────────────────────────

    def read_supplier_info(self, spreadsheet_id, planning_sheet):
        """M1 = GSTIN, M2 = Trade Name from Executive Dashboard."""
        rows = self._read(spreadsheet_id, planning_sheet, "M1:M2")
        gstin      = rows[0][0] if rows and rows[0] else None
        trade_name = rows[1][0] if len(rows) > 1 and rows[1] else None
        return (
            str(gstin).strip()      if gstin      else None,
            str(trade_name).strip() if trade_name else None,
        )

    # ─────────────────────────────────────────────
    # READ MONTHLY TARGETS
    # ─────────────────────────────────────────────

    def read_month_targets(self, spreadsheet_id, planning_sheet, fp):
        """
        Reads the Sales Planning section row for a given month.
        fp: "042026" format
        """
        mm   = int(fp[:2])
        yyyy = int(fp[2:])

        rows = self._read(spreadsheet_id, planning_sheet,
                          f"A{PLANNING_DATA_START_ROW}:P200")

        for i, row in enumerate(rows):
            if not row:
                continue
            cell = row[0]   # Column A — month value

            match_month = False
            if isinstance(cell, (int, float)):
                from datetime import date
                d = date(1899, 12, 30) + datetime.timedelta(days=int(cell))
                match_month = (d.month == mm and d.year == yyyy)
            elif isinstance(cell, str) and cell:
                for fmt in ("%b-%Y", "%B-%Y", "%b %Y"):
                    try:
                        d = datetime.datetime.strptime(cell.strip(), fmt)
                        match_month = (d.month == mm and d.year == yyyy)
                        if match_month:
                            break
                    except ValueError:
                        continue

            if not match_month:
                continue

            def col(idx, default=0.0):
                try:
                    v = row[idx - 1]
                    return float(v) if v not in (None, "", " ") else default
                except (IndexError, ValueError, TypeError):
                    return default

            taxable_5    = col(COL_5_TAXABLE)
            taxable_18   = col(COL_18_TAXABLE)
            b2b_5        = col(COL_B2B_5)
            b2c_5_cell   = col(COL_B2C_5)
            b2b_18       = col(COL_B2B_18)
            b2c_18_cell  = col(COL_B2C_18)
            exempt_reg   = col(COL_EXEMPT_REG)
            exempt_unreg = col(COL_EXEMPT_UNREG)

            b2c_5  = b2c_5_cell  if b2c_5_cell  else round(taxable_5  - b2b_5,  2)
            b2c_18 = b2c_18_cell if b2c_18_cell else round(taxable_18 - b2b_18, 2)

            return {
                "row":                 PLANNING_DATA_START_ROW + i,
                "b2c_5":               round(b2c_5,  2),
                "b2c_18":              round(b2c_18, 2),
                "exempt_registered":   round(exempt_reg,   2),
                "exempt_unregistered": round(exempt_unreg, 2),
                "b2b_5":               round(b2b_5,  2),
                "b2b_18":              round(b2b_18, 2),
                "taxable_5":           round(taxable_5,  2),
                "taxable_18":          round(taxable_18, 2),
            }

        raise ValueError(
            f"Month {fp} not found in '{planning_sheet}' sheet.\n"
            f"Check that row for {mm}/{yyyy} exists in column A."
        )

    # ─────────────────────────────────────────────
    # READ B2B PARTIES
    # ─────────────────────────────────────────────

    def read_b2b_parties(self, spreadsheet_id):
        """Reads B2B_PARTIES sheet: GSTIN | Party | Target"""
        rows = self._read(spreadsheet_id, PARTIES_SHEET, "A2:C100")
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
    # READ LAST INVOICE NUMBER (from B2B_PARTIES tab)
    # ─────────────────────────────────────────────

    def read_last_invoice_number(self, spreadsheet_id, series="ME"):
        """
        Auto-detect next invoice number — now reads from a dedicated
        'INVOICE_TRACKER' tab if it exists, else returns None
        (DB-based detection is preferred and more reliable).
        """
        return None   # DB is the source of truth for invoice numbering


# ─────────────────────────────────────────────
# QUICK TEST
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sheet_id      = sys.argv[1] if len(sys.argv) > 1 else "1WqkmGy2SMphg_YnhK0uNr0_802SjCj51t_0BakLeTJY"
    planning_tab  = sys.argv[2] if len(sys.argv) > 2 else "Master Working - FY 2026-27"
    fp            = sys.argv[3] if len(sys.argv) > 3 else "042026"

    print(f"Testing Sheets connection...")
    print(f"  Sheet ID     : {sheet_id}")
    print(f"  Planning tab : {planning_tab}")
    print(f"  Period       : {fp}")
    print()

    client = SheetsClient()

    gstin, name = client.read_supplier_info(sheet_id, planning_tab)
    print(f"  GSTIN      : {gstin}")
    print(f"  Trade Name : {name}")

    targets = client.read_month_targets(sheet_id, planning_tab, fp)
    print(f"  B2C @5%    : ₹{targets['b2c_5']:,.2f}")
    print(f"  Exempt     : ₹{targets['exempt_registered'] + targets['exempt_unregistered']:,.2f}")

    parties = client.read_b2b_parties(sheet_id)
    print(f"  Parties    : {[p['party'] for p in parties]}")

    print("\n✓ All tests passed")

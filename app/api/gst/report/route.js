import { NextResponse } from "next/server";
import { neon } from "@neondatabase/serverless";

function getSql() {
  const url = process.env.DATABASE_URL;
  if (!url) throw new Error("DATABASE_URL not set");
  return neon(url);
}

// GET /api/gst/report?fp=042026&gstin=...&type=B2B
// Returns ERP-ready structured report (replaces B2B-SALES-RECORDS sheet)
export async function GET(request) {
  try {
    const sql = getSql();
    const { searchParams } = new URL(request.url);
    const fp     = searchParams.get("fp");
    const gstin  = searchParams.get("gstin");
    const type   = searchParams.get("type") || "B2B";  // B2B | B2C | ALL

    if (!fp)    return NextResponse.json({ message: "fp required" }, { status: 400 });
    if (!gstin) return NextResponse.json({ message: "gstin required" }, { status: 400 });

    // Type filter
    let typeClause = "";
    const params = [fp, gstin];
    if (type === "B2B") {
      typeClause = "AND invoice_type = 'B2B'";
    } else if (type === "B2C") {
      typeClause = "AND invoice_type IN ('B2C_5','B2C_18','EXEMPT')";
    }
    // ALL = no filter

    const rows = await sql.query(
      `SELECT
         ROW_NUMBER() OVER (ORDER BY invoice_date, invoice_no) AS sl,
         invoice_no,
         TO_CHAR(invoice_date, 'DD-Mon-YYYY') AS invoice_date,
         invoice_type,
         party_gstin,
         party_name,
         qty_1l,
         qty_500ml,
         taxable_value,
         gst_rate,
         (COALESCE(cgst_amount,0) + COALESCE(sgst_amount,0) + COALESCE(igst_amount,0)) AS gst_amount,
         invoice_value,
         hsn_code,
         erp_synced
       FROM invoices
       WHERE fp = $1 AND supplier_gstin = $2 AND is_cancelled = FALSE ${typeClause}
       ORDER BY invoice_date, invoice_no`,
      params
    );

    // Aggregate totals for report footer
    const totals = rows.reduce((acc, r) => {
      acc.qty_1l       += Number(r.qty_1l)        || 0;
      acc.qty_500ml    += Number(r.qty_500ml)     || 0;
      acc.taxable      += Number(r.taxable_value) || 0;
      acc.gst          += Number(r.gst_amount)    || 0;
      acc.invoice_value += Number(r.invoice_value) || 0;
      return acc;
    }, { qty_1l: 0, qty_500ml: 0, taxable: 0, gst: 0, invoice_value: 0, count: rows.length });

    // Party-wise breakdown
    const partyBreakdown = {};
    for (const r of rows) {
      const key = r.party_name || r.party_gstin || "—";
      if (!partyBreakdown[key]) {
        partyBreakdown[key] = { party: key, gstin: r.party_gstin, count: 0, taxable: 0, invoice_value: 0 };
      }
      partyBreakdown[key].count += 1;
      partyBreakdown[key].taxable += Number(r.taxable_value) || 0;
      partyBreakdown[key].invoice_value += Number(r.invoice_value) || 0;
    }

    return NextResponse.json({
      rows,
      totals,
      partyBreakdown: Object.values(partyBreakdown),
      period: fp,
      gstin,
      type,
    });
  } catch (error) {
    console.error("Report error:", error);
    return NextResponse.json({ message: error.message }, { status: 500 });
  }
}

// PATCH — mark invoices as ERP-synced (after you've entered them in ERP)
export async function PATCH(request) {
  try {
    const sql = getSql();
    const { invoiceNos } = await request.json();
    if (!Array.isArray(invoiceNos) || !invoiceNos.length) {
      return NextResponse.json({ message: "invoiceNos array required" }, { status: 400 });
    }
    await sql.query(
      `UPDATE invoices SET erp_synced = TRUE WHERE invoice_no = ANY($1)`,
      [invoiceNos]
    );
    return NextResponse.json({ success: true, updated: invoiceNos.length });
  } catch (error) {
    return NextResponse.json({ message: error.message }, { status: 500 });
  }
}

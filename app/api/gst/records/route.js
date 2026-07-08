import { NextResponse } from "next/server";
import { neon } from "@neondatabase/serverless";

function getSql() {
  const url = process.env.DATABASE_URL;
  if (!url) throw new Error("DATABASE_URL is not set in environment");
  return neon(url);
}

export async function GET(request) {
  try {
    const sql = getSql();
    const { searchParams } = new URL(request.url);
    const fp     = searchParams.get("fp");
    const type   = searchParams.get("type")   || null;
    const series = searchParams.get("series") || null;

    if (!fp) return NextResponse.json({ message: "fp required (e.g. 042026)" }, { status: 400 });

    // Build results using sql.query() — supports $1 placeholders + params array
    let query = `
      SELECT invoice_no, invoice_date, invoice_type, series,
             party_gstin, party_name,
             taxable_value, gst_rate, cgst_amount, sgst_amount, igst_amount,
             invoice_value, qty_1l, qty_500ml, hsn_code,
             json_exported, erp_synced
      FROM invoices
      WHERE fp = $1 AND is_cancelled = FALSE
    `;
    const params = [fp];

    if (type)   { params.push(type);   query += ` AND invoice_type = $${params.length}`; }
    if (series) { params.push(series); query += ` AND series = $${params.length}`; }
    query += ` ORDER BY series, invoice_date, invoice_no`;

    const [invoices, summaryRows] = await Promise.all([
      sql.query(query, params),
      sql.query(`SELECT * FROM monthly_summary WHERE fp = $1`, [fp]),
    ]);

    return NextResponse.json({
      invoices,
      summary: summaryRows[0] ?? null,
      count: invoices.length,
    });
  } catch (error) {
    console.error("Records GET error:", error);
    return NextResponse.json({ message: error.message }, { status: 500 });
  }
}

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

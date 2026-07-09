import { NextResponse } from "next/server";
import { neon } from "@neondatabase/serverless";

function getSql() {
  const url = process.env.DATABASE_URL;
  if (!url) throw new Error("DATABASE_URL not set");
  return neon(url);
}

export async function GET() {
  try {
    const sql = getSql();
    const companies = await sql.query(
      `SELECT gstin, trade_name, short_name, state_code,
              spreadsheet_id, planning_sheet
       FROM companies
       WHERE is_active = TRUE
       ORDER BY short_name`,
      []
    );
    return NextResponse.json({ companies });
  } catch (error) {
    return NextResponse.json({ message: error.message }, { status: 500 });
  }
}

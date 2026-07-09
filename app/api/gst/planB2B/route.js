import { NextResponse } from "next/server";
import { spawn } from "child_process";
import path from "path";
import fs from "fs/promises";

function spawnPython(scriptPath, args) {
  const pythonPath = process.env.PYTHON_PATH || "python3";
  const cwd = process.cwd();
  return spawn(pythonPath, [scriptPath, ...args], {
    cwd,
    env: {
      ...process.env,
      PYTHONPATH: [path.join(cwd, "db"), path.join(cwd, "scripts")].join(":"),
    },
  });
}

export async function POST(request) {
  let proc = null;
  try {
    const { month, gstin, spreadsheetId } = await request.json();

    if (!month)
      return NextResponse.json({ message: "month required (e.g. 052026)" }, { status: 400 });
    if (!spreadsheetId)
      return NextResponse.json({ message: "spreadsheetId required — company select karo" }, { status: 400 });

    const cwd = process.cwd();
    const scriptPath = path.join(cwd, "scripts", "invoice_engine.py");

    // Sheets mode — NO local xlsx path, script reads directly from Google Sheets
    const args = [
      "--month",    month,
      "--sheet-id", spreadsheetId,
      ...(gstin ? ["--gstin", gstin] : []),
    ];

    proc = spawnPython(scriptPath, args);

    return new Promise((resolve) => {
      let stdout = [], stderr = [];
      proc.stdout.on("data", (d) => stdout.push(d));
      proc.stderr.on("data", (d) => stderr.push(d));
      proc.on("error", (e) =>
        resolve(NextResponse.json({ message: `Process error: ${e.message}` }, { status: 500 }))
      );
      proc.on("close", async (code) => {
        const output    = Buffer.concat(stdout).toString();
        const errOutput = Buffer.concat(stderr).toString();
        if (code !== 0) {
          return resolve(NextResponse.json({
            message: `Script error: ${errOutput || "Unknown"}`, output,
          }, { status: 500 }));
        }
        const invoiceMatch = output.match(/Total invoices generated:\s*(\d+)/);
        const warnings = output.split("\n")
          .filter(l => l.trim().startsWith("- "))
          .map(l => l.replace(/^[\s-]+/, ""));
        resolve(NextResponse.json({
          success: true,
          totalInvoices: invoiceMatch ? parseInt(invoiceMatch[1]) : null,
          warnings,
          output,
        }));
      });
    });
  } catch (e) {
    if (proc) proc.kill();
    return NextResponse.json({ message: `Server error: ${e.message}` }, { status: 500 });
  }
}

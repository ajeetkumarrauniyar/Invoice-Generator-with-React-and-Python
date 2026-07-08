import { NextResponse } from "next/server";
import { spawn } from "child_process";
import path from "path";
import fs from "fs/promises";

// shared spawn helper — same pattern for all 3 GST routes
function spawnPython(scriptPath, args) {
  const pythonPath = process.env.PYTHON_PATH || "python3";
  const cwd = process.cwd();
  return spawn(pythonPath, [scriptPath, ...args], {
    cwd,
    env: {
      ...process.env,
      // Let db/ folder be importable from scripts/
      PYTHONPATH: path.join(cwd, "db"),
    },
  });
}

export async function POST(request) {
  let proc = null;
  try {
    const { month, workbookPath } = await request.json();
    if (!month) return NextResponse.json({ message: "month required (e.g. 052026)" }, { status: 400 });

    const cwd = process.cwd();
    const scriptPath = path.join(cwd, "scripts", "invoice_engine.py");
    const resolvedWorkbook = workbookPath
      ? path.resolve(workbookPath)
      : path.join(cwd, "GST_Monthwise_Ratewise_Bifurcation.xlsx");

    proc = spawnPython(scriptPath, [resolvedWorkbook, month]);

    return new Promise((resolve) => {
      let stdout = [], stderr = [];
      proc.stdout.on("data", (d) => stdout.push(d));
      proc.stderr.on("data", (d) => stderr.push(d));
      proc.on("error", (e) =>
        resolve(NextResponse.json({ message: `Process error: ${e.message}` }, { status: 500 }))
      );
      proc.on("close", async (code) => {
        const output = Buffer.concat(stdout).toString();
        const errOutput = Buffer.concat(stderr).toString();
        if (code !== 0) {
          return resolve(NextResponse.json({ message: `Script error: ${errOutput || "Unknown"}`, output }, { status: 500 }));
        }
        const invoiceMatch = output.match(/Total invoices generated:\s*(\d+)/);
        const warnings = output.split("\n")
          .filter(l => l.trim().startsWith("- "))
          .map(l => l.replace(/^[\s-]+/, ""));
        let salesRecordsCsv = null;
        try { salesRecordsCsv = await fs.readFile(path.join(cwd, "sales_records_addition.csv"), "utf-8"); } catch (_) {}
        resolve(NextResponse.json({
          success: true,
          totalInvoices: invoiceMatch ? parseInt(invoiceMatch[1]) : null,
          warnings,
          output,
          salesRecordsCsv,
        }));
      });
    });
  } catch (e) {
    if (proc) proc.kill();
    return NextResponse.json({ message: `Server error: ${e.message}` }, { status: 500 });
  }
}

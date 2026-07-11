import { NextResponse } from "next/server";
import { spawn } from "child_process";
import path from "path";

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
    const { month, gstin, spreadsheetId, planningSheet, force } = await request.json();

    if (!month)         return NextResponse.json({ message: "month required" }, { status: 400 });
    if (!spreadsheetId) return NextResponse.json({ message: "company select karo" }, { status: 400 });
    if (!gstin)         return NextResponse.json({ message: "gstin required" }, { status: 400 });

    const cwd        = process.cwd();
    const scriptPath = path.join(cwd, "scripts", "invoice_engine.py");

    const args = [
      "--month",    month,
      "--sheet-id", spreadsheetId,
      "--gstin",    gstin,
      ...(planningSheet ? ["--planning-sheet", planningSheet] : []),
      ...(force ? ["--force-regenerate"] : []),
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
          return resolve(NextResponse.json({ message: errOutput || "Script error", output }, { status: 500 }));
        }

        // Check if script returned existing data (Lock & Fetch mode)
        const existingMatch = output.match(/EXISTING_DATA: count=(\d+) from=(\S+) to=(\S+)/);
        if (existingMatch) {
          return resolve(NextResponse.json({
            success: true,
            alreadyExists: true,
            totalInvoices: parseInt(existingMatch[1]),
            invoiceFrom:   existingMatch[2],
            invoiceTo:     existingMatch[3],
            output,
            message: `${month.slice(0,2)}/${month.slice(2)} ka data pehle se hai — existing ${existingMatch[1]} invoices return ho rahe hain.`,
          }));
        }

        const invoiceMatch = output.match(/Total invoices generated:\s*(\d+)/);
        const warnings = output.split("\n")
          .filter(l => l.trim().startsWith("- "))
          .map(l => l.replace(/^[\s-]+/, ""));

        resolve(NextResponse.json({
          success: true,
          alreadyExists: false,
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

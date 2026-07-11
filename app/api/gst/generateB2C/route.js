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
    const {
      month,
      gstin,
      spreadsheetId,
      planningSheet,
      hsn5,
      hsn18,
      hsnExempt,
      force,
    } = await request.json();

    if (!month)
      return NextResponse.json({ message: "month required" }, { status: 400 });
    if (!spreadsheetId)
      return NextResponse.json(
        { message: "company select karo" },
        { status: 400 },
      );
    if (!gstin)
      return NextResponse.json({ message: "gstin required" }, { status: 400 });

    const cwd = process.cwd();
    const scriptPath = path.join(cwd, "scripts", "b2c_generator.py");
    const b2cOutdir = path.join(cwd, "b2c_output");

    const args = [
      "--month",
      month,
      "--sheet-id",
      spreadsheetId,
      "--gstin",
      gstin,
      "--outdir",
      b2cOutdir,
      ...(planningSheet ? ["--planning-sheet", planningSheet] : []),
      ...(hsn5 ? ["--hsn5", hsn5] : []),
      ...(hsn18 ? ["--hsn18", hsn18] : []),
      ...(hsnExempt ? ["--hsn-exempt", hsnExempt] : []),
      ...(force ? ["--force-regenerate"] : []),
    ];

    proc = spawnPython(scriptPath, args);

    return new Promise((resolve) => {
      let stdout = [],
        stderr = [];
      proc.stdout.on("data", (d) => stdout.push(d));
      proc.stderr.on("data", (d) => stderr.push(d));
      proc.on("error", (e) =>
        resolve(
          NextResponse.json(
            { message: `Process error: ${e.message}` },
            { status: 500 },
          ),
        ),
      );
      proc.on("close", async (code) => {
        const output = Buffer.concat(stdout).toString();
        const errOutput = Buffer.concat(stderr).toString();

        if (code !== 0) {
          return resolve(
            NextResponse.json(
              { message: errOutput || "Script error", output },
              { status: 500 },
            ),
          );
        }
        if (code !== 0) {
          console.error("========== PYTHON STDERR ==========");
          console.error(errOutput);

          console.error("========== PYTHON STDOUT ==========");
          console.error(output);

          console.error("========== PYTHON EXIT CODE ==========");
          console.error(code);

          return NextResponse.json(
            {
              message: errOutput || "Script error",
              output,
              stderr: errOutput,
              stdout: output,
              exitCode: code,
            },
            { status: 500 },
          );
        }

        // Lock & Fetch mode — existing data returned
        const existingMatch = output.match(
          /EXISTING_DATA: count=(\d+) from=(\S+) to=(\S+)/,
        );
        if (existingMatch) {
          return resolve(
            NextResponse.json({
              success: true,
              alreadyExists: true,
              totalInvoices: parseInt(existingMatch[1]),
              invoiceFrom: existingMatch[2],
              invoiceTo: existingMatch[3],
              output,
              message: `${month.slice(0, 2)}/${month.slice(2)} ka B2C data pehle se hai.`,
            }),
          );
        }

        const rangeMatch = output.match(
          /Invoice range\s*:\s*(\S+)\s*→\s*(\S+)/,
        );
        const countMatch = output.match(/Total invoices:\s*(\d+)/);
        const warnings = output
          .split("\n")
          .filter((l) => l.trim().startsWith("- "))
          .map((l) => l.replace(/^[\s-]+/, ""));

        const readCsv = async (name) => {
          try {
            return await fs.readFile(path.join(b2cOutdir, name), "utf-8");
          } catch {
            return null;
          }
        };
        const [b2csCsv, exempCsv, hsnB2cCsv, recordsCsv] = await Promise.all([
          readCsv("b2cs_rows.csv"),
          readCsv("exemp_row.csv"),
          readCsv("hsn_b2c_rows.csv"),
          readCsv("cash_sales_records.csv"),
        ]);

        resolve(
          NextResponse.json({
            success: true,
            alreadyExists: false,
            totalInvoices: countMatch ? parseInt(countMatch[1]) : null,
            invoiceFrom: rangeMatch?.[1] ?? null,
            invoiceTo: rangeMatch?.[2] ?? null,
            warnings,
            output,
            files: { b2csCsv, exempCsv, hsnB2cCsv, cashRecordsCsv: recordsCsv },
          }),
        );
      });
    });
  } catch (e) {
    if (proc) proc.kill();
    return NextResponse.json(
      { message: `Server error: ${e.message}` },
      { status: 500 },
    );
  }
}

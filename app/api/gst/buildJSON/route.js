import { NextResponse } from "next/server";
import { spawn } from "child_process";
import path from "path";
import fs from "fs/promises";

function spawnPython(scriptPath, args, extraEnv = {}) {
  const pythonPath = process.env.PYTHON_PATH || "python3";
  const cwd = process.cwd();
  return spawn(pythonPath, [scriptPath, ...args], {
    cwd,
    env: {
      ...process.env,
      PYTHONPATH: [path.join(cwd, "db"), path.join(cwd, "scripts")].join(":"),
      ...extraEnv,
    },
  });
}

export async function POST(request) {
  let proc = null;
  try {
    const { month, gstin, spreadsheetId } = await request.json();
    if (!month) return NextResponse.json({ message: "month required" }, { status: 400 });

    const cwd        = process.cwd();
    const scriptPath = path.join(cwd, "scripts", "gstr1_generator.py");
    const outJsonPath = path.join(cwd, `gstr1_${month}.json`);

    // DB-first mode — no Excel or CSV paths needed
    // Script reads B2B/B2C/HSN all from NeonDB
    const args = [
      "--month", month,
      "--out",   outJsonPath,
      ...(gstin        ? ["--gstin", gstin]          : []),
      ...(spreadsheetId ? ["--sheet-id", spreadsheetId] : []),
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
            message: errOutput || "Script error", output
          }, { status: 500 }));
        }
        try {
          const jsonContent = await fs.readFile(outJsonPath, "utf-8");
          resolve(new NextResponse(jsonContent, {
            status: 200,
            headers: {
              "Content-Type": "application/json",
              "Content-Disposition": `attachment; filename="gstr1_${month}.json"`,
              "X-Script-Output": encodeURIComponent(output.slice(0, 1000)),
            },
          }));
        } catch {
          resolve(NextResponse.json({ message: "JSON file not created", output }, { status: 500 }));
        }
      });
    });
  } catch (e) {
    if (proc) proc.kill();
    return NextResponse.json({ message: `Server error: ${e.message}` }, { status: 500 });
  }
}

import { NextResponse } from "next/server";
import { spawn } from "child_process";
import { writeFile, unlink } from "fs/promises";
import path from "path";
import fs from "fs/promises";
import os from "os";

export async function POST(request) {
  let partyDataPath = null;
  let pythonProcess = null;

  try {
    const data = await request.json();

    // Validate required fields
    if (
      !data.startDate ||
      !data.endDate ||
      !data.startInvoiceNumber ||
      !data.productName
    ) {
      return NextResponse.json(
        { message: "Missing required fields" },
        { status: 400 }
      );
    }

    // Validate numeric fields
    if (
      isNaN(data.startInvoiceNumber) ||
      isNaN(data.minPurchaseRate) ||
      isNaN(data.maxPurchaseRate) ||
      isNaN(data.minMarginPercentage) ||
      isNaN(data.maxMarginPercentage)
    ) {
      return NextResponse.json(
        { message: "Invalid numeric fields" },
        { status: 400 }
      );
    }

    // Only validate totalAmount and partyLimit if generating parties automatically
    if (data.generateParties) {
      if (isNaN(data.totalAmount) || isNaN(data.partyLimit)) {
        return NextResponse.json(
          { message: "Invalid numeric fields" },
          { status: 400 }
        );
      }
    }

    // Validate date range
    const startDate = new Date(data.startDate);
    const endDate = new Date(data.endDate);
    if (startDate > endDate) {
      return NextResponse.json(
        { message: "Start date must be before end date" },
        { status: 400 }
      );
    }

    // Validate totalAmount and partyLimit
    if (data.totalAmount <= 0 || data.partyLimit <= 0) {
      console.error("Invalid totalAmount or partyLimit:", data);
      return NextResponse.json(
        { message: "Total amount and party limit must be positive" },
        { status: 400 }
      );
    }

    // Validate partyLimit <= totalAmount
    if (data.partyLimit > data.totalAmount) {
      return NextResponse.json(
        { message: "Party limit cannot be greater than total amount" },
        { status: 400 }
      );
    }

    // Get the Python executable path and script path
    const pythonPath = process.env.PYTHON_PATH || "python3";
    const scriptPath = path.join(
      process.cwd(),
      "scripts",
      "generate_invoices.py"
    );

    let scriptArgs;

    if (data.generateParties) {
      // Validate generate parties data
      if (!data.totalAmount || !data.partyLimit) {
        return NextResponse.json(
          {
            message: "Missing total amount or party limit for party generation",
          },
          { status: 400 }
        );
      }

      // Use the new party generation functionality
      scriptArgs = [
        scriptPath,
        data.startDate,
        data.endDate,
        data.startInvoiceNumber.toString(),
        "--generate",
        data.totalAmount.toString(),
        data.partyLimit.toString(),
        data.productName,
        (data.minPurchaseRate || 22).toString(),
        (data.maxPurchaseRate || 23).toString(),
        (data.minMarginPercentage || 2.25).toString(),
        (data.maxMarginPercentage || 2.65).toString(),
      ];
    } else {
      // Original functionality with party data file
      if (!data.generateParties && !data.partyData) {
        return NextResponse.json(
          { message: "Missing party data" },
          { status: 400 }
        );
      }

      // Create a temporary file for the party data
      const tempDir = path.join(os.tmpdir(), "invoice-generator");
      try {
        await fs.mkdir(tempDir, { recursive: true });
      } catch (err) {
        console.error("Failed to create temp directory:", err);
      }

      partyDataPath = path.join(tempDir, `party_data_${Date.now()}.csv`);
      await writeFile(partyDataPath, data.partyData);

      scriptArgs = [
        scriptPath,
        data.startDate,
        data.endDate,
        data.startInvoiceNumber.toString(),
        partyDataPath,
        data.productName,
        (data.minPurchaseRate || 22).toString(),
        (data.maxPurchaseRate || 23).toString(),
        (data.minMarginPercentage || 2.25).toString(),
        (data.maxMarginPercentage || 2.65).toString(),
      ];
    }
    // Execute the Python script
    pythonProcess = spawn(pythonPath, scriptArgs);

    return new Promise((resolve, reject) => {
      let outputData = [];
      let errorData = [];

      pythonProcess.stdout.on("data", (data) => {
        console.log("Python stdout:", data.toString());
        outputData.push(data);
      });

      pythonProcess.stderr.on("data", (data) => {
        console.error("Python stderr:", data.toString());
        errorData.push(data);
      });

      pythonProcess.on("error", (error) => {
        console.error("Failed to start Python process:", error);
        resolve(
          NextResponse.json(
            { message: `Failed to start Python process: ${error.message}` },
            { status: 500 }
          )
        );
      });

      pythonProcess.on("close", async (code) => {
        // Clean up the temporary file
        try {
          if (partyDataPath) {
            await unlink(partyDataPath);
          }
        } catch (err) {
          console.error("Error cleaning up temp file:", err);
        }

        if (code !== 0) {
          const errorMessage = Buffer.concat(errorData).toString();
          console.error(
            "Python script exited with code:",
            code,
            "Error:",
            errorMessage
          );
          resolve(
            NextResponse.json(
              {
                message: `Python script error: ${
                  errorMessage || "Unknown error occurred"
                }`,
              },
              { status: 500 }
            )
          );
        } else {
          const csvData = Buffer.concat(outputData);
          if (!csvData.length) {
            resolve(
              NextResponse.json(
                { message: "No data generated from Python script" },
                { status: 500 }
              )
            );
            return;
          }
          resolve(
            new NextResponse(csvData, {
              status: 200,
              headers: {
                "Content-Type": "text/csv",
                "Content-Disposition": "attachment; filename=invoices.csv",
              },
            })
          );
        }
      });
    });
  } catch (error) {
    console.error("API route error:", error);
    // Clean up resources
    try {
      if (pythonProcess) {
        pythonProcess.kill();
      }
      if (partyDataPath) {
        await unlink(partyDataPath);
      }
    } catch (err) {
      console.error("Error cleaning up resources:", err);
    }
    return NextResponse.json(
      { message: `Internal server error: ${error.message}` },
      { status: 500 }
    );
  }
}

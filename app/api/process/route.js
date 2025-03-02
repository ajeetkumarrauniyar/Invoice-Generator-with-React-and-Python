import { NextResponse } from "next/server";
import { spawn } from "child_process";
import path from "path";

export async function POST(request) {
  try {
    // Get the input data from the request body
    const data = await request.text();
    
    if (!data) {
      return NextResponse.json(
        { message: "No input data provided" },
        { status: 400 }
      );
    }

    // Get the Python executable path and script path
    const pythonPath = process.env.PYTHON_PATH || "python3";
    const scriptPath = path.join(
      process.cwd(),
      "scripts",
      "process_payments.py"
    );

    // Execute the Python script
    const pythonProcess = spawn(pythonPath, [scriptPath]);

    return new Promise((resolve, reject) => {
      let outputData = [];
      let errorData = [];

      // Handle stdout (output from the Python script)
      pythonProcess.stdout.on("data", (data) => {
        // console.log(`Python stdout: ${data.toString().substring(0, 200)}...`); // Log only part to avoid flooding
        outputData.push(data);
      });

      // Handle stderr (errors from the Python script)
      pythonProcess.stderr.on("data", (data) => {
        console.error("Python stderr:", data.toString());
        errorData.push(data);
      });

      // Handle process errors
      pythonProcess.on("error", (error) => {
        console.error("Failed to start Python process:", error);
        resolve(
          NextResponse.json(
            { message: `Failed to start Python process: ${error.message}` },
            { status: 500 }
          )
        );
      });

      // Handle process completion
      pythonProcess.on("close", (code) => {
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
          const csvData = Buffer.concat(outputData).toString().trim();
          if (!csvData.length) {
            resolve(
              NextResponse.json(
                { message: "No data generated from Python script" },
                { status: 500 }
              )
            );
            return;
          }

          // Create formatted filename
          const currentDate = new Date().toISOString().split("T")[0];
          const filename = `payments_${currentDate}.csv`;

          // Return the CSV data as a response
          resolve(
            new NextResponse(csvData, {
              status: 200,
              headers: {
                "Content-Type": "text/csv",
                "Content-Disposition": `attachment; filename="${filename}"`,
              },
            })
          );
        }
      });

      // Send the input data to the Python script
      pythonProcess.stdin.write(data);
      pythonProcess.stdin.end();
    });
  } catch (error) {
    console.error("API route error:", error);
    return NextResponse.json(
      { message: `Internal server error: ${error.message}` },
      { status: 500 }
    );
  }
}

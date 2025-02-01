import { NextResponse } from 'next/server'
import { spawn } from 'child_process'
import { writeFile, unlink } from 'fs/promises'
import path from 'path'
import fs from 'fs/promises'
import os from 'os'

export async function POST(request) {
  let partyDataPath = null;
  let pythonProcess = null;
  
  try {
    const data = await request.json()
    
    // Validate the input data
    if (!data.startDate || !data.endDate || !data.partyData || !data.startInvoiceNumber || !data.productName) {
      return NextResponse.json(
        { message: 'Missing required fields' },
        { status: 400 }
      )
    }

    // Create a temporary file for the party data
    const tempDir = path.join(os.tmpdir(), 'invoice-generator')
    try {
      await fs.mkdir(tempDir, { recursive: true })
    } catch (err) {
      console.error('Failed to create temp directory:', err)
    }
    
    partyDataPath = path.join(tempDir, `party_data_${Date.now()}.csv`)
    await writeFile(partyDataPath, data.partyData)

    // Get the Python executable path and script path
    const pythonPath = process.env.PYTHON_PATH || 'python3'
    const scriptPath = path.join(process.cwd(), 'scripts', 'generate_invoices.py')
    
    // Prepare the Python script arguments
    const scriptArgs = [
      scriptPath,
      data.startDate,
      data.endDate,
      data.startInvoiceNumber,
      partyDataPath,
      data.productName,
      data.minPurchaseRate || "22.00",
      data.maxPurchaseRate || "23.00",
      data.minMarginPercentage || "2.25",
      data.maxMarginPercentage || "2.65"
    ]

    console.log('Environment:', process.env.NODE_ENV)
    console.log('Python executable path:', pythonPath)
    console.log('Script path:', scriptPath)
    console.log('Temp directory:', tempDir)
    console.log('Party data path:', partyDataPath)
    console.log('Executing Python script with args:', scriptArgs)

    // Execute the Python script
    pythonProcess = spawn(pythonPath, scriptArgs)

    return new Promise((resolve, reject) => {
      let outputData = []
      let errorData = []

      pythonProcess.stdout.on('data', (data) => {
        console.log('Python stdout:', data.toString())
        outputData.push(data)
      })

      pythonProcess.stderr.on('data', (data) => {
        console.error('Python stderr:', data.toString())
        errorData.push(data)
      })

      pythonProcess.on('error', (error) => {
        console.error('Failed to start Python process:', error)
        resolve(NextResponse.json(
          { message: `Failed to start Python process: ${error.message}` },
          { status: 500 }
        ))
      })

      pythonProcess.on('close', async (code) => {
        // Clean up the temporary file
        try {
          if (partyDataPath) {
            await unlink(partyDataPath)
          }
        } catch (err) {
          console.error('Error cleaning up temp file:', err)
        }

        if (code !== 0) {
          const errorMessage = Buffer.concat(errorData).toString()
          console.error('Python script exited with code:', code, 'Error:', errorMessage)
          resolve(NextResponse.json(
            { message: `Python script error: ${errorMessage || 'Unknown error occurred'}` },
            { status: 500 }
          ))
        } else {
          const csvData = Buffer.concat(outputData)
          if (!csvData.length) {
            resolve(NextResponse.json(
              { message: 'No data generated from Python script' },
              { status: 500 }
            ))
            return
          }
          resolve(new NextResponse(csvData, {
            status: 200,
            headers: {
              'Content-Type': 'text/csv',
              'Content-Disposition': 'attachment; filename=invoices.csv'
            }
          }))
        }
      })
    })
  } catch (error) {
    console.error('API route error:', error)
    // Clean up resources
    try {
      if (pythonProcess) {
        pythonProcess.kill()
      }
      if (partyDataPath) {
        await unlink(partyDataPath)
      }
    } catch (err) {
      console.error('Error cleaning up resources:', err)
    }
    return NextResponse.json(
      { message: `Internal server error: ${error.message}` },
      { status: 500 }
    )
  }
} 
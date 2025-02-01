import { NextResponse } from 'next/server'
import { spawn } from 'child_process'
import { writeFile, unlink } from 'fs/promises'
import path from 'path'

export async function POST(request) {
  let partyDataPath = null;
  
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
    partyDataPath = path.join(process.cwd(), 'temp_party_data.csv')
    await writeFile(partyDataPath, data.partyData)

    // Get the virtual environment Python path
    const pythonPath = path.join(process.cwd(), 'venv', 'bin', 'python3')
    
    // Prepare the Python script arguments
    const scriptPath = path.join(process.cwd(), 'scripts', 'generate_invoices.py')
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

    console.log('Executing Python script with args:', scriptArgs)

    // Execute the Python script
    const pythonProcess = spawn(pythonPath, scriptArgs)

    return new Promise((resolve, reject) => {
      let outputData = []
      let errorData = []

      pythonProcess.stdout.on('data', (data) => {
        outputData.push(data)
      })

      pythonProcess.stderr.on('data', (data) => {
        console.error('Python script error:', data.toString())
        errorData.push(data)
      })

      pythonProcess.on('error', (error) => {
        console.error('Failed to start Python process:', error)
        resolve(NextResponse.json(
          { message: 'Failed to start Python process: ' + error.message },
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
            { message: 'Python script error: ' + errorMessage },
            { status: 500 }
          ))
        } else {
          const csvData = Buffer.concat(outputData)
          if (!csvData.length) {
            resolve(NextResponse.json(
              { message: 'No data generated' },
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
    // Clean up the temporary file if it exists
    try {
      if (partyDataPath) {
        await unlink(partyDataPath)
      }
    } catch (err) {
      console.error('Error cleaning up temp file:', err)
    }
    return NextResponse.json(
      { message: 'Internal server error: ' + error.message },
      { status: 500 }
    )
  }
} 
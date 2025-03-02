"use client";

import { useState } from "react";

export default function Home() {
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  const handleFileChange = (e) => {
    setFile(e.target.files[0]);
    setErrorMessage("");
  };

  const handleSubmit = async () => {
    if (!file) {
      setErrorMessage("Please upload a file");
      return;
    }

    setLoading(true);
    setErrorMessage("");

    try {
      // Read the file content
      const fileContent = await file.text();

      // Send the file content to the API
      const response = await fetch("/api/process", {
        method: "POST",
        body: fileContent,
        headers: {
          "Content-Type": "text/csv",
        },
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.message || "Failed to process the file");
      }

      // Download the processed CSV file
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "payments.csv";
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error("Error:", error);
      setErrorMessage(
        error.message || "An error occurred while processing the file"
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="container mx-auto p-8">
      <h1 className="text-3xl font-bold mb-6">Payment Processor</h1>
      <p className="mb-4">
        Upload a CSV file with your invoice data. The system will process
        payments and split them if they exceed the daily limit of ₹20,000.
      </p>

      <div className="mb-6 p-4 border rounded-md">
        <h2 className="text-xl font-semibold mb-2">Instructions:</h2>
        <ol className="list-decimal ml-5 space-y-1">
          <li>
            Upload your CSV file with columns: Date, Bill, Party Name, and
            Amount
          </li>
          <li>Click the "Process and Download" button</li>
          <li>
            The system will create a payment schedule that respects the ₹20,000
            daily limit
          </li>
          <li>Download the resulting payments.csv file</li>
        </ol>
      </div>

      <div className="flex flex-col space-y-4">
        <input
          type="file"
          accept=".csv"
          onChange={handleFileChange}
          className="border p-2 rounded w-full max-w-md"
        />

        <button
          onClick={handleSubmit}
          disabled={loading}
          className={`bg-blue-500 text-white py-2 px-4 rounded max-w-md ${
            loading ? "opacity-50 cursor-not-allowed" : "hover:bg-blue-600"
          }`}
        >
          {loading ? "Processing..." : "Process and Download"}
        </button>

        {errorMessage && (
          <div className="text-red-500 mt-2">{errorMessage}</div>
        )}
      </div>
    </div>
  );
}

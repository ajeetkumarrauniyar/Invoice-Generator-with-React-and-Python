'use client'

import InvoiceForm from '@/components/InvoiceForm'

export default function Home() {
  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-7xl mx-auto">
        <div className="text-center mb-12">
          <h1 className="text-4xl font-bold tracking-tight text-gray-900 sm:text-5xl font-sans">
            Invoice Generator
          </h1>
          <p className="mt-4 text-lg leading-relaxed text-gray-600 max-w-2xl mx-auto font-medium">
            Generate invoices with customizable parameters and export as CSV. Simple, fast, and efficient.
          </p>
        </div>
        <InvoiceForm />
      </div>
    </div>
  )
} 
'use client'

import InvoiceForm from '@/components/InvoiceForm'
import { Button } from "@/components/ui/button";
import Link from "next/link";

export default function Home() {
  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-7xl mx-auto">
        <div className="text-center mb-12">
          <div className="flex justify-center items-center">
            <h1 className="text-4xl font-bold tracking-tight text-gray-900 sm:text-5xl font-sans">
              Invoice Generator
            </h1>
            <Button asChild className="flex justify-center items-center ml-4">
              <Link href="/vouchers">Vouchers</Link>
            </Button>
          </div>
          <p className="mt-4 text-lg leading-relaxed text-gray-600 max-w-2xl mx-auto font-medium">
            Generate invoices with customizable parameters and export as CSV. Simple, fast, and efficient.
          </p>
        </div>
        <InvoiceForm />
      </div>
    </div>
  )
}
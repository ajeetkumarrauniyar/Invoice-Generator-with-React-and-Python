'use client'

import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import * as z from 'zod'
import axios from 'axios'

import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { useToast } from "@/hooks/use-toast"

const formSchema = z.object({
  startDate: z.string().min(1, 'Start date is required'),
  endDate: z.string().min(1, 'End date is required'),
  startInvoiceNumber: z.string()
    .min(1, 'Starting invoice number is required')
    .transform(val => parseInt(val))
    .refine(val => !isNaN(val) && val > 0, 'Must be a positive number'),
  productName: z.string().min(1, 'Product name is required'),
  partyData: z.string().min(1, 'Party data is required').refine(
    (data) => {
      const lines = data.trim().split('\n')
      return lines.every(line => {
        const parts = line.split(',')
        return parts.length === 2 && !isNaN(parseFloat(parts[1]))
      })
    },
    {
      message: 'Invalid party data format. Each line should be "Party Name, Balance"'
    }
  ),
  minPurchaseRate: z.string()
    .transform(val => parseFloat(val))
    .refine(val => !isNaN(val) && val > 0, 'Must be a positive number'),
  maxPurchaseRate: z.string()
    .transform(val => parseFloat(val))
    .refine(val => !isNaN(val) && val > 0, 'Must be a positive number'),
  minMarginPercentage: z.string()
    .transform(val => parseFloat(val))
    .refine(val => !isNaN(val) && val >= 0, 'Must be a non-negative number'),
  maxMarginPercentage: z.string()
    .transform(val => parseFloat(val))
    .refine(val => !isNaN(val) && val >= 0, 'Must be a non-negative number'),
  useFileUpload: z.boolean().optional()
}).refine(
  (data) => {
    const start = new Date(data.startDate)
    const end = new Date(data.endDate)
    return start <= end
  },
  {
    message: "End date must be after start date",
    path: ["endDate"]
  }
).refine(
  (data) => {
    return parseFloat(data.minPurchaseRate) <= parseFloat(data.maxPurchaseRate)
  },
  {
    message: "Maximum purchase rate must be greater than minimum purchase rate",
    path: ["maxPurchaseRate"]
  }
).refine(
  (data) => {
    return parseFloat(data.minMarginPercentage) <= parseFloat(data.maxMarginPercentage)
  },
  {
    message: "Maximum margin percentage must be greater than minimum margin percentage",
    path: ["maxMarginPercentage"]
  }
)

export default function InvoiceForm() {
  const [isLoading, setIsLoading] = useState(false)
  const [useFileUpload, setUseFileUpload] = useState(false)
  const { toast } = useToast()

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm({
    resolver: zodResolver(formSchema),
    defaultValues: {
      minPurchaseRate: '22.00',
      maxPurchaseRate: '23.00',
      minMarginPercentage: '2.25',
      maxMarginPercentage: '2.65',
      productName: 'Paddy',
      useFileUpload: false
    }
  })

  const handleFileUpload = async (e) => {
    const file = e.target.files?.[0]
    if (file) {
      try {
        const text = await file.text()
        const textarea = document.querySelector('textarea[name="partyData"]')
        if (textarea) {
          textarea.value = text
          textarea.dispatchEvent(new Event('input', { bubbles: true }))
        }
      } catch (err) {
        toast({
          variant: "destructive",
          title: "Error",
          description: 'Failed to read file: ' + err.message
        })
      }
    }
  }

  const onSubmit = async (data) => {
    try {
      setIsLoading(true)
      
      const response = await axios.post('/api/generateInvoices', data, {
        responseType: 'blob',
      })

      const contentType = response.headers['content-type']
      if (contentType && contentType.includes('application/json')) {
        const reader = new FileReader()
        reader.onload = () => {
          const errorData = JSON.parse(reader.result)
          toast({
            variant: "destructive",
            title: "Error",
            description: errorData.message || 'An error occurred while generating invoices'
          })
        }
        reader.readAsText(response.data)
        return
      }

      const url = window.URL.createObjectURL(new Blob([response.data]))
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', 'invoices.csv')
      document.body.appendChild(link)
      link.click()
      link.remove()

      toast({
        title: "Success",
        description: "Invoices generated successfully"
      })
    } catch (err) {
      console.error('Form submission error:', err)
      toast({
        variant: "destructive",
        title: "Error",
        description: err.response?.data?.message || 'An error occurred while generating invoices'
      })
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <Card className="w-full max-w-4xl mx-auto shadow-lg">
      <CardHeader className="space-y-1">
        <CardTitle className="text-2xl font-bold tracking-tight">Generate Invoices</CardTitle>
        <CardDescription className="text-base text-gray-500">
          Fill in the details below to generate invoices with customized parameters.
        </CardDescription>
      </CardHeader>
      <form onSubmit={handleSubmit(onSubmit)}>
        <CardContent className="space-y-8">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-2.5">
              <Label className="text-sm font-medium" htmlFor="startDate">Invoice Start Date</Label>
              <Input
                id="startDate"
                type="date"
                className="font-medium"
                {...register('startDate')}
              />
              {errors.startDate && (
                <p className="text-sm font-medium text-destructive mt-1.5">{errors.startDate.message}</p>
              )}
            </div>

            <div className="space-y-2.5">
              <Label className="text-sm font-medium" htmlFor="endDate">Invoice End Date</Label>
              <Input
                id="endDate"
                type="date"
                className="font-medium"
                {...register('endDate')}
              />
              {errors.endDate && (
                <p className="text-sm font-medium text-destructive mt-1.5">{errors.endDate.message}</p>
              )}
            </div>

            <div className="space-y-2.5">
              <Label className="text-sm font-medium" htmlFor="startInvoiceNumber">Starting Invoice Number</Label>
              <Input
                id="startInvoiceNumber"
                type="number"
                placeholder="e.g., 1001"
                className="font-medium"
                {...register('startInvoiceNumber')}
              />
              {errors.startInvoiceNumber && (
                <p className="text-sm font-medium text-destructive mt-1.5">{errors.startInvoiceNumber.message}</p>
              )}
            </div>

            <div className="space-y-2.5">
              <Label className="text-sm font-medium" htmlFor="productName">Product Name</Label>
              <Input
                id="productName"
                type="text"
                className="font-medium"
                {...register('productName')}
              />
              {errors.productName && (
                <p className="text-sm font-medium text-destructive mt-1.5">{errors.productName.message}</p>
              )}
            </div>

            <div className="space-y-2.5">
              <Label className="text-sm font-medium" htmlFor="minPurchaseRate">Minimum Purchase Rate (₹/kg)</Label>
              <Input
                id="minPurchaseRate"
                type="number"
                step="0.01"
                className="font-medium"
                {...register('minPurchaseRate')}
              />
              {errors.minPurchaseRate && (
                <p className="text-sm font-medium text-destructive mt-1.5">{errors.minPurchaseRate.message}</p>
              )}
            </div>

            <div className="space-y-2.5">
              <Label className="text-sm font-medium" htmlFor="maxPurchaseRate">Maximum Purchase Rate (₹/kg)</Label>
              <Input
                id="maxPurchaseRate"
                type="number"
                step="0.01"
                className="font-medium"
                {...register('maxPurchaseRate')}
              />
              {errors.maxPurchaseRate && (
                <p className="text-sm font-medium text-destructive mt-1.5">{errors.maxPurchaseRate.message}</p>
              )}
            </div>

            <div className="space-y-2.5">
              <Label className="text-sm font-medium" htmlFor="minMarginPercentage">Minimum Margin Percentage (%)</Label>
              <Input
                id="minMarginPercentage"
                type="number"
                step="0.01"
                className="font-medium"
                {...register('minMarginPercentage')}
              />
              {errors.minMarginPercentage && (
                <p className="text-sm font-medium text-destructive mt-1.5">{errors.minMarginPercentage.message}</p>
              )}
            </div>

            <div className="space-y-2.5">
              <Label className="text-sm font-medium" htmlFor="maxMarginPercentage">Maximum Margin Percentage (%)</Label>
              <Input
                id="maxMarginPercentage"
                type="number"
                step="0.01"
                className="font-medium"
                {...register('maxMarginPercentage')}
              />
              {errors.maxMarginPercentage && (
                <p className="text-sm font-medium text-destructive mt-1.5">{errors.maxMarginPercentage.message}</p>
              )}
            </div>
          </div>

          <div className="space-y-2.5">
            <div className="flex items-center justify-between">
              <Label className="text-sm font-medium" htmlFor="partyData">Party Data</Label>
              <div className="flex items-center space-x-3">
                <label className="text-sm flex items-center space-x-2">
                  <input
                    type="checkbox"
                    className="rounded border-gray-300 text-primary focus:ring-primary"
                    checked={useFileUpload}
                    onChange={(e) => setUseFileUpload(e.target.checked)}
                  />
                  <span className="font-medium">Upload CSV file</span>
                </label>
                {useFileUpload && (
                  <Input
                    type="file"
                    accept=".csv,text/csv"
                    onChange={handleFileUpload}
                    className="max-w-[200px] text-sm font-medium"
                  />
                )}
              </div>
            </div>
            <div className="text-sm text-muted-foreground mb-2 font-medium">
              Enter each party in a new line with format: "Party Name, Balance"
            </div>
            <Textarea
              id="partyData"
              {...register('partyData')}
              placeholder="UNR- ABHISHEK KUMAR, 300000.00&#10;UNR- CHANDAN SINGH, 300000.00"
              className="font-mono text-sm min-h-[150px]"
              rows={6}
            />
            {errors.partyData && (
              <p className="text-sm font-medium text-destructive mt-1.5">{errors.partyData.message}</p>
            )}
          </div>
        </CardContent>
        <CardFooter>
          <Button 
            type="submit" 
            className="w-full font-semibold text-base py-6"
            disabled={isLoading}
          >
            {isLoading ? 'Generating...' : 'Generate Invoices'}
          </Button>
        </CardFooter>
      </form>
    </Card>
  )
} 
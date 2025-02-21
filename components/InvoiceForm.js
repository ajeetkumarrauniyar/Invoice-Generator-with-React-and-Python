"use client";

import { useEffect, useState } from "react";
import { set, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import axios from "axios";

import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { useToast } from "@/hooks/use-toast";
import { RadioGroup, RadioGroupItem } from "./ui/radio-group";

const baseSchema = {
  startDate: z.string().min(1, "Start date is required"),
  endDate: z.string().min(1, "End date is required"),
  startInvoiceNumber: z
    .string()
    .min(1, "Starting invoice number is required")
    .transform((val) => parseInt(val))
    .refine((val) => !isNaN(val) && val > 0, "Must be a positive number"),
  productName: z.string().min(1, "Product name is required"),
  minPurchaseRate: z
    .string()
    .transform((val) => parseFloat(val))
    .refine((val) => !isNaN(val) && val > 0, "Must be a positive number"),
  maxPurchaseRate: z
    .string()
    .transform((val) => parseFloat(val))
    .refine((val) => !isNaN(val) && val > 0, "Must be a positive number"),
  minMarginPercentage: z
    .string()
    .transform((val) => parseFloat(val))
    .refine((val) => !isNaN(val) && val >= 0, "Must be a non-negative number"),
  maxMarginPercentage: z
    .string()
    .transform((val) => parseFloat(val))
    .refine((val) => !isNaN(val) && val >= 0, "Must be a non-negative number"),
  dataEntryMode: z.enum(["manual", "generate"]),
  invoiceType: z.enum(["purchase", "sales"]).default("purchase"),
};

const manualSchema = z.object({
  ...baseSchema,
  dataEntryMode: z.literal("manual"),
  partyData: z
    .string()
    .min(1, "Party data is required")
    .refine(
      (data) => {
        const lines = data.trim().split("\n");
        return lines.every((line) => {
          const parts = line.split(",");
          return parts.length === 2 && !isNaN(parseFloat(parts[1]));
        });
      },
      {
        message:
          'Invalid party data format. Each line should be "Party Name, Balance"',
      }
    ),
  useFileUpload: z.boolean().optional(),
});

const generateSchema = z.object({
  ...baseSchema,
  dataEntryMode: z.literal("generate"),
  generateParties: z.boolean(),
  totalAmount: z
    .string()
    .min(1, "Total amount is required")
    .transform((val) => parseFloat(val))
    .refine((val) => !isNaN(val) && val > 0, "Must be a positive number"),
  partyLimit: z
    .string()
    .min(1, "Per-party limit is required")
    .transform((val) => parseFloat(val))
    .refine((val) => !isNaN(val) && val > 0, "Must be a positive number"),
});

const formSchema = z
  .discriminatedUnion("dataEntryMode", [manualSchema, generateSchema])
  // Validate dates
  .refine(
    (data) => {
      const start = new Date(data.startDate);
      const end = new Date(data.endDate);
      return start <= end;
    },
    {
      message: "End date must be after start date",
      path: ["endDate"],
    }
  )
  // Validate rates
  .refine(
    (data) => {
      return (
        parseFloat(data.minPurchaseRate) <= parseFloat(data.maxPurchaseRate)
      );
    },
    {
      message:
        "Maximum purchase rate must be greater than minimum purchase rate",
      path: ["maxPurchaseRate"],
    }
  )
  // Validate margins
  .refine(
    (data) => {
      return (
        parseFloat(data.minMarginPercentage) <=
        parseFloat(data.maxMarginPercentage)
      );
    },
    {
      message:
        "Maximum margin percentage must be greater than minimum margin percentage",
      path: ["maxMarginPercentage"],
    }
  )
  // Validate Party limit
  .refine(
    (data) => {
      if (data.dataEntryMode === "generate") {
        return parseFloat(data.partyLimit) <= parseFloat(data.totalAmount);
      }
      return true;
    },
    {
      message: "Party limit cannot be greater than total amount",
      path: ["partyLimit"],
    }
  );

export default function InvoiceForm() {
  const [isLoading, setIsLoading] = useState(false);
  const [useFileUpload, setUseFileUpload] = useState(false);
  const { toast } = useToast();

  const {
    register,
    handleSubmit,
    formState: { errors },
    watch,
    setValue,
  } = useForm({
    resolver: zodResolver(formSchema),
    defaultValues: {
      startDate: "",
      endDate: "",
      startInvoiceNumber: "",
      minPurchaseRate: "22.00",
      maxPurchaseRate: "23.00",
      minMarginPercentage: "2.25",
      maxMarginPercentage: "2.65",
      productName: "WHOLE PADDY GRAINS",
      useFileUpload: false,
      dataEntryMode: "manual",
      generateParties: true,
      totalAmount: "",
      partyLimit: "",
      invoiceType: "purchase",
    },
  });

  const invoiceType = watch("invoiceType");

  useEffect(() => {
    if (invoiceType === "sales") {
      setValue("minPurchaseRate", "22.50");
      setValue("maxPurchaseRate", "23.65");
      setValue("minMarginPercentage", "0");
      setValue("maxMarginPercentage", "0");
      setValue("totalAmount", 0);
    } else {
      setValue("minPurchaseRate", "22.00");
      setValue("maxPurchaseRate", "23.00");
      setValue("minMarginPercentage", "2.25");
      setValue("maxMarginPercentage", "2.65");
      setValue("totalAmount", "4500000");
      setValue("partyLimit", "200000");
    }
  }, [invoiceType, setValue]);

  const handleFileUpload = async (e) => {
    const file = e.target.files?.[0];
    if (file) {
      try {
        const text = await file.text();
        setValue("partyData", text, { shouldValidate: true });
      } catch (err) {
        toast({
          variant: "destructive",
          title: "Error",
          description: "Failed to read file: " + err.message,
        });
      }
    }
  };

  const onSubmit = async (data) => {
    try {
      setIsLoading(true);

      const requestData = {
        ...data,
        generateParties: true,
        partyData: data.dataEntryMode === "generate" ? [] : data.partyData,
      };

      if (requestData.generateParties === false && !requestData.partyData) {
        console.error("partyData is required when generateParties is false");
      }

      // Validate party data format
      const partyLines = data.partyData
        ? data.partyData.trim().split("\n")
        : [];
      const validPartyData = partyLines.every((line) => {
        const [name, balance] = line.split(",").map((s) => s.trim());
        return name && !isNaN(balance) && parseFloat(balance) > 0;
      });

      if (!validPartyData) {
        toast({
          variant: "destructive",
          title: "Error",
          description:
            "Invalid party data format. Each line should be in the format: 'Party Name, Balance' with positive balance",
        });
        return;
      }

      const response = await axios.post("/api/generateInvoices", data, {
        responseType: "blob",
        timeout: 30000, // 30 second timeout
        headers: {
          "Content-Type": "application/json",
        },
      });

      const contentType = response.headers["content-type"];
      if (contentType && contentType.includes("application/json")) {
        const reader = new FileReader();
        reader.onload = () => {
          try {
            const errorData = JSON.parse(reader.result);
            toast({
              variant: "destructive",
              title: "Error",
              description:
                errorData.message ||
                "An error occurred while generating invoices",
            });
          } catch (err) {
            console.error("Error parsing error response:", err);
            toast({
              variant: "destructive",
              title: "Error",
              description: "Failed to parse error response from server",
            });
          }
        };
        reader.onerror = () => {
          console.error("Error reading error response:", reader.error);
          toast({
            variant: "destructive",
            title: "Error",
            description: "Failed to read error response from server",
          });
        };
        reader.readAsText(response.data);
        return;
      }

      // Validate that we received data
      if (!response.data || response.data.size === 0) {
        toast({
          variant: "destructive",
          title: "Error",
          description: "No data received from server",
        });
        return;
      }

      const url = window.URL.createObjectURL(
        new Blob([response.data], { type: "text/csv" })
      );
      const link = document.createElement("a");
      link.href = url;

      // Get filename from Content-Disposition header
      const contentDisposition = response.headers.get("content-disposition");
      const filename = contentDisposition
        ? contentDisposition.split("filename=")[1].replace(/"/g, "")
        : `${data.invoiceType}_invoices_${
            new Date().toISOString().split("T")[0]
          }.csv`;

      link.setAttribute("download", filename);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url); // Clean up the URL object

      toast({
        title: "Success",
        description: "Invoices generated successfully",
      });
    } catch (err) {
      console.error("Form submission error:", err);
      let errorMessage = "An error occurred while generating invoices";

      if (err.code === "ECONNABORTED") {
        errorMessage = "Request timed out. Please try again.";
      } else if (err.response) {
        // Try to read the error message from the blob response
        try {
          const reader = new FileReader();
          reader.onload = () => {
            try {
              const errorData = JSON.parse(reader.result);
              toast({
                variant: "destructive",
                title: "Error",
                description: errorData.message || "Server error occurred",
              });
            } catch (parseErr) {
              console.error("Error parsing error response:", parseErr);
              toast({
                variant: "destructive",
                title: "Error",
                description: "Server error occurred",
              });
            }
          };
          reader.onerror = () => {
            console.error("Error reading error response:", reader.error);
            toast({
              variant: "destructive",
              title: "Error",
              description: "Server error occurred",
            });
          };
          reader.readAsText(err.response.data);
        } catch (blobErr) {
          console.error("Error handling blob response:", blobErr);
          toast({
            variant: "destructive",
            title: "Error",
            description: err.response.data?.message || "Server error occurred",
          });
        }
      } else if (err.request) {
        errorMessage =
          "Unable to reach the server. Please check your connection.";
        toast({
          variant: "destructive",
          title: "Error",
          description: errorMessage,
        });
      } else {
        toast({
          variant: "destructive",
          title: "Error",
          description: errorMessage,
        });
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Card className="w-full max-w-4xl mx-auto shadow-lg">
      <CardHeader className="space-y-1">
        <CardTitle className="text-2xl font-bold tracking-tight">
          Generate Invoices
        </CardTitle>
        <CardDescription className="text-base text-gray-500">
          Fill in the details below to generate invoices with customized
          parameters.
        </CardDescription>
        <div className="mt-4 flex items-center justify-end space-x-3">
          <span
            className={`text-md font-bold ${
              invoiceType === "purchase" ? "text-blue-500" : "text-gray-400"
            }`}
          >
            Purchase
          </span>
          <Switch
            checked={invoiceType === "sales"}
            onCheckedChange={(checked) =>
              setValue("invoiceType", checked ? "sales" : "purchase", {
                shouldValidate: true,
              })
            }
          />
          <span
            className={`text-md font-bold ${
              invoiceType === "sales" ? "text-green-500" : "text-gray-400"
            }`}
          >
            Sales
          </span>
        </div>
      </CardHeader>
      <form onSubmit={handleSubmit(onSubmit)}>
        <CardContent className="space-y-8">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-2.5">
              <Label className="text-sm font-medium" htmlFor="startDate">
                Invoice Start Date
              </Label>
              <Input
                id="startDate"
                type="date"
                className="font-medium"
                {...register("startDate")}
              />
              {errors.startDate && (
                <p className="text-sm font-medium text-destructive mt-1.5">
                  {errors.startDate.message}
                </p>
              )}
            </div>

            <div className="space-y-2.5">
              <Label className="text-sm font-medium" htmlFor="endDate">
                Invoice End Date
              </Label>
              <Input
                id="endDate"
                type="date"
                className="font-medium"
                {...register("endDate")}
              />
              {errors.endDate && (
                <p className="text-sm font-medium text-destructive mt-1.5">
                  {errors.endDate.message}
                </p>
              )}
            </div>

            <div className="space-y-2.5">
              <Label
                className="text-sm font-medium"
                htmlFor="startInvoiceNumber"
              >
                Starting Invoice Number
              </Label>
              <Input
                id="startInvoiceNumber"
                type="number"
                placeholder="e.g., 1001"
                className="font-medium"
                {...register("startInvoiceNumber")}
              />
              {errors.startInvoiceNumber && (
                <p className="text-sm font-medium text-destructive mt-1.5">
                  {errors.startInvoiceNumber.message}
                </p>
              )}
            </div>

            <div className="space-y-2.5">
              <Label className="text-sm font-medium" htmlFor="productName">
                Product Name
              </Label>
              <Input
                id="productName"
                type="text"
                className="font-medium"
                {...register("productName")}
              />
              {errors.productName && (
                <p className="text-sm font-medium text-destructive mt-1.5">
                  {errors.productName.message}
                </p>
              )}
            </div>

            <div className="space-y-2.5">
              <Label className="text-sm font-medium" htmlFor="minPurchaseRate">
                Minimum {invoiceType === "sales" ? "Sales" : "Purchase"} Rate
                (₹/kg)
              </Label>
              <Input
                id="minPurchaseRate"
                type="number"
                step="0.01"
                className="font-medium"
                {...register("minPurchaseRate")}
              />
              {errors.minPurchaseRate && (
                <p className="text-sm font-medium text-destructive mt-1.5">
                  {errors.minPurchaseRate.message}
                </p>
              )}
            </div>

            <div className="space-y-2.5">
              <Label className="text-sm font-medium" htmlFor="maxPurchaseRate">
                Maximum {invoiceType === "sales" ? "Sales" : "Purchase"} Rate
                (₹/kg)
              </Label>
              <Input
                id="maxPurchaseRate"
                type="number"
                step="0.01"
                className="font-medium"
                {...register("maxPurchaseRate")}
              />
              {errors.maxPurchaseRate && (
                <p className="text-sm font-medium text-destructive mt-1.5">
                  {errors.maxPurchaseRate.message}
                </p>
              )}
            </div>
            {invoiceType === "purchase" && (
              <>
                <div className="space-y-2.5">
                  <Label
                    className="text-sm font-medium"
                    htmlFor="minMarginPercentage"
                  >
                    Minimum Margin Percentage (%)
                  </Label>
                  <Input
                    id="minMarginPercentage"
                    type="number"
                    step="0.01"
                    defaultValue="2.25"
                    className="font-medium"
                    {...register("minMarginPercentage")}
                  />
                  {errors.minMarginPercentage && (
                    <p className="text-sm font-medium text-destructive mt-1.5">
                      {errors.minMarginPercentage.message}
                    </p>
                  )}
                </div>

                <div className="space-y-2.5">
                  <Label
                    className="text-sm font-medium"
                    htmlFor="maxMarginPercentage"
                  >
                    Maximum Margin Percentage (%)
                  </Label>
                  <Input
                    id="maxMarginPercentage"
                    type="number"
                    step="0.01"
                    defaultValue="2.65"
                    className="font-medium"
                    {...register("maxMarginPercentage")}
                  />
                  {errors.maxMarginPercentage && (
                    <p className="text-sm font-medium text-destructive mt-1.5">
                      {errors.maxMarginPercentage.message}
                    </p>
                  )}
                </div>
              </>
            )}
          </div>

          <div className="space-y-4">
            <Label className="text-sm font-medium">Data Entry Mode</Label>
            <RadioGroup
              defaultValue="manual"
              className="grid grid-cols-2 gap-4"
              {...register("dataEntryMode")}
              onValueChange={(value) =>
                setValue("dataEntryMode", value, { shouldValidate: true })
              }
            >
              <div className="flex items-center space-x-2">
                <RadioGroupItem value="manual" id="manual" />
                <Label htmlFor="manual">Manual Party Data Entry</Label>
              </div>
              <div className="flex items-center space-x-2">
                <RadioGroupItem value="generate" id="generate" />
                <Label htmlFor="generate">Auto-Generate Party Data</Label>
              </div>
            </RadioGroup>
          </div>

          {watch("dataEntryMode") === "manual" ? (
            <div className="space-y-2.5">
              <div className="flex items-center justify-between">
                <Label className="text-sm font-medium" htmlFor="partyData">
                  Party Data
                </Label>
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
                Enter each party in a new line with format: "Party Name,
                Balance"
              </div>
              <Textarea
                id="partyData"
                {...register("partyData")}
                placeholder="UNR- ABHISHEK KUMAR, 300000.00&#10;UNR- CHANDAN SINGH, 300000.00"
                className="font-mono text-sm min-h-[150px]"
                rows={6}
              />
              {errors.partyData && (
                <p className="text-sm font-medium text-destructive mt-1.5">
                  {errors.partyData.message}
                </p>
              )}
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="space-y-2.5">
                <Label className="text-sm font-medium" htmlFor="totalAmount">
                  Total {invoiceType === "sales" ? "Sales" : "Purchase"} Amount
                  (₹)
                </Label>
                <Input
                  id="totalAmount"
                  type="number"
                  step="0.01"
                  // placeholder="e.g., 1000000"
                  defaultValue="3000000"
                  className="font-medium"
                  {...register("totalAmount")}
                />
                {errors.totalAmount && (
                  <p className="text-sm font-medium text-destructive mt-1.5">
                    {errors.totalAmount.message}
                  </p>
                )}
              </div>
              {invoiceType === "purchase" && (
                <div className="space-y-2.5">
                  <Label className="text-sm font-medium" htmlFor="partyLimit">
                    Per-Party Limit (₹)
                  </Label>
                  <Input
                    id="partyLimit"
                    type="number"
                    step="0.01"
                    // placeholder="e.g., 200000"
                    default="200000"
                    className="font-medium"
                    {...register("partyLimit")}
                  />
                  {errors.partyLimit && (
                    <p className="text-sm font-medium text-destructive mt-1.5">
                      {errors.partyLimit.message}
                    </p>
                  )}
                </div>
              )}
            </div>
          )}
        </CardContent>
        <CardFooter>
          <Button
            type="submit"
            className="w-full font-semibold text-base py-6"
            disabled={isLoading}
          >
            {isLoading ? "Generating..." : "Generate Invoices"}
          </Button>
        </CardFooter>
      </form>
    </Card>
  );
}

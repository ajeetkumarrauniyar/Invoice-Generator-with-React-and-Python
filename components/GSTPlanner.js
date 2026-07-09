"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useToast } from "@/hooks/use-toast";
import { Toaster } from "@/components/ui/toaster";
import Link from "next/link";

// ─── helpers ───────────────────────────────────────────────
function downloadFile(content, filename, mime = "application/octet-stream") {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function StatusBadge({ status }) {
  const map = {
    idle:    "bg-gray-100 text-gray-600",
    running: "bg-blue-100 text-blue-700",
    done:    "bg-green-100 text-green-700",
    error:   "bg-red-100 text-red-700",
  };
  const label = { idle: "Pending", running: "Running…", done: "Done", error: "Error" };
  return (
    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${map[status]}`}>
      {label[status]}
    </span>
  );
}

function StepCard({ number, title, status, children }) {
  return (
    <Card className="border border-gray-200">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-3 text-base font-semibold text-gray-800">
          <span className="w-7 h-7 rounded-full bg-indigo-600 text-white text-sm flex items-center justify-center flex-shrink-0">
            {number}
          </span>
          {title}
          <StatusBadge status={status} />
        </CardTitle>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

function OutputBlock({ text }) {
  if (!text) return null;
  return (
    <pre className="mt-3 p-3 bg-gray-950 text-green-400 text-xs rounded-lg overflow-x-auto whitespace-pre-wrap font-mono">
      {text}
    </pre>
  );
}

// ─── main component ────────────────────────────────────────
export default function GSTPlanner() {
  const { toast } = useToast();

  // companies
  const [companies, setCompanies]     = useState([]);
  const [selectedCo, setSelectedCo]   = useState(null); // { gstin, trade_name, short_name, spreadsheet_id }

  // shared
  const [month, setMonth] = useState("");

  // Load companies on mount
  useState(() => {
    fetch("/api/gst/companies")
      .then((r) => r.json())
      .then((d) => {
        setCompanies(d.companies || []);
        if (d.companies?.length === 1) setSelectedCo(d.companies[0]);
      })
      .catch(() => {});
  });

  // step states
  const [step1Status, setStep1Status] = useState("idle");
  const [step1Output, setStep1Output] = useState("");
  const [step1Warnings, setStep1Warnings] = useState([]);

  const [step2Status, setStep2Status] = useState("idle");
  const [step2Output, setStep2Output] = useState("");
  const [step2Range, setStep2Range] = useState(null);
  const [hsn18, setHsn18] = useState("");

  const [step3Status, setStep3Status] = useState("idle");
  const [step3Output, setStep3Output] = useState("");

  const [step4Status, setStep4Status] = useState("idle");
  const [records, setRecords] = useState([]);
  const [summary, setSummary] = useState(null);
  const [filterType, setFilterType] = useState("");

  // ── Step 1: B2B invoices ──
  async function runStep1() {
    if (!month.match(/^\d{6}$/)) {
      toast({ title: "Month format galat hai", description: "MMYYYY format mein dalein, jaise 052026", variant: "destructive" });
      return;
    }
    setStep1Status("running");
    setStep1Output("");
    setStep1Warnings([]);

    try {
      const res = await fetch("/api/gst/planB2B", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ month, gstin: selectedCo?.gstin, spreadsheetId: selectedCo?.spreadsheet_id }),
      });
      const data = await res.json();

      if (!res.ok) {
        setStep1Status("error");
        setStep1Output(data.output || data.message);
        toast({ title: "B2B generation failed", description: data.message, variant: "destructive" });
        return;
      }

      setStep1Status("done");
      setStep1Output(data.output);
      setStep1Warnings(data.warnings || []);

      if (data.salesRecordsCsv) {
        downloadFile(data.salesRecordsCsv, "sales_records_addition.csv", "text/csv");
      }

      toast({
        title: `B2B done — ${data.totalInvoices} invoices`,
        description: data.warnings?.length
          ? `${data.warnings.length} warnings — check output below`
          : "Sab sahi, Excel updated, CSV downloaded",
      });
    } catch (e) {
      setStep1Status("error");
      toast({ title: "Network error", description: e.message, variant: "destructive" });
    }
  }

  // ── Step 2: B2C + Exempt ──
  async function runStep2() {
    if (!month.match(/^\d{6}$/)) {
      toast({ title: "Month format galat hai", description: "MMYYYY format mein dalein", variant: "destructive" });
      return;
    }
    setStep2Status("running");
    setStep2Output("");
    setStep2Range(null);

    try {
      const res = await fetch("/api/gst/generateB2C", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ month, hsn18: hsn18 || undefined, gstin: selectedCo?.gstin, spreadsheetId: selectedCo?.spreadsheet_id }),
      });
      const data = await res.json();

      if (!res.ok) {
        setStep2Status("error");
        setStep2Output(data.output || data.message);
        toast({ title: "B2C generation failed", description: data.message, variant: "destructive" });
        return;
      }

      setStep2Status("done");
      setStep2Output(data.output);
      setStep2Range({ from: data.invoiceFrom, to: data.invoiceTo, count: data.totalInvoices });

      // Download all B2C CSVs
      const { files } = data;
      if (files?.cashRecordsCsv) downloadFile(files.cashRecordsCsv, "cash_sales_records.csv", "text/csv");

      toast({
        title: `B2C done — ${data.totalInvoices} invoices`,
        description: `${data.invoiceFrom} → ${data.invoiceTo}`,
      });
    } catch (e) {
      setStep2Status("error");
      toast({ title: "Network error", description: e.message, variant: "destructive" });
    }
  }

  // ── Step 3: Generate JSON ──
  async function runStep3() {
    if (!month.match(/^\d{6}$/)) {
      toast({ title: "Month format galat hai", description: "MMYYYY format mein dalein", variant: "destructive" });
      return;
    }
    setStep3Status("running");
    setStep3Output("");

    try {
      const res = await fetch("/api/gst/buildJSON", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ month, gstin: selectedCo?.gstin, spreadsheetId: selectedCo?.spreadsheet_id }),
      });

      if (!res.ok) {
        const data = await res.json();
        setStep3Status("error");
        setStep3Output(data.output || data.message);
        toast({ title: "JSON generation failed", description: data.message, variant: "destructive" });
        return;
      }

      // File download directly
      const blob = await res.blob();
      downloadFile(await blob.arrayBuffer(), `gstr1_${month}.json`, "application/json");

      const scriptOutput = decodeURIComponent(res.headers.get("X-Script-Output") || "");
      setStep3Status("done");
      setStep3Output(scriptOutput);

      toast({
        title: "GSTR-1 JSON ready",
        description: `gstr1_${month}.json downloaded — portal pe upload karo`,
      });
    } catch (e) {
      setStep3Status("error");
      toast({ title: "Network error", description: e.message, variant: "destructive" });
    }
  }

  // ── Step 4: Sales Records ──
  async function loadRecords() {
    if (!month.match(/^\d{6}$/)) {
      toast({ title: "Month format galat hai", variant: "destructive" });
      return;
    }
    setStep4Status("running");
    setRecords([]);
    setSummary(null);

    try {
      const params = new URLSearchParams({ fp: month });
      if (filterType) params.set("type", filterType);

      const res = await fetch(`/api/gst/records?${params}`);
      const data = await res.json();

      if (!res.ok) {
        setStep4Status("error");
        toast({ title: "Records fetch failed", description: data.message, variant: "destructive" });
        return;
      }

      setStep4Status("done");
      setRecords(data.invoices || []);
      setSummary(data.summary);
    } catch (e) {
      setStep4Status("error");
      toast({ title: "Network error", description: e.message, variant: "destructive" });
    }
  }

  function downloadRecordsCsv() {
    if (!records.length) return;
    const cols = ["invoice_no","invoice_date","invoice_type","party_gstin","party_name","taxable_value","cgst_amount","sgst_amount","invoice_value","qty_1l","qty_500ml"];
    const header = cols.join(",");
    const rows = records.map(r => cols.map(c => r[c] ?? "").join(","));
    downloadFile([header, ...rows].join("\n"), `records_${month}.csv`, "text/csv");
  }

  const mmyyyy = month.length === 6
    ? `${month.slice(0,2)}/${month.slice(2)}`
    : "—";

  return (
    <div className="min-h-screen bg-gray-50">
      <Toaster />

      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="max-w-4xl mx-auto flex flex-wrap items-center gap-4 justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-900">GST Smart Planner</h1>
            <p className="text-sm text-gray-500 mt-0.5">IT Maverick Solutions</p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            {/* Company selector */}
            {companies.length > 1 && (
              <select
                value={selectedCo?.gstin || ""}
                onChange={(e) =>
                  setSelectedCo(
                    companies.find((c) => c.gstin === e.target.value) || null,
                  )
                }
                className="border border-gray-300 rounded-md px-3 py-1.5 text-sm bg-white font-medium text-gray-800"
              >
                <option value="">Select Company</option>
                {companies.map((c) => (
                  <option key={c.gstin} value={c.gstin}>
                    {c.short_name} — {c.gstin}
                  </option>
                ))}
              </select>
            )}
            {/* {selectedCo && (
              <span className="text-xs text-gray-400 font-mono hidden sm:block">
                {selectedCo.trade_name}
              </span>
            )} */}
            <Label
              htmlFor="month"
              className="text-sm font-medium text-gray-700 whitespace-nowrap"
            >
              Tax Period
            </Label>
            <Input
              id="month"
              placeholder="052026"
              value={month}
              onChange={(e) =>
                setMonth(e.target.value.replace(/\D/g, "").slice(0, 6))
              }
              className="w-28 text-center font-mono"
            />
            {/* <span className="text-sm text-gray-400 font-mono min-w-[48px]">
              {mmyyyy}
            </span> */}
          </div>
          <Button asChild className="flex justify-center items-center ml-4">
            <Link href="/reports">Reports</Link>
          </Button>
        </div>
      </div>

      {/* Steps */}
      <div className="max-w-4xl mx-auto px-6 py-8 space-y-6">

        {/* Step 1 */}
        <StepCard number="1" title="B2B Invoices" status={step1Status}>
          <p className="text-sm text-gray-500 mb-4">
            B2B_PARTIES sheet se parties + targets padh kar invoices generate karta hai, Excel update karta hai, aur NeonDB mein save karta hai.
          </p>
          <Button
            onClick={runStep1}
            disabled={step1Status === "running" || !month}
            className="bg-indigo-600 hover:bg-indigo-700 text-white"
          >
            {step1Status === "running" ? "Generating…" : "Generate B2B Invoices"}
          </Button>

          {step1Warnings.length > 0 && (
            <div className="mt-3 p-3 bg-amber-50 border border-amber-200 rounded-lg">
              <p className="text-xs font-semibold text-amber-800 mb-1">⚠ Warnings</p>
              {step1Warnings.map((w, i) => (
                <p key={i} className="text-xs text-amber-700">• {w}</p>
              ))}
            </div>
          )}
          <OutputBlock text={step1Output} />
        </StepCard>

        {/* Step 2 */}
        <StepCard number="2" title="B2C + Exempt Invoices" status={step2Status}>
          <p className="text-sm text-gray-500 mb-4">
            FY2026-27 sheet se targets padhta hai (5%, 18%, exempt). CM series auto-detect hoti hai DB se.
          </p>
          <div className="flex items-center gap-3 mb-4">
            <Label htmlFor="hsn18" className="text-sm whitespace-nowrap text-gray-600">HSN @18%</Label>
            <Input
              id="hsn18"
              placeholder="e.g. 151349 (agar 18% sales hain)"
              value={hsn18}
              onChange={e => setHsn18(e.target.value)}
              className="max-w-xs font-mono"
            />
          </div>
          <Button
            onClick={runStep2}
            disabled={step2Status === "running" || !month}
            className="bg-indigo-600 hover:bg-indigo-700 text-white"
          >
            {step2Status === "running" ? "Generating…" : "Generate B2C + Exempt"}
          </Button>

          {step2Range && (
            <p className="mt-3 text-sm text-green-700 font-medium">
              Invoice Planning: <span className="font-mono">{step2Range.from}</span> → <span className="font-mono">{step2Range.to}</span> &nbsp;·&nbsp; {step2Range.count} invoices
            </p>
          )}
          <OutputBlock text={step2Output} />
        </StepCard>

        {/* Step 3 */}
        <StepCard number="3" title="GSTR-1 JSON" status={step3Status}>
          <p className="text-sm text-gray-500 mb-4">
            Sab sections (B2B + HSN + B2CS + EXEMP + DOCS) combine karke portal-ready JSON download karta hai.
          </p>
          <Button
            onClick={runStep3}
            disabled={step3Status === "running" || !month}
            className="bg-indigo-600 hover:bg-indigo-700 text-white"
          >
            {step3Status === "running" ? "Building JSON…" : "Download GSTR-1 JSON"}
          </Button>

          {step3Status === "done" && (
            <p className="mt-3 text-sm text-green-700 font-medium">
              ✓ <span className="font-mono">gstr1_{month}.json</span> downloaded — GST Portal pe upload karo
            </p>
          )}
          <OutputBlock text={step3Output} />
        </StepCard>

        {/* Step 4 */}
        <StepCard number="4" title="Sales Records" status={step4Status}>
          <p className="text-sm text-gray-500 mb-4">
            NeonDB se us mahine ke saare invoices — filter, review, aur CSV export karo ERP entry ke liye.
          </p>
          <div className="flex flex-wrap items-center gap-3 mb-4">
            <select
              value={filterType}
              onChange={e => setFilterType(e.target.value)}
              className="border border-gray-300 rounded-md px-3 py-1.5 text-sm bg-white"
            >
              <option value="">All types</option>
              <option value="B2B">B2B only</option>
              <option value="B2C_5">B2C @5%</option>
              <option value="B2C_18">B2C @18%</option>
              <option value="EXEMPT">Exempt</option>
            </select>
            <Button
              onClick={loadRecords}
              disabled={step4Status === "running" || !month}
              variant="outline"
              className="border-indigo-300 text-indigo-700 hover:bg-indigo-50"
            >
              {step4Status === "running" ? "Loading…" : "Load Records"}
            </Button>
            {records.length > 0 && (
              <Button onClick={downloadRecordsCsv} variant="outline" className="text-gray-700">
                Download CSV
              </Button>
            )}
          </div>

          {/* Summary bar */}
          {summary && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
              {[
                { label: "B2B Taxable", val: summary.b2b_taxable },
                { label: "B2C @5% Taxable", val: summary.b2c_5_taxable },
                { label: "B2C @18% Taxable", val: summary.b2c_18_taxable },
                { label: "Exempt", val: summary.exempt_taxable },
              ].map(({ label, val }) => (
                <div key={label} className="bg-white border border-gray-200 rounded-lg p-3">
                  <p className="text-xs text-gray-500">{label}</p>
                  <p className="text-sm font-semibold text-gray-800 mt-0.5">
                    ₹{Number(val || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}
                  </p>
                </div>
              ))}
            </div>
          )}

          {/* Table */}
          {records.length > 0 && (
            <div className="overflow-x-auto rounded-lg border border-gray-200">
              <table className="min-w-full text-xs">
                <thead className="bg-gray-50 text-gray-600 uppercase tracking-wide">
                  <tr>
                    {["Invoice No", "Date", "Type", "Party", "Taxable ₹", "GST ₹", "Total ₹"].map(h => (
                      <th key={h} className="px-3 py-2 text-left font-medium whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 bg-white">
                  {records.map((r) => (
                    <tr key={r.invoice_no} className="hover:bg-gray-50">
                      <td className="px-3 py-2 font-mono font-medium text-indigo-700">
                        {r.invoice_no}
                      </td>
                      <td className="px-3 py-2 text-gray-600">
                        {r.invoice_date?.slice(0, 10)}
                      </td>
                      <td className="px-3 py-2">
                        <span
                          className={`px-1.5 py-0.5 rounded text-xs font-medium ${
                            r.invoice_type === "B2B"
                              ? "bg-blue-100 text-blue-700"
                              : r.invoice_type?.startsWith("B2C")
                                ? "bg-purple-100 text-purple-700"
                                : "bg-gray-100 text-gray-600"
                          }`}
                        >
                          {r.invoice_type}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-gray-700 max-w-[160px] truncate">
                        {r.party_name || "—"}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums">
                        {Number(r.taxable_value).toLocaleString("en-IN", { maximumFractionDigits: 2 })}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums text-gray-500">
                        {(
                          (Number(r.cgst_amount) || 0) +
                          (Number(r.sgst_amount) || 0) +
                          (Number(r.igst_amount) || 0)
                        ).toLocaleString("en-IN", { maximumFractionDigits: 2 })}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums font-medium">
                        {Number(r.invoice_value).toLocaleString("en-IN", { maximumFractionDigits: 2 })}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {step4Status === "done" && records.length === 0 && (
            <p className="text-sm text-gray-400 mt-2">Is period mein koi records nahi hain.</p>
          )}
        </StepCard>

      </div>
    </div>
  );
}

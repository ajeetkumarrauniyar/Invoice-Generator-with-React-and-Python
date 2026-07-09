"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/hooks/use-toast";
import { Toaster } from "@/components/ui/toaster";

function downloadCsv(rows, totals, filename) {
  const headers = ["Sl", "Invoice No.", "Invoice Date", "GSTIN", "Receiver Name",
                   "1 Ltr CTN", "500ml CTN", "Taxable Value (₹)", "GST (₹)", "Invoice Value (₹)"];
  const lines = [headers.join(",")];
  rows.forEach(r => {
    lines.push([
      r.sl, r.invoice_no, r.invoice_date,
      r.party_gstin || "", `"${r.party_name || ""}"`,
      r.qty_1l || 0, r.qty_500ml || 0,
      Number(r.taxable_value).toFixed(2),
      Number(r.gst_amount).toFixed(2),
      Number(r.invoice_value).toFixed(2),
    ].join(","));
  });
  // Totals row
  lines.push([
    "", "TOTAL", "", "", "",
    totals.qty_1l, totals.qty_500ml,
    totals.taxable.toFixed(2), totals.gst.toFixed(2), totals.invoice_value.toFixed(2),
  ].join(","));

  const blob = new Blob([lines.join("\n")], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

const inr = (n) => Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 });

export default function SalesReport() {
  const { toast } = useToast();
  const [companies, setCompanies]   = useState([]);
  const [selectedCo, setSelectedCo] = useState(null);
  const [month, setMonth]           = useState("");
  const [type, setType]             = useState("B2B");
  const [report, setReport]         = useState(null);
  const [loading, setLoading]       = useState(false);

  useEffect(() => {
    fetch("/api/gst/companies")
      .then(r => r.json())
      .then(d => setCompanies(d.companies || []))
      .catch(() => {});
  }, []);

  async function loadReport() {
    if (!month.match(/^\d{6}$/)) {
      toast({ title: "Month format galat", description: "MMYYYY (e.g. 042026)", variant: "destructive" });
      return;
    }
    if (!selectedCo) {
      toast({ title: "Company select karo", variant: "destructive" });
      return;
    }
    setLoading(true);
    setReport(null);
    try {
      const params = new URLSearchParams({ fp: month, gstin: selectedCo.gstin, type });
      const res = await fetch(`/api/gst/report?${params}`);
      const data = await res.json();
      if (!res.ok) {
        toast({ title: "Report failed", description: data.message, variant: "destructive" });
        return;
      }
      setReport(data);
      if (!data.rows.length) {
        toast({ title: "Koi records nahi", description: `${month} mein ${type} data nahi mila` });
      }
    } catch (e) {
      toast({ title: "Network error", description: e.message, variant: "destructive" });
    } finally {
      setLoading(false);
    }
  }

  const mmyyyy = month.length === 6 ? `${month.slice(0,2)}/${month.slice(2)}` : "—";

  return (
    <div className="min-h-screen bg-gray-50">
      <Toaster />

      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="max-w-6xl mx-auto flex flex-wrap items-center gap-4 justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-900">Sales Report</h1>
            <p className="text-sm text-gray-500 mt-0.5">ERP-ready · queried live from NeonDB</p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <select
              value={selectedCo?.gstin || ""}
              onChange={e => setSelectedCo(companies.find(c => c.gstin === e.target.value) || null)}
              className="border border-gray-300 rounded-md px-3 py-1.5 text-sm bg-white font-medium"
            >
              <option value="">Select Company</option>
              {companies.map(c => (
                <option key={c.gstin} value={c.gstin}>{c.short_name} — {c.gstin}</option>
              ))}
            </select>
            <select
              value={type}
              onChange={e => setType(e.target.value)}
              className="border border-gray-300 rounded-md px-3 py-1.5 text-sm bg-white"
            >
              <option value="B2B">B2B</option>
              <option value="B2C">B2C + Exempt</option>
              <option value="ALL">All</option>
            </select>
            <Input
              placeholder="042026"
              value={month}
              onChange={e => setMonth(e.target.value.replace(/\D/g, "").slice(0, 6))}
              className="w-28 text-center font-mono"
            />
            <span className="text-sm text-gray-400 font-mono">{mmyyyy}</span>
            <Button onClick={loadReport} disabled={loading} className="bg-indigo-600 hover:bg-indigo-700 text-white">
              {loading ? "Loading…" : "Load Report"}
            </Button>
          </div>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-6 py-8">
        {!report && (
          <div className="text-center py-20 text-gray-400">
            <p>Company aur month select karke "Load Report" click karo</p>
          </div>
        )}

        {report && report.rows.length > 0 && (
          <>
            {/* Summary cards */}
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-6">
              {[
                { label: "Invoices", val: report.totals.count, isCount: true },
                { label: "1 Ltr CTN", val: report.totals.qty_1l, isCount: true },
                { label: "500ml CTN", val: report.totals.qty_500ml, isCount: true },
                { label: "Taxable ₹", val: report.totals.taxable },
                { label: "Invoice Value ₹", val: report.totals.invoice_value },
              ].map(({ label, val, isCount }) => (
                <div key={label} className="bg-white border border-gray-200 rounded-lg p-4">
                  <p className="text-xs text-gray-500">{label}</p>
                  <p className="text-lg font-semibold text-gray-800 mt-1">
                    {isCount ? val : `₹${inr(val)}`}
                  </p>
                </div>
              ))}
            </div>

            {/* Party breakdown */}
            {report.partyBreakdown.length > 0 && type !== "B2C" && (
              <div className="mb-6">
                <h3 className="text-sm font-semibold text-gray-700 mb-2">Party-wise Summary</h3>
                <div className="flex flex-wrap gap-3">
                  {report.partyBreakdown.map(p => (
                    <div key={p.party} className="bg-white border border-gray-200 rounded-lg px-4 py-2">
                      <p className="text-sm font-medium text-gray-800">{p.party}</p>
                      <p className="text-xs text-gray-500">{p.count} invoices · ₹{inr(p.invoice_value)}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Download button */}
            <div className="flex justify-between items-center mb-3">
              <h3 className="text-sm font-semibold text-gray-700">
                {type} Records — {report.period.slice(0,2)}/{report.period.slice(2)}
              </h3>
              <Button
                variant="outline"
                onClick={() => downloadCsv(report.rows, report.totals, `${type}_records_${report.period}.csv`)}
                className="text-gray-700"
              >
                Download CSV (ERP)
              </Button>
            </div>

            {/* Table */}
            <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
              <table className="min-w-full text-xs">
                <thead className="bg-gray-50 text-gray-600 uppercase tracking-wide sticky top-0">
                  <tr>
                    {["Sl", "Invoice No", "Date", "GSTIN", "Party", "1L", "500ml", "Taxable ₹", "GST ₹", "Value ₹"].map(h => (
                      <th key={h} className="px-3 py-2 text-left font-medium whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {report.rows.map((r) => (
                    <tr key={r.invoice_no} className="hover:bg-gray-50">
                      <td className="px-3 py-2 text-gray-400">{r.sl}</td>
                      <td className="px-3 py-2 font-mono font-medium text-indigo-700">{r.invoice_no}</td>
                      <td className="px-3 py-2 text-gray-600 whitespace-nowrap">{r.invoice_date}</td>
                      <td className="px-3 py-2 font-mono text-gray-500">{r.party_gstin || "—"}</td>
                      <td className="px-3 py-2 text-gray-700 max-w-[160px] truncate">{r.party_name || "—"}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{r.qty_1l || 0}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{r.qty_500ml || 0}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{inr(r.taxable_value)}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-gray-500">{inr(r.gst_amount)}</td>
                      <td className="px-3 py-2 text-right tabular-nums font-medium">{inr(r.invoice_value)}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot className="bg-gray-50 font-semibold text-gray-800 border-t-2 border-gray-200">
                  <tr>
                    <td colSpan={5} className="px-3 py-2 text-right">TOTAL</td>
                    <td className="px-3 py-2 text-right tabular-nums">{report.totals.qty_1l}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{report.totals.qty_500ml}</td>
                    <td className="px-3 py-2 text-right tabular-nums">₹{inr(report.totals.taxable)}</td>
                    <td className="px-3 py-2 text-right tabular-nums">₹{inr(report.totals.gst)}</td>
                    <td className="px-3 py-2 text-right tabular-nums">₹{inr(report.totals.invoice_value)}</td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

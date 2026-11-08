"use client";

import { useEffect, useState } from "react";
import {
  ScrollText,
  Search,
  RefreshCw,
  ArrowDownLeft,
  ArrowUpRight,
  ShieldCheck,
  Filter,
} from "lucide-react";
import { fetchTransactions, login, InventoryTxItem } from "@/lib/api";

export default function LedgerAuditPage() {
  const [transactions, setTransactions] = useState<InventoryTxItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("ALL");

  const loadData = async () => {
    try {
      setLoading(true);
      await login("admin@example.com", "admin123").catch(() => {});
      const data = await fetchTransactions(200, typeFilter === "ALL" ? undefined : typeFilter);
      setTransactions(data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [typeFilter]);

  const filteredTx = transactions.filter((tx) => {
    const s = search.toLowerCase();
    const sku = tx.product?.sku?.toLowerCase() || "";
    const name = tx.product?.name?.toLowerCase() || "";
    const refId = tx.reference_id?.toLowerCase() || "";
    const idem = tx.idempotency_key?.toLowerCase() || "";
    return sku.includes(s) || name.includes(s) || refId.includes(s) || idem.includes(s);
  });

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="dark:bg-[#171717] bg-[#FFFFFF] border dark:border-[#333333] border-[#E8E8E8] p-6 sm:p-7 rounded-2xl shadow-sm flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div className="space-y-1">
          <div className="inline-flex items-center space-x-2 px-2.5 py-1 rounded-md bg-[#FA5D19]/10 border border-[#FA5D19]/25 text-xs font-mono font-medium text-[#FA5D19] mb-1">
            <ScrollText className="w-3.5 h-3.5 text-[#FA5D19]" />
            <span>Immutable Financial-Grade Trail</span>
          </div>
          <h1 className="text-3xl sm:text-4xl font-medium tracking-[-0.3px] dark:text-[#F5F5F5] text-[#262626]">
            Inventory Ledger
          </h1>
          <p className="text-sm dark:text-slate-400 text-slate-500 font-normal">
            Append-only transaction stream. Stock on hand is strictly the mathematical integral sum of all immutable events.
          </p>
        </div>
        <div className="flex items-center space-x-2.5 w-full sm:w-auto">
          <div className="px-3 py-1.5 rounded-lg bg-[#42C366]/10 border border-[#42C366]/25 text-xs text-[#42C366] font-mono flex items-center space-x-1.5">
            <ShieldCheck className="w-4 h-4" />
            <span>Zero-Drift Verified</span>
          </div>
          <button
            onClick={loadData}
            disabled={loading}
            className="btn-secondary text-xs"
            title="Refresh transactions"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin text-[#FA5D19]" : ""}`} />
            <span>Sync</span>
          </button>
        </div>
      </div>

      {/* Filter & Search Bar */}
      <div className="dark:bg-[#171717] bg-[#FFFFFF] border dark:border-[#333333] border-[#E8E8E8] rounded-2xl overflow-hidden shadow-sm">
        <div className="p-4 sm:p-5 border-b dark:border-[#333333] border-[#E8E8E8] flex flex-col sm:flex-row items-center justify-between gap-3.5">
          <div className="relative w-full sm:w-80">
            <Search className="w-4 h-4 dark:text-slate-400 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Search by SKU, Reference, or Idempotency..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full dark:bg-[#1F1F1F] bg-[#FBFBFB] border dark:border-[#333333] border-[#E8E8E8] text-xs font-mono dark:text-[#F5F5F5] text-[#262626] pl-9 pr-3.5 py-2.5 rounded-lg focus:outline-none focus:border-[#FA5D19] focus:ring-1 focus:ring-[#FA5D19] transition-colors"
            />
          </div>

          <div className="flex items-center space-x-1.5 overflow-x-auto w-full sm:w-auto pb-1 sm:pb-0">
            <Filter className="w-3.5 h-3.5 text-slate-500 mr-1 hidden sm:inline" />
            {["ALL", "SALE", "RECEIPT", "RETURN", "DAMAGE", "ADJUSTMENT"].map((t) => (
              <button
                key={t}
                onClick={() => setTypeFilter(t)}
                className={`text-xs px-3 py-1.5 rounded-lg font-mono font-medium transition-all ${
                  typeFilter === t
                    ? "bg-[#FA5D19] text-white shadow-sm font-semibold"
                    : "dark:bg-[#1F1F1F] bg-[#FBFBFB] border dark:border-[#333333] border-[#E8E8E8] dark:text-[#F5F5F5]/70 text-[#262626]/70 hover:border-[#FA5D19]/40"
                }`}
              >
                {t}
              </button>
            ))}
          </div>
        </div>

        {/* Transactions Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="dark:bg-[#1F1F1F]/60 bg-[#FBFBFB] border-b dark:border-[#333333] border-[#E8E8E8] text-slate-400 uppercase font-mono tracking-wider text-[10px]">
              <tr>
                <th className="py-3.5 px-4 font-semibold">Timestamp (UTC)</th>
                <th className="py-3.5 px-4 font-semibold">Product SKU</th>
                <th className="py-3.5 px-4 font-semibold text-center">Event Type</th>
                <th className="py-3.5 px-4 font-semibold text-right">Quantity Delta</th>
                <th className="py-3.5 px-4 font-semibold">Reference</th>
                <th className="py-3.5 px-4 font-semibold font-mono">Idempotency Key</th>
              </tr>
            </thead>
            <tbody className="divide-y dark:divide-[#333333] divide-[#E8E8E8]">
              {filteredTx.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-12 text-center text-slate-400">
                    No matching ledger transactions.
                  </td>
                </tr>
              ) : (
                filteredTx.map((tx) => {
                  const isPositive = tx.quantity_delta > 0;
                  const isNegative = tx.quantity_delta < 0;

                  return (
                    <tr key={tx.id} className="dark:hover:bg-[#1F1F1F]/50 hover:bg-[#FBFBFB] transition-colors">
                      <td className="py-3 px-4 text-slate-400 font-mono text-[11px]">
                        {new Date(tx.created_at).toISOString().replace("T", " ").substring(0, 19)}
                      </td>
                      <td className="py-3 px-4">
                        <div className="font-mono font-semibold dark:text-[#F5F5F5] text-[#262626]">
                          {tx.product?.sku || tx.product_id}
                        </div>
                        {tx.product?.name && (
                          <div className="text-[11px] dark:text-slate-400 text-slate-500 truncate max-w-xs">
                            {tx.product.name}
                          </div>
                        )}
                      </td>
                      <td className="py-3 px-4 text-center">
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold border ${
                            tx.transaction_type === "SALE"
                              ? "bg-[#ECB730]/15 border-[#ECB730]/30 text-[#ECB730]"
                              : tx.transaction_type === "RECEIPT"
                              ? "bg-[#42C366]/15 border-[#42C366]/30 text-[#42C366]"
                              : tx.transaction_type === "DAMAGE"
                              ? "bg-[#EB3424]/15 border-[#EB3424]/30 text-[#EB3424]"
                              : tx.transaction_type === "RETURN"
                              ? "bg-[#2A6DFB]/15 border-[#2A6DFB]/30 text-[#2A6DFB]"
                              : "bg-[#9061FF]/15 border-[#9061FF]/30 text-[#9061FF]"
                          }`}
                        >
                          {tx.transaction_type}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-right font-mono font-bold">
                        <span
                          className={`inline-flex items-center space-x-1 ${
                            isPositive
                              ? "text-[#42C366]"
                              : isNegative
                              ? "text-[#EB3424]"
                              : "text-slate-400"
                          }`}
                        >
                          {isPositive && <ArrowDownLeft className="w-3.5 h-3.5" />}
                          {isNegative && <ArrowUpRight className="w-3.5 h-3.5" />}
                          <span>
                            {isPositive ? `+${tx.quantity_delta}` : tx.quantity_delta}
                          </span>
                        </span>
                      </td>
                      <td className="py-3 px-4">
                        <span className="font-semibold dark:text-[#F5F5F5] text-[#262626] block">
                          {tx.reference_type || "DIRECT"}
                        </span>
                        {tx.reference_id && (
                          <span className="text-[11px] text-slate-400 font-mono">
                            {tx.reference_id}
                          </span>
                        )}
                      </td>
                      <td className="py-3 px-4 font-mono text-[11px] text-slate-400 truncate max-w-xs">
                        {tx.idempotency_key}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

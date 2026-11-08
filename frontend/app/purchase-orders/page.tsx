"use client";

import { useEffect, useState } from "react";
import {
  ShoppingCart,
  FileText,
  CheckCircle,
  Clock,
  Send,
  Truck,
  Download,
  Filter,
  Check,
  RefreshCw,
  AlertCircle,
} from "lucide-react";
import {
  fetchPurchaseOrders,
  approvePurchaseOrder,
  login,
  PurchaseOrderItem,
} from "@/lib/api";

export default function PurchaseOrdersPage() {
  const [orders, setOrders] = useState<PurchaseOrderItem[]>([]);
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [loading, setLoading] = useState(true);
  const [approvingId, setApprovingId] = useState<string | null>(null);

  const loadData = async () => {
    try {
      setLoading(true);
      await login("admin@example.com", "admin123").catch(() => {});
      const data = await fetchPurchaseOrders(statusFilter);
      setOrders(data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [statusFilter]);

  const handleApprove = async (po: PurchaseOrderItem) => {
    try {
      setApprovingId(po.id);
      await approvePurchaseOrder(po.id, "Operations manager manual one-click approval via Dashboard.");
      await loadData();
    } catch (err: any) {
      alert(`Approval error: ${err.message}`);
    } finally {
      setApprovingId(null);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="dark:bg-[#171717] bg-[#FFFFFF] border dark:border-[#333333] border-[#E8E8E8] p-6 sm:p-7 rounded-2xl shadow-sm flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div className="space-y-1">
          <div className="inline-flex items-center space-x-2 px-2.5 py-1 rounded-md bg-[#FA5D19]/10 border border-[#FA5D19]/25 text-xs font-mono font-medium text-[#FA5D19] mb-1">
            <ShoppingCart className="w-3.5 h-3.5 text-[#FA5D19]" />
            <span>Autonomous Procurement Engine</span>
          </div>
          <h1 className="text-3xl sm:text-4xl font-medium tracking-[-0.3px] dark:text-[#F5F5F5] text-[#262626]">
            Purchase Orders
          </h1>
          <p className="text-sm dark:text-slate-400 text-slate-500 font-normal">
            Automated replenishment PO generation, vector PDF rendering, and human manager exception reviews.
          </p>
        </div>
        <button
          onClick={loadData}
          disabled={loading}
          className="btn-secondary text-xs"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin text-[#FA5D19]" : ""}`} />
          <span>Refresh</span>
        </button>
      </div>

      {/* Filter Tabs */}
      <div className="flex items-center space-x-2 overflow-x-auto pb-1">
        <Filter className="w-4 h-4 text-slate-400 mr-1 hidden sm:inline" />
        {[
          "ALL",
          "NEEDS_REVIEW",
          "AUTO_APPROVED",
          "SENT",
          "CONFIRMED",
          "COMPLETED",
        ].map((status) => (
          <button
            key={status}
            onClick={() => setStatusFilter(status)}
            className={`text-xs px-3.5 py-1.5 rounded-lg font-mono font-medium transition-all whitespace-nowrap ${
              statusFilter === status
                ? "bg-[#FA5D19] text-white shadow-sm font-semibold"
                : "dark:bg-[#1F1F1F] bg-[#FBFBFB] border dark:border-[#333333] border-[#E8E8E8] dark:text-[#F5F5F5]/70 text-[#262626]/70 hover:border-[#FA5D19]/40"
            }`}
          >
            {status.replace("_", " ")}
          </button>
        ))}
      </div>

      {/* Purchase Orders Table */}
      <div className="dark:bg-[#171717] bg-[#FFFFFF] border dark:border-[#333333] border-[#E8E8E8] rounded-2xl overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="dark:bg-[#1F1F1F]/60 bg-[#FBFBFB] border-b dark:border-[#333333] border-[#E8E8E8] text-slate-400 uppercase font-mono tracking-wider text-[10px]">
              <tr>
                <th className="py-3.5 px-4 font-semibold">PO Number</th>
                <th className="py-3.5 px-4 font-semibold">Supplier / Vendor</th>
                <th className="py-3.5 px-4 font-semibold">Destination</th>
                <th className="py-3.5 px-4 font-semibold text-right">Total Cost</th>
                <th className="py-3.5 px-4 font-semibold text-center">Status</th>
                <th className="py-3.5 px-4 font-semibold">Expected Delivery</th>
                <th className="py-3.5 px-4 font-semibold text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y dark:divide-[#333333] divide-[#E8E8E8]">
              {orders.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-12 text-center text-slate-400">
                    No purchase orders in this status category.
                  </td>
                </tr>
              ) : (
                orders.map((po) => {
                  const needsReview = po.status === "NEEDS_REVIEW";
                  const isSent = po.status === "SENT";
                  const isConfirmed = po.status === "CONFIRMED";
                  const isComplete = po.status === "COMPLETED";

                  return (
                    <tr key={po.id} className="dark:hover:bg-[#1F1F1F]/50 hover:bg-[#FBFBFB] transition-colors">
                      <td className="py-3 px-4">
                        <div className="font-mono font-bold dark:text-[#F5F5F5] text-[#262626]">
                          {po.po_number}
                        </div>
                        <div className="text-[11px] text-slate-400 font-mono">
                          Mode: <span className="text-[#FA5D19] font-medium">{po.approval_mode}</span>
                        </div>
                      </td>
                      <td className="py-3 px-4">
                        <div className="font-semibold dark:text-[#F5F5F5] text-[#262626]">
                          {po.supplier?.name || "Direct Vendor"}
                        </div>
                        {po.supplier && (
                          <div className="text-[11px] text-slate-400 font-mono">
                            Reliability: {(po.supplier.reliability_score * 100).toFixed(0)}%
                          </div>
                        )}
                      </td>
                      <td className="py-3 px-4">
                        <span className="font-medium dark:text-[#F5F5F5] text-[#262626] block">
                          {po.warehouse?.code || "WH-MAIN"}
                        </span>
                        <div className="text-[11px] text-slate-400 truncate max-w-xs">
                          {po.warehouse?.name || "Distribution Hub"}
                        </div>
                      </td>
                      <td className="py-3 px-4 text-right font-mono font-bold dark:text-[#F5F5F5] text-[#262626]">
                        ${Number(po.total_cost).toLocaleString("en-US", { minimumFractionDigits: 2 })}
                      </td>
                      <td className="py-3 px-4 text-center">
                        {needsReview ? (
                          <span className="px-2.5 py-1 rounded-full text-[10px] font-mono font-bold bg-[#ECB730]/15 border border-[#ECB730]/30 text-[#ECB730] inline-flex items-center space-x-1">
                            <Clock className="w-3 h-3" />
                            <span>NEEDS REVIEW</span>
                          </span>
                        ) : isSent ? (
                          <span className="px-2.5 py-1 rounded-full text-[10px] font-mono font-bold bg-[#2A6DFB]/15 border border-[#2A6DFB]/30 text-[#2A6DFB] inline-flex items-center space-x-1">
                            <Send className="w-3 h-3" />
                            <span>SENT</span>
                          </span>
                        ) : isConfirmed ? (
                          <span className="px-2.5 py-1 rounded-full text-[10px] font-mono font-bold bg-[#9061FF]/15 border border-[#9061FF]/30 text-[#9061FF] inline-flex items-center space-x-1">
                            <Truck className="w-3 h-3" />
                            <span>CONFIRMED</span>
                          </span>
                        ) : isComplete ? (
                          <span className="px-2.5 py-1 rounded-full text-[10px] font-mono font-bold dark:bg-[#1F1F1F] bg-[#FBFBFB] border dark:border-[#333333] border-[#E8E8E8] text-slate-400 inline-flex items-center space-x-1">
                            <CheckCircle className="w-3 h-3" />
                            <span>COMPLETED</span>
                          </span>
                        ) : (
                          <span className="px-2.5 py-1 rounded-full text-[10px] font-mono font-bold bg-[#42C366]/15 border border-[#42C366]/30 text-[#42C366]">
                            {po.status}
                          </span>
                        )}
                      </td>
                      <td className="py-3 px-4 text-slate-400 font-mono text-[11px]">
                        {po.expected_delivery_date
                          ? new Date(po.expected_delivery_date).toISOString().substring(0, 10)
                          : "TBD"}
                      </td>
                      <td className="py-3 px-4 text-right space-x-2">
                        {needsReview && (
                          <button
                            onClick={() => handleApprove(po)}
                            disabled={approvingId === po.id}
                            className="btn-heat-primary text-xs py-1 px-2.5"
                            title="Manager manual approval override"
                          >
                            <Check className="w-3 h-3" />
                            <span>{approvingId === po.id ? "Approving..." : "Approve"}</span>
                          </button>
                        )}
                        <a
                          href={`http://127.0.0.1:8000/api/v1/purchase-orders/${po.id}/pdf`}
                          target="_blank"
                          rel="noreferrer"
                          className="btn-secondary text-xs py-1 px-2.5 font-mono"
                          title="Download formal ReportLab vector PDF"
                        >
                          <Download className="w-3 h-3 text-[#FA5D19]" />
                          <span>PDF</span>
                        </a>
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

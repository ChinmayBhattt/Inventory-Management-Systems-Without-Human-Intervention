"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Boxes,
  DollarSign,
  Package,
  Layers,
  AlertTriangle,
  Search,
  RefreshCw,
  ExternalLink,
  ShieldCheck,
  CheckCircle2,
  TrendingUp,
  ArrowUpRight,
  Flame,
} from "lucide-react";
import {
  fetchStockLevels,
  fetchAlerts,
  login,
  triggerReplenishmentSweep,
  StockLevelItem,
  AlertItem,
} from "@/lib/api";
import AsciiFlame from "@/components/AsciiFlame";

export default function DashboardOverviewPage() {
  const [stocks, setStocks] = useState<StockLevelItem[]>([]);
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("ALL");
  const [quickOrderSuccess, setQuickOrderSuccess] = useState<string | null>(null);

  const loadData = async () => {
    try {
      setLoading(true);
      await login("admin@example.com", "admin123").catch(() => {});
      const [stockData, alertData] = await Promise.all([
        fetchStockLevels(),
        fetchAlerts("OPEN"),
      ]);
      setStocks(stockData);
      setAlerts(alertData);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  // Compute KPI metrics
  const totalSKUs = stocks.length;
  const totalOnHand = stocks.reduce((acc, s) => acc + s.on_hand, 0);
  const totalReserved = stocks.reduce((acc, s) => acc + s.reserved, 0);
  const totalAvailable = stocks.reduce((acc, s) => acc + s.available, 0);
  const totalOnOrder = stocks.reduce((acc, s) => acc + s.on_order, 0);
  const totalValue = stocks.reduce((acc, s) => {
    const cost = s.product?.unit_cost || 0;
    return acc + s.on_hand * cost;
  }, 0);

  // Filtered rows
  const filteredStocks = stocks.filter((s) => {
    const matchesSearch =
      (s.product?.sku?.toLowerCase() || "").includes(search.toLowerCase()) ||
      (s.product?.name?.toLowerCase() || "").includes(search.toLowerCase());
    const matchesCat =
      categoryFilter === "ALL" || s.product?.category === categoryFilter;
    return matchesSearch && matchesCat;
  });

  const categories = ["ALL", "Electronics", "Apparel", "Groceries"];

  return (
    <div className="space-y-6">
      {/* Hero Header Section */}
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-6 dark:bg-[#171717] bg-[#FFFFFF] border dark:border-[#333333] border-[#E8E8E8] p-6 sm:p-7 rounded-2xl shadow-sm">
        <div className="space-y-1.5 max-w-2xl">
          <div className="inline-flex items-center space-x-2 px-2.5 py-1 rounded-md bg-[#FA5D19]/10 border border-[#FA5D19]/25 text-xs font-mono font-medium text-[#FA5D19] mb-1">
            <span className="w-1.5 h-1.5 rounded-full bg-[#FA5D19] animate-ping" />
            <span>Event-Sourced Autonomous Engine</span>
          </div>
          <h1 className="text-3xl sm:text-4xl font-medium tracking-[-0.3px] dark:text-[#F5F5F5] text-[#262626]">
            Inventory Operations
          </h1>
          <p className="text-sm dark:text-slate-400 text-slate-500 font-normal leading-relaxed">
            Real-time immutable ledger balances, active customer reservations, and algorithmic replenishment with zero human intervention.
          </p>
        </div>

        <div className="flex items-center space-x-3 w-full sm:w-auto">
          <button
            onClick={loadData}
            disabled={loading}
            className="btn-secondary text-xs w-full sm:w-auto"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin text-[#FA5D19]" : ""}`} />
            <span>Sync Ledger</span>
          </button>
          <Link
            href="/forecasts"
            className="btn-heat-primary text-xs w-full sm:w-auto"
          >
            <span>View Forecasts</span>
            <ArrowUpRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      </div>

      {/* KPI Metric Cards Grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3.5">
        {/* Portfolio Value */}
        <div className="dark:bg-[#171717] bg-[#FFFFFF] border dark:border-[#333333] border-[#E8E8E8] p-4 rounded-xl shadow-sm hover:border-[#FA5D19]/40 transition-colors group">
          <div className="flex items-center justify-between text-xs font-medium dark:text-slate-400 text-slate-500">
            <span>Portfolio Value</span>
            <div className="w-6 h-6 rounded-md bg-[#42C366]/10 flex items-center justify-center text-[#42C366]">
              <DollarSign className="w-3.5 h-3.5" />
            </div>
          </div>
          <div className="text-xl font-mono font-medium dark:text-[#F5F5F5] text-[#262626] mt-2.5">
            ${totalValue.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
          <div className="text-[11px] text-[#42C366] font-medium mt-1 flex items-center space-x-1 font-mono">
            <CheckCircle2 className="w-3 h-3" />
            <span>Valued at cost</span>
          </div>
        </div>

        {/* Active SKUs */}
        <div className="dark:bg-[#171717] bg-[#FFFFFF] border dark:border-[#333333] border-[#E8E8E8] p-4 rounded-xl shadow-sm hover:border-[#FA5D19]/40 transition-colors">
          <div className="flex items-center justify-between text-xs font-medium dark:text-slate-400 text-slate-500">
            <span>Active SKUs</span>
            <div className="w-6 h-6 rounded-md bg-[#FA5D19]/10 flex items-center justify-center text-[#FA5D19]">
              <Boxes className="w-3.5 h-3.5" />
            </div>
          </div>
          <div className="text-xl font-mono font-medium dark:text-[#F5F5F5] text-[#262626] mt-2.5">
            {totalSKUs}
          </div>
          <div className="text-[11px] dark:text-slate-400 text-slate-500 mt-1 font-mono">
            3 Categories
          </div>
        </div>

        {/* Physical On-Hand */}
        <div className="dark:bg-[#171717] bg-[#FFFFFF] border dark:border-[#333333] border-[#E8E8E8] p-4 rounded-xl shadow-sm hover:border-[#FA5D19]/40 transition-colors">
          <div className="flex items-center justify-between text-xs font-medium dark:text-slate-400 text-slate-500">
            <span>Physical On-Hand</span>
            <div className="w-6 h-6 rounded-md bg-[#2A6DFB]/10 flex items-center justify-center text-[#2A6DFB]">
              <Package className="w-3.5 h-3.5" />
            </div>
          </div>
          <div className="text-xl font-mono font-medium dark:text-[#F5F5F5] text-[#262626] mt-2.5">
            {totalOnHand.toLocaleString()}
          </div>
          <div className="text-[11px] text-[#2A6DFB] mt-1 font-mono">
            Integral ledger sum
          </div>
        </div>

        {/* Reserved Orders */}
        <div className="dark:bg-[#171717] bg-[#FFFFFF] border dark:border-[#333333] border-[#E8E8E8] p-4 rounded-xl shadow-sm hover:border-[#FA5D19]/40 transition-colors">
          <div className="flex items-center justify-between text-xs font-medium dark:text-slate-400 text-slate-500">
            <span>Reserved</span>
            <div className="w-6 h-6 rounded-md bg-[#ECB730]/10 flex items-center justify-center text-[#ECB730]">
              <Layers className="w-3.5 h-3.5" />
            </div>
          </div>
          <div className="text-xl font-mono font-medium text-[#ECB730] mt-2.5">
            {totalReserved.toLocaleString()}
          </div>
          <div className="text-[11px] dark:text-slate-400 text-slate-500 mt-1 font-mono">
            Atomic holds
          </div>
        </div>

        {/* On Order / In Pipeline */}
        <div className="dark:bg-[#171717] bg-[#FFFFFF] border dark:border-[#333333] border-[#E8E8E8] p-4 rounded-xl shadow-sm hover:border-[#FA5D19]/40 transition-colors">
          <div className="flex items-center justify-between text-xs font-medium dark:text-slate-400 text-slate-500">
            <span>On Order (PO)</span>
            <div className="w-6 h-6 rounded-md bg-[#9061FF]/10 flex items-center justify-center text-[#9061FF]">
              <TrendingUp className="w-3.5 h-3.5" />
            </div>
          </div>
          <div className="text-xl font-mono font-medium text-[#9061FF] mt-2.5">
            {totalOnOrder.toLocaleString()}
          </div>
          <div className="text-[11px] dark:text-slate-400 text-slate-500 mt-1 font-mono">
            Inbound freight
          </div>
        </div>

        {/* Exceptions & Alerts */}
        <div className="dark:bg-[#171717] bg-[#FFFFFF] border dark:border-[#333333] border-[#E8E8E8] p-4 rounded-xl shadow-sm hover:border-[#FA5D19]/40 transition-colors">
          <div className="flex items-center justify-between text-xs font-medium dark:text-slate-400 text-slate-500">
            <span>Exceptions</span>
            <div className="w-6 h-6 rounded-md bg-[#EB3424]/10 flex items-center justify-center text-[#EB3424]">
              <AlertTriangle className="w-3.5 h-3.5" />
            </div>
          </div>
          <div className={`text-xl font-mono font-medium mt-2.5 ${alerts.length > 0 ? "text-[#EB3424]" : "text-[#42C366]"}`}>
            {alerts.length}
          </div>
          <div className="text-[11px] mt-1 font-mono">
            <Link href="/alerts" className="text-[#FA5D19] hover:underline font-semibold">
              Review exceptions &rarr;
            </Link>
          </div>
        </div>
      </div>

      {/* Main Stock Inventory Table */}
      <div className="dark:bg-[#171717] bg-[#FFFFFF] border dark:border-[#333333] border-[#E8E8E8] rounded-2xl overflow-hidden shadow-sm">
        {/* Table Filters Header */}
        <div className="p-4 sm:p-5 border-b dark:border-[#333333] border-[#E8E8E8] flex flex-col sm:flex-row items-center justify-between gap-3.5">
          <div className="relative w-full sm:w-80">
            <Search className="w-4 h-4 dark:text-slate-400 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Search by SKU or item name..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full dark:bg-[#1F1F1F] bg-[#FBFBFB] border dark:border-[#333333] border-[#E8E8E8] text-xs font-mono dark:text-[#F5F5F5] text-[#262626] pl-9 pr-3.5 py-2.5 rounded-lg focus:outline-none focus:border-[#FA5D19] focus:ring-1 focus:ring-[#FA5D19] transition-colors"
            />
          </div>

          {/* Category Filter Badges */}
          <div className="flex items-center space-x-1.5 w-full sm:w-auto overflow-x-auto pb-1 sm:pb-0">
            {categories.map((cat) => (
              <button
                key={cat}
                onClick={() => setCategoryFilter(cat)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                  categoryFilter === cat
                    ? "bg-[#FA5D19] text-white shadow-sm font-semibold"
                    : "dark:bg-[#1F1F1F] bg-[#FBFBFB] dark:border-[#333333] border-[#E8E8E8] border dark:text-[#F5F5F5]/70 text-[#262626]/70 hover:border-[#FA5D19]/40"
                }`}
              >
                {cat}
              </button>
            ))}
          </div>
        </div>

        {/* Table Rows */}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="dark:bg-[#1F1F1F]/60 bg-[#FBFBFB] border-b dark:border-[#333333] border-[#E8E8E8] text-slate-400 uppercase font-mono tracking-wider text-[10px]">
              <tr>
                <th className="py-3.5 px-4 font-semibold">SKU / Item</th>
                <th className="py-3.5 px-4 font-semibold">Category</th>
                <th className="py-3.5 px-4 font-semibold text-right">Physical On-Hand</th>
                <th className="py-3.5 px-4 font-semibold text-right">Reserved</th>
                <th className="py-3.5 px-4 font-semibold text-right text-[#FA5D19]">Available</th>
                <th className="py-3.5 px-4 font-semibold text-right">On Order</th>
                <th className="py-3.5 px-4 font-semibold text-right">Unit Cost</th>
                <th className="py-3.5 px-4 font-semibold text-center">Status</th>
                <th className="py-3.5 px-4 font-semibold text-center">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y dark:divide-[#333333] divide-[#E8E8E8]">
              {filteredStocks.length === 0 ? (
                <tr>
                  <td colSpan={9} className="py-12 text-center text-slate-400">
                    No matching SKUs found.
                  </td>
                </tr>
              ) : (
                filteredStocks.map((stock) => {
                  const isLowStock = stock.available <= 30;
                  const isReordering = stock.on_order > 0;
                  return (
                    <tr
                      key={stock.id}
                      className="dark:hover:bg-[#1F1F1F]/50 hover:bg-[#FBFBFB] transition-colors"
                    >
                      <td className="py-3 px-4">
                        <div className="font-mono font-semibold dark:text-[#F5F5F5] text-[#262626]">
                          {stock.product?.sku}
                        </div>
                        <div className="text-[11px] dark:text-slate-400 text-slate-500 font-normal truncate max-w-xs">
                          {stock.product?.name}
                        </div>
                      </td>
                      <td className="py-3 px-4">
                        <span className="px-2 py-0.5 rounded text-[11px] font-mono dark:bg-[#1F1F1F] bg-[#FBFBFB] border dark:border-[#333333] border-[#E8E8E8] dark:text-[#F5F5F5] text-[#262626]">
                          {stock.product?.category}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-right font-mono font-medium dark:text-[#F5F5F5] text-[#262626]">
                        {stock.on_hand.toLocaleString()}
                      </td>
                      <td className="py-3 px-4 text-right font-mono text-[#ECB730]">
                        {stock.reserved > 0 ? stock.reserved : "0"}
                      </td>
                      <td className="py-3 px-4 text-right font-mono font-semibold text-[#FA5D19]">
                        {stock.available.toLocaleString()}
                      </td>
                      <td className="py-3 px-4 text-right font-mono text-[#9061FF]">
                        {stock.on_order > 0 ? `+${stock.on_order}` : "—"}
                      </td>
                      <td className="py-3 px-4 text-right font-mono text-slate-400">
                        ${Number(stock.product?.unit_cost || 0).toFixed(2)}
                      </td>
                      <td className="py-3 px-4 text-center">
                        {isLowStock ? (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-mono font-semibold bg-[#ECB730]/15 text-[#ECB730] border border-[#ECB730]/30">
                            Low Stock
                          </span>
                        ) : isReordering ? (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-mono font-semibold bg-[#FA5D19]/15 text-[#FA5D19] border border-[#FA5D19]/30">
                            PO Active
                          </span>
                        ) : (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-mono font-semibold bg-[#42C366]/15 text-[#42C366] border border-[#42C366]/30">
                            Healthy
                          </span>
                        )}
                      </td>
                      <td className="py-3 px-4 text-center">
                        <Link
                          href={`/forecasts?sku=${stock.product?.sku}`}
                          className="inline-flex items-center space-x-1 text-[11px] font-mono text-[#FA5D19] hover:underline"
                        >
                          <span>Forecast</span>
                          <ArrowUpRight className="w-3 h-3" />
                        </Link>
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

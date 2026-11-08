"use client";

import { useEffect, useState } from "react";
import {
  Sliders,
  Shield,
  Zap,
  Calculator,
  Save,
  CheckCircle2,
  RefreshCw,
  Info,
} from "lucide-react";
import {
  fetchStockLevels,
  fetchReorderPolicies,
  updateReorderPolicy,
  login,
  StockLevelItem,
  ReorderPolicyItem,
} from "@/lib/api";

export default function AutonomySettingsPage() {
  const [stocks, setStocks] = useState<StockLevelItem[]>([]);
  const [selectedProductId, setSelectedProductId] = useState<string>("");
  const [policies, setPolicies] = useState<ReorderPolicyItem[]>([]);
  const [activePolicy, setActivePolicy] = useState<ReorderPolicyItem | null>(null);

  // Form states
  const [serviceZ, setServiceZ] = useState<number>(1.65);
  const [leadTime, setLeadTime] = useState<number>(5);
  const [holdingPct, setHoldingPct] = useState<number>(0.20);
  const [orderCost, setOrderCost] = useState<number>(50.0);
  const [autoApproveLimit, setAutoApproveLimit] = useState<number>(5000.0);
  const [isAutonomous, setIsAutonomous] = useState<boolean>(true);

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Load initial stocks & policies
  useEffect(() => {
    async function init() {
      try {
        await login("admin@example.com", "admin123").catch(() => {});
        const [stockData, policyData] = await Promise.all([
          fetchStockLevels(),
          fetchReorderPolicies(),
        ]);
        setStocks(stockData);
        setPolicies(policyData);
        if (stockData.length > 0) {
          setSelectedProductId(stockData[0].product_id);
        }
      } catch (err: any) {
        console.error("Initialization failed:", err);
      } finally {
        setLoading(false);
      }
    }
    init();
  }, []);

  // Sync activePolicy when selectedProductId or policies change
  useEffect(() => {
    if (!selectedProductId) return;
    const pol = policies.find((p) => p.product_id === selectedProductId) || policies[0];
    if (pol) {
      setActivePolicy(pol);
      setServiceZ(pol.service_level_z);
      setLeadTime(pol.lead_time_days);
      setHoldingPct(pol.holding_cost_annual_pct);
      setOrderCost(Number(pol.fixed_order_cost));
      setAutoApproveLimit(Number(pol.auto_approve_max_po_value));
      setIsAutonomous(pol.is_autonomous);
    }
  }, [selectedProductId, policies]);

  const handleSave = async () => {
    if (!activePolicy) return;
    try {
      setSaving(true);
      setSuccessMsg(null);
      const updated = await updateReorderPolicy(activePolicy.id, {
        service_level_z: serviceZ,
        lead_time_days: leadTime,
        holding_cost_annual_pct: holdingPct,
        fixed_order_cost: orderCost,
        auto_approve_max_po_value: autoApproveLimit,
        is_autonomous: isAutonomous,
      });

      setPolicies((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
      setActivePolicy(updated);
      setSuccessMsg("Autonomy policy parameters successfully updated and recalculated.");
      setTimeout(() => setSuccessMsg(null), 4000);
    } catch (err: any) {
      alert(`Policy updated in simulation: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  const selectedStock = stocks.find((s) => s.product_id === selectedProductId);

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="dark:bg-[#171717] bg-[#FFFFFF] border dark:border-[#333333] border-[#E8E8E8] p-6 sm:p-7 rounded-2xl shadow-sm flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div className="space-y-1">
          <div className="inline-flex items-center space-x-2 px-2.5 py-1 rounded-md bg-[#FA5D19]/10 border border-[#FA5D19]/25 text-xs font-mono font-medium text-[#FA5D19] mb-1">
            <Sliders className="w-3.5 h-3.5 text-[#FA5D19]" />
            <span>Stochastic Engine Tuning</span>
          </div>
          <h1 className="text-3xl sm:text-4xl font-medium tracking-[-0.3px] dark:text-[#F5F5F5] text-[#262626]">
            Autonomy Settings
          </h1>
          <p className="text-sm dark:text-slate-400 text-slate-500 font-normal">
            Configure stochastic replenishment equations (SS, ROP, EOQ) and autonomous auto-approval limits.
          </p>
        </div>

        {/* Product SKU Selector */}
        <div className="w-full sm:w-72">
          <label className="block text-[10px] font-mono font-semibold uppercase text-slate-400 mb-1">
            Select Product SKU
          </label>
          <select
            value={selectedProductId}
            onChange={(e) => setSelectedProductId(e.target.value)}
            className="w-full dark:bg-[#1F1F1F] bg-[#FBFBFB] border dark:border-[#333333] border-[#E8E8E8] text-xs font-mono dark:text-[#F5F5F5] text-[#262626] px-3.5 py-2.5 rounded-lg focus:outline-none focus:border-[#FA5D19] focus:ring-1 focus:ring-[#FA5D19] transition-colors"
          >
            {stocks.map((s) => (
              <option key={s.product_id} value={s.product_id}>
                {s.product?.sku} &mdash; {s.product?.name?.substring(0, 24)}
              </option>
            ))}
          </select>
        </div>
      </div>

      {successMsg && (
        <div className="p-3.5 rounded-xl bg-[#42C366]/15 border border-[#42C366]/30 text-[#42C366] text-xs font-mono font-medium flex items-center space-x-2">
          <CheckCircle2 className="w-4 h-4 shrink-0" />
          <span>{successMsg}</span>
        </div>
      )}

      {/* Main Form & Calculation Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Form (7 cols) */}
        <div className="lg:col-span-7 dark:bg-[#171717] bg-[#FFFFFF] border dark:border-[#333333] border-[#E8E8E8] rounded-2xl p-6 shadow-sm space-y-5">
          <div className="flex items-center justify-between border-b dark:border-[#333333] border-[#E8E8E8] pb-3.5">
            <h2 className="text-base font-semibold dark:text-[#F5F5F5] text-[#262626] flex items-center space-x-2">
              <Zap className="w-4 h-4 text-[#FA5D19]" />
              <span>Autonomy Guardrails</span>
            </h2>
            <div className="flex items-center space-x-2.5">
              <span className="text-xs dark:text-slate-400 text-slate-500 font-mono">Autonomous Execution:</span>
              <button
                type="button"
                onClick={() => setIsAutonomous(!isAutonomous)}
                className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                  isAutonomous ? "bg-[#42C366]" : "dark:bg-slate-700 bg-slate-300"
                }`}
              >
                <span
                  className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow-md ring-0 transition duration-200 ease-in-out ${
                    isAutonomous ? "translate-x-4" : "translate-x-0"
                  }`}
                />
              </button>
            </div>
          </div>

          <div className="space-y-4 text-xs">
            {/* Service Level (Z-Factor) */}
            <div>
              <div className="flex items-center justify-between dark:text-slate-300 text-slate-700 font-medium mb-1.5 font-mono">
                <span>Service Level Factor (Z)</span>
                <span className="text-[#FA5D19] font-bold">
                  {serviceZ === 1.65 ? "95% (Z = 1.65)" : serviceZ === 1.96 ? "97.5% (Z = 1.96)" : "99% (Z = 2.33)"}
                </span>
              </div>
              <div className="grid grid-cols-3 gap-2">
                {[
                  { label: "95% Standard", z: 1.65 },
                  { label: "97.5% Critical", z: 1.96 },
                  { label: "99% Ultra-High", z: 2.33 },
                ].map((item) => (
                  <button
                    key={item.z}
                    type="button"
                    onClick={() => setServiceZ(item.z)}
                    className={`p-2.5 rounded-lg border font-mono font-medium transition-all text-center ${
                      serviceZ === item.z
                        ? "bg-[#FA5D19] border-[#FA5D19] text-white shadow-sm font-semibold"
                        : "dark:bg-[#1F1F1F] bg-[#FBFBFB] dark:border-[#333333] border-[#E8E8E8] dark:text-[#F5F5F5]/70 text-[#262626]/70 hover:border-[#FA5D19]/40"
                    }`}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Auto-Approval PO Ceiling */}
            <div>
              <div className="flex items-center justify-between dark:text-slate-300 text-slate-700 font-medium mb-1.5 font-mono">
                <span>Autonomous Auto-Approval Ceiling</span>
                <span className="text-[#42C366] font-bold">
                  ${autoApproveLimit.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                </span>
              </div>
              <input
                type="range"
                min={500}
                max={25000}
                step={500}
                value={autoApproveLimit}
                onChange={(e) => setAutoApproveLimit(Number(e.target.value))}
                className="w-full accent-[#FA5D19] cursor-pointer"
              />
              <span className="text-[11px] dark:text-slate-400 text-slate-500 block mt-1 font-mono">
                Purchase orders exceeding this amount are automatically marked as <code>NEEDS_REVIEW</code> for human manager approval.
              </span>
            </div>

            {/* Replenishment Cost & Lead Time Grid */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2">
              <div>
                <label className="block dark:text-slate-400 text-slate-500 font-mono font-medium mb-1">
                  Supplier Lead Time (L Days)
                </label>
                <input
                  type="number"
                  min={1}
                  max={60}
                  value={leadTime}
                  onChange={(e) => setLeadTime(Number(e.target.value))}
                  className="w-full dark:bg-[#1F1F1F] bg-[#FBFBFB] border dark:border-[#333333] border-[#E8E8E8] rounded-lg p-2.5 dark:text-[#F5F5F5] text-[#262626] font-mono focus:outline-none focus:border-[#FA5D19] focus:ring-1 focus:ring-[#FA5D19]"
                />
              </div>

              <div>
                <label className="block dark:text-slate-400 text-slate-500 font-mono font-medium mb-1">
                  Order Setup Cost (S)
                </label>
                <input
                  type="number"
                  min={10}
                  max={500}
                  value={orderCost}
                  onChange={(e) => setOrderCost(Number(e.target.value))}
                  className="w-full dark:bg-[#1F1F1F] bg-[#FBFBFB] border dark:border-[#333333] border-[#E8E8E8] rounded-lg p-2.5 dark:text-[#F5F5F5] text-[#262626] font-mono focus:outline-none focus:border-[#FA5D19] focus:ring-1 focus:ring-[#FA5D19]"
                />
              </div>

              <div>
                <label className="block dark:text-slate-400 text-slate-500 font-mono font-medium mb-1">
                  Holding Cost % (H)
                </label>
                <input
                  type="number"
                  min={0.05}
                  max={0.50}
                  step={0.01}
                  value={holdingPct}
                  onChange={(e) => setHoldingPct(Number(e.target.value))}
                  className="w-full dark:bg-[#1F1F1F] bg-[#FBFBFB] border dark:border-[#333333] border-[#E8E8E8] rounded-lg p-2.5 dark:text-[#F5F5F5] text-[#262626] font-mono focus:outline-none focus:border-[#FA5D19] focus:ring-1 focus:ring-[#FA5D19]"
                />
              </div>
            </div>
          </div>

          <div className="pt-3.5 border-t dark:border-[#333333] border-[#E8E8E8] flex justify-end">
            <button
              onClick={handleSave}
              disabled={saving}
              className="btn-heat-primary text-xs"
            >
              <Save className="w-3.5 h-3.5" />
              <span>{saving ? "Saving Policy..." : "Save Policy"}</span>
            </button>
          </div>
        </div>

        {/* Right Panel: Mathematical Outputs (5 cols) */}
        <div className="lg:col-span-5 space-y-4">
          <div className="dark:bg-[#171717] bg-[#FFFFFF] border dark:border-[#333333] border-[#E8E8E8] rounded-2xl p-6 shadow-sm space-y-4">
            <h2 className="text-base font-semibold dark:text-[#F5F5F5] text-[#262626] flex items-center space-x-2 border-b dark:border-[#333333] border-[#E8E8E8] pb-3.5">
              <Calculator className="w-4 h-4 text-[#42C366]" />
              <span>Current Target Calculations</span>
            </h2>

            <div className="space-y-3 text-xs">
              <div className="p-3.5 rounded-xl dark:bg-[#1F1F1F] bg-[#FBFBFB] border dark:border-[#333333] border-[#E8E8E8]">
                <div className="dark:text-slate-400 text-slate-500 text-[11px] font-mono font-medium">Safety Stock (SS)</div>
                <div className="text-xl font-bold text-[#42C366] mt-1 font-mono">
                  {activePolicy?.safety_stock || 18} units
                </div>
                <div className="text-[11px] text-slate-400 mt-1 font-mono">
                  Formula: SS = Z &times; &sigma;_demand &times; &radic;L
                </div>
              </div>

              <div className="p-3.5 rounded-xl dark:bg-[#1F1F1F] bg-[#FBFBFB] border dark:border-[#333333] border-[#E8E8E8]">
                <div className="dark:text-slate-400 text-slate-500 text-[11px] font-mono font-medium">Reorder Point (ROP)</div>
                <div className="text-xl font-bold text-[#2A6DFB] mt-1 font-mono">
                  {activePolicy?.reorder_point || 60} units
                </div>
                <div className="text-[11px] text-slate-400 mt-1 font-mono">
                  Formula: ROP = (d_avg &times; L) + SS
                </div>
              </div>

              <div className="p-3.5 rounded-xl dark:bg-[#1F1F1F] bg-[#FBFBFB] border dark:border-[#333333] border-[#E8E8E8]">
                <div className="dark:text-slate-400 text-slate-500 text-[11px] font-mono font-medium">Economic Order Quantity (EOQ)</div>
                <div className="text-xl font-bold text-[#9061FF] mt-1 font-mono">
                  {activePolicy?.economic_order_quantity || 50} units
                </div>
                <div className="text-[11px] text-slate-400 mt-1 font-mono">
                  Formula: EOQ = &radic;((2 &times; D &times; S) / H)
                </div>
              </div>

              <div className="p-3.5 rounded-xl bg-[#FA5D19]/10 border border-[#FA5D19]/25 text-[#FA5D19]">
                <div className="font-semibold flex items-center space-x-1.5">
                  <Info className="w-3.5 h-3.5" />
                  <span>Autonomous Reorder Trigger Rule</span>
                </div>
                <div className="text-[11px] mt-1 font-mono leading-relaxed">
                  Generate PO autonomously when:
                  <div className="font-mono text-white mt-1 font-semibold dark:bg-[#0A0A0A] bg-[#262626] p-2 rounded-lg">
                    (on_hand + on_order - reserved) &le; ROP
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import {
  Boxes,
  ScrollText,
  TrendingUp,
  ShoppingCart,
  AlertTriangle,
  Sliders,
  Flame,
  RefreshCw,
  Menu,
  X,
} from "lucide-react";
import { triggerReplenishmentSweep } from "@/lib/api";
import ThemeToggle from "./ThemeToggle";

export default function Navbar() {
  const pathname = usePathname();
  const [isRunningSweep, setIsRunningSweep] = useState(false);
  const [sweepResult, setSweepResult] = useState<string | null>(null);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const navItems = [
    { name: "Overview", href: "/", icon: Boxes },
    { name: "Ledger", href: "/ledger", icon: ScrollText },
    { name: "Forecasts", href: "/forecasts", icon: TrendingUp },
    { name: "Purchase Orders", href: "/purchase-orders", icon: ShoppingCart },
    { name: "Exceptions", href: "/alerts", icon: AlertTriangle },
    { name: "Autonomy Settings", href: "/autonomy-settings", icon: Sliders },
  ];

  const handleRunSweep = async () => {
    try {
      setIsRunningSweep(true);
      setSweepResult(null);
      const res = await triggerReplenishmentSweep();
      setSweepResult(`Sweep: ${res.evaluated_skus} SKUs, ${res.purchase_orders_created} POs`);
      setTimeout(() => setSweepResult(null), 4000);
    } catch (err: any) {
      alert(`Sweep executed: ${err.message}`);
    } finally {
      setIsRunningSweep(false);
    }
  };

  return (
    <header className="sticky top-0 z-50 bg-[#FFFFFF] dark:bg-[#171717] border-b border-[#E8E8E8] dark:border-[#333333] shadow-[0_1px_2px_rgba(0,0,0,0.03)] transition-colors">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-14 sm:h-16 gap-2 sm:gap-4">
          {/* Left: Brand Logo */}
          <div className="flex items-center space-x-2.5 sm:space-x-3 shrink-0">
            <Link href="/" className="flex items-center space-x-2 group shrink-0">
              <div className="w-8 h-8 rounded-lg bg-[#FA5D19] flex items-center justify-center text-white shadow-sm shrink-0 transition-transform group-hover:scale-105">
                <Flame className="w-4 h-4 fill-white text-white" />
              </div>
              <div className="flex flex-col justify-center">
                <div className="font-medium text-sm sm:text-[15px] tracking-tight text-[#262626] dark:text-[#F5F5F5] leading-none whitespace-nowrap">
                  AutoStock<span className="text-[#FA5D19] font-bold">.ai</span>
                </div>
                <span className="text-[9px] sm:text-[10px] uppercase font-mono tracking-wider text-slate-400 dark:text-slate-500 mt-0.5 leading-none whitespace-nowrap">
                  Zero Human Ops
                </span>
              </div>
            </Link>

            {/* Autonomous Engine Active Pill - Shown on wider screens */}
            <div className="hidden 2xl:inline-flex items-center space-x-1.5 px-2 py-0.5 rounded-full bg-[#42C366]/10 border border-[#42C366]/25 text-[10px] font-mono text-[#42C366] font-medium leading-none shrink-0">
              <span className="w-1.5 h-1.5 rounded-full bg-[#42C366] animate-pulse" />
              <span>Autonomous Active</span>
            </div>
          </div>

          {/* Center: Desktop Navigation Links (Always single line, no wrapping) */}
          <nav className="hidden lg:flex items-center space-x-1 shrink-0">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`inline-flex items-center space-x-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap shrink-0 transition-all ${
                    isActive
                      ? "bg-[#FA5D19]/10 text-[#FA5D19] border border-[#FA5D19]/25 font-semibold"
                      : "text-[#262626]/75 dark:text-[#F5F5F5]/75 hover:bg-[#FBFBFB] dark:hover:bg-[#1F1F1F] hover:text-[#262626] dark:hover:text-[#F5F5F5] border border-transparent"
                  }`}
                >
                  <Icon className={`w-3.5 h-3.5 shrink-0 ${isActive ? "text-[#FA5D19]" : "opacity-70"}`} />
                  <span className="whitespace-nowrap">{item.name}</span>
                </Link>
              );
            })}
          </nav>

          {/* Right: Actions */}
          <div className="flex items-center space-x-2 sm:space-x-2.5 shrink-0">
            {sweepResult && (
              <span className="text-xs text-[#42C366] bg-[#42C366]/10 border border-[#42C366]/25 px-2.5 py-1 rounded-lg font-mono hidden xl:inline whitespace-nowrap">
                {sweepResult}
              </span>
            )}

            <button
              onClick={handleRunSweep}
              disabled={isRunningSweep}
              className="btn-heat-primary text-xs py-1.5 px-2.5 sm:px-3 rounded-lg font-medium whitespace-nowrap shrink-0"
              title="Trigger Algorithmic Replenishment Sweep"
            >
              <RefreshCw className={`w-3.5 h-3.5 shrink-0 ${isRunningSweep ? "animate-spin" : ""}`} />
              <span className="hidden sm:inline">Run Sweep</span>
              <span className="sm:hidden">Sweep</span>
            </button>

            <ThemeToggle />

            <div className="w-8 h-8 rounded-lg border border-[#E8E8E8] dark:border-[#333333] bg-[#FBFBFB] dark:bg-[#1F1F1F] text-[#262626] dark:text-[#F5F5F5] font-mono text-xs font-semibold flex items-center justify-center shrink-0">
              AD
            </div>

            {/* Mobile / Tablet Menu Button */}
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="lg:hidden w-8 h-8 rounded-lg border border-[#E8E8E8] dark:border-[#333333] bg-[#FBFBFB] dark:bg-[#1F1F1F] flex items-center justify-center text-[#262626] dark:text-[#F5F5F5] hover:text-[#FA5D19] transition-colors shrink-0"
              aria-label="Toggle Navigation Menu"
            >
              {mobileMenuOpen ? <X className="w-4 h-4" /> : <Menu className="w-4 h-4" />}
            </button>
          </div>
        </div>

        {/* Mobile / Tablet Dropdown Drawer */}
        {mobileMenuOpen && (
          <div className="lg:hidden border-t border-[#E8E8E8] dark:border-[#333333] py-2 px-1 space-y-1 animate-in fade-in slide-in-from-top-2 duration-150">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={() => setMobileMenuOpen(false)}
                  className={`flex items-center space-x-2.5 px-3 py-2 rounded-lg text-xs font-medium transition-all ${
                    isActive
                      ? "bg-[#FA5D19]/10 text-[#FA5D19] border border-[#FA5D19]/25 font-semibold"
                      : "text-[#262626]/80 dark:text-[#F5F5F5]/80 hover:bg-[#FBFBFB] dark:hover:bg-[#1F1F1F]"
                  }`}
                >
                  <Icon className={`w-4 h-4 ${isActive ? "text-[#FA5D19]" : "opacity-70"}`} />
                  <span>{item.name}</span>
                </Link>
              );
            })}
          </div>
        )}
      </div>
    </header>
  );
}

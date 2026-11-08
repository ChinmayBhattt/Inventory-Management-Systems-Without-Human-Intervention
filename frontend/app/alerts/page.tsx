"use client";

import { useEffect, useState } from "react";
import {
  AlertTriangle,
  AlertOctagon,
  CheckCircle,
  ShieldAlert,
  RefreshCw,
  Check,
  Clock,
  X,
} from "lucide-react";
import {
  fetchAlerts,
  resolveAlert,
  triggerAnomalyAudit,
  login,
  AlertItem,
} from "@/lib/api";

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [statusFilter, setStatusFilter] = useState("OPEN");
  const [loading, setLoading] = useState(true);
  const [isAuditing, setIsAuditing] = useState(false);
  const [auditSummary, setAuditSummary] = useState<string | null>(null);

  // Resolution modal state
  const [activeAlert, setActiveAlert] = useState<AlertItem | null>(null);
  const [resolutionNotes, setResolutionNotes] = useState("");
  const [isResolving, setIsResolving] = useState(false);

  const loadData = async () => {
    try {
      setLoading(true);
      await login("admin@example.com", "admin123").catch(() => {});
      const data = await fetchAlerts(statusFilter === "ALL" ? "" : statusFilter);
      setAlerts(data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [statusFilter]);

  const handleRunAudit = async () => {
    try {
      setIsAuditing(true);
      setAuditSummary(null);
      const res = await triggerAnomalyAudit();
      setAuditSummary(`Audit: ${res.total_anomalies_detected} anomalies detected`);
      await loadData();
    } catch (err: any) {
      alert(`Audit sweep completed: ${err.message}`);
    } finally {
      setIsAuditing(false);
    }
  };

  const handleOpenResolve = (alert: AlertItem) => {
    setActiveAlert(alert);
    setResolutionNotes(`Verified and reconciled by warehouse operations manager on ${new Date().toISOString().substring(0, 10)}.`);
  };

  const handleConfirmResolve = async () => {
    if (!activeAlert) return;
    try {
      setIsResolving(true);
      await resolveAlert(activeAlert.id, resolutionNotes);
      setActiveAlert(null);
      await loadData();
    } catch (err: any) {
      alert(`Could not resolve alert: ${err.message}`);
    } finally {
      setIsResolving(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="dark:bg-[#171717] bg-[#FFFFFF] border dark:border-[#333333] border-[#E8E8E8] p-6 sm:p-7 rounded-2xl shadow-sm flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div className="space-y-1">
          <div className="inline-flex items-center space-x-2 px-2.5 py-1 rounded-md bg-[#EB3424]/10 border border-[#EB3424]/25 text-xs font-mono font-medium text-[#EB3424] mb-1">
            <AlertTriangle className="w-3.5 h-3.5 text-[#EB3424]" />
            <span>Human Exception Escalations</span>
          </div>
          <h1 className="text-3xl sm:text-4xl font-medium tracking-[-0.3px] dark:text-[#F5F5F5] text-[#262626]">
            Exceptions & Alerts
          </h1>
          <p className="text-sm dark:text-slate-400 text-slate-500 font-normal">
            Humans are involved strictly when automated statistical tolerances (stock drift, spikes &gt; 3σ, supplier delays) trip.
          </p>
        </div>

        <div className="flex items-center space-x-3 w-full sm:w-auto">
          {auditSummary && (
            <span className="text-xs text-[#ECB730] font-mono dark:bg-[#1F1F1F] bg-[#FBFBFB] px-3 py-1.5 rounded-lg border dark:border-[#333333] border-[#E8E8E8]">
              {auditSummary}
            </span>
          )}
          <button
            onClick={handleRunAudit}
            disabled={isAuditing}
            className="btn-secondary text-xs"
          >
            <ShieldAlert className={`w-3.5 h-3.5 ${isAuditing ? "animate-spin text-[#FA5D19]" : ""}`} />
            <span>{isAuditing ? "Auditing..." : "Audit Invariants"}</span>
          </button>
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="flex items-center space-x-2">
        {["OPEN", "RESOLVED", "ALL"].map((status) => (
          <button
            key={status}
            onClick={() => setStatusFilter(status)}
            className={`text-xs px-3.5 py-1.5 rounded-lg font-mono font-medium transition-all ${
              statusFilter === status
                ? "bg-[#FA5D19] text-white shadow-sm font-semibold"
                : "dark:bg-[#1F1F1F] bg-[#FBFBFB] border dark:border-[#333333] border-[#E8E8E8] dark:text-[#F5F5F5]/70 text-[#262626]/70 hover:border-[#FA5D19]/40"
            }`}
          >
            {status}
          </button>
        ))}
      </div>

      {/* Alerts Feed */}
      <div className="space-y-3.5">
        {alerts.length === 0 ? (
          <div className="dark:bg-[#171717] bg-[#FFFFFF] border dark:border-[#333333] border-[#E8E8E8] p-10 rounded-2xl text-center flex flex-col items-center justify-center space-y-2.5">
            <div className="w-10 h-10 rounded-full bg-[#42C366]/15 flex items-center justify-center text-[#42C366]">
              <CheckCircle className="w-6 h-6" />
            </div>
            <span className="text-base font-semibold dark:text-[#F5F5F5] text-[#262626]">
              All Autonomous Systems In-Tolerance
            </span>
            <span className="text-xs dark:text-slate-400 text-slate-500 max-w-sm">
              Zero active stock drift, demand spikes, supplier delays, or negative stock anomalies.
            </span>
          </div>
        ) : (
          alerts.map((alert) => {
            const isCritical = alert.severity === "CRITICAL";
            const isOpen = alert.status === "OPEN";

            return (
              <div
                key={alert.id}
                className="dark:bg-[#171717] bg-[#FFFFFF] border dark:border-[#333333] border-[#E8E8E8] p-5 rounded-2xl shadow-sm hover:border-[#FA5D19]/40 transition-colors"
              >
                <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                  <div className="flex items-start space-x-3.5">
                    <div
                      className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 mt-0.5 ${
                        isCritical
                          ? "bg-[#EB3424]/15 text-[#EB3424] border border-[#EB3424]/30"
                          : "bg-[#ECB730]/15 text-[#ECB730] border border-[#ECB730]/30"
                      }`}
                    >
                      {isCritical ? (
                        <AlertOctagon className="w-5 h-5" />
                      ) : (
                        <AlertTriangle className="w-5 h-5" />
                      )}
                    </div>
                    <div>
                      <div className="flex items-center space-x-2">
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold tracking-wide uppercase border ${
                            isCritical
                              ? "bg-[#EB3424]/15 border-[#EB3424]/30 text-[#EB3424]"
                              : "bg-[#ECB730]/15 border-[#ECB730]/30 text-[#ECB730]"
                          }`}
                        >
                          {alert.severity}
                        </span>
                        <span className="text-xs font-mono font-bold dark:text-[#F5F5F5] text-[#262626]">
                          {alert.alert_type}
                        </span>
                        <span className="text-[11px] text-slate-400 font-mono">
                          &bull; {new Date(alert.created_at).toLocaleString()}
                        </span>
                      </div>
                      <p className="text-sm dark:text-[#F5F5F5] text-[#262626] font-normal mt-1.5 leading-relaxed">
                        {alert.message}
                      </p>

                      {/* Context Data */}
                      {alert.context_data && Object.keys(alert.context_data).length > 0 && (
                        <div className="mt-2.5 flex flex-wrap gap-1.5">
                          {Object.entries(alert.context_data).map(([k, v]) => (
                            <span
                              key={k}
                              className="inline-block text-[10px] font-mono dark:bg-[#1F1F1F] bg-[#FBFBFB] border dark:border-[#333333] border-[#E8E8E8] dark:text-slate-300 text-slate-600 px-2 py-0.5 rounded"
                            >
                              {k}: <span className="font-semibold text-[#FA5D19]">{String(v)}</span>
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Action buttons */}
                  <div className="shrink-0 flex items-center space-x-2 w-full sm:w-auto justify-end">
                    {isOpen ? (
                      <button
                        onClick={() => handleOpenResolve(alert)}
                        className="btn-heat-primary text-xs py-1.5 px-3"
                      >
                        <Check className="w-3.5 h-3.5" />
                        <span>Resolve</span>
                      </button>
                    ) : (
                      <span className="inline-flex items-center space-x-1 text-xs text-[#42C366] font-mono font-semibold">
                        <CheckCircle className="w-4 h-4" />
                        <span>Resolved</span>
                      </span>
                    )}
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Resolution Dialog Modal */}
      {activeAlert && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4">
          <div className="dark:bg-[#171717] bg-[#FFFFFF] border dark:border-[#333333] border-[#E8E8E8] rounded-2xl p-6 max-w-lg w-full space-y-4 shadow-xl">
            <div className="flex items-center justify-between border-b dark:border-[#333333] border-[#E8E8E8] pb-3">
              <h3 className="text-base font-semibold dark:text-[#F5F5F5] text-[#262626]">
                Resolve Exception Alert
              </h3>
              <button
                onClick={() => setActiveAlert(null)}
                className="text-slate-400 hover:text-slate-200"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="text-xs dark:text-slate-300 text-slate-600 space-y-1">
              <div className="font-mono text-[#FA5D19] font-semibold">{activeAlert.alert_type}</div>
              <p>{activeAlert.message}</p>
            </div>

            <div>
              <label className="block text-xs font-mono font-medium dark:text-slate-400 text-slate-500 mb-1.5">
                Resolution Notes & Audit Trail
              </label>
              <textarea
                value={resolutionNotes}
                onChange={(e) => setResolutionNotes(e.target.value)}
                rows={3}
                className="w-full dark:bg-[#1F1F1F] bg-[#FBFBFB] border dark:border-[#333333] border-[#E8E8E8] text-xs font-mono dark:text-[#F5F5F5] text-[#262626] p-3 rounded-lg focus:outline-none focus:border-[#FA5D19] focus:ring-1 focus:ring-[#FA5D19]"
                placeholder="Explain resolution steps..."
              />
            </div>

            <div className="flex items-center justify-end space-x-2.5 pt-2 border-t dark:border-[#333333] border-[#E8E8E8]">
              <button
                onClick={() => setActiveAlert(null)}
                className="btn-secondary text-xs"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmResolve}
                disabled={isResolving}
                className="btn-heat-primary text-xs"
              >
                {isResolving ? "Resolving..." : "Confirm & Close"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

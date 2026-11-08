"use client";

import React, { useEffect, useState } from "react";
import { Sun, Moon } from "lucide-react";

export default function ThemeToggle() {
  const [theme, setTheme] = useState<"dark" | "light">("light");

  useEffect(() => {
    const saved = localStorage.getItem("autostock_theme") as "dark" | "light" | null;
    if (saved === "dark") {
      setTheme("dark");
      document.documentElement.classList.add("dark");
    } else {
      setTheme("light");
      document.documentElement.classList.remove("dark");
    }
  }, []);

  const toggleTheme = () => {
    const nextTheme = theme === "dark" ? "light" : "dark";
    setTheme(nextTheme);
    localStorage.setItem("autostock_theme", nextTheme);
    if (nextTheme === "dark") {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
  };

  return (
    <button
      onClick={toggleTheme}
      title={theme === "dark" ? "Switch to Light Theme" : "Switch to Dark Theme"}
      className="w-8 h-8 rounded-lg border dark:border-[#333333] border-[#E8E8E8] dark:bg-[#1F1F1F] bg-[#FFFFFF] flex items-center justify-center text-slate-500 hover:text-[#FA5D19] transition-all active:scale-[0.98] shrink-0"
      aria-label="Toggle Theme"
    >
      {theme === "dark" ? (
        <Sun className="w-3.5 h-3.5 text-[#FA5D19]" />
      ) : (
        <Moon className="w-3.5 h-3.5 text-slate-600" />
      )}
    </button>
  );
}

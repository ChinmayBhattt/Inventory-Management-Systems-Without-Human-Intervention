import type { Metadata } from "next";
import "./globals.css";
import Navbar from "@/components/Navbar";

export const metadata: Metadata = {
  title: "AutoStock AI - Autonomous Inventory Management System",
  description: "Pure software-based autonomous inventory management with zero routine human intervention.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        <meta name="color-scheme" content="light dark" />
      </head>
      <body className="min-h-screen flex flex-col bg-[#F9F9F9] dark:bg-[#0A0A0A] text-[#262626] dark:text-[#F5F5F5] antialiased selection:bg-[#FA5D19]/20 selection:text-[#FA5D19]">
        <Navbar />
        <main className="flex-1 max-w-7xl w-full mx-auto p-4 sm:p-6 lg:p-8">
          {children}
        </main>
        <footer className="border-t dark:border-[#333333] border-[#E8E8E8] dark:bg-[#171717]/80 bg-[#FFFFFF]/80 py-4 text-center text-xs dark:text-slate-500 text-slate-400 font-mono">
          AutoStock.ai &bull; Autonomous Event-Sourced Inventory Engine &bull; Zero Routine Human Intervention
        </footer>
      </body>
    </html>
  );
}

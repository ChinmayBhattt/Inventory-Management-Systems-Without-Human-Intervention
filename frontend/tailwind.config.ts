import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // User Design System Colors
        heat: {
          DEFAULT: "#FA5D19",
          4: "rgba(250, 93, 25, 0.04)",
          8: "rgba(250, 93, 25, 0.08)",
          12: "rgba(250, 93, 25, 0.12)",
          16: "rgba(250, 93, 25, 0.16)",
          20: "rgba(250, 93, 25, 0.20)",
          40: "rgba(250, 93, 25, 0.40)",
          90: "rgba(250, 93, 25, 0.90)",
        },
        graphite: "#262626",
        base: {
          light: "#F9F9F9",
          lighter: "#FBFBFB",
        },
        surface: {
          light: "#FFFFFF",
          dark: "#171717",
          raised: "#1F1F1F",
        },
        border: {
          muted: "#E8E8E8",
          faint: "#EDEDED",
          loud: "#E6E6E6",
          dark: "#333333",
          "dark-faint": "#262626",
          "dark-loud": "#3A3A3A",
        },
        bluetron: "#2A6DFB",
        crimson: "#EB3424",
        honey: "#ECB730",
        forest: "#42C366",
        amethyst: "#9061FF",
        dark: {
          bg: "#0A0A0A",
          surface: "#171717",
          raised: "#1F1F1F",
          text: "#F5F5F5",
          border: "#333333",
        },
      },
      fontFamily: {
        sans: [
          "SuisseIntl",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
        mono: [
          "Geist Mono",
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Monaco",
          "Consolas",
          "Liberation Mono",
          "Courier New",
          "monospace",
        ],
        flame: [
          "Roboto Mono",
          "Geist Mono",
          "monospace",
        ],
      },
      boxShadow: {
        heat: "0 1px 3px rgba(250, 93, 25, 0.25), 0 4px 14px rgba(250, 93, 25, 0.35), 0 10px 22px rgba(250, 93, 25, 0.2)",
        "heat-sm": "0 1px 2px rgba(250, 93, 25, 0.2), 0 2px 8px rgba(250, 93, 25, 0.25)",
        card: "0 1px 3px rgba(0, 0, 0, 0.04), 0 2px 6px rgba(0, 0, 0, 0.02)",
        "dark-card": "0 1px 3px rgba(0, 0, 0, 0.5), 0 4px 12px rgba(0, 0, 0, 0.4)",
      },
      transitionTimingFunction: {
        standard: "cubic-bezier(0.25, 0.1, 0.25, 1)",
      },
      scale: {
        "995": "0.995",
        "985": "0.985",
      },
    },
  },
  plugins: [],
};

export default config;

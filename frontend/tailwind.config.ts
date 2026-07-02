import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        scarlet: "#0D9488",
        slate:   "#134E4A",
        chalk:   "#F8FAFC",
        carbon:  "#1A1A1A",
        fog:     "#64748B",
        ember:   "#E67E22",
        verdant: "#27AE60",
        ink:     "#1e293b",
        border:  "#E2E8F0",
        light:   "#F8F9FA",
      },
      fontFamily: {
        serif:   ["var(--font-spectral)", "Georgia", "serif"],
        display: ["var(--font-display)", "serif"],
        sans:    ["var(--font-inter)", "system-ui", "sans-serif"],
        mono:    ["var(--font-mono)", "monospace"],
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};
export default config;

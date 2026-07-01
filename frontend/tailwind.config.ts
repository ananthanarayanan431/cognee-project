import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        scarlet: "#C0392B",
        slate:   "#2C3E50",
        chalk:   "#F5F5F0",
        carbon:  "#1A1A1A",
        fog:     "#7F8C8D",
        ember:   "#E67E22",
        verdant: "#27AE60",
        ink:     "#0D0D0D",
        border:  "#D5D8DC",
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
  plugins: [],
};
export default config;

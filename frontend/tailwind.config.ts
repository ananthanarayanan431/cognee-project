import type { Config } from "tailwindcss";

const config: Config = {
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
      },
      fontFamily: {
        serif:   ["Spectral", "Georgia", "serif"],
        display: ["DM Serif Display", "serif"],
        sans:    ["Inter", "system-ui", "sans-serif"],
        mono:    ["JetBrains Mono", "monospace"],
      },
    },
  },
  plugins: [],
};
export default config;

import { ClerkProvider as AuthProvider } from "@clerk/nextjs";
import type { Metadata } from "next";
import { Inter, Spectral, JetBrains_Mono, DM_Serif_Display } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const spectral = Spectral({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-spectral" });
const mono = JetBrains_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-mono" });
const display = DM_Serif_Display({ subsets: ["latin"], weight: "400", variable: "--font-display" });

export const metadata: Metadata = {
  title: "DebateMind",
  description: "The AI That Learns How You Argue",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${inter.variable} ${spectral.variable} ${mono.variable} ${display.variable} bg-chalk text-ink`}>
        <AuthProvider
          afterSignOutUrl="/"
          appearance={{
            layout: { unsafe_disableDevelopmentModeWarnings: true },
            variables: {
              colorPrimary: "#0D9488",
              colorText: "#1e293b",
              colorTextSecondary: "#64748B",
              colorBackground: "#ffffff",
              colorInputBackground: "#ffffff",
              colorInputText: "#1e293b",
              borderRadius: "0.75rem",
              fontFamily: "var(--font-inter), system-ui, sans-serif",
            },
            elements: {
              footer: "hidden",
              userButtonPopoverFooter: "hidden",
            },
          }}
        >
          {children}
        </AuthProvider>
      </body>
    </html>
  );
}

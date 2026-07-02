import { SignUp } from "@clerk/nextjs";

const appearance = {
  variables: {
    fontFamily: "var(--font-inter), Inter, -apple-system, sans-serif",
    fontFamilyButtons: "var(--font-inter), Inter, -apple-system, sans-serif",
    fontSize: "14px",
    fontWeight: { normal: 400, medium: 500, semibold: 600, bold: 700 },
    colorPrimary: "#0D9488",
    colorText: "#1e293b",
    colorTextSecondary: "#64748B",
    colorBackground: "#ffffff",
    colorInputBackground: "#F8FAFC",
    colorInputText: "#1e293b",
    borderRadius: "8px",
  },
  elements: {
    footer: { display: "none" },
    card: {
      boxShadow: "0 1px 3px 0 rgb(0 0 0 / 0.08)",
      border: "1px solid #E2E8F0",
      borderRadius: "12px",
    },
    formButtonPrimary: {
      textTransform: "none" as const,
      letterSpacing: "0",
      fontWeight: "600",
    },
    socialButtonsBlockButton: {
      border: "1px solid #E2E8F0",
      borderRadius: "8px",
    },
  },
};

export default function SignUpPage() {
  return (
    <div className="min-h-screen bg-chalk flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="flex items-center justify-center gap-2 mb-8">
          <div className="w-7 h-7 bg-scarlet rounded flex items-center justify-center">
            <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
            </svg>
          </div>
          <span className="font-semibold text-base text-ink tracking-tight">DebateMind</span>
        </div>
        <SignUp appearance={appearance} />
      </div>
    </div>
  );
}

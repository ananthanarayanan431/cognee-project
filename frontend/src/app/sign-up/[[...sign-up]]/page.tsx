import { SignUp } from "@clerk/nextjs";

const appearance = {
  elements: {
    footer: { display: "none" },
    card: {
      boxShadow: "0 1px 3px 0 rgb(0 0 0 / 0.08)",
      border: "1px solid #E2E8F0",
      borderRadius: "12px",
    },
    headerTitle: { color: "#1e293b", fontWeight: "600" },
    headerSubtitle: { color: "#64748B" },
    socialButtonsBlockButton: {
      border: "1px solid #E2E8F0",
      color: "#1e293b",
      borderRadius: "8px",
      "&:hover": { backgroundColor: "#F8FAFC" },
    },
    dividerLine: { backgroundColor: "#E2E8F0" },
    dividerText: { color: "#64748B" },
    formFieldLabel: { color: "#1e293b" },
    formFieldInput: {
      border: "1px solid #E2E8F0",
      borderRadius: "8px",
      color: "#1e293b",
      "&:focus": { borderColor: "#0D9488", boxShadow: "none" },
    },
    formButtonPrimary: {
      backgroundColor: "#0D9488",
      borderRadius: "8px",
      "&:hover": { backgroundColor: "#0b8277" },
    },
    identityPreviewText: { color: "#1e293b" },
    formResendCodeLink: { color: "#0D9488" },
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

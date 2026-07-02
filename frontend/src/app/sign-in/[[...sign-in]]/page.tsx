import { SignIn } from "@clerk/nextjs";

const noClerkBranding = {
  elements: {
    footer: { display: "none" },
  },
};

export default function SignInPage() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <SignIn appearance={noClerkBranding} />
    </div>
  );
}

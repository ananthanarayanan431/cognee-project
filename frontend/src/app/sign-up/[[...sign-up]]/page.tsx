import { SignUp } from "@clerk/nextjs";

const appearance = {
  elements: {
    footer: { display: "none" },
  },
};

export default function SignUpPage() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <SignUp appearance={appearance} />
    </div>
  );
}

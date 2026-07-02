"use client";
import { useSignIn } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useState } from "react";

function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
      <path d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.875 2.684-6.615z" fill="#4285F4"/>
      <path d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 009 18z" fill="#34A853"/>
      <path d="M3.964 10.71A5.41 5.41 0 013.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 000 9c0 1.452.348 2.827.957 4.042l3.007-2.332z" fill="#FBBC05"/>
      <path d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 00.957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z" fill="#EA4335"/>
    </svg>
  );
}

export default function SignInPage() {
  const { isLoaded, signIn, setActive } = useSignIn();
  const router = useRouter();
  const [email, setEmail]       = useState("");
  const [password, setPassword] = useState("");
  const [error, setError]       = useState("");
  const [loading, setLoading]   = useState(false);

  async function handleGoogle() {
    if (!isLoaded) return;
    await signIn.authenticateWithRedirect({
      strategy: "oauth_google",
      redirectUrl: "/sso-callback",
      redirectUrlComplete: "/",
    });
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!isLoaded) return;
    setLoading(true);
    setError("");
    try {
      const result = await signIn.create({ identifier: email, password });
      if (result.status === "complete") {
        await setActive({ session: result.createdSessionId });
        router.push("/");
      }
    } catch (err: unknown) {
      const ce = err as { errors?: { message: string }[] };
      setError(ce.errors?.[0]?.message ?? "Sign in failed. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-white flex items-start justify-center pt-20 px-6">
      <div className="w-full max-w-[360px]">

        {/* Heading */}
        <h1 className="font-display text-[36px] text-ink leading-tight mb-2">
          Sign in to DebateMind
        </h1>
        <p className="font-sans text-[14px] text-fog mb-8">
          Welcome back — start arguing.
        </p>

        {/* Google */}
        <button
          onClick={handleGoogle}
          className="w-full flex items-center justify-center gap-3 border border-border rounded-xl py-3 px-4 font-sans text-[14px] text-ink font-medium hover:bg-chalk transition-colors"
        >
          <GoogleIcon />
          Continue with Google
        </button>

        {/* Divider */}
        <div className="flex items-center gap-3 my-6">
          <div className="flex-1 h-px bg-border" />
          <span className="font-sans text-[12px] text-fog">or</span>
          <div className="flex-1 h-px bg-border" />
        </div>

        {/* Email/password form */}
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <label className="font-sans text-[13px] font-medium text-ink">Email</label>
            <input
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="border border-border rounded-xl px-4 py-3 font-sans text-[14px] text-ink placeholder:text-fog/40 bg-white outline-none focus:border-scarlet transition-colors"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="font-sans text-[13px] font-medium text-ink">Password</label>
            <input
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="border border-border rounded-xl px-4 py-3 font-sans text-[14px] text-ink placeholder:text-fog/40 bg-white outline-none focus:border-scarlet transition-colors"
            />
          </div>

          {error && (
            <p className="font-sans text-[13px] text-red-500">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading || !isLoaded}
            className="w-full bg-ink text-white font-sans text-[14px] font-semibold py-3 rounded-xl hover:bg-ink/85 transition-colors disabled:opacity-50 mt-1"
          >
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <p className="font-sans text-[13px] text-fog text-center mt-7">
          New to DebateMind?{" "}
          <Link href="/sign-up" className="text-scarlet hover:underline font-medium">
            Create account
          </Link>
        </p>
      </div>
    </div>
  );
}

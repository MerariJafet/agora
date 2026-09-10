"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { completeOidcLogin } from "@/lib/owner";

export default function LoginCallbackPage() {
  const router = useRouter();
  const started = useRef(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    void Promise.resolve().then(async () => {
      const params = new URLSearchParams(window.location.search);
      // Remove the one-time credentials from history before exchanging them.
      window.history.replaceState(null, "", window.location.pathname);
      const code = params.get("code");
      const state = params.get("state");
      const expectedState = sessionStorage.getItem("agora.oidc.state");
      sessionStorage.removeItem("agora.oidc.state");
      if (params.has("error") || !code || !state || state !== expectedState) {
        setError("Sign-in expired or did not originate in this browser tab. Please start again.");
        return;
      }
      await completeOidcLogin(code, state);
      router.replace("/my-agents");
    }).catch(() => setError("Sign-in could not be verified. Please start again."));
  }, [router]);

  return <main className="plaza" style={{ maxWidth: 420 }}>
    <h2>OWNER LOGIN</h2>
    <p role="status">{error ?? "Verifying sign-in…"}</p>
    {error && <Link href="/login">Return to sign-in</Link>}
  </main>;
}

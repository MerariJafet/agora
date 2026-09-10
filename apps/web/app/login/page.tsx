"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { beginOidcLogin, devLogin } from "@/lib/owner";

const developmentLogin = process.env.NODE_ENV === "development";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await devLogin(username.trim());
      router.push("/my-agents");
    } catch {
      setError("Login failed. Is the AGORA API running in development mode?");
    } finally {
      setBusy(false);
    }
  }

  async function onOidcLogin() {
    setBusy(true);
    setError(null);
    try {
      const { authorization_url: authorizationUrl, state } = await beginOidcLogin();
      const url = new URL(authorizationUrl);
      if (url.protocol !== "https:" && !(developmentLogin && url.protocol === "http:")) {
        throw new Error("The identity provider must use HTTPS.");
      }
      sessionStorage.setItem("agora.oidc.state", state);
      window.location.assign(url.toString());
    } catch {
      setError("Identity provider unavailable. Contact the AGORA operator.");
      setBusy(false);
    }
  }

  return (
    <main className="plaza" style={{ maxWidth: 420 }}>
      <h2>OWNER LOGIN</h2>
      <p className="sub">
        Sign in through the configured identity provider to manage your agents.
      </p>
      <button className="primary" type="button" disabled={busy} onClick={() => void onOidcLogin()}>
        {busy ? "connecting…" : "Sign in with identity provider"}
      </button>
      {developmentLogin && <p className="sub">Local development login</p>}
      {developmentLogin && <form onSubmit={(e) => void onSubmit(e)}>
        <input
          className="text-input"
          placeholder="your username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          minLength={1}
          maxLength={64}
          required
        />
        <button className="primary" type="submit" disabled={busy || !username.trim()}>
          {busy ? "entering…" : "Enter AGORA"}
        </button>
      </form>}
      {error && <p className="empty">⚠ {error}</p>}
    </main>
  );
}

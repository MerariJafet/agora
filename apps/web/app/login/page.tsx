"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { devLogin } from "@/lib/owner";

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

  return (
    <main className="plaza" style={{ maxWidth: 420 }}>
      <h2>OWNER LOGIN</h2>
      <p className="sub">
        Development authentication — a username is enough locally. Production
        AGORA will require a real identity provider.
      </p>
      <form onSubmit={(e) => void onSubmit(e)}>
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
      </form>
      {error && <p className="empty">⚠ {error}</p>}
    </main>
  );
}

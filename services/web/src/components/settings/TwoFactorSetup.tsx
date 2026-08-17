"use client";

import { FormEvent, useState } from "react";
import QRCode from "react-qr-code";
import { useAuth } from "@/components/auth/AuthProvider";
import { formatApiError } from "@/lib/api";
import { enable2FA, verify2FA } from "@/lib/auth-api";
import { getAccessToken } from "@/lib/auth";

type Stage = "idle" | "setup" | "confirm" | "done";

export function TwoFactorSetup() {
  const { user, refreshMe } = useAuth();
  const [stage, setStage] = useState<Stage>("idle");
  const [secretUri, setSecretUri] = useState<string | null>(null);
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([]);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const enabled = Boolean(user?.totp_enabled);

  async function startSetup() {
    setError(null);
    setPending(true);
    try {
      const token = getAccessToken();
      if (!token) throw new Error("Not authenticated");
      const result = await enable2FA(token);
      setSecretUri(result.secret_uri);
      setRecoveryCodes(result.recovery_codes);
      setStage("setup");
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setPending(false);
    }
  }

  async function confirmSetup(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (!code.trim()) {
      setError("Enter the 6-digit code from your authenticator app.");
      return;
    }
    setPending(true);
    try {
      const token = getAccessToken();
      if (!token) throw new Error("Not authenticated");
      // Confirming enrollment re-uses the access token; the backend treats
      // it the same as a fresh registration "setup" token for this step.
      await verify2FA(token, code.trim());
      setCode("");
      setStage("done");
      await refreshMe();
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setPending(false);
    }
  }

  function reset() {
    setStage("idle");
    setSecretUri(null);
    setRecoveryCodes([]);
    setCode("");
    setError(null);
  }

  return (
    <section className="rounded-xl border border-border bg-card p-5">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h2 className="font-serif text-lg font-semibold">
            Two-factor authentication
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Require an authenticator app code (or recovery code) when signing in.
          </p>
        </div>
        {enabled && stage !== "setup" && (
          <span className="shrink-0 rounded-full border border-primary/40 bg-primary/10 px-3 py-1 text-xs font-medium text-primary">
            Enabled
          </span>
        )}
      </div>

      {error && (
        <p className="mt-4 rounded-md border border-destructive/40 bg-popover px-3 py-2 text-sm text-destructive">
          {error}
        </p>
      )}

      {stage === "idle" && !enabled && (
        <button
          type="button"
          onClick={startSetup}
          disabled={pending}
          className="mt-4 rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground disabled:opacity-60"
        >
          {pending ? "Starting…" : "Enable 2FA"}
        </button>
      )}

      {stage === "idle" && enabled && (
        <p className="mt-4 text-sm text-muted-foreground">
          2FA is active on this account. Disabling it is not supported yet —
          contact support if you lose access to your authenticator app and
          recovery codes.
        </p>
      )}

      {stage === "setup" && secretUri && (
        <div className="mt-5 space-y-5">
          <div className="flex flex-col items-center gap-4 rounded-lg border border-border bg-background p-5 sm:flex-row sm:items-start">
            <div className="rounded-md bg-white p-3">
              <QRCode value={secretUri} size={148} />
            </div>
            <div className="space-y-2 text-sm text-muted-foreground">
              <p>
                Scan this code with an authenticator app (Google Authenticator,
                1Password, Authy, etc.), then enter the 6-digit code it
                generates below.
              </p>
              <p className="break-all font-mono text-xs text-foreground">
                {secretUri}
              </p>
            </div>
          </div>

          <div className="rounded-lg border border-primary/40 bg-primary/10 p-4">
            <p className="text-sm font-medium">Save your recovery codes</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Each code can be used once to sign in if you lose access to your
              authenticator app. Store them somewhere safe — they will not be
              shown again.
            </p>
            <div className="mt-3 grid grid-cols-2 gap-2 font-mono text-sm sm:grid-cols-4">
              {recoveryCodes.map((rc) => (
                <span
                  key={rc}
                  className="rounded-md border border-border bg-background px-2 py-1 text-center"
                >
                  {rc}
                </span>
              ))}
            </div>
          </div>

          <form className="flex flex-col gap-3 sm:flex-row sm:items-end" onSubmit={confirmSetup}>
            <label className="flex-1 space-y-1.5">
              <span className="block text-sm font-medium">Authentication code</span>
              <input
                value={code}
                onChange={(e) => setCode(e.target.value)}
                autoComplete="one-time-code"
                placeholder="123456"
                className="h-10 w-full rounded-md border border-border bg-background px-3 text-sm outline-none focus:border-ring focus:ring-1 focus:ring-ring"
              />
            </label>
            <div className="flex gap-2">
              <button
                type="submit"
                disabled={pending}
                className="h-10 rounded-md bg-primary px-5 text-sm font-semibold text-primary-foreground disabled:opacity-60"
              >
                {pending ? "Verifying…" : "Confirm"}
              </button>
              <button
                type="button"
                onClick={reset}
                disabled={pending}
                className="h-10 rounded-md border border-border px-4 text-sm font-medium text-muted-foreground hover:bg-muted"
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      {stage === "done" && (
        <div className="mt-4 rounded-lg border border-primary/40 bg-primary/10 px-4 py-3 text-sm">
          Two-factor authentication is now enabled on your account.
        </div>
      )}
    </section>
  );
}

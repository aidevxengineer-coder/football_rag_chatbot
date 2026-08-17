"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { formatApiError } from "@/lib/api";
import {
  googleOAuthUrl,
  fetchOAuthProviders,
  loginUser,
  registerUser,
  verify2FA,
  verifyEmail,
} from "@/lib/auth-api";
import { useAuth } from "@/components/auth/AuthProvider";

type Mode = "signup" | "signin";
type Step = "form" | "verifyEmail" | "verify2fa";

type FieldErrors = {
  first_name?: string;
  email?: string;
  password?: string;
  code?: string;
};

export function AuthModal() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { applyTokens } = useAuth();

  const authParam = searchParams.get("auth");
  const open = authParam === "signup" || authParam === "signin";
  const mode: Mode = authParam === "signin" ? "signin" : "signup";

  const [step, setStep] = useState<Step>("form");
  const [firstName, setFirstName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [verificationToken, setVerificationToken] = useState<string | null>(null);
  const [stepUpToken, setStepUpToken] = useState<string | null>(null);
  const [devVerificationCode, setDevVerificationCode] = useState<string | null>(null);
  const [verificationEmailSent, setVerificationEmailSent] = useState(false);
  const [verificationEmailError, setVerificationEmailError] = useState<string | null>(null);
  const [googleOAuthEnabled, setGoogleOAuthEnabled] = useState(false);
  const [oauthChecked, setOauthChecked] = useState(false);

  useEffect(() => {
    if (!open) {
      setOauthChecked(false);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const providers = await fetchOAuthProviders();
        if (!cancelled) setGoogleOAuthEnabled(providers.google);
      } catch {
        if (!cancelled) setGoogleOAuthEnabled(false);
      } finally {
        if (!cancelled) setOauthChecked(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open]);

  useEffect(() => {
    if (!open) {
      setStep("form");
      setErrors({});
      setFormError(null);
      setCode("");
      setVerificationToken(null);
      setStepUpToken(null);
      setDevVerificationCode(null);
      setVerificationEmailSent(false);
      setVerificationEmailError(null);
      return;
    }
    setStep("form");
    setErrors({});
    setFormError(null);
  }, [open, mode]);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key !== "Escape") return;
      const params = new URLSearchParams(searchParams.toString());
      params.delete("auth");
      const q = params.toString();
      router.replace(q ? `${pathname}?${q}` : pathname);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, pathname, router, searchParams]);

  const title = useMemo(() => {
    if (step === "verifyEmail") return "Verify your email";
    if (step === "verify2fa") return "Two-factor authentication";
    return mode === "signup" ? "Create an account" : "Sign in";
  }, [mode, step]);

  const subtitle = useMemo(() => {
    if (step === "verifyEmail") {
      if (devVerificationCode) {
        return `SMTP is not configured. Use the dev code below to verify ${email}.`;
      }
      if (verificationEmailSent) {
        return `Enter the 6-digit code we sent to ${email}.`;
      }
      return `We could not send a verification email to ${email}. Check SMTP settings or use the dev code below.`;
    }
    if (step === "verify2fa") {
      return "Enter the 6-digit code from your authenticator app, or a recovery code.";
    }
    return mode === "signup"
      ? "Enter your details below to create your account"
      : "Enter your email and password to continue";
  }, [devVerificationCode, email, mode, step, verificationEmailSent]);

  function close() {
    const params = new URLSearchParams(searchParams.toString());
    params.delete("auth");
    const q = params.toString();
    router.replace(q ? `${pathname}?${q}` : pathname);
  }

  function setMode(next: Mode) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("auth", next);
    router.replace(`${pathname}?${params.toString()}`);
  }

  function validateForm(): FieldErrors {
    const next: FieldErrors = {};
    if (mode === "signup" && !firstName.trim()) {
      next.first_name = "Enter your first name.";
    }
    if (!email.trim()) next.email = "Enter your email address.";
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      next.email = "Enter a valid email address.";
    }
    if (!password) next.password = "Enter a password.";
    else if (mode === "signup" && password.length < 8) {
      next.password = "Password must be at least 8 characters.";
    }
    return next;
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);

    if (step === "form") {
      const nextErrors = validateForm();
      setErrors(nextErrors);
      if (Object.keys(nextErrors).length) return;

      setPending(true);
      try {
        if (mode === "signup") {
          const result = await registerUser({
            email: email.trim(),
            password,
            first_name: firstName.trim(),
          });
          setVerificationToken(result.verification_token);
          setVerificationEmailSent(Boolean(result.verification_email_sent));
          setVerificationEmailError(result.verification_email_error ?? null);
          setDevVerificationCode(result.dev_verification_code ?? null);
          if (result.dev_verification_code) {
            setCode(result.dev_verification_code);
          } else {
            setCode("");
          }
          setStep("verifyEmail");
        } else {
          const result = await loginUser({
            email: email.trim(),
            password,
          });
          if (result.requires_2fa) {
            setStepUpToken(result.step_up_token ?? null);
            setCode("");
            setStep("verify2fa");
          } else if (result.access_token && result.refresh_token) {
            await applyTokens({
              access_token: result.access_token,
              refresh_token: result.refresh_token,
              expires_in: result.expires_in ?? 0,
              token_type: result.token_type || "bearer",
            });
            close();
          } else {
            setFormError("Unexpected response from server. Try again.");
          }
        }
      } catch (err) {
        setFormError(formatApiError(err));
      } finally {
        setPending(false);
      }
      return;
    }

    if (!code.trim()) {
      setErrors({ code: "Enter your verification code." });
      return;
    }

    if (step === "verify2fa") {
      if (!stepUpToken) {
        setFormError("Session expired. Start again.");
        setStep("form");
        return;
      }
      setPending(true);
      setErrors({});
      try {
        const tokens = await verify2FA(stepUpToken, code.trim());
        await applyTokens(tokens);
        close();
      } catch (err) {
        setFormError(formatApiError(err));
      } finally {
        setPending(false);
      }
      return;
    }

    if (!verificationToken) {
      setFormError("Session expired. Start again.");
      setStep("form");
      return;
    }
    setPending(true);
    setErrors({});
    try {
      const tokens = await verifyEmail(verificationToken, code.trim());
      await applyTokens(tokens);
      close();
    } catch (err) {
      setFormError(formatApiError(err));
    } finally {
      setPending(false);
    }
  }

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex cursor-default items-center justify-center bg-[rgba(4,12,8,0.55)] p-6"
      role="dialog"
      aria-modal="true"
      aria-labelledby="auth-title"
      onClick={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <div
        className="relative w-full max-w-md rounded-xl border border-border bg-card p-7 text-card-foreground shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          aria-label="Close"
          onClick={close}
          className="absolute right-3.5 top-3.5 inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          <span className="material-symbols-outlined text-[20px]">close</span>
        </button>

        <header className="mb-6 px-7 text-center">
          <h1 id="auth-title" className="text-xl font-semibold tracking-tight">
            {title}
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">{subtitle}</p>
        </header>

        {step === "form" && oauthChecked && googleOAuthEnabled && (
          <>
            <button
              type="button"
              className="mb-5 flex h-10 w-full items-center justify-center gap-2 rounded-md border border-border bg-background text-sm font-medium hover:border-ring hover:bg-muted"
              onClick={() => {
                window.location.href = googleOAuthUrl();
              }}
            >
              <GoogleIcon />
              Continue with Google
            </button>
            <div className="mb-5 flex items-center gap-3">
              <div className="h-px flex-1 bg-border" />
              <span className="font-mono text-[11px] uppercase tracking-wide text-muted-foreground">
                Or continue with
              </span>
              <div className="h-px flex-1 bg-border" />
            </div>
          </>
        )}

        {step === "form" && oauthChecked && !googleOAuthEnabled && (
          <p className="mb-5 rounded-md border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
            Google sign-in is not configured yet. Add{" "}
            <span className="font-mono">GOOGLE_CLIENT_ID</span> and{" "}
            <span className="font-mono">GOOGLE_CLIENT_SECRET</span> in Settings, or
            use email and password below.
          </p>
        )}

        <form className="flex flex-col gap-4" onSubmit={onSubmit} noValidate>
          {step === "form" && mode === "signup" && (
            <Field
              id="first-name"
              label="First name"
              value={firstName}
              onChange={setFirstName}
              error={errors.first_name}
              autoComplete="given-name"
              placeholder="Alex"
            />
          )}

          {step === "form" && (
            <>
              <Field
                id="email"
                label="Email"
                type="email"
                value={email}
                onChange={setEmail}
                error={errors.email}
                autoComplete="email"
                placeholder="m@example.com"
              />
              <Field
                id="password"
                label="Password"
                type="password"
                value={password}
                onChange={setPassword}
                error={errors.password}
                autoComplete={mode === "signup" ? "new-password" : "current-password"}
                placeholder="••••••••"
              />
            </>
          )}

          {step === "verifyEmail" && verificationEmailError && (
            <p className="rounded-md border border-destructive/40 bg-popover px-3 py-2 text-sm text-destructive whitespace-pre-wrap">
              Email could not be sent: {verificationEmailError}
            </p>
          )}

          {step === "verifyEmail" && devVerificationCode && (
            <div className="rounded-md border border-primary/40 bg-primary/10 px-3 py-2 text-center">
              <p className="font-mono text-[11px] uppercase tracking-wide text-muted-foreground">
                Dev verification code
              </p>
              <p className="mt-1 font-mono text-2xl font-semibold tracking-[0.35em] text-primary">
                {devVerificationCode}
              </p>
            </div>
          )}

          {step === "verifyEmail" && (
            <Field
              id="email-code"
              label="Verification code"
              value={code}
              onChange={setCode}
              error={errors.code}
              autoComplete="one-time-code"
              placeholder="123456"
            />
          )}

          {step === "verify2fa" && (
            <Field
              id="totp-code"
              label="Authentication code"
              value={code}
              onChange={setCode}
              error={errors.code}
              autoComplete="one-time-code"
              placeholder="123456 or recovery code"
            />
          )}

          {formError && (
            <p className="rounded-md border border-destructive/40 bg-popover px-3 py-2 text-sm text-destructive">
              {formError}
            </p>
          )}

          <button
            type="submit"
            disabled={pending}
            className="h-10 rounded-md bg-primary text-sm font-semibold text-primary-foreground hover:brightness-110 disabled:opacity-60"
          >
            {pending
              ? "Please wait…"
              : step === "form"
                ? mode === "signup"
                  ? "Create account"
                  : "Sign in"
                : step === "verify2fa"
                  ? "Verify and sign in"
                  : "Verify and continue"}
          </button>
        </form>

        {step === "form" && (
          <p className="mt-5 text-center text-sm text-muted-foreground">
            {mode === "signup" ? "Already have an account?" : "Need an account?"}{" "}
            <button
              type="button"
              className="font-medium text-foreground underline underline-offset-4 hover:text-primary"
              onClick={() => setMode(mode === "signup" ? "signin" : "signup")}
            >
              {mode === "signup" ? "Sign in" : "Sign up"}
            </button>
          </p>
        )}
      </div>
    </div>
  );
}

function Field({
  id,
  label,
  value,
  onChange,
  error,
  type = "text",
  autoComplete,
  placeholder,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  error?: string;
  type?: string;
  autoComplete?: string;
  placeholder?: string;
}) {
  return (
    <div className="relative">
      <label htmlFor={id} className="mb-1.5 block text-sm font-medium">
        {label}
      </label>
      <input
        id={id}
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        autoComplete={autoComplete}
        placeholder={placeholder}
        aria-invalid={Boolean(error)}
        className={`h-10 w-full rounded-md border bg-background px-3 text-sm outline-none transition-colors ${
          error
            ? "border-destructive shadow-[0_0_0_1px_var(--destructive)]"
            : "border-border focus:border-ring focus:shadow-[0_0_0_1px_var(--ring)]"
        }`}
      />
      {error && (
        <span
          role="alert"
          className="pointer-events-none absolute bottom-[calc(100%-0.15rem)] left-0 z-10 whitespace-nowrap rounded-md border border-destructive/50 bg-popover px-2.5 py-1.5 text-xs font-medium text-destructive shadow-lg"
        >
          {error}
        </span>
      )}
    </div>
  );
}

function GoogleIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" aria-hidden="true">
      <path
        fill="#4285F4"
        d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
      />
      <path
        fill="#34A853"
        d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
      />
      <path
        fill="#FBBC05"
        d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
      />
      <path
        fill="#EA4335"
        d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
      />
    </svg>
  );
}

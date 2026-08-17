"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/auth/AuthProvider";

export default function OAuthCallbackPage() {
  const router = useRouter();
  const { applyTokens } = useAuth();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const accessToken = params.get("access_token");
    const refreshToken = params.get("refresh_token");
    const expiresIn = params.get("expires_in");

    if (!accessToken || !refreshToken) {
      setError("Google sign-in did not return session tokens.");
      return;
    }

    (async () => {
      try {
        await applyTokens({
          access_token: accessToken,
          refresh_token: refreshToken,
          expires_in: Number(expiresIn || 900),
          token_type: "bearer",
        });
        router.replace("/");
      } catch {
        setError("Could not complete Google sign-in.");
      }
    })();
  }, [applyTokens, router]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-6">
      <p className="text-sm text-muted-foreground">
        {error ?? "Completing Google sign-in…"}
      </p>
    </div>
  );
}

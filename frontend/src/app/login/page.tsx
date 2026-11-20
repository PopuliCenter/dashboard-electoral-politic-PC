"use client";

import { LogIn } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { apiBaseUrl } from "@/lib/api";

const inputClass =
  "mt-1 block w-full rounded-md border bg-background px-3 py-2 text-sm shadow-sm " +
  "focus:outline-none focus:ring-2 focus:ring-ring";

export default function LoginPage() {
  const router = useRouter();
  const [galat, setGalat] = useState<string | null>(null);
  const [sedangMasuk, setSedangMasuk] = useState(false);

  async function masuk(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setGalat(null);
    setSedangMasuk(true);
    try {
      const response = await fetch(`${apiBaseUrl}/auth/login`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: form.get("email"), password: form.get("password") }),
      });
      if (response.ok) {
        router.replace("/");
        router.refresh();
        return;
      }
      const body = (await response.json().catch(() => null)) as { detail?: unknown } | null;
      setGalat(typeof body?.detail === "string" ? body.detail : "Login gagal.");
    } catch {
      setGalat("API tidak bisa dihubungi.");
    } finally {
      setSedangMasuk(false);
    }
  }

  return (
    <main className="container flex min-h-screen max-w-md items-center py-16">
      <Card className="w-full">
        <CardHeader>
          <p className="text-sm font-medium text-muted-foreground">Populi Center</p>
          <CardTitle>Masuk</CardTitle>
          <CardDescription>Dashboard internal. Akun dibuat oleh Admin.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={masuk} className="space-y-4">
            <label className="block text-sm font-medium">
              Email
              <input
                name="email"
                type="email"
                autoComplete="username"
                required
                className={inputClass}
              />
            </label>
            <label className="block text-sm font-medium">
              Password
              <input
                name="password"
                type="password"
                autoComplete="current-password"
                required
                className={inputClass}
              />
            </label>
            {galat ? (
              <p role="alert" className="text-sm text-destructive">
                {galat}
              </p>
            ) : null}
            <Button type="submit" className="w-full" disabled={sedangMasuk}>
              <LogIn className="mr-2 h-4 w-4" aria-hidden />
              {sedangMasuk ? "Memeriksa..." : "Masuk"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}

"use client";

import { LogOut } from "lucide-react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { apiBaseUrl } from "@/lib/api";

export function LogoutButton() {
  const router = useRouter();

  async function keluar() {
    await fetch(`${apiBaseUrl}/auth/logout`, { method: "POST", credentials: "include" }).catch(
      () => null,
    );
    router.replace("/login");
    router.refresh();
  }

  return (
    <Button variant="outline" size="sm" onClick={keluar}>
      <LogOut className="mr-2 h-4 w-4" aria-hidden />
      Keluar
    </Button>
  );
}

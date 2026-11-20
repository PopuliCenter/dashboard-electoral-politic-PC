"use client";

import { LogOut } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { apiBaseUrl } from "@/lib/api";

/**
 * Pindah ke halaman login HANYA bila server benar-benar mengakhiri sesi.
 * Di komputer bersama, sesi yang diam-diam masih hidup lebih berbahaya daripada
 * pesan galat.
 */
export function LogoutButton() {
  const router = useRouter();
  const [galat, setGalat] = useState<string | null>(null);

  async function keluar() {
    setGalat(null);
    try {
      const response = await fetch(`${apiBaseUrl}/auth/logout`, {
        method: "POST",
        credentials: "include",
      });
      // 401: sesi memang sudah berakhir, jadi sudah keluar.
      if (response.status === 204 || response.status === 401) {
        router.replace("/login");
        router.refresh();
        return;
      }
      setGalat(`Gagal keluar (status ${response.status}). Sesi Anda mungkin masih aktif.`);
    } catch {
      setGalat("Gagal keluar: API tidak bisa dihubungi. Sesi Anda mungkin masih aktif.");
    }
  }

  return (
    <span className="flex items-center gap-3">
      {galat ? (
        <span role="alert" className="text-sm text-destructive">
          {galat}
        </span>
      ) : null}
      <Button variant="outline" size="sm" onClick={keluar}>
        <LogOut className="mr-2 h-4 w-4" aria-hidden />
        Keluar
      </Button>
    </span>
  );
}

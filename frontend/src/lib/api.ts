/**
 * Klien API dashboard.
 *
 * Dari server Next.js dipakai API_INTERNAL_BASE_URL (nama layanan di jaringan compose);
 * dari browser dipakai NEXT_PUBLIC_API_BASE_URL.
 */

export const apiBaseUrl =
  typeof window === "undefined"
    ? (process.env.API_INTERNAL_BASE_URL ?? "http://api:8000/api/v1")
    : (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1");

export type DatabaseHealth = {
  connected: boolean;
  postgres_version?: string | null;
  postgis_version?: string | null;
  error?: string | null;
};

export type HealthResponse = {
  status: "ok" | "degraded";
  app_env: string;
  database: DatabaseHealth;
};

export type HealthResult =
  | { reachable: true; data: HealthResponse }
  | { reachable: false; error: string };

/**
 * Partai dari /parties. Warna selalu dari API (data/reference/party_colors.csv),
 * tidak pernah di-hard-code di frontend (T4.5). color_source "fallback" berarti
 * warna pembeda sementara, bukan identitas visual partai: tampilkan keterangannya
 * di legenda.
 */
export type Party = {
  id: string;
  code: string;
  name: string;
  abbreviation: string | null;
  contested_2019: boolean;
  contested_2024: boolean;
  ballot_number_2019: number | null;
  ballot_number_2024: number | null;
  new_in_2024: boolean;
  color: string;
  color_source: "config" | "fallback";
};

export type Role = "admin" | "researcher";

export type CurrentUser = {
  id: string;
  email: string;
  full_name: string;
  role: Role;
};

export const roleLabel: Record<Role, string> = { admin: "Admin", researcher: "Peneliti" };

/**
 * Pengguna yang sedang login, dibaca di server Next.js dengan meneruskan cookie
 * sesi dari permintaan peramban. null bila belum login atau API tidak terjangkau.
 */
export async function fetchCurrentUser(cookieHeader: string): Promise<CurrentUser | null> {
  if (!cookieHeader) return null;
  try {
    const response = await fetch(`${apiBaseUrl}/auth/me`, {
      cache: "no-store",
      headers: { cookie: cookieHeader },
    });
    return response.ok ? ((await response.json()) as CurrentUser) : null;
  } catch {
    return null;
  }
}

/** Tidak pernah melempar: halaman harus tetap tampil walau API mati. */
export async function fetchHealth(): Promise<HealthResult> {
  try {
    const response = await fetch(`${apiBaseUrl}/health`, { cache: "no-store" });
    const data = (await response.json()) as HealthResponse;
    return { reachable: true, data };
  } catch (error) {
    return {
      reachable: false,
      error: error instanceof Error ? error.message : "galat tidak dikenal",
    };
  }
}

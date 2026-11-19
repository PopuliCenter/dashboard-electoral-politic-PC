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

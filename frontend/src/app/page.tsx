import { Activity, CircleAlert, CircleCheck } from "lucide-react";
import { cookies } from "next/headers";
import Link from "next/link";

import { LogoutButton } from "@/components/logout-button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { apiBaseUrl, fetchCurrentUser, fetchHealth, roleLabel } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function Home() {
  const cookieHeader = (await cookies()).toString();
  const [health, user] = await Promise.all([fetchHealth(), fetchCurrentUser(cookieHeader)]);
  const sehat = health.reachable && health.data.status === "ok";

  return (
    <main className="container max-w-3xl py-16">
      <div className="mb-6 flex items-center justify-end gap-3 text-sm">
        {user ? (
          <>
            <span className="text-muted-foreground">
              {user.full_name} · {roleLabel[user.role]}
            </span>
            <Link href="/data" className="font-medium underline underline-offset-4">
              Data dan sumber
            </Link>
            <LogoutButton />
          </>
        ) : (
          <Link href="/login" className="font-medium underline underline-offset-4">
            Masuk
          </Link>
        )}
      </div>
      <header className="mb-10">
        <p className="text-sm font-medium text-muted-foreground">Populi Center</p>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight">
          Political &amp; Electoral Intelligence Dashboard
        </h1>
        <p className="mt-3 text-muted-foreground">
          Pilot fase 1: Jawa Barat, Pemilu 2019 dan 2024, sampai tingkat kecamatan. Kontestasi yang
          dicakup: Pilpres, DPR RI, dan DPRD Provinsi.
        </p>
      </header>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <Activity className="h-4 w-4 text-muted-foreground" aria-hidden />
              <CardTitle>Status layanan</CardTitle>
            </div>
            <Badge variant={sehat ? "default" : "destructive"}>{sehat ? "ok" : "degraded"}</Badge>
          </div>
          <CardDescription>
            Dibaca dari <code className="font-mono text-xs">{apiBaseUrl}/health</code>
          </CardDescription>
        </CardHeader>
        <CardContent>
          {health.reachable ? (
            <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
              <Baris label="Lingkungan" nilai={health.data.app_env} />
              <Baris
                label="Database"
                nilai={health.data.database.connected ? "terhubung" : "tidak terhubung"}
                ok={health.data.database.connected}
              />
              <Baris label="PostgreSQL" nilai={health.data.database.postgres_version ?? "—"} />
              <Baris label="PostGIS" nilai={health.data.database.postgis_version ?? "—"} />
            </dl>
          ) : (
            <p className="flex items-start gap-2 text-sm text-muted-foreground">
              <CircleAlert className="mt-0.5 h-4 w-4 shrink-0 text-destructive" aria-hidden />
              <span>
                API tidak bisa dihubungi: {health.error}. Jalankan{" "}
                <code className="font-mono text-xs">docker compose up</code>.
              </span>
            </p>
          )}
        </CardContent>
      </Card>

      <p className="mt-8 text-sm text-muted-foreground">
        Tahap 0 (fondasi repo) selesai. Tahap 1 menunggu dokumen KPU, kode wilayah Kemendagri, dan
        batas wilayah. Urutan kerja ada di <code className="font-mono text-xs">docs/TASKS.md</code>.
      </p>
    </main>
  );
}

function Baris({ label, nilai, ok }: { label: string; nilai: string; ok?: boolean }) {
  return (
    <div className="rounded-lg border p-3">
      <dt className="text-xs uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className="mt-1 flex items-center gap-1.5 font-medium">
        {ok === true ? <CircleCheck className="h-4 w-4 text-emerald-600" aria-hidden /> : null}
        {ok === false ? <CircleAlert className="h-4 w-4 text-destructive" aria-hidden /> : null}
        <span className="font-mono text-sm">{nilai}</span>
      </dd>
    </div>
  );
}

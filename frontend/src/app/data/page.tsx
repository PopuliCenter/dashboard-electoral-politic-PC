import { CircleAlert, Database, FileText } from "lucide-react";
import { cookies } from "next/headers";
import Link from "next/link";
import { redirect } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  dataStatusLabel,
  fetchAuthed,
  type DatasetSummary,
  type DatasetVersion,
  type SourceItem,
} from "@/lib/api";

export const dynamic = "force-dynamic";

const kindLabel: Record<string, string> = {
  party_votes: "Suara partai",
  candidate_votes: "Suara paslon",
  turnout: "Partisipasi",
};
const electionLabel: Record<string, string> = {
  presidential: "Pilpres",
  legislative_dpr: "DPR RI",
  legislative_dprd_province: "DPRD Provinsi",
};
const levelLabel: Record<string, string> = {
  province: "provinsi",
  regency: "kab/kota",
  district: "kecamatan",
};
const validationLabel: Record<string, string> = {
  pending: "menunggu rekonsiliasi",
  passed: "lolos",
  failed: "gagal",
};

function tanggal(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleDateString("id-ID", { dateStyle: "medium" });
}

function lingkup(v: DatasetVersion): string {
  if (!v.record_kind) return "—";
  const kontestasi = v.election_type ? electionLabel[v.election_type] : "";
  const tingkat = v.region_levels.map((l) => levelLabel[l] ?? l).join(", ");
  return `${kindLabel[v.record_kind] ?? v.record_kind} · ${kontestasi} ${v.election_year ?? ""} · ${tingkat}`;
}

export default async function DataPage() {
  const cookieHeader = (await cookies()).toString();
  const [datasets, sources] = await Promise.all([
    fetchAuthed<DatasetSummary[]>("/datasets", cookieHeader),
    fetchAuthed<SourceItem[]>("/sources", cookieHeader),
  ]);
  if ((!datasets.ok && datasets.status === 401) || (!sources.ok && sources.status === 401)) {
    redirect("/login");
  }

  return (
    <main className="container max-w-5xl py-12">
      <header className="mb-8">
        <Link href="/" className="text-sm text-muted-foreground underline underline-offset-4">
          Beranda
        </Link>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight">Data dan sumber</h1>
        <p className="mt-2 text-muted-foreground">
          Setiap angka di dashboard berasal dari satu versi dataset dan satu dokumen sumber. Versi
          lama tetap tercatat; barisnya digantikan versi yang lebih baru.
        </p>
      </header>

      <Card className="mb-8">
        <CardHeader>
          <div className="flex items-center gap-2">
            <Database className="h-4 w-4 text-muted-foreground" aria-hidden />
            <CardTitle>Dataset</CardTitle>
          </div>
          <CardDescription>Versi yang sedang dipakai untuk setiap dataset.</CardDescription>
        </CardHeader>
        <CardContent>
          {!datasets.ok ? (
            <Gagal />
          ) : datasets.data.length === 0 ? (
            <p className="text-sm text-muted-foreground">Belum ada dataset yang dimuat.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs uppercase tracking-wide text-muted-foreground">
                  <tr>
                    <th className="py-2 pr-4">Dataset</th>
                    <th className="py-2 pr-4">Versi</th>
                    <th className="py-2 pr-4">Isi</th>
                    <th className="py-2 pr-4">Status data</th>
                    <th className="py-2 pr-4">Validasi</th>
                    <th className="py-2 pr-4">Baris</th>
                    <th className="py-2">Sumber</th>
                  </tr>
                </thead>
                <tbody>
                  {datasets.data.map((d) => (
                    <tr key={d.dataset_name} className="border-t align-top">
                      <td className="py-2 pr-4 font-mono text-xs">{d.dataset_name}</td>
                      <td className="py-2 pr-4">
                        {d.current ? `v${d.current.version_number}` : "—"}
                        <span className="text-muted-foreground"> / {d.version_count}</span>
                      </td>
                      <td className="py-2 pr-4">{d.current ? lingkup(d.current) : "—"}</td>
                      <td className="py-2 pr-4">
                        {d.current ? (
                          <Badge
                            variant={
                              d.current.data_status === "official" ? "default" : "destructive"
                            }
                          >
                            {dataStatusLabel[d.current.data_status]}
                          </Badge>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="py-2 pr-4">
                        {d.current ? validationLabel[d.current.validation_status] : "—"}
                      </td>
                      <td className="py-2 pr-4 tabular-nums">
                        {d.current?.record_count?.toLocaleString("id-ID") ?? "—"}
                      </td>
                      <td className="py-2">{d.current?.source_name ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <FileText className="h-4 w-4 text-muted-foreground" aria-hidden />
            <CardTitle>Dokumen sumber</CardTitle>
          </div>
          <CardDescription>Asal data, cara pengumpulan, dan tanggal pengambilan.</CardDescription>
        </CardHeader>
        <CardContent>
          {!sources.ok ? (
            <Gagal />
          ) : sources.data.length === 0 ? (
            <p className="text-sm text-muted-foreground">Belum ada sumber yang tercatat.</p>
          ) : (
            <ul className="space-y-3">
              {sources.data.map((s) => (
                <li key={s.id} className="rounded-lg border p-3 text-sm">
                  <p className="font-medium">{s.name}</p>
                  <p className="mt-1 text-muted-foreground">
                    {s.type}
                    {s.collection_method ? ` · ${s.collection_method}` : ""} · diambil{" "}
                    {tanggal(s.retrieved_at)} · {s.version_count} versi dataset
                  </p>
                  {s.url ? (
                    <a
                      href={s.url}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-1 block break-all text-xs underline underline-offset-4"
                    >
                      {s.url}
                    </a>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </main>
  );
}

function Gagal() {
  return (
    <p className="flex items-center gap-2 text-sm text-muted-foreground">
      <CircleAlert className="h-4 w-4 text-destructive" aria-hidden />
      API tidak bisa dihubungi.
    </p>
  );
}

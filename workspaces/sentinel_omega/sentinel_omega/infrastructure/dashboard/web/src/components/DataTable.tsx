import { useState } from "react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function DataTable({
  columns,
  rows,
  empty = "Sin datos en DB",
  pageSize = 15,
}: {
  columns: { key: string; label: string; render?: (row: Record<string, unknown>, value: unknown) => ReactNode }[];
  rows: Record<string, unknown>[];
  empty?: string;
  pageSize?: number;
}) {
  const [page, setPage] = useState(0);
  const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));
  const paginated = rows.slice(page * pageSize, (page + 1) * pageSize);

  if (!rows.length) {
    return <div className="text-center text-gray-400 py-8">{empty}</div>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-700">
            {columns.map((c) => (
              <th key={c.key} className="text-left p-2 font-semibold text-gray-300">
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {paginated.map((row, i) => (
            <tr key={i} className="border-b border-gray-800 hover:bg-gray-800/50">
              {columns.map((c) => (
                <td key={c.key} className="p-2 font-mono text-gray-100">
                  {c.render ? c.render(row, row[c.key]) : String(row[c.key] ?? "—")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-3 text-sm text-gray-400">
          <span>Página {page + 1} / {totalPages}</span>
          <div className="flex gap-2">
            <button
              onClick={() => setPage((p: number) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="px-2 py-1 bg-gray-800 rounded hover:bg-gray-700 disabled:opacity-50"
            >
              Anterior
            </button>
            <button
              onClick={() => setPage((p: number) => Math.min(totalPages - 1, p + 1))}
              disabled={page === totalPages - 1}
              className="px-2 py-1 bg-gray-800 rounded hover:bg-gray-700 disabled:opacity-50"
            >
              Siguiente
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
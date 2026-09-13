import type { ReactNode } from "react";
import { Card, CardContent, CardTitle } from "@/components/ui/card";

export function Kpi({
  label,
  value,
  hint,
  accent,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  accent?: string;
}) {
  return (
    <Card>
      <div className="px-4 pt-4">
        <CardTitle>{label}</CardTitle>
      </div>
      <CardContent>
        <div className="text-2xl font-semibold tracking-tight" style={{ color: accent }}>
          {value}
        </div>
        {hint ? <div className="mono mt-1 text-xs text-muted">{hint}</div> : null}
      </CardContent>
    </Card>
  );
}

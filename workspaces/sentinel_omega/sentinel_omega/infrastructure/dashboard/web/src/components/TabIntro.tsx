export function TabIntro({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-border bg-card/50 px-4 py-3">
      <h3 className="text-base font-semibold tracking-tight">{title}</h3>
      <div className="mt-1 space-y-1 text-sm leading-relaxed text-muted">{children}</div>
    </div>
  );
}

export function Caption({ children }: { children: React.ReactNode }) {
  return <p className="text-xs leading-relaxed text-muted">{children}</p>;
}

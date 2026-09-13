import type { CSSProperties, ReactNode } from "react";
import { cn } from "@/lib/utils";

export function Badge({
  className,
  style,
  children,
}: {
  className?: string;
  style?: CSSProperties;
  children: ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border border-border px-2.5 py-0.5 text-xs font-medium",
        className,
      )}
      style={style}
    >
      {children}
    </span>
  );
}

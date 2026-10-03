// Copyright (c) 2026 V2 Software LLC. All rights reserved.

import { cn } from "@/lib/utils";

/** Title, one line of description and right-aligned actions. Every app page starts with one. */
export function PageHeader({
  title,
  description,
  actions,
  breadcrumb,
  size = "md",
  className,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  breadcrumb?: React.ReactNode;
  size?: "md" | "lg";
  className?: string;
}) {
  return (
    <header className={cn("flex flex-col gap-2 pb-6", className)}>
      {breadcrumb}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <h1
            className={cn(
              "font-semibold tracking-tight text-foreground text-balance",
              size === "lg" ? "text-2xl" : "text-xl"
            )}
          >
            {title}
          </h1>
          {description && <p className="text-sm text-muted-foreground">{description}</p>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
    </header>
  );
}

/** One content width for every app page. */
export function PageContainer({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={cn("mx-auto w-full max-w-[1120px] px-4 pb-24 pt-6 sm:px-6 lg:px-8 lg:pb-12", className)}>
      {children}
    </div>
  );
}

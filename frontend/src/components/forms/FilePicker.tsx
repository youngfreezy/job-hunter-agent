// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useRef, useState } from "react";
import { cn } from "@/lib/utils";

interface FilePickerProps {
  id: string;
  accept: string;
  onFile: (file: File) => void;
  disabled?: boolean;
  /** Label of the button that opens the file dialog. */
  buttonLabel?: string;
  /** Shown beside the button, e.g. the current file name or the accepted types. */
  children?: React.ReactNode;
  /** Announced to screen readers when it changes (parse progress, errors). */
  status?: string;
  className?: string;
}

function acceptsFile(file: File, accept: string): boolean {
  const ext = "." + (file.name.split(".").pop() ?? "").toLowerCase();
  return accept
    .split(",")
    .map((a) => a.trim().toLowerCase())
    .some((a) => a === ext || a === file.type);
}

/**
 * A keyboard-reachable file picker that also accepts a dropped file.
 * The native input stays in the DOM (visually hidden) so the button can open it.
 */
export function FilePicker({
  id,
  accept,
  onFile,
  disabled,
  buttonLabel = "Choose file",
  children,
  status,
  className,
}: FilePickerProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [rejected, setRejected] = useState<string | null>(null);

  function take(file: File | undefined) {
    if (!file) return;
    if (!acceptsFile(file, accept)) {
      setRejected(`${file.name} is not a supported file. Use ${accept.split(",").join(", ")}.`);
      return;
    }
    setRejected(null);
    onFile(file);
  }

  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-3 rounded-lg border border-border bg-card px-4 py-3 transition-colors",
        dragging && "border-dashed border-primary bg-primary/5",
        className
      )}
      onDragOver={(e) => {
        if (disabled) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = "copy";
        setDragging(true);
      }}
      onDragLeave={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragging(false);
      }}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        if (disabled) return;
        take(e.dataTransfer.files?.[0]);
      }}
    >
      <input
        ref={inputRef}
        id={id}
        type="file"
        accept={accept}
        className="sr-only"
        tabIndex={-1}
        aria-hidden="true"
        disabled={disabled}
        onChange={(e) => {
          take(e.target.files?.[0]);
          e.target.value = "";
        }}
      />
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        disabled={disabled}
        aria-busy={disabled || undefined}
        className="inline-flex h-9 items-center rounded-md border border-border bg-background px-3 text-sm font-medium hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:opacity-60"
      >
        {buttonLabel}
      </button>
      <div className="min-w-0 flex-1 text-sm text-muted-foreground">
        {children}
        <span className="block text-xs">{dragging ? "Drop to upload" : "or drop a file here"}</span>
      </div>
      <p aria-live="polite" className="w-full text-xs empty:hidden">
        {rejected ? <span className="text-destructive">{rejected}</span> : status}
      </p>
    </div>
  );
}

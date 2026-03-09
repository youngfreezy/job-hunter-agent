// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

interface NotificationBannerProps {
  /** Main message text */
  message: string;
  /** Bold prefix before the message (optional) */
  label?: string;
  /** Primary action button */
  action?: {
    text: string;
    onClick: () => void;
  };
  /** Called when the user dismisses the banner */
  onDismiss: () => void;
}

export function NotificationBanner({ message, label, action, onDismiss }: NotificationBannerProps) {
  return (
    <div className="border-b border-blue-200 bg-blue-50 dark:border-blue-900 dark:bg-blue-950/30 px-4 py-2.5">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-3">
        <p className="text-xs text-blue-800 dark:text-blue-300">
          {label && <span className="font-semibold">{label}</span>} {message}
        </p>
        <div className="flex items-center gap-2 shrink-0">
          {action && (
            <button
              onClick={action.onClick}
              className="rounded-md bg-blue-600 px-3 py-1 text-xs font-medium text-white hover:bg-blue-700"
            >
              {action.text}
            </button>
          )}
          <button
            onClick={onDismiss}
            className="text-blue-400 hover:text-blue-600 dark:text-blue-500 dark:hover:text-blue-300"
            aria-label="Dismiss"
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}

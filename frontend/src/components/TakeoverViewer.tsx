"use client";

import { useMemo, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

type Status = "connecting" | "connected" | "disconnected" | "error";

type MousePayload = {
  action: "click" | "wheel";
  x?: number;
  y?: number;
  button?: "left" | "middle" | "right";
  delta_x?: number;
  delta_y?: number;
};

type KeyboardPayload =
  | { action: "press"; key: string }
  | { action: "type"; text: string };

interface TakeoverViewerProps {
  imageUrl: string | null;
  currentUrl?: string;
  wsStatus: Status;
  controlActive: boolean;
  onRequestControl: () => void;
  onReleaseControl: () => void;
  onMouseAction: (payload: MousePayload) => void;
  onKeyboardAction: (payload: KeyboardPayload) => void;
}

export function TakeoverViewer({
  imageUrl,
  currentUrl,
  wsStatus,
  controlActive,
  onRequestControl,
  onReleaseControl,
  onMouseAction,
  onKeyboardAction,
}: TakeoverViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const imageRef = useRef<HTMLImageElement>(null);

  const statusLabel = useMemo(() => {
    if (controlActive) return "controlling";
    return wsStatus;
  }, [controlActive, wsStatus]);

  const resolvePoint = (clientX: number, clientY: number) => {
    const img = imageRef.current;
    if (!img) return null;

    const rect = img.getBoundingClientRect();
    const naturalWidth = img.naturalWidth;
    const naturalHeight = img.naturalHeight;
    if (!naturalWidth || !naturalHeight) {
      return null;
    }

    const containerRatio = rect.width / rect.height;
    const imageRatio = naturalWidth / naturalHeight;

    let renderedWidth = rect.width;
    let renderedHeight = rect.height;
    let offsetX = 0;
    let offsetY = 0;

    if (containerRatio > imageRatio) {
      renderedWidth = rect.height * imageRatio;
      offsetX = (rect.width - renderedWidth) / 2;
    } else {
      renderedHeight = rect.width / imageRatio;
      offsetY = (rect.height - renderedHeight) / 2;
    }

    const contentLeft = rect.left + offsetX;
    const contentTop = rect.top + offsetY;
    const contentRight = contentLeft + renderedWidth;
    const contentBottom = contentTop + renderedHeight;

    if (
      clientX < contentLeft ||
      clientX > contentRight ||
      clientY < contentTop ||
      clientY > contentBottom
    ) {
      return null;
    }

    return {
      x: ((clientX - contentLeft) / renderedWidth) * naturalWidth,
      y: ((clientY - contentTop) / renderedHeight) * naturalHeight,
    };
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-3">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium">Live Browser Control</span>
            <Badge variant={controlActive ? "default" : "secondary"}>
              {statusLabel}
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground">
            Click inside the live image to control the browser. Keyboard input
            works after the panel is focused.
          </p>
        </div>
        <div className="flex gap-2">
          {controlActive ? (
            <Button variant="outline" size="sm" onClick={onReleaseControl}>
              Release Control
            </Button>
          ) : (
            <Button size="sm" onClick={onRequestControl}>
              Take Control
            </Button>
          )}
        </div>
      </div>

      <div
        ref={containerRef}
        tabIndex={0}
        data-testid="takeover-container"
        className="relative min-h-[320px] overflow-hidden rounded-xl border border-border/60 bg-zinc-950 outline-none focus:ring-2 focus:ring-blue-500"
        onClick={(event) => {
          const point = resolvePoint(event.clientX, event.clientY);
          if (!controlActive || !point) return;
          onMouseAction({ action: "click", x: point.x, y: point.y });
        }}
        onWheel={(event) => {
          if (!controlActive) return;
          event.preventDefault();
          onMouseAction({
            action: "wheel",
            delta_x: event.deltaX,
            delta_y: event.deltaY,
          });
        }}
        onKeyDown={(event) => {
          if (!controlActive) return;
          if (event.metaKey || event.ctrlKey || event.altKey) return;

          if (event.key.length === 1) {
            event.preventDefault();
            onKeyboardAction({ action: "type", text: event.key });
            return;
          }

          const passthroughKeys = new Set([
            "Enter",
            "Tab",
            "Backspace",
            "Delete",
            "Escape",
            "ArrowUp",
            "ArrowDown",
            "ArrowLeft",
            "ArrowRight",
          ]);
          if (passthroughKeys.has(event.key)) {
            event.preventDefault();
            onKeyboardAction({ action: "press", key: event.key });
          }
        }}
      >
        {currentUrl && (
          <div className="absolute left-3 top-3 z-10 max-w-[80%] rounded-full bg-black/60 px-3 py-1 text-xs text-white backdrop-blur">
            {currentUrl}
          </div>
        )}

        {imageUrl ? (
          <img
            ref={imageRef}
            src={imageUrl}
            alt="Controlled browser"
            data-testid="takeover-image"
            className="h-full w-full object-contain"
          />
        ) : (
          <div className="flex h-full min-h-[320px] items-center justify-center text-center text-zinc-400">
            <div>
              <p className="text-lg font-medium">Waiting for a live browser page</p>
              <p className="mt-2 text-sm">
                Start an application or manual intervention flow, then request
                control here.
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

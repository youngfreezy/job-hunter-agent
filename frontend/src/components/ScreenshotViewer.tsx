"use client";

import { useEffect, useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";

interface ScreenshotViewerProps {
  imageUrl: string | null;
  currentUrl?: string;
  fps?: number;
  status?: "connecting" | "connected" | "disconnected" | "error";
}

export function ScreenshotViewer({
  imageUrl,
  currentUrl,
  fps,
  status = "connecting",
}: ScreenshotViewerProps) {
  const imgRef = useRef<HTMLImageElement>(null);
  const [dimensions, setDimensions] = useState({ w: 0, h: 0 });

  useEffect(() => {
    if (imgRef.current && imageUrl) {
      const img = new Image();
      img.onload = () => setDimensions({ w: img.width, h: img.height });
      img.src = imageUrl;
    }
  }, [imageUrl]);

  const statusColor = {
    connecting: "bg-yellow-500",
    connected: "bg-green-500",
    disconnected: "bg-zinc-400",
    error: "bg-red-500",
  }[status];

  return (
    <div className="relative w-full h-full bg-zinc-900 rounded-lg overflow-hidden flex items-center justify-center min-h-[400px]">
      {/* Status indicator */}
      <div className="absolute top-3 left-3 flex items-center gap-2 z-10">
        <div className={`w-2 h-2 rounded-full ${statusColor} animate-pulse`} />
        <span className="text-xs text-zinc-400">{status}</span>
        {fps && <span className="text-xs text-zinc-500">{fps} FPS</span>}
      </div>

      {/* Current URL */}
      {currentUrl && (
        <div className="absolute top-3 right-3 z-10">
          <Badge variant="secondary" className="text-xs max-w-[300px] truncate">
            {currentUrl}
          </Badge>
        </div>
      )}

      {/* Screenshot */}
      {imageUrl ? (
        <img
          ref={imgRef}
          src={imageUrl}
          alt="Live browser view"
          className="max-w-full max-h-full object-contain"
        />
      ) : (
        <div className="text-center text-zinc-500">
          <div className="w-16 h-16 border-2 border-zinc-600 border-t-zinc-300 rounded-full animate-spin mx-auto mb-4" />
          <p className="text-lg">Connecting to browser...</p>
          <p className="text-sm mt-1">
            The screenshot feed will appear here once the agent starts browsing.
          </p>
        </div>
      )}

      {/* Dimensions overlay */}
      {dimensions.w > 0 && (
        <div className="absolute bottom-3 right-3 text-xs text-zinc-500">
          {dimensions.w}x{dimensions.h}
        </div>
      )}
    </div>
  );
}

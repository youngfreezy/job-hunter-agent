export default function HistoryLoading() {
  return (
    <div className="min-h-screen bg-background">
      <div className="border-b border-border/70 px-6 py-3">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="h-6 w-36 bg-muted rounded animate-pulse" />
          <div className="h-8 w-24 bg-muted rounded animate-pulse" />
        </div>
      </div>
      <div className="max-w-5xl mx-auto px-6 py-8 space-y-6">
        <div className="space-y-2">
          <div className="h-8 w-48 bg-muted rounded animate-pulse" />
          <div className="h-4 w-80 bg-muted rounded animate-pulse" />
        </div>
        <div className="h-36 bg-muted rounded-2xl animate-pulse" />
        <div className="space-y-3">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="h-24 bg-muted rounded-2xl animate-pulse" />
          ))}
        </div>
      </div>
    </div>
  );
}

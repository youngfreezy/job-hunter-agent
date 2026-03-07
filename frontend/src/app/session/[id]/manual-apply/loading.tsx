export default function ManualApplyLoading() {
  return (
    <div className="min-h-screen bg-background">
      <nav className="sticky top-0 z-50 border-b border-border/70 bg-background/95 px-6 py-3 shadow-sm supports-[backdrop-filter]:bg-background/90 supports-[backdrop-filter]:backdrop-blur-md">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="h-6 w-40 bg-muted rounded-lg animate-pulse" />
          <div className="flex gap-3">
            <div className="h-8 w-20 bg-muted rounded-lg animate-pulse" />
            <div className="h-8 w-20 bg-muted rounded-lg animate-pulse" />
            <div className="h-8 w-20 bg-muted rounded-lg animate-pulse" />
          </div>
        </div>
      </nav>
      <div className="max-w-5xl mx-auto px-6 py-8 space-y-4">
        <div className="h-8 w-64 bg-muted rounded-lg animate-pulse" />
        <div className="h-4 w-96 bg-muted rounded animate-pulse" />
        <div className="space-y-3 mt-6">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-40 bg-muted rounded-xl animate-pulse" />
          ))}
        </div>
      </div>
    </div>
  );
}

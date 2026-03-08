export default function PivotResultLoading() {
  return (
    <div className="container mx-auto max-w-4xl p-6 space-y-6">
      <div className="h-8 w-48 bg-muted animate-pulse rounded" />
      <div className="flex justify-center py-12">
        <div className="h-32 w-32 bg-muted animate-pulse rounded-full" />
      </div>
      <div className="space-y-4">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="h-6 bg-muted animate-pulse rounded" />
        ))}
      </div>
      <div className="grid gap-4 mt-8">
        {[...Array(3)].map((_, i) => (
          <div key={i} className="h-40 bg-muted animate-pulse rounded-lg" />
        ))}
      </div>
    </div>
  );
}

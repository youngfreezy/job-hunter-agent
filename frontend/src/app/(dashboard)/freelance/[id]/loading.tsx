export default function FreelanceResultLoading() {
  return (
    <div className="container mx-auto max-w-4xl p-6 space-y-6">
      <div className="h-8 w-48 bg-muted animate-pulse rounded" />
      <div className="h-4 w-64 bg-muted animate-pulse rounded" />
      <div className="space-y-4 mt-8">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="h-36 bg-muted animate-pulse rounded-lg" />
        ))}
      </div>
    </div>
  );
}

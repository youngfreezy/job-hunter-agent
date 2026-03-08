export default function InterviewPrepLoading() {
  return (
    <div className="container mx-auto max-w-3xl p-6 space-y-6">
      <div className="h-8 w-64 bg-muted animate-pulse rounded" />
      <div className="h-48 bg-muted animate-pulse rounded-lg" />
      <div className="space-y-4">
        {[...Array(3)].map((_, i) => (
          <div key={i} className="h-24 bg-muted animate-pulse rounded-lg" />
        ))}
      </div>
    </div>
  );
}

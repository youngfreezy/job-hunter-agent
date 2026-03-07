export default function BillingLoading() {
  return (
    <main className="mx-auto max-w-3xl px-4 py-10">
      <div className="animate-pulse space-y-6">
        <div className="h-8 w-48 bg-muted rounded" />
        <div className="h-32 w-full bg-muted rounded-xl" />
        <div className="h-6 w-36 bg-muted rounded" />
        <div className="grid grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-28 bg-muted rounded-xl" />
          ))}
        </div>
        <div className="h-6 w-40 bg-muted rounded" />
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-12 bg-muted rounded" />
          ))}
        </div>
      </div>
    </main>
  );
}

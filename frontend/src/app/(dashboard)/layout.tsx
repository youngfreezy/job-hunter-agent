import { GlobalNav } from "@/components/nav/GlobalNav";

export default function DashboardGroupLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-background flex flex-col">
      <GlobalNav />
      <div className="flex-1">{children}</div>
    </div>
  );
}

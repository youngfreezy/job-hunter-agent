import { SessionShell } from "@/components/nav/SessionShell";

export default function SessionGroupLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <SessionShell>{children}</SessionShell>;
}

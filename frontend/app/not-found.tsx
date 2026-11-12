import { EmptyState } from "@/components/ui/EmptyState";

export default function NotFound() {
  return (
    <EmptyState
      title="Page not found"
      description="The page you are looking for does not exist or has moved."
      actionText="Go to home"
      actionHref="/dashboard"
    />
  );
}

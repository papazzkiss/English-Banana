import type { Metadata } from "next";

// The page is a client component, so its tab title ("Admin · Banana English") lives here.
// Its own template too: a child's title would otherwise lose the " · Banana English" suffix.
export const metadata: Metadata = { title: { default: "Admin", template: "%s · Banana English" } };

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}

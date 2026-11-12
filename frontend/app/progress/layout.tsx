import type { Metadata } from "next";

// The page is a client component, so its tab title ("Progress · Banana English") lives here.
export const metadata: Metadata = { title: "Progress" };

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}

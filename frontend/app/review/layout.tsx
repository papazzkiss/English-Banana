import type { Metadata } from "next";

// The page is a client component, so its tab title ("Content review · Banana English") lives here.
export const metadata: Metadata = { title: "Content review" };

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}

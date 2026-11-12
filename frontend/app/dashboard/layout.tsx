import type { Metadata } from "next";

// The page is a client component, so its tab title ("Home · Banana English") lives here.
export const metadata: Metadata = { title: "Home" };

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}

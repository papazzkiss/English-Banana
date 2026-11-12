import type { Metadata } from "next";

// The page is a client component, so its tab title ("Listening · Banana English") lives here.
export const metadata: Metadata = { title: "Listening" };

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}

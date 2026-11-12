import type { Metadata } from "next";

// The page is a client component, so its tab title ("Vocabulary · Banana English") lives here.
export const metadata: Metadata = { title: "Vocabulary" };

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}

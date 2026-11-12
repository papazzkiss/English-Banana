import type { Metadata } from "next";

// The page is a client component, so its tab title ("Users · Banana English") lives here.
export const metadata: Metadata = { title: "Users" };

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}

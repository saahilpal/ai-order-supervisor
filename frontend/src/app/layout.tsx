import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import Link from "next/link";
import { Activity, PackageCheck } from "lucide-react";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Order Supervisor",
  description: "Long-running AI workflow supervisor for order operations",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${inter.className} min-h-screen bg-background text-foreground`}>
        <header className="sticky top-0 z-30 border-b border-border/80 bg-white/90 backdrop-blur">
          <div className="mx-auto flex h-14 w-full max-w-7xl items-center justify-between px-4 sm:px-6">
            <Link
              href="/"
              className="flex min-w-0 items-center gap-2.5 text-sm font-semibold tracking-[0.01em] text-foreground transition hover:text-primary"
            >
              <span className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-sm">
                <PackageCheck className="size-4" />
              </span>
              <span className="truncate">Order Supervisor</span>
            </Link>
            <div className="flex items-center gap-2 rounded-lg border border-border bg-muted/40 px-2.5 py-1 text-xs font-medium text-muted-foreground">
              <Activity className="size-3.5 text-primary" />
              <span>Temporal POC</span>
            </div>
          </div>
        </header>
        <main className="mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 lg:py-8">
          {children}
        </main>
      </body>
    </html>
  );
}

import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import { ThemeToggle } from "@/components/theme-toggle";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "MonsoonQuant",
  description: "Pricing and hedging India's exchange-traded rainfall futures.",
};

const NAV = [
  { href: "/", label: "Overview" },
  { href: "/hedge", label: "Hedge Lab" },
  { href: "/basis", label: "Basis Map" },
  { href: "/track-record", label: "Track Record" },
  { href: "/learn", label: "Learn" },
  { href: "/methods", label: "Methods" },
];

const THEME_INIT_SCRIPT = `
(function () {
  try {
    var stored = localStorage.getItem("mq-theme");
    var theme = stored || (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    document.documentElement.setAttribute("data-theme", theme);
  } catch (e) {}
})();
`;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body className="min-h-full flex flex-col bg-background text-foreground">
        <header className="border-b border-border">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-6 py-4">
            <div className="flex items-center gap-6">
              <Link href="/" className="text-sm font-semibold tracking-tight">
                MonsoonQuant
              </Link>
              <nav className="flex gap-4 text-xs text-muted">
                {NAV.map((item) => (
                  <Link key={item.href} href={item.href} className="hover:text-foreground">
                    {item.label}
                  </Link>
                ))}
              </nav>
            </div>
            <ThemeToggle />
          </div>
        </header>
        <main className="flex-1">{children}</main>
        <footer className="border-t border-border">
          <div className="mx-auto max-w-6xl px-6 py-4 text-xs text-muted">
            Research analytics. Not investment advice.
          </div>
        </footer>
      </body>
    </html>
  );
}

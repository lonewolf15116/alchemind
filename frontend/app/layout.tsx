import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
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
  metadataBase: new URL("https://veridex.fyi"),
  title: {
    default: "Veridex — Red-team your strategy in 30 seconds",
    template: "%s · Veridex",
  },
  description:
    "Paste your strategy. Four independent AI critics return structured flaws, ranked by severity, in about 30 seconds. Pre-Mortem, Unit Economics, Adversarial Competitor, Execution Risk. No flattery.",
  keywords: [
    "strategy review",
    "AI critic",
    "pre-mortem",
    "unit economics",
    "red team",
    "startup strategy",
    "pitch feedback",
    "product strategy",
  ],
  authors: [{ name: "Mahesh Reddy Pagadala" }],
  creator: "Mahesh Reddy Pagadala",
  openGraph: {
    type: "website",
    url: "https://veridex.fyi",
    siteName: "Veridex",
    title: "Veridex — Red-team your strategy in 30 seconds",
    description:
      "Four independent AI critics stress-test your strategy. Structured flaws, ranked by severity. No flattery.",
    locale: "en_US",
  },
  twitter: {
    card: "summary_large_image",
    title: "Veridex — Red-team your strategy in 30 seconds",
    description:
      "Four independent AI critics stress-test your strategy. Structured flaws, ranked by severity. No flattery.",
    creator: "@0xShura",
    site: "@0xShura",
  },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-image-preview": "large",
      "max-snippet": -1,
    },
  },
  alternates: {
    canonical: "https://veridex.fyi",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        {children}
      </body>
    </html>
  );
}

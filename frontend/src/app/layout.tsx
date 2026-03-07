import type { Metadata } from "next";
import localFont from "next/font/local";
import NextTopLoader from "nextjs-toploader";
import "./globals.css";

const geistSans = localFont({
  src: "./fonts/GeistVF.woff",
  variable: "--font-geist-sans",
  weight: "100 900",
});
const geistMono = localFont({
  src: "./fonts/GeistMonoVF.woff",
  variable: "--font-geist-mono",
  weight: "100 900",
});

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || "https://jobhunteragent.com";

export const metadata: Metadata = {
  title: {
    default: "JobHunter Agent — AI-Powered Job Application Automation",
    template: "%s | JobHunter Agent",
  },
  description:
    "Automate your job search across LinkedIn, Indeed, Glassdoor & more. AI tailors your resume per role, submits applications, and you stay in control with two approval steps. Start with 3 free applications.",
  keywords: [
    "job application automation",
    "AI job search",
    "automated job applications",
    "resume optimization",
    "job board automation",
    "LinkedIn apply bot",
    "Indeed auto apply",
    "AI resume tailoring",
    "job search assistant",
    "apply to jobs automatically",
  ],
  authors: [{ name: "V2 Software LLC" }],
  creator: "V2 Software LLC",
  metadataBase: new URL(siteUrl),
  openGraph: {
    type: "website",
    locale: "en_US",
    url: siteUrl,
    siteName: "JobHunter Agent",
    title: "JobHunter Agent — Land More Interviews While Saving 15+ Hours a Week",
    description:
      "Your AI assistant finds the best roles across 5 job boards, tailors your resume for each one, and submits applications automatically. Start with 3 free applications.",
  },
  twitter: {
    card: "summary_large_image",
    title: "JobHunter Agent — AI-Powered Job Application Automation",
    description:
      "Automate job applications across LinkedIn, Indeed, Glassdoor & more. AI-tailored resumes, two approval checkpoints, pay per application.",
  },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-video-preview": -1,
      "max-image-preview": "large",
      "max-snippet": -1,
    },
  },
  alternates: {
    canonical: siteUrl,
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <head>
        {process.env.NEXT_PUBLIC_UMAMI_WEBSITE_ID && (
          <script
            defer
            src={`${process.env.NEXT_PUBLIC_UMAMI_URL || "http://localhost:3001"}/script.js`}
            data-website-id={process.env.NEXT_PUBLIC_UMAMI_WEBSITE_ID}
          />
        )}
      </head>
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        <NextTopLoader color="#3b82f6" showSpinner={false} height={2} />
        {children}
      </body>
    </html>
  );
}

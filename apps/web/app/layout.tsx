import type { Metadata, Viewport } from "next";
import { OfflineShellProvider } from "./serwist-provider";
import "./globals.css";

export const metadata: Metadata = {
  title: "Offline Reels",
  description: "Personal offline Reels application",
  applicationName: "Offline Reels",
  icons: {
    icon: "/icon.svg",
    apple: "/icon.svg",
  },
  appleWebApp: {
    capable: true,
    title: "Offline Reels",
    statusBarStyle: "default",
  },
};

export const viewport: Viewport = {
  themeColor: "#0f172a",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ru">
      <body><OfflineShellProvider>{children}</OfflineShellProvider></body>
    </html>
  );
}

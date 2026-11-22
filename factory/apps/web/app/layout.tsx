import type { ReactNode } from "react";
import { Geist } from "next/font/google";
import "./globals.css";
import { AppShell } from "./app-shell";
import { themeBootScript } from "@/lib/theme";

const geist = Geist({ subsets: ["latin"], variable: "--font-geist", display: "swap" });

// Owner data comes from the API on every request; never prerender it at build time.
export const dynamic = "force-dynamic";

export const metadata = {
  title: "Factory Agent OS",
  description: "Panel del dueño — conversaciones, pedidos, inventario, caja, proveedores y analítica",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="es" className={geist.variable} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeBootScript }} />
      </head>
      <body>
        <AppShell tenant="Del Campus Café">{children}</AppShell>
      </body>
    </html>
  );
}

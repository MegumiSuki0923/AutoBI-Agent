import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AutoBI 数据分析系统",
  description: "基于大模型与数仓的智能数据分析助手",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}

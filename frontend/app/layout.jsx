import "./globals.css";

export const metadata = {
  title: "Content Guard · 发布前先过一遍",
  description: "小红书带货文案的合规检查与改写",
};

export default function RootLayout({ children }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}

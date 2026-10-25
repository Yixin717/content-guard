/** @type {import('next').NextConfig} */
const nextConfig = {
  // 静态导出：D6 部署时把 out/ 交给 Nginx，后端 API 由 /api 反代
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
};

export default nextConfig;

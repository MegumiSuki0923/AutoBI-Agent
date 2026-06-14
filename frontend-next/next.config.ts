import type { NextConfig } from "next";

const backendUrl = process.env.AUTOBI_BACKEND_URL ?? 'http://127.0.0.1:8000';

const nextConfig: NextConfig = {
  output: 'standalone',
  allowedDevOrigins: ['192.168.6.150', '192.168.6.197'],
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;

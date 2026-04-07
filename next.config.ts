import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Suppress font preload warnings
  experimental: {
    optimizePackageImports: ['lucide-react'],
  },
  
  // Suppress external cookie warnings
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          {
            key: 'X-Content-Type-Options',
            value: 'nosniff',
          },
        ],
      },
    ];
  },
};

export default nextConfig;

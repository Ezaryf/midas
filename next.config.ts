import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Keep dev output away from production build output.
  // On Windows/OneDrive, a running `next dev` can lock `.next` and make
  // `next build` fail with EPERM while unlinking static assets.
  distDir: process.env.NODE_ENV === "development" ? ".next-dev" : ".next",

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

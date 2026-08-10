/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/v1/:path*",
        destination: `${process.env.BACKEND_URL || "http://localhost:8000"}/v1/:path*`,
      },
      {
        source: "/health",
        destination: `${process.env.BACKEND_URL || "http://localhost:8000"}/health`,
      },
    ];
  },
};

export default nextConfig;

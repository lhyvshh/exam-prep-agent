/** @type {import('next').NextConfig} */
const nextConfig = {
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  experimental: {
    middlewareClientMaxBodySize: "256mb",
    proxyTimeout: 600_000
  },
  reactStrictMode: true,
  async rewrites() {
    const backendBaseUrl = process.env.EXAM_PREP_BACKEND_URL ?? "http://127.0.0.1:8000";

    return [
      {
        source: "/api/v1/:path*",
        destination: `${backendBaseUrl}/api/v1/:path*`
      }
    ];
  }
};

module.exports = nextConfig;

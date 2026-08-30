import type { NextConfig } from "next";

const developmentScriptPolicy =
  process.env.NODE_ENV === "development" ? " 'unsafe-eval'" : "";
const contentSecurityPolicy = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${developmentScriptPolicy}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  "connect-src 'self' ws://127.0.0.1:* ws://localhost:*",
  "worker-src 'self' blob:",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ");

const disableStandaloneOutput = process.env.FOUNDER_NEXT_STANDALONE === "0";

const nextConfig: NextConfig = {
  distDir: process.env.FOUNDER_NEXT_DIST_DIR?.trim() || ".next",
  output: disableStandaloneOutput ? undefined : "standalone",
  devIndicators: false,
  async headers() {
    return [
      {
        headers: [
          {
            key: "Content-Security-Policy",
            value: contentSecurityPolicy,
          },
          {
            key: "Referrer-Policy",
            value: "no-referrer",
          },
          {
            key: "X-Content-Type-Options",
            value: "nosniff",
          },
        ],
        source: "/:path*",
      },
    ];
  },
  poweredByHeader: false,
  reactStrictMode: true,
  webpack(config, { webpack }) {
    config.resolve ??= {};
    config.resolve.symlinks = false;
    config.plugins ??= [];
    config.plugins.push(
      new webpack.NormalModuleReplacementPlugin(
        /^\.\/([A-Za-z]:\/.*)$/,
        (resource: { request: string }) => {
          resource.request = resource.request.slice(2);
        },
      ),
    );
    return config;
  },
};

export default nextConfig;

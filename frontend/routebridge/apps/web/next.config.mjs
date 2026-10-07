/** @type {import('next').NextConfig} */
// Demo mode (docker-compose.demo.yml): API_INTERNAL_URL is set at build time, the page calls /api on its own address and this server
// passes those calls on to the API. Normal builds leave it unset and the browser talks to the API address directly.
const apiInternal = process.env.API_INTERNAL_URL;

const nextConfig = {
  reactStrictMode: true,
  // Self-contained server bundle (.next/standalone) so the container image carries only what the server needs.
  output: 'standalone',
  // the live event stream must not be held back by compression; the tunnel compresses at its edge
  compress: !apiInternal,
  async rewrites() {
    return apiInternal ? [{ source: '/api/:path*', destination: `${apiInternal.replace(/\/$/, '')}/api/:path*` }] : [];
  },
};
export default nextConfig;

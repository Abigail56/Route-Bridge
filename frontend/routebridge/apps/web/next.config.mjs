/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Self-contained server bundle (.next/standalone) so the container image carries only what the server needs.
  output: 'standalone',
};
export default nextConfig;

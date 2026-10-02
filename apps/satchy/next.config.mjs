/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "api.terrasatch.com",
        pathname: "/assets/**",
      },
    ],
  },
};

export default nextConfig;

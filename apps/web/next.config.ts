import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  serverExternalPackages: [
    "@aws-sdk/credential-providers",
    "@aws-sdk/client-lambda",
  ],
};

export default nextConfig;

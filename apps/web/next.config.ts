import type { NextConfig } from "next";

const config: NextConfig = {
  output: "standalone",
  experimental: { cpus: 1 },
  poweredByHeader: false,
};
export default config;

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Served from https://nrjalela.github.io/opsmesh/
export default defineConfig({
  base: "/opsmesh/",
  plugins: [react()],
  test: {
    environment: "jsdom",
  },
});

import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "Segoe UI",
          "-apple-system",
          "BlinkMacSystemFont",
          "Roboto",
          "Helvetica Neue",
          "sans-serif",
        ],
      },
      colors: {
        fabric: {
          blue: "#0078d4",
          "blue-dark": "#106ebe",
          "blue-light": "#deecf9",
          "gray-10": "#faf9f8",
          "gray-20": "#f3f2f1",
          "gray-30": "#edebe9",
          "gray-130": "#605e5c",
          "gray-160": "#323130",
          "gray-190": "#201f1e",
          success: "#107c10",
          warning: "#ffaa44",
          error: "#d13438",
        },
      },
      boxShadow: {
        sm: "0 1px 2px rgba(0,0,0,0.04), 0 1px 1px rgba(0,0,0,0.06)",
        card: "0 2px 6px rgba(0,0,0,0.05), 0 0 1px rgba(0,0,0,0.08)",
      },
    },
  },
  plugins: [],
} satisfies Config;

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bio: {
          bg: "#0a0f14",
          card: "#141b22",
          border: "#1e2a35",
          accent: "#00bfa5",
          muted: "#7a8a9a",
        },
      },
    },
  },
  plugins: [],
};

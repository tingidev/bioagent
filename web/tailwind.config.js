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
        phase: {
          research: "#60a5fa",   // blue-400
          plan: "#fbbf24",       // amber-400
          execute: "#34d399",    // emerald-400
          synthesize: "#c084fc", // purple-400
        },
      },
      animation: {
        scan: "scan 2s ease-in-out infinite",
      },
      keyframes: {
        scan: {
          "0%": { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(400%)" },
        },
      },
    },
  },
  plugins: [],
};

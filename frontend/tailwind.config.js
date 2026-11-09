/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: { 50: "#fdf6ee", 100: "#f9e8d4", 400: "#e3a86b", 500: "#d48c4a", 600: "#b8703a", 700: "#92562f" },
        ink: { 900: "#2b2420", 700: "#4a403a", 500: "#7a6e66", 300: "#b9aea6" },
      },
      fontFamily: { sans: ["Inter", "system-ui", "Segoe UI", "Roboto", "sans-serif"] },
    },
  },
  plugins: [],
};

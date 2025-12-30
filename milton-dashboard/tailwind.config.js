/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        "nexus-blue": "#2563EB",
        "cortex-purple": "#7C3AED",
        "frontier-teal": "#059669",
        "success-green": "#10B981",
        "warning-amber": "#F59E0B",
        "error-red": "#EF4444",
      },
      fontFamily: {
        mono: ["Fira Code", "Courier New", "monospace"],
      },
    },
  },
  plugins: [],
};

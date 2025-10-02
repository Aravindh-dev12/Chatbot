/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/**/*.{js,jsx,ts,tsx}", // <--- This line is essential
    "./public/index.html",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
}
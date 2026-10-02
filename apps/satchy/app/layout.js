import "./globals.css";

export const metadata = {
  title: "Satchy · TerraSatch",
  description: "Satchy connects your TerraSatch workspace, field context, and approved actions.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

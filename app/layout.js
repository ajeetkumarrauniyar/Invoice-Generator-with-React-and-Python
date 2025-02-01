import './globals.css'
import { Inter as FontSans } from 'next/font/google'
import { Toaster } from "@/components/ui/toaster"

const fontSans = FontSans({
  subsets: ['latin'],
  variable: '--font-sans',
  display: 'swap',
  weight: ['400', '500', '600', '700'],
})

export const metadata = {
  title: 'Invoice Generator',
  description: 'Generate invoices with customizable parameters',
}

export default function RootLayout({ children }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${fontSans.variable} font-sans antialiased`}>
        {children}
        <Toaster />
      </body>
    </html>
  )
} 
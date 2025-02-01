# Invoice Generator

A modern, full-stack invoice generation application built with Next.js and Python. This application allows users to generate multiple invoices based on input parameters and export them as CSV files.

## 🚀 Features

### Invoice Generation
- Generate multiple invoices simultaneously with customizable parameters
- Support for various invoice formats and templates
- Automatic invoice numbering with customizable prefixes
- Configurable date formats and time zones
- Line item management with automatic calculations
- Tax rate configuration and automatic tax calculations
- Support for multiple currencies
- Customizable company branding and logos

### Data Management
- Bulk invoice generation from CSV input
- Export invoices to CSV format for easy integration
- Save and load invoice templates
- Client information management
- Product/service catalog management

### User Interface
- Modern React-based UI with ShadCN components
- Intuitive form interface with real-time validation
- Live preview of invoice changes
- Toast notifications for operation feedback
- Responsive design for all devices
- Dark/Light mode support

### Data Validation & Security
- Real-time form validation
- Input sanitization
- Secure data handling
- Error handling with detailed feedback

## 🛠️ Tech Stack

### Frontend
- Next.js 14
- React
- TailwindCSS
- ShadCN UI Components
- React Hook Form

### Backend
- Python
- FastAPI (for invoice generation logic)

## 📦 Prerequisites

Before you begin, ensure you have the following installed:
- Node.js (v18 or higher)
- Python (v3.8 or higher)
- npm or yarn
- pip (Python package manager)

## 🔧 Installation

1. Clone the repository:
```bash
git clone <your-repo-url>
cd invoice_generator
```

2. Install frontend dependencies:
```bash
npm install
# or
yarn install
```

3. Set up Python virtual environment and install dependencies:
```bash
python -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate
pip install -r requirements.txt
```

## 🚀 Running the Application

1. Start the frontend development server:
```bash
npm run dev
# or
yarn dev
```

2. The application will be available at `http://localhost:3000`

## 📁 Project Structure

```
invoice_generator/
├── app/                    # Next.js app directory
│   ├── api/               # API routes
│   ├── layout.js          # Root layout
│   └── page.js            # Home page
├── components/            # React components
│   ├── ui/               # ShadCN UI components
│   └── InvoiceForm.js    # Main invoice form
├── hooks/                 # Custom React hooks
├── scripts/              # Python scripts for invoice generation
└── public/               # Static assets
```

## 🔄 Development Workflow

1. Make changes to the frontend code in the `app` and `components` directories
2. Python scripts for invoice generation are located in the `scripts` directory
3. API routes are handled in the `app/api` directory

## 🧪 Testing

```bash
# Run frontend tests
npm test

# Run Python tests
python -m pytest
```

## 📝 Environment Variables

Create a `.env.local` file in the root directory with the following variables:
```
NEXT_PUBLIC_API_URL=http://localhost:3000
```

## 🤝 Contributing

1. Fork the repository
2. Create a new branch
3. Make your changes
4. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 👥 Support

For support, please open an issue in the GitHub repository or contact the maintainers. 
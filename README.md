# Invoice Generator

A powerful and flexible invoice generation tool built with Next.js and Python. Designed for small businesses and wholesale traders, this application allows users to easily generate multiple invoices based on input parameters and export them as CSV files.

🔗 **Live Link**: [Invoice Generator](https://invoice-generator-f1nn.onrender.com/)  
📂 **Repo Link**: [GitHub Repository](https://github.com/ajeetkumarrauniyar/Invoice-Generator-with-React-and-Python/tree/v2.0.0)  

----

## 🚀 Features  

### ✅ **Optimized Invoice Generation**  
- Prevents floating-point inaccuracies in tax and margin calculations.  
- Ensures accurate invoice amounts and structured invoice formatting.
- Generate multiple invoices simultaneously with customizable parameters.
- Automatic invoice numbering with customizable prefixes, like UNR-, for consistency

### 🔄 **Flexible Data Input**  
- Supports **predefined party data from a CSV file** or **auto-generates parties dynamically**.  
- Eliminates the need for manually preparing party data.

### 🤖 **Auto-Generated Party Data**  
- Users can generate parties automatically by providing **totalAmount** and **partyLimit**.  
- If `generateParties` is enabled, the API directly generates party data, streamlining the process.  

### 📅 **Month-Based Sorting for Financial Year**  
- Invoices are **sorted from April to March**, following the financial year, ensuring chronological organization and preventing errors caused by unordered records.
- Invoices are sorted by month and invoice number, making financial tracking and auditing easier.

### 🛡️ **Enhanced Error Handling & Validation**  
- **Zod-based validation** ensures data accuracy.
- Real-time form validation to prevent errors during data entry.
- Prevents **empty CSV downloads**, **invalid party limits**, and incorrect entries.
- Input sanitization ensures clean data and secure handling.
- Improves error tracking with better logging and debugging.  

### 🔢 **Standardized Naming Convention**  
- Invoice numbers follow a **structured format with prefixes like `UNR-`**, ensuring consistency.

### 📊 **Efficient CSV Output**
- Export invoices to **CSV format** for easy integration with external systems or record-keeping.
- Organized output with invoices sorted by month and invoice number, enhancing financial record-keeping. 

### 🤖 **User Interface**
- Modern React-based UI using ShadCN components for a sleek and responsive design.
- Intuitive form interface with real-time validation for smooth user experience.
- Toast notifications for real-time feedback during operations.
- Responsive design for accessibility across all devices, from mobile to desktop.

### 🔒 **Data Security**
- Secure data handling ensures that sensitive information is well-protected.
- Detailed error handling and real-time feedback for seamless operation.

---  

## 🏢 **Why is it Helpful for Businesses?**  
This tool is designed to **simplify invoice generation** for small businesses, traders, and wholesalers dealing with **unregistered parties**. It:  
✔️ **Saves Time** – No need to manually enter party details; supports auto-generation.  
✔️ **Eliminates Errors** – Prevents floating-point inaccuracies and unordered invoice records.  
✔️ **Ensures Compliance** – Generates structured and validated invoices.  
✔️ **Organizes Financial Records** – Invoices are sorted in a proper financial-year format.  

---

## 🛠️ Tech Stack  
- **Frontend**: Next.js, React, Tailwind CSS, ShadCn UI  
- **Backend**: Python (FastAPI)  
- **Validation**: Zod  
- **State Management**: React Hook Form

---

## 📦 Prerequisites

Before you begin, ensure you have the following installed:
- Node.js (v18 or higher)
- Python (v3.8 or higher)
- npm or yarn
- pip (Python package manager)

---  

## 🔧 Installation

1. Clone the repository:
```bash
git clone https://github.com/ajeetkumarrauniyar/Invoice-Generator-with-React-and-Python
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

---

## 🚀 Running the Application

1. Start the frontend development server:
```bash
npm run dev
# or
yarn dev
```

2. The application will be available at `http://localhost:3000`

---   

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
---

## 🔄 Development Workflow

1. Make changes to the frontend code in the `app` and `components` directories
2. Python scripts for invoice generation are located in the `scripts` directory
3. API routes are handled in the `app/api` directory

---

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
PYTHON_PATH=your_path
```

---

## 🤝 Contributing

1. Fork the repository
2. Create a new branch
3. Make your changes
4. Submit a pull request

---   

## 📜 License  
This project is open-source and available for use under the MIT License. 

---

## 👥 Support

For support, please open an issue in the GitHub repository or contact the maintainers. 

---  

Start generating invoices effortlessly with [Invoice Generator](https://invoice-generator-f1nn.onrender.com/) today! 🚀

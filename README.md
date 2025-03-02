# InvoiceFlow Pro (formerly Invoice Generator) 🌟

A comprehensive invoicing and payment scheduling system designed to automate invoice generation and manage daily payment limits efficiently. Built for small businesses and wholesale traders. 💼

🔗 **Live Link**: [InvoiceFlow Pro](https://invoice-generator-f1nn.onrender.com/) 🚀  
📂 **Repo Link**: [GitHub Repository](https://github.com/ajeetkumarrauniyar/Invoice-Generator-with-React-and-Python/tree/v2.0.0) 📁  

---

## 🚀 Key Features

### 🎯 Core Functionality
- **Dual Mode Operation**:
  - 📋 **Invoice Generation**: Create purchase/sales invoices with customizable rates, margins, and party data.
  - 💸 **Payment Scheduling**: Process payments with ₹20,000 daily limits, splitting large invoices across days.

### 🔧 Technical Excellence
- 🧮 **Optimized Calculations**:
  - Prevents floating-point inaccuracies in tax/margin calculations
  - Ensures 100% accurate invoice amounts
  - Generate multiple invoices simultaneously with customizable parameters.
  - 🔢 Structured invoice numbering (e.g., `UNR-001`, `APR-042`)

- 🔄 **Flexible Data Input**  
    - Supports **predefined party data from a CSV file** or **auto-generates parties dynamically**.  
    - Eliminates the need for manually preparing party data.

- 🗃️ **Smart Data Handling**:
  - 👨🌾 Auto-generate realistic party names (farmers/businesses)
  - 📤 Import CSV data or generate parties dynamically
  - 📅 Month-based sorting (**April-March** financial year format)

### ✨ User Experience
- 🖥️ **Modern UI**:
  - Responsive React interface with ShadCN components
  - 🛡️ Real-time form validation & toast notifications
  - 📱 Cross-device compatibility (mobile/desktop)

- 🔒 **Enterprise-Grade Security**:
  - ✅ Zod schema validation
  - 🧼 Input sanitization
  - 🚨 Error tracking with detailed logging

### 📊 Output Management
- 📥 **CSV Export**:
  - Download organized payment schedules
  - 📂 Standardized financial records
  - 🚫 Prevents empty/invalid CSV exports
  - Easy integration with external systems, ERPs or record-keeping.

## 🛠️ Tech Stack
- ⚛️ **Frontend**: Next.js, React, Tailwind CSS  
- 🐍 **Backend**: Python (Pandas), FastAPI  
- ✅ **Validation**: Zod, React Hook Form  
- 🎨 **UI Components**: ShadCN  

---

## 🏁 Getting Started

### 📋 Prerequisites
Before you begin, ensure you have the following installed:
- Node.js v18+ 🟢
- Python 3.8+ 🐍
- npm/yarn 📦
- pip 🧪

### ⚙️ Installation

1. Clone the repository
2. Install frontend dependencies
3. Set up Python virtual environment and install dependencies

```bash
git clone https://github.com/ajeetkumarrauniyar/Invoice-Generator-with-React-and-Python
cd Invoice-Generator-with-React-and-Python
npm install
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```
---

## 🧑💻 Usage Guide

### 📤 Generate Invoices (/generate-invoices)
1. 🎛️ Select invoice type (Purchase/Sales)
2. 📅 Set date range & financial parameters
3. 📥 Upload CSV or auto-generate parties
4. ⬇️ Download formatted CSV

### 💸 Process Payments (Homepage)
1. 📤 Upload CSV with columns:

- Date, Bill, Party Name, Amount

2. ⬇️ Download payments.csv with daily payment splits

---

## 🏗️ Project Structure

```
📁 invoiceflow-pro/
├── 📂 app/                  
│   ├── 📂 api/              # Next.js API routes
│   └── 📄 page.js           # Main UI
├── 📂 components/           
│   └── 📄 InvoiceForm.js    # Core form logic
├── 📂 scripts/              
│   ├── 🐍 generate_invoices.py  # Invoice logic
│   └── 🐍 process_payments.py   # Payment scheduler
└── 📂 public/               # Static assets
```
---

## 🔄 Development Workflow
1. 🎨 Frontend: Modify app/ & components/

2. ⚙️ Backend: Edit Python scripts in scripts/

3. 🌐 API: Update routes in app/api/

```bash
# Start dev server
npm run dev 
# or
yarn dev
```

---   

## 🧪 Testing

```bash
# Run frontend tests
npm test

# Run Python tests
python -m pytest
```

##  🌐 Deployment

Create a `.env.local` file in the root directory with the following variables:
```env
PYTHON_PATH=your_path
```

---

## 🤝 Contributing

1. 🍴 Fork repository
2. 🌿 Create feature branch
3. 🔧 Make your changes
4. 🔀 Submit [PR](https://github.com/ajeetkumarrauniyar/Invoice-Generator-with-React-and-Python/pulls) with detailed description

---   

## 📜 License  
This project is open-source and available for use under the MIT License - See [LICENSE 📃](https://github.com/ajeetkumarrauniyar/Invoice-Generator-with-React-and-Python/blob/main/LICENSE.md). 

---

## ❓ Support

Open issues on [GitHub 🐛] (https://github.com/ajeetkumarrauniyar/Invoice-Generator-with-React-and-Python/issues) or contact maintainers. 📧

---  
[Live Demo 🌐](https://invoice-generator-f1nn.onrender.com/) | Full Documentation 📚

Start generating invoices effortlessly with [Invoice Generator](https://invoice-generator-f1nn.onrender.com/) today! 🚀

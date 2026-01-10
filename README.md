<<<<<<< HEAD
# 1st Month Project - User Authentication System

This is a scoped version of the groundwater-platform project, containing only the deliverables for the **1st month report**. The project demonstrates a complete user authentication system with database setup, backend API, and frontend UI.

## 📋 Project Scope (1st Month)

This project includes:

- ✅ **Users Entity Database**: PostgreSQL database with users table supporting 3 roles
- ✅ **Authentication System**: JWT-based authentication with token refresh
- ✅ **Login UI**: React-based login interface with role-based access
- ✅ **3 User Roles**: Admin, Analyst, and Viewer with different permissions
- ✅ **Protected Routes**: Dashboard accessible only to authenticated users

## 🏗️ Project Structure

```
abc/
├── backend/                 # Node.js/Express/TypeScript backend
│   ├── src/
│   │   ├── config/         # Database and environment configuration
│   │   ├── controllers/    # Authentication controller
│   │   ├── middleware/     # Auth, role, and error handling middleware
│   │   ├── models/         # User model (Sequelize ORM)
│   │   ├── routes/         # Authentication routes
│   │   ├── services/       # Authentication service
│   │   ├── utils/          # JWT and logger utilities
│   │   ├── app.ts          # Express app setup
│   │   └── server.ts       # Server entry point
│   ├── package.json
│   ├── tsconfig.json
│   └── .env
├── frontend/               # React/TypeScript frontend
│   ├── src/
│   │   ├── components/     # ProtectedRoute component
│   │   ├── context/        # Authentication context
│   │   ├── hooks/          # useAuth hook
│   │   ├── pages/          # Login and Dashboard pages
│   │   ├── routes/         # App routing
│   │   ├── services/       # API client and auth service
│   │   ├── types/          # TypeScript types
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   └── index.css
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── tailwind.config.js
│   └── index.html
└── database/
    └── seeders/
        └── seed.sql        # Initial user data (3 users)
```

## 🚀 Setup Instructions

### Prerequisites

- Node.js (v18 or higher)
- PostgreSQL (v14 or higher)
- npm or yarn

### 1. Database Setup

1. Create a PostgreSQL database:
```sql
CREATE DATABASE groundwater_db;
```

2. Run the seed file to create users:
```bash
psql -U postgres -d groundwater_db -f database/seeders/seed.sql
```

### 2. Backend Setup

1. Navigate to backend directory:
```bash
cd backend
```

2. Install dependencies:
```bash
npm install
```

3. Configure environment variables:
   - Update `.env` file with your database credentials
   - Default configuration uses:
     - Database: `groundwater_db`
     - User: `postgres`
     - Password: `040812` (change this!)
     - Port: `5432`

4. Start the backend server:
```bash
npm run dev
```

The backend will run on `http://localhost:5000`

### 3. Frontend Setup

1. Navigate to frontend directory:
```bash
cd frontend
```

2. Install dependencies:
```bash
npm install
```

3. Start the development server:
```bash
npm run dev
```

The frontend will run on `http://localhost:5173`

## 🔐 Test Credentials

The system comes with 3 pre-configured users:

| Role | Email | Password |
|------|-------|----------|
| **Admin** | admin@example.com | admin123 |
| **Analyst** | analyst@example.com | analyst123 |
| **Viewer** | viewer@example.com | viewer123 |

## 🎯 Features Demonstrated

### Backend Features
- User model with password hashing (bcrypt)
- JWT token generation and verification
- Token refresh mechanism
- Role-based authorization middleware
- RESTful API endpoints for authentication
- Error handling and validation (Joi)
- Database connection with Sequelize ORM

### Frontend Features
- Login page with form validation
- Authentication context and hooks
- Protected routes with role checking
- Token storage and automatic refresh
- Dashboard displaying user information
- Responsive UI with Tailwind CSS

## 📡 API Endpoints

### Authentication Routes (`/api/v1/auth`)

- `POST /register` - Register a new user
- `POST /login` - Login with email and password
- `POST /refresh` - Refresh access token
- `GET /me` - Get current user (protected)
- `POST /logout` - Logout (protected)

## 🔧 Technology Stack

### Backend
- **Runtime**: Node.js with TypeScript
- **Framework**: Express.js
- **Database**: PostgreSQL with Sequelize ORM
- **Authentication**: JWT (jsonwebtoken)
- **Password Hashing**: bcrypt
- **Validation**: Joi
- **Security**: Helmet, CORS, Rate Limiting

### Frontend
- **Framework**: React 18 with TypeScript
- **Routing**: React Router v6
- **Styling**: Tailwind CSS
- **HTTP Client**: Axios
- **Build Tool**: Vite

## 📝 What's NOT Included (Future Months)

This 1st month scope does NOT include:
- Wells, water samples, or parameters entities
- ML service integration for predictions
- Map visualizations
- CSV import functionality
- Activity logs and alerts
- Admin panel features
- Data analytics and charts

These features are part of the full 10-month groundwater-platform project.

## 🐛 Troubleshooting

### Backend won't start
- Ensure PostgreSQL is running
- Check database credentials in `.env`
- Verify port 5000 is not in use

### Frontend won't connect to backend
- Ensure backend is running on port 5000
- Check CORS settings in backend `.env`
- Verify API_URL in frontend (defaults to `http://localhost:5000/api/v1`)

### Login fails
- Ensure database has been seeded with users
- Check browser console for error messages
- Verify JWT secrets are set in backend `.env`

## 📄 License

MIT

## 👨‍💻 Author

1st Month Project - Groundwater Platform Authentication System

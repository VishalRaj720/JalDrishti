# Groundwater Quality & Aquifer Vulnerability Prediction Platform

A production-ready full-stack ML platform for predicting groundwater quality degradation and aquifer vulnerability in regions near uranium in-situ recovery (ISR) mining sites. Uses machine learning on Indian groundwater datasets to identify contamination risks and support smarter monitoring network design.

## 🌟 Features

- **ML-Powered Predictions**: RandomForest and XGBoost models predict uranium contamination levels
- **Interactive Dashboard**: Real-time visualization of wells, risk levels, and water quality data
- **Risk Classification**: Automatic classification into LOW/MEDIUM/HIGH/VERY_HIGH risk categories
- **Role-Based Access**: Admin, Analyst, and Viewer roles with different permissions
- **Geospatial Visualization**: Interactive maps showing well locations and risk zones
- **RESTful API**: Complete backend API with authentication and authorization
- **Responsive UI**: Modern React interface with Tailwind CSS

## 🏗️ Architecture

```
groundwater-platform/
├── backend/          # Node.js + Express + PostgreSQL + Sequelize
├── ml-service/       # Python + FastAPI + scikit-learn + XGBoost
├── frontend/         # React + TypeScript + Vite + Tailwind CSS
├── infra/            # Docker configuration
├── database/         # SQL migrations and seed data
└── docs/             # Documentation
```

## 🚀 Quick Start

### Prerequisites

- **Docker & Docker Compose** (recommended)
- OR manually:
  - Node.js 18+
  - Python 3.10+
  - PostgreSQL 15+
  - Redis 7+

### Option 1: Docker (Recommended)

1. **Clone the repository**
   ```bash
   cd groundwater-platform
   ```

2. **Set up environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **Start all services**
   ```bash
   cd infra
   docker-compose up -d
   ```

4. **Access the application**
   - Frontend: http://localhost
   - Backend API: http://localhost:5000
   - ML Service: http://localhost:8000
   - API Docs: http://localhost:8000/docs

5. **Default credentials**
   - Email: `admin@example.com`
   - Password: `admin123`

### Option 2: Manual Setup

#### Backend

```bash
cd backend
npm install
cp ../.env.example .env
# Edit .env with your database credentials
npm run dev
```

#### ML Service

```bash
cd ml-service
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# Generate synthetic training data and train models
python -m app.data.generate_synthetic_data
uvicorn app.main:app --reload
```

#### Frontend

```bash
cd frontend
npm install
npm run dev
```

## 📊 ML Models

The platform uses two machine learning models:

1. **RandomForest Regressor**
   - Ensemble method with 100 trees
   - Robust to outliers
   - Feature importance analysis

2. **XGBoost Regressor**
   - Gradient boosting algorithm
   - High accuracy
   - Handles missing values

### Features Used

- Distance from ISR site (km)
- Well depth (meters)
- pH level
- Electrical conductivity (µS/cm)
- Dissolved oxygen (mg/L)
- Temperature (°C)

### Risk Classification

- **LOW**: < 15 µg/L uranium
- **MEDIUM**: 15-30 µg/L (WHO guideline: 30 µg/L)
- **HIGH**: 30-60 µg/L
- **VERY_HIGH**: > 60 µg/L

## 🔐 Authentication & Authorization

### Roles

- **Admin**: Full access to all features, user management
- **Analyst**: Can create wells, samples, and run predictions
- **Viewer**: Read-only access to dashboards

### API Authentication

All API requests require a JWT token in the Authorization header:

```
Authorization: Bearer <access_token>
```

Tokens expire after 1 hour. Use the refresh token to get a new access token.

## 📡 API Endpoints

### Authentication
- `POST /api/v1/auth/register` - Register new user
- `POST /api/v1/auth/login` - Login
- `POST /api/v1/auth/refresh` - Refresh access token
- `GET /api/v1/auth/me` - Get current user

### Wells
- `GET /api/v1/wells` - List wells (with filters)
- `POST /api/v1/wells` - Create well (Admin/Analyst)
- `GET /api/v1/wells/:id` - Get well details
- `PUT /api/v1/wells/:id` - Update well (Admin/Analyst)
- `DELETE /api/v1/wells/:id` - Delete well (Admin)
- `GET /api/v1/wells/map` - Get wells for map view

### Water Samples
- `GET /api/v1/wells/:wellId/samples` - Get samples for a well
- `POST /api/v1/wells/:wellId/samples` - Add sample (Admin/Analyst)
- `GET /api/v1/samples/:id` - Get sample details
- `DELETE /api/v1/samples/:id` - Delete sample (Admin)

### Predictions
- `POST /api/v1/predictions` - Create prediction (Admin/Analyst)
- `GET /api/v1/wells/:wellId/predictions` - Get predictions for a well
- `GET /api/v1/predictions/summary` - Get risk summary statistics

### ML Service
- `POST /ml/train` - Train ML models
- `POST /ml/predict` - Make prediction
- `GET /ml/health` - Health check

## 🗄️ Database Schema

### Key Tables

- **users**: User accounts with roles
- **wells**: Well locations and metadata
- **water_samples**: Water quality measurements
- **predictions**: ML prediction results
- **alerts**: Threshold violation alerts
- **parameters**: Water quality parameter definitions
- **activity_logs**: Audit trail

## 🎨 Frontend Pages

- **Login**: Authentication page
- **Dashboard**: Main view with map, risk summary, and charts
- **Admin Panel**: Wells, samples, and user management
- **Not Found**: 404 error page

## 🧪 Testing

### Backend
```bash
cd backend
npm test
```

### ML Service
```bash
cd ml-service
pytest
```

### Frontend
```bash
cd frontend
npm test
```

## 📦 Deployment

### Production Checklist

1. **Change JWT secrets** in `.env`
2. **Use strong database passwords**
3. **Enable HTTPS** (configure nginx or use a reverse proxy)
4. **Set `NODE_ENV=production`**
5. **Configure CORS** to allow only your frontend domain
6. **Set up database backups**
7. **Configure logging** and monitoring
8. **Use migrations** instead of `sequelize.sync()`

### Environment Variables

See `.env.example` for all required environment variables.

## 🛠️ Development

### Project Structure

```
backend/
├── src/
│   ├── config/       # Database and environment config
│   ├── models/       # Sequelize models
│   ├── middleware/   # Auth, error handling
│   ├── routes/       # API routes
│   ├── controllers/  # Request handlers
│   ├── services/     # Business logic
│   └── utils/        # Helper functions

ml-service/
├── app/
│   ├── core/         # Config, schemas, utilities
│   ├── data/         # Data generation
│   └── models/       # Trained ML models

frontend/
├── src/
│   ├── components/   # React components
│   ├── pages/        # Page components
│   ├── services/     # API clients
│   ├── context/      # React context
│   ├── hooks/        # Custom hooks
│   └── types/        # TypeScript types
```

### Adding New Features

1. **Backend**: Add route → controller → service → model
2. **ML Service**: Update schemas → add endpoint → implement logic
3. **Frontend**: Create service → add component → update routes

## 📝 License

MIT

## 🤝 Contributing

Contributions welcome! Please follow the existing code style and add tests for new features.

## 📧 Support

For issues and questions, please open a GitHub issue.

---

**Built with ❤️ for groundwater quality monitoring and environmental protection**

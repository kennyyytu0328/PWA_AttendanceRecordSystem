<p align="center">
  <img src="gogo_fresh.jpg" alt="GoGoFresh Logo" width="280" />
</p>

<h1 align="center">GoGoFresh Attendance Record System</h1>

<p align="center">
  Zero-Trust PWA Attendance System for hybrid work (Office + WFH).<br/>
  Replaces physical punch clocks with biometric-bound, location-verified digital attendance.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Next.js-16-black?logo=next.js" alt="Next.js" />
  <img src="https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi" alt="FastAPI" />
  <img src="https://img.shields.io/badge/PostgreSQL-16-336791?logo=postgresql" alt="PostgreSQL" />
  <img src="https://img.shields.io/badge/WebAuthn-FIDO2-4285F4?logo=google" alt="WebAuthn" />
  <img src="https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker" alt="Docker" />
  <img src="https://img.shields.io/badge/Tests-343_passing-brightgreen" alt="Tests" />
</p>

---

## Features

- **Biometric Authentication** — WebAuthn/FIDO2 (Windows Hello, Touch ID, etc.) for daily punch-in
- **GPS Location Verification** — Haversine-based geofencing (2km threshold) auto-detects Office vs. WFH
- **Immutable Event Sourcing** — All punches recorded with full metadata (GPS, accuracy, IP, work mode); no updates or deletes
- **Tardiness Detection** — Real-time LATE / EARLY_LEAVE / LATE_AND_EARLY_LEAVE alerts with configurable grace period
- **Late/Early-Leave Reasons** — Employees submit reasons immediately after a tardy punch
- **Role-Based Access** — 4-tier permission hierarchy (EMPLOYEE < MANAGER < HR < ADMIN)
- **Team & Reports** — Managers view team attendance; HR generates filtered reports with CSV/JSON/Excel export
- **Admin Panel** — Employee CRUD, office location config, department management, grace period settings
- **Compliant Employee Lifecycle** — Soft-delete ("mark as resigned") preserves attendance history as required by Taiwan Labor Standards Act §30(5) (5-year retention); HR can re-include resigned employees in Reports / Exports via an audit toggle
- **PWA** — Installable on mobile/desktop for native-like experience
- **i18n** — English and Traditional Chinese (繁體中文)

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16 (App Router), React 19, TailwindCSS 4, Framer Motion, Zod |
| Backend | Python 3.12+, FastAPI, SQLAlchemy 2 (async), SQLModel, Alembic |
| Database | PostgreSQL 16 |
| Auth | WebAuthn/FIDO2 (`@simplewebauthn/browser` + `webauthn`), JWT (`python-jose`) |
| Geospatial | Haversine formula with configurable office location |
| Testing | pytest + pytest-asyncio (backend), Vitest + Testing Library + Playwright (frontend) |
| Container | Docker Compose |
| Icons | Lucide React |

## Architecture

```
┌─────────────────────────────────────────────────┐
│                   Frontend (PWA)                │
│         Next.js 16 · React 19 · TailwindCSS     │
│                                                 │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐  │
│  │Login │ │Punch │ │Attend│ │ Team │ │Admin │  │
│  │      │ │      │ │ance  │ │      │ │      │  │
│  └──┬───┘ └──┬───┘ └──┬───┘ └──┬───┘ └──┬───┘  │
│     └────────┴────────┴────────┴────────┘       │
│              WebAuthn · GPS · JWT               │
└──────────────────────┬──────────────────────────┘
                       │ REST API
┌──────────────────────┴──────────────────────────┐
│                Backend (FastAPI)                 │
│                                                 │
│  Routers → Services → Repositories → Database   │
│                                                 │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐ │
│  │   Auth   │ │Attendance│ │    Reporting      │ │
│  │ WebAuthn │ │ Punch/   │ │ Summary/Export    │ │
│  │   JWT    │ │ Override │ │ CSV/JSON/XLSX     │ │
│  └──────────┘ └──────────┘ └──────────────────┘ │
└──────────────────────┬──────────────────────────┘
                       │
              ┌────────┴────────┐
              │  PostgreSQL 16  │
              │                 │
              │  employees      │
              │  authenticators │
              │  attendance_logs│
              │  daily_summaries│
              │  reasons        │
              │  system_config  │
              └─────────────────┘
```

## Quick Start

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) & Docker Compose
- Or: Python 3.12+, Node.js 20+, PostgreSQL 16

### Docker (Recommended)

```bash
# Start all services
docker-compose up -d

# Run database migrations
docker-compose exec backend alembic upgrade head

# Seed demo data
docker-compose exec backend python seed.py
```

The app is now running at:
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

### Manual Setup

**Backend:**

```bash
cd backend
pip install -e ".[dev]"

# Start PostgreSQL (or use docker-compose up db)
# Set environment variable:
export DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5433/attendance"
export SECRET_KEY="your-secret-key"

alembic upgrade head     # Run migrations
python seed.py           # Seed demo data
uvicorn app.main:app --reload
```

**Frontend:**

```bash
cd frontend
npm install
npm run dev
```

## Demo Accounts

After running `seed.py`:

| Employee ID | Role | Password | Permissions |
|------------|------|----------|-------------|
| `ADMIN01` | ADMIN | `admin123` | Full system access |
| `HR01` | HR | `hr123456` | Employee management, reports, config |
| `MGR01` | MANAGER | `mgr12345` | Team attendance view |
| `EMP01` | EMPLOYEE | `emp12345` | Punch, view own history |
| `EMP02` | EMPLOYEE | `emp12345` | Punch, view own history |

## Role Permissions

| Capability | EMPLOYEE | MANAGER | HR | ADMIN |
|-----------|:--------:|:-------:|:--:|:-----:|
| Clock in/out | O | O | O | O |
| View own attendance | O | O | O | O |
| View team attendance | | O | O | O |
| Manage employees | | | O | O |
| View all attendance | | | O | O |
| Export reports | | | O | O |
| Change office location | | | O | O |
| System config | | | | O |

## Testing

**Backend** (275 tests):

```bash
cd backend
pytest                                          # All tests
pytest tests/unit/                              # Unit tests (201)
pytest tests/integration/                       # Integration tests (69)
pytest tests/e2e/                               # End-to-end tests (5)
pytest --cov=app --cov-report=term-missing      # Coverage report
```

**Frontend** (68 tests + 33 E2E stubs):

```bash
cd frontend
npx vitest run                    # Unit tests
npx vitest run --coverage         # Coverage report
npx playwright test               # E2E tests (requires running app)
```

## Project Structure

```
GoGoFresh_AttendanceRecord/
├── backend/
│   ├── app/
│   │   ├── models/           # SQLAlchemy/SQLModel ORM models
│   │   ├── schemas/          # Pydantic request/response validation
│   │   ├── repositories/     # Data access layer (Repository pattern)
│   │   ├── services/         # Business logic layer
│   │   ├── routers/          # FastAPI route handlers
│   │   ├── middleware/       # Auth (JWT), rate limiting
│   │   └── utils/            # Haversine, password hashing
│   ├── alembic/              # Database migrations
│   ├── tests/                # pytest (unit, integration, e2e)
│   └── seed.py               # Demo data seeder
├── frontend/
│   ├── src/
│   │   ├── app/              # Next.js App Router pages
│   │   ├── components/       # Reusable UI components
│   │   ├── hooks/            # useGeolocation, useWebAuthn, etc.
│   │   ├── lib/              # API client, auth context, validators
│   │   ├── messages/         # i18n (en.json, zh.json)
│   │   └── types/            # TypeScript interfaces
│   └── __tests__/            # Vitest + Playwright tests
└── docker-compose.yml
```

## Core Design Decisions

1. **Immutable attendance logs** — No UPDATE/DELETE on punch records. Manager overrides create new entries.
2. **Office location from DB** — Never hardcoded. Configured via admin panel, read at punch time.
3. **First-In-Last-Out** — MIN(timestamp) = clock-in, MAX(timestamp) = clock-out per day.
4. **Single punch = clock-in** — On time = NORMAL, past grace = LATE. Summary regenerated on clock-out.
5. **Event sourcing** — Every punch stores GPS coordinates, accuracy, IP, and work mode.
6. **No external SSO** — Employee ID + Password for onboarding; WebAuthn for daily use.

## API Endpoints

| Method | Endpoint | Auth | Description |
|--------|---------|------|-------------|
| POST | `/api/auth/login` | Public | Employee login |
| GET | `/api/auth/me` | Any | Current user info |
| POST | `/api/attendance/punch` | Any | Clock in/out with GPS |
| GET | `/api/attendance/today` | Any | Today's punches |
| GET | `/api/attendance/history` | Any | Own attendance history |
| GET | `/api/attendance/team` | MANAGER+ | Team attendance logs |
| GET | `/api/attendance/all` | HR+ | All attendance logs |
| POST | `/api/attendance/override` | MANAGER+ | Manager override |
| GET | `/api/reports/daily` | HR+ | Daily attendance report |
| GET | `/api/reports/export` | HR+ | Export CSV/JSON/Excel |
| POST | `/api/reasons` | Any | Submit late/early reason |
| CRUD | `/api/employees/*` | HR+ | Employee management |
| CRUD | `/api/config/*` | HR+/ADMIN | System configuration |

## Security

- WebAuthn/FIDO2 biometric authentication with clone detection
- JWT tokens with expiry validation
- bcrypt password hashing (never plaintext)
- Rate limiting on login (5 attempts/min)
- CORS with configurable origins
- Secure headers (HSTS, CSP, X-Frame-Options, etc.)
- No user enumeration (same error for wrong password / non-existent user)
- Parameterized queries only (no SQL injection)
- Input validation via Pydantic (backend) and Zod (frontend)



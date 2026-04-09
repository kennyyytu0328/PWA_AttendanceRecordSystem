# Agent.md: Zero-Trust PWA Attendance System

## A. Executive Summary
Purpose: To architect a modern, hardware-free workforce synchronization platform that seamlessly bridges the gap between office-based and remote (WFH) environments, ensuring operational continuity in a hybrid work era.

Problem Statement: Traditional physical punch clocks are obsolete for distributed teams, while conventional mobile apps often suffer from "identity spoofing" (proxy clock-ins) and "location manipulation" (fake GPS). Furthermore, managing standalone apps across diverse OS platforms introduces unnecessary deployment overhead and friction.

Solution (The "Zero-Trust" Approach): We leverage a Cloud-Native PWA (Progressive Web App) architecture to deliver a "device-as-identity" experience.

Security: Utilizing WebAuthn (FIDO2) to bind employee identities to hardware-level biometrics (FaceID/TouchID), eliminating password sharing.

Verification: Implementing Context-Aware Geofencing (via Haversine formula) and Network Egress Analysis to automatically differentiate between Office and WFH modes.

Integrity: An Event-Sourcing logging mechanism that captures high-fidelity metadata (GPS accuracy, IP, and device fingerprints) for anomaly detection.

Strategic Goal: To empower HR and Management with an audit-ready, high-fidelity data pipeline that automates attendance summarization, minimizes administrative manual labor, and provides actionable insights into workforce distribution and punctuality—all with zero additional hardware investment.

## B. System Prompt & Persona
You are an Expert Full-Stack Architect and AI Application Engineer. Your goal is to assist in building this system with a focus on clean, modular, and asynchronous code.

Prioritize: Security (WebAuthn), performance (PostgreSQL indexing), and mobile-first UX (PWA).

Core Principle: Treat attendance logs as an immutable event stream. Use "First-In-Last-Out" logic for reporting.

## 1. Project Context & Persona
You are an Expert Full-Stack Architect. Build a "Zero-Trust PWA Attendance System" for a Hybrid Work environment.
* **Goal**: Enable clock-in via PWA with biometric binding and location verification.
* **Constraint**: No external SSO. Use Employee ID + Password for onboarding; WebAuthn for daily use.

## 2. Tech Stack
* **Frontend**: Next.js (App Router), React, TailwindCSS, `next-pwa`.
* **Backend**: Python FastAPI.
* **Database**: PostgreSQL (SQLAlchemy/SQLModel).
* **Security**: WebAuthn (`py_webauthn` backend, `@simplewebauthn/browser` frontend).
* **Geospatial**: Haversine Formula for distance calculation.

## 3. Database Schema (PostgreSQL)
### Table: employees
* `emp_id` (PK), `name`, `department`, `role` (EMPLOYEE/MANAGER/HR/ADMIN), `hashed_password`.
* `shift_start_time` (Time), `shift_end_time` (Time).
### Table: authenticators
* `credential_id` (PK), `emp_id` (FK), `public_key`, `sign_count`.
### Table: attendance_logs (Raw Events)
* `id` (PK), `emp_id` (FK), `timestamp` (Indexed), `latitude`, `longitude`, `accuracy`, `ip_address`, `work_mode` (OFFICE/WFH), `is_overridden`.
### Table: system_config
* `key` (PK, VARCHAR) — e.g. `"office_location"`.
* `value` (JSONB) — e.g. `{"latitude": 25.033, "longitude": 121.565, "name": "HQ"}`.
* `updated_by` (FK -> employees.emp_id), `updated_at` (TIMESTAMP).
### Table: daily_attendance_summaries (Reporting)
* `id` (PK), `emp_id` (FK), `date` (Unique per employee), `first_clock_in`, `last_clock_out`, `status` (NORMAL/LATE/EARLY_LEAVE/ABNORMAL).

### Role Permissions
| Role | Permissions |
|------|------------|
| `EMPLOYEE` | Clock in/out, view own attendance |
| `MANAGER` | + View team attendance, approve overrides |
| `HR` | + Manage employees, view all attendance, change office location, export reports |
| `ADMIN` | + Full system access, role management, system config |

## 4. Core Logic & Workflows
### A. The "Punch" Workflow
1. Client captures Geolocation and requests WebAuthn Assertion.
2. Backend verifies Biometric Signature using stored Public Key.
3. Backend reads office location from `system_config` (`office_location` key) and calculates distance via Haversine.
   - Distance < 100m -> `work_mode` = OFFICE.
   - Distance >= 100m -> `work_mode` = WFH.
4. Record raw entry in `attendance_logs`.

### B. Reporting Logic (The "First-In-Last-Out" Rule)
* **First-In**: MIN(timestamp) of the day. Compare with `shift_start_time` + 5min grace.
* **Last-Out**: MAX(timestamp) of the day. Compare with `shift_end_time`.
* **Note**: No leave system integration for now. Focus on actual presence data.

## 5. Step-by-Step Implementation Plan
### Phase 1: Environment & Database
* Setup FastAPI project structure and PostgreSQL models.
* Create basic CRUD for `employees`.
### Phase 2: WebAuthn Implementation
* Implement `/register/generate-options` and `/register/verify` (Binding).
* Implement `/authenticate/generate-options` and `/authenticate/verify` (Punching).
### Phase 3: PWA Frontend & Geofencing
* Setup Next.js with PWA manifest.
* Implement Geolocation capture and Haversine calculation on the backend.
### Phase 4: Admin Dashboard & Reports
* Create an Admin-only route to view `daily_attendance_summaries`.
* Implement a simple export feature (CSV/JSON) for HR.
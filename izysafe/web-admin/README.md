# IzySafe — School Admin Web Panel

React + Vite + TypeScript dashboard for school administrators. Talks to the
IzySafe backend (`/api/v1/schools/*`) using the school-admin JWT flow.

## Stack

- **React 18** + **TypeScript** + **Vite 6**
- **React Router 6** — routing (protected routes + auth gate)
- **TanStack Query 5** — server-state / data fetching
- **Axios** — HTTP client with refresh-on-401 interceptor
- **Tailwind CSS 3** + **shadcn/ui** (new-york style) — UI

## Getting started

```bash
cd izysafe/web-admin
cp .env.example .env      # point VITE_API_BASE_URL at the backend
npm install
npm run dev               # http://localhost:5173
```

The dev backend runs at `http://localhost:8000` (see `izysafe/docker-compose.yml`);
its CORS allow-list already includes `http://localhost:5173`.

## Scripts

| Command | What |
|---|---|
| `npm run dev` | Vite dev server (HMR) on :5173 |
| `npm run build` | Type-check (`tsc -b`) + production build to `dist/` |
| `npm run typecheck` | Type-check only |
| `npm run preview` | Serve the production build locally |

## Auth flow

- `POST /schools/auth/login` → stores the `{access_token, refresh_token}` pair in
  `localStorage` (`src/lib/tokenStore.ts`).
- Every request carries `Authorization: Bearer <access>` (`src/lib/api.ts`).
- On a `401`, the client refreshes once via `POST /schools/auth/refresh`
  (single-flight, rotating both tokens) and retries; on failure it clears the
  session and redirects to `/login`.
- `AuthProvider` (`src/auth/AuthContext.tsx`) resolves the current admin via
  `GET /schools/admins/me` and exposes `login` / `logout` / `admin` / `status`.

## Layout

```
src/
  auth/          AuthContext, useAuth, ProtectedRoute, authApi
  components/
    layout/      AppLayout, Sidebar, Topbar, nav config
    ui/          shadcn primitives (button, input, label, card)
    PageHeader, PlaceholderPage
  lib/           api client, token store, env, utils
  pages/         Login, Dashboard, Attendance, Reports, Roster, Drivers, Audit, Settings
  types/         API envelope + domain types
  routes.tsx     router (login + protected shell)
```

Adding shadcn components later: `npx shadcn@latest add <component>` (config in
`components.json`).

## Status

Initial scaffold: auth + layout shell + navigation with placeholder pages.
Pages are built out slice-by-slice — attendance reporting/export (Sprint 10
backend) is next.

# DaveLovable Unified UI — Design Spec

**Date:** 2026-03-16
**Status:** Approved
**Goal:** Merge DaveFelix Coding Engine (Electron dashboard) and DaveLovable (web-based vibe coder) into a single unified web UI that supports both full microservice generation monitoring and interactive vibe-coding simultaneously.

---

## 1. Design Principles

1. **DaveLovable aesthetic is the base** — dark purple/indigo theme, shadcn/ui components, clean modern design
2. **Tab-based separation** — don't cram everything on one screen; use tabs to switch views
3. **VNC preview is always visible** — right panel stays fixed regardless of which work tab is active
4. **Engine runs in background** — generation progress is accessible but not intrusive
5. **Vibe Coder for live adjustments** — chat + editor available while engine generates

---

## 2. Top-Level Navigation

Four tabs in the top nav bar:

| Tab | Purpose | Source |
|-----|---------|--------|
| **Projects** | Unified project gallery (Engine + Vibe projects) | Merged from both apps |
| **Editor** | Main workspace with sub-tabs | New unified view |
| **Marketplace** | Template/blueprint marketplace | From DaveFelix |
| **Docs** | Unified documentation | Merged from both apps |

**Top-right status area:**
- Engine status pill (running/stopped, progress %, phase)
- User avatar

---

## 3. Projects Page

### 3.1 Layout
- Header with title, subtitle, filter buttons
- Responsive card grid

### 3.2 Project Cards
Each card shows:
- Thumbnail/gradient with project icon
- Type badge: `⚡ Engine` (blue) or `💜 Vibe` (purple)
- Project name and description
- Stats row (endpoints/stories for Engine, files/chats for Vibe)
- Status indicator (Running ▶ / Queued ⏸ / Done ✓)
- Progress bar for active Engine projects

### 3.3 Filters
- All / Engine / Vibe / Running

### 3.4 Data Sources
- **Engine projects**: Scanned from `backend/engine/Data/all_services/` + orchestrator API
- **Vibe projects**: Existing DaveLovable SQLite database via FastAPI

### 3.5 Actions
- Click card → opens in Editor tab
- "New Project" card → create project modal (choose Engine or Vibe type)
- Favorite toggle (existing DaveLovable feature preserved)

---

## 4. Editor Page

The main workspace. Split into two areas:
- **Left: Work Area** with switchable sub-tabs
- **Right: VNC Preview** (always visible, fixed width)

### 4.1 Work Area Sub-Tabs

Two tabs at the top of the work area:

#### Tab 1: 💬 Vibe Coder
Three-column layout:
1. **Chat Panel** (280px, left) — AI chat with Planner/Coder/Reviewer agent tags, model selector, streaming SSE responses
2. **Code Editor** (flex, center) — Monaco Editor with file tabs, file tree explorer, syntax highlighting. Shows generated files with green dots (●) and user-modified files with orange dots (●)
3. *(VNC is to the right, outside this tab)*

#### Tab 2: 🟢 Generation Monitor
Full-width layout with:
1. **Progress Header** — Project name, phase, progress bar, agent count
2. **Sub-tabs**: Agents | Epics | Tasks | Dependencies | Logs | Validation | Traceability
3. **Two-column body**:
   - Left: Agent list with real-time status (running/done/queued), task description, elapsed time
   - Right: Epic sidebar with progress bars and task counts

### 4.2 VNC Preview Panel (Always Visible)
- Fixed 380px right panel
- Header with "Live Preview" title and connection status
- VNC body showing noVNC iframe (or WebContainers for Vibe projects)
- URL bar at bottom
- Always shows the active project's preview regardless of which work tab is selected

### 4.3 File Synchronization
When Engine generates/modifies a file and user is in Vibe Coder tab:
- File tab gets green dot indicator (auto-generated)
- Monaco editor refreshes if the file is currently open
- File tree updates in real-time via WebSocket events

When user modifies a file via Vibe Coder while Engine is running:
- File is marked as user-modified (orange dot)
- Engine's next validation pass picks up the change
- Git service commits with appropriate attribution

---

## 5. Marketplace Page

Standalone tab. Content from DaveFelix's Portal component:
- Card grid with templates, starter packs, service blueprints
- Search and filter
- Detail modal on click

---

## 6. Docs Page

Standalone tab. Merged documentation:
- DaveLovable usage docs (existing)
- DaveFelix Engine docs (from engine/docs/)
- API reference
- Getting started guide

---

## 7. Backend Integration

### 7.1 Existing DaveLovable API (preserved)
All existing endpoints continue to work:
- `/api/v1/projects/*` — Project CRUD
- `/api/v1/chat/*` — Chat streaming
- `/api/v1/projects/{id}/files/*` — File management
- `/api/v1/projects/{id}/git/*` — Git operations

### 7.2 New Engine API Endpoints
New routes to bridge the Engine into the FastAPI backend:

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/engine/projects` | List Engine projects from Data/ |
| GET | `/api/v1/engine/projects/{name}` | Get Engine project details (services, endpoints, stories) |
| POST | `/api/v1/engine/projects/{name}/start` | Start generation pipeline |
| POST | `/api/v1/engine/projects/{name}/stop` | Stop generation |
| GET | `/api/v1/engine/projects/{name}/status` | Get generation status |
| GET | `/api/v1/engine/projects/{name}/epics` | List epics with progress |
| GET | `/api/v1/engine/projects/{name}/agents` | List agent statuses |
| WS | `/api/v1/engine/ws` | WebSocket for real-time engine events |

### 7.3 WebSocket Events (Engine)
Extend existing WebSocket with engine-specific events:

```
engine:agent_status    — Agent running/completed/failed
engine:epic_progress   — Epic completion %
engine:task_update     — Task started/completed
engine:file_generated  — New file created by engine
engine:validation      — Validation results
engine:phase_change    — Pipeline phase transition
engine:progress        — Overall progress %
```

### 7.4 Engine Service Layer
New `backend/app/services/engine_service.py`:
- Wraps `backend/engine/` Python modules
- Calls `SpecParser`, `SkeletonGenerator`, `ServiceOrchestrator`
- Manages generation state in-memory (or SQLite)
- Emits WebSocket events during generation

---

## 8. Frontend Component Architecture

### 8.1 New Components

```
front/src/
├── components/
│   ├── engine/
│   │   ├── GenerationMonitor.tsx    — Main monitor container
│   │   ├── AgentList.tsx            — Real-time agent status list
│   │   ├── EpicSidebar.tsx          — Epic progress cards
│   │   ├── TaskBoard.tsx            — Task dependency view
│   │   ├── LogViewer.tsx            — Real-time log stream
│   │   ├── ValidationPanel.tsx      — Validation results
│   │   ├── TraceabilityPanel.tsx    — Requirement tracing
│   │   ├── ProgressHeader.tsx       — Phase + progress bar
│   │   └── EngineStatusPill.tsx     — Top-nav status indicator
│   ├── projects/
│   │   ├── UnifiedProjectCard.tsx   — Card supporting both types
│   │   └── ProjectFilters.tsx       — Filter bar component
│   └── editor/
│       ├── WorkTabs.tsx             — Vibe Coder / Gen Monitor switcher
│       └── VncPreview.tsx           — Always-visible VNC panel
```

### 8.2 Modified Components
- `Navbar.tsx` — Add Marketplace + Docs tabs, Engine status pill
- `ChatPanel.tsx` — Preserve as-is, used in Vibe Coder tab
- `CodeEditor.tsx` — Add generated/modified file indicators
- `FileExplorer.tsx` — Add multi-service tree support
- `PreviewPanelWithWebContainer.tsx` — Integrate VNC fallback for Engine projects

### 8.3 New Zustand Stores
- `engineStore.ts` — Adapt from DaveFelix's engineStore (generation state, agents, epics, WebSocket)
- Extend `projectStore.ts` — Add Engine project support

### 8.4 New API Service
- `front/src/services/engineApi.ts` — Engine REST + WebSocket client

---

## 9. State Flow

```
User clicks Engine Project
  → Editor tab opens
  → Engine API starts generation (POST /engine/projects/{name}/start)
  → WebSocket receives engine:* events
  → Generation Monitor shows real-time progress
  → User switches to Vibe Coder tab
  → Chat + Editor available for live code adjustments
  → VNC Preview always shows running app
  → Engine validation picks up user changes
  → Generation completes → status updates
```

---

## 10. Migration Strategy

1. **Phase 1**: Add new nav tabs + routing (Projects/Editor/Marketplace/Docs)
2. **Phase 2**: Build Engine API endpoints in FastAPI backend
3. **Phase 3**: Build Generation Monitor components
4. **Phase 4**: Integrate VNC preview panel
5. **Phase 5**: Unify project cards and data sources
6. **Phase 6**: Wire WebSocket events for real-time updates
7. **Phase 7**: Polish and test end-to-end

---

## 11. Tech Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Framework | Keep React + Vite | Already working, no need to change |
| UI Library | Keep shadcn/ui | DaveLovable's aesthetic stays |
| State | Keep Zustand | Already used, add engine store |
| VNC | noVNC iframe | Same as DaveFelix, proven approach |
| Engine comms | WebSocket + REST | SSE for chat (existing), WS for engine events |
| Preview for Vibe | WebContainers | Keep existing approach |
| Preview for Engine | VNC (noVNC) | Keep existing approach |

---

## 12. Out of Scope (YAGNI)

- Authentication (keep MOCK_USER_ID for now)
- Multi-tenant support
- Collaborative editing
- Mobile responsive (desktop-first)
- Electron packaging (web-only for now)

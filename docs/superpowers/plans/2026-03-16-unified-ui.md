# DaveLovable Unified UI — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge DaveFelix Coding Engine dashboard and DaveLovable vibe coder into a single web UI with tab-based navigation, generation monitoring, and always-visible VNC preview.

**Architecture:** Extend the existing DaveLovable React + FastAPI app. Add new top-level routes (Marketplace, Engine Editor), new Engine API endpoints in FastAPI, a new `engineApi.ts` frontend service, engine-specific React components, and a Zustand store for real-time engine state via WebSocket.

**Tech Stack:** React 18 + TypeScript, Vite, shadcn/ui, TanStack React Query, Zustand (new, for engine WS state), FastAPI, SQLAlchemy, WebSocket (engine events), noVNC (iframe).

**Design Spec:** `docs/superpowers/specs/2026-03-16-unified-ui-design.md`

---

## File Map

### New Files — Backend
| File | Responsibility |
|------|---------------|
| `backend/app/api/engine.py` | Engine REST endpoints + WebSocket |
| `backend/app/services/engine_service.py` | Wraps engine Python modules, manages generation state |
| `backend/app/schemas/engine.py` | Pydantic schemas for engine API |

### New Files — Frontend
| File | Responsibility |
|------|---------------|
| `front/src/pages/Marketplace.tsx` | Marketplace page (placeholder) |
| `front/src/pages/EngineEditor.tsx` | Editor page for Engine projects with sub-tabs |
| `front/src/services/engineApi.ts` | Engine REST + WebSocket client |
| `front/src/hooks/useEngine.ts` | React Query hooks for engine data |
| `front/src/stores/engineStore.ts` | Zustand store for real-time engine WebSocket state |
| `front/src/components/engine/EngineStatusPill.tsx` | Top-nav engine status indicator |
| `front/src/components/engine/GenerationMonitor.tsx` | Full generation monitor view |
| `front/src/components/engine/AgentList.tsx` | Real-time agent status list |
| `front/src/components/engine/EpicSidebar.tsx` | Epic progress cards |
| `front/src/components/engine/ProgressHeader.tsx` | Phase + progress bar |
| `front/src/components/engine/VncPreview.tsx` | Always-visible VNC preview panel |
| `front/src/components/engine/WorkTabs.tsx` | Vibe Coder / Generation Monitor tab switcher |
| `front/src/components/projects/UnifiedProjectCard.tsx` | Card supporting both Engine and Vibe types |
| `front/src/components/projects/ProjectFilters.tsx` | Filter bar (All / Engine / Vibe / Running) |

### Modified Files
| File | Change |
|------|--------|
| `front/src/App.tsx` | Add routes: `/marketplace`, `/engine-editor/:projectName` |
| `front/src/components/Navbar.tsx` | Replace nav links with Projects/Editor/Marketplace/Docs tabs + EngineStatusPill |
| `front/src/pages/Projects.tsx` | Add Engine projects, use UnifiedProjectCard, add filters |
| `backend/app/api/__init__.py` | Register engine router |
| `backend/app/main.py` | Add engine WebSocket endpoint mount |

---

## Chunk 1: Backend Engine API (Tasks 1–4)

### Task 1: Engine Pydantic Schemas

**Files:**
- Create: `backend/app/schemas/engine.py`

- [ ] **Step 1: Create engine schemas**

```python
# backend/app/schemas/engine.py
from pydantic import BaseModel
from typing import Optional
from enum import Enum


class EngineProjectType(str, Enum):
    ENGINE = "engine"
    VIBE = "vibe"


class AgentStatus(str, Enum):
    RUNNING = "running"
    DONE = "done"
    QUEUED = "queued"
    FAILED = "failed"


class GenerationPhase(str, Enum):
    IDLE = "idle"
    PARSING = "parsing"
    SKELETON = "skeleton"
    GENERATION = "generation"
    VALIDATION = "validation"
    INTEGRATION = "integration"
    COMPLETE = "complete"
    FAILED = "failed"


class EngineProjectSummary(BaseModel):
    name: str
    path: str
    service_count: int = 0
    endpoint_count: int = 0
    story_count: int = 0
    type: EngineProjectType = EngineProjectType.ENGINE


class EngineProjectDetail(EngineProjectSummary):
    services: list[dict] = []
    generation_order: list[str] = []
    dependency_graph: dict[str, list[str]] = {}


class AgentInfo(BaseModel):
    name: str
    status: AgentStatus
    task: str = ""
    elapsed_seconds: float = 0


class EpicInfo(BaseModel):
    id: str
    name: str
    progress_pct: int = 0
    tasks_total: int = 0
    tasks_complete: int = 0


class GenerationStatus(BaseModel):
    project_name: str
    phase: GenerationPhase = GenerationPhase.IDLE
    progress_pct: int = 0
    agents: list[AgentInfo] = []
    epics: list[EpicInfo] = []
    service_count: int = 0
    endpoint_count: int = 0


class StartGenerationRequest(BaseModel):
    skeleton_only: bool = False
    service: Optional[str] = None
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/schemas/engine.py
git commit -m "feat: add Pydantic schemas for engine API"
```

---

### Task 2: Engine Service Layer

**Files:**
- Create: `backend/app/services/engine_service.py`

- [ ] **Step 1: Create engine service**

```python
# backend/app/services/engine_service.py
"""Service layer wrapping the DaveFelix Coding Engine."""
import logging
import os
import json
from pathlib import Path
from typing import Optional

from app.schemas.engine import (
    EngineProjectSummary,
    EngineProjectDetail,
    GenerationStatus,
    GenerationPhase,
    AgentInfo,
    AgentStatus,
    EpicInfo,
)

logger = logging.getLogger(__name__)

# Path to engine data directory
ENGINE_DATA_DIR = Path(__file__).parent.parent.parent / "engine" / "Data" / "all_services"


class EngineService:
    """Manages engine projects and generation state."""

    # In-memory generation state (per project)
    _generation_state: dict[str, GenerationStatus] = {}

    @classmethod
    def list_projects(cls) -> list[EngineProjectSummary]:
        """Scan Data/all_services/ for engine projects."""
        projects = []
        if not ENGINE_DATA_DIR.exists():
            logger.warning(f"Engine data dir not found: {ENGINE_DATA_DIR}")
            return projects

        for entry in sorted(ENGINE_DATA_DIR.iterdir()):
            if not entry.is_dir():
                continue
            # Detect valid project by presence of key files
            has_arch = (entry / "architecture").is_dir() or (entry / "MASTER_DOCUMENT.md").exists()
            if not has_arch:
                continue

            summary = cls._scan_project(entry)
            if summary:
                projects.append(summary)

        return projects

    @classmethod
    def _scan_project(cls, project_dir: Path) -> Optional[EngineProjectSummary]:
        """Scan a single project directory for metadata."""
        try:
            # Count services from architecture dir
            service_count = 0
            arch_dir = project_dir / "architecture"
            if arch_dir.exists():
                service_count = sum(
                    1 for f in arch_dir.iterdir()
                    if f.suffix == ".md" and f.name != "architecture.md"
                )

            # Count endpoints from openapi spec
            endpoint_count = 0
            api_spec = project_dir / "api" / "openapi_spec.yaml"
            if api_spec.exists():
                try:
                    import yaml
                    with open(api_spec) as f:
                        spec = yaml.safe_load(f)
                    paths = spec.get("paths", {})
                    for path_methods in paths.values():
                        endpoint_count += len([
                            m for m in path_methods
                            if m in ("get", "post", "put", "delete", "patch")
                        ])
                except Exception:
                    pass

            # Count stories
            story_count = 0
            stories_dir = project_dir / "user_stories"
            if stories_dir.exists():
                for f in stories_dir.glob("*.json"):
                    try:
                        with open(f) as fh:
                            data = json.load(fh)
                        if isinstance(data, list):
                            story_count += len(data)
                        elif isinstance(data, dict) and "user_stories" in data:
                            story_count += len(data["user_stories"])
                    except Exception:
                        pass

            return EngineProjectSummary(
                name=project_dir.name,
                path=str(project_dir),
                service_count=service_count,
                endpoint_count=endpoint_count,
                story_count=story_count,
            )
        except Exception as e:
            logger.error(f"Failed to scan project {project_dir}: {e}")
            return None

    @classmethod
    def get_project(cls, project_name: str) -> Optional[EngineProjectDetail]:
        """Get detailed project info including parsed spec data."""
        project_dir = ENGINE_DATA_DIR / project_name
        if not project_dir.exists():
            return None

        summary = cls._scan_project(project_dir)
        if not summary:
            return None

        # Try structured parse for detailed info
        services = []
        generation_order = []
        dependency_graph = {}

        try:
            import sys
            engine_root = str(Path(__file__).parent.parent.parent / "engine")
            if engine_root not in sys.path:
                sys.path.insert(0, engine_root)
            from src.engine.spec_parser import SpecParser

            parsed = SpecParser(project_dir).parse()
            for svc_name, svc in parsed.services.items():
                services.append({
                    "name": svc_name,
                    "port": svc.port,
                    "endpoint_count": len(svc.endpoints),
                    "entity_count": len(svc.entities),
                    "story_count": len(svc.stories),
                })
            generation_order = parsed.generation_order
            dependency_graph = parsed.dependency_graph
        except Exception as e:
            logger.warning(f"Structured parse failed for {project_name}: {e}")

        return EngineProjectDetail(
            name=summary.name,
            path=summary.path,
            service_count=summary.service_count,
            endpoint_count=summary.endpoint_count,
            story_count=summary.story_count,
            services=services,
            generation_order=generation_order,
            dependency_graph=dependency_graph,
        )

    @classmethod
    def get_generation_status(cls, project_name: str) -> GenerationStatus:
        """Get current generation status for a project."""
        if project_name in cls._generation_state:
            return cls._generation_state[project_name]
        return GenerationStatus(
            project_name=project_name,
            phase=GenerationPhase.IDLE,
        )

    @classmethod
    def start_generation(cls, project_name: str, skeleton_only: bool = False) -> GenerationStatus:
        """Start generation for a project (skeleton phase for now)."""
        project_dir = ENGINE_DATA_DIR / project_name
        if not project_dir.exists():
            raise ValueError(f"Project not found: {project_name}")

        status = GenerationStatus(
            project_name=project_name,
            phase=GenerationPhase.SKELETON if skeleton_only else GenerationPhase.PARSING,
            progress_pct=0,
        )
        cls._generation_state[project_name] = status

        # Run skeleton generation synchronously for now
        try:
            import sys
            engine_root = str(Path(__file__).parent.parent.parent / "engine")
            if engine_root not in sys.path:
                sys.path.insert(0, engine_root)
            from src.engine.spec_parser import SpecParser
            from src.engine.skeleton_generator import SkeletonGenerator

            status.phase = GenerationPhase.PARSING
            status.progress_pct = 10
            parsed = SpecParser(project_dir).parse()

            status.phase = GenerationPhase.SKELETON
            status.progress_pct = 30
            status.service_count = len(parsed.services)
            status.endpoint_count = sum(len(s.endpoints) for s in parsed.services.values())

            output_dir = project_dir.parent.parent.parent / "output" / project_name
            gen = SkeletonGenerator(parsed, str(output_dir))
            gen.generate_all()

            status.phase = GenerationPhase.COMPLETE if skeleton_only else GenerationPhase.GENERATION
            status.progress_pct = 100 if skeleton_only else 50

        except Exception as e:
            logger.error(f"Generation failed for {project_name}: {e}")
            status.phase = GenerationPhase.FAILED

        return status

    @classmethod
    def stop_generation(cls, project_name: str) -> GenerationStatus:
        """Stop generation for a project."""
        if project_name in cls._generation_state:
            cls._generation_state[project_name].phase = GenerationPhase.IDLE
            cls._generation_state[project_name].progress_pct = 0
        return cls.get_generation_status(project_name)
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/engine_service.py
git commit -m "feat: add EngineService wrapping coding engine modules"
```

---

### Task 3: Engine API Endpoints

**Files:**
- Create: `backend/app/api/engine.py`
- Modify: `backend/app/api/__init__.py`

- [ ] **Step 1: Create engine router**

```python
# backend/app/api/engine.py
"""Engine API endpoints for project listing, generation control, and WebSocket events."""
import logging
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from typing import Optional

from app.schemas.engine import (
    EngineProjectSummary,
    EngineProjectDetail,
    GenerationStatus,
    StartGenerationRequest,
)
from app.services.engine_service import EngineService

logger = logging.getLogger(__name__)
router = APIRouter()

# WebSocket connections for engine events
_ws_connections: list[WebSocket] = []


@router.get("/projects", response_model=list[EngineProjectSummary])
def list_engine_projects():
    """List all engine projects from Data/all_services/."""
    return EngineService.list_projects()


@router.get("/projects/{project_name}", response_model=EngineProjectDetail)
def get_engine_project(project_name: str):
    """Get detailed engine project info."""
    project = EngineService.get_project(project_name)
    if not project:
        raise HTTPException(status_code=404, detail=f"Engine project not found: {project_name}")
    return project


@router.get("/projects/{project_name}/status", response_model=GenerationStatus)
def get_generation_status(project_name: str):
    """Get current generation status."""
    return EngineService.get_generation_status(project_name)


@router.post("/projects/{project_name}/start", response_model=GenerationStatus)
def start_generation(project_name: str, request: StartGenerationRequest = StartGenerationRequest()):
    """Start generation pipeline for a project."""
    try:
        return EngineService.start_generation(
            project_name,
            skeleton_only=request.skeleton_only,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Generation start failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_name}/stop", response_model=GenerationStatus)
def stop_generation(project_name: str):
    """Stop generation for a project."""
    return EngineService.stop_generation(project_name)


@router.websocket("/ws")
async def engine_websocket(websocket: WebSocket):
    """WebSocket for real-time engine events."""
    await websocket.accept()
    _ws_connections.append(websocket)
    try:
        while True:
            # Keep connection alive, receive client messages if needed
            data = await websocket.receive_text()
            # Could handle client commands here
    except WebSocketDisconnect:
        _ws_connections.remove(websocket)


async def broadcast_engine_event(event_type: str, data: dict):
    """Broadcast an engine event to all connected WebSocket clients."""
    message = {"type": event_type, "data": data}
    disconnected = []
    for ws in _ws_connections:
        try:
            await ws.send_json(message)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        _ws_connections.remove(ws)
```

- [ ] **Step 2: Register engine router**

Add to `backend/app/api/__init__.py`:

```python
from app.api import chat, projects, engine

api_router.include_router(engine.router, prefix="/engine", tags=["engine"])
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/engine.py backend/app/api/__init__.py backend/app/schemas/engine.py
git commit -m "feat: add engine API endpoints with REST + WebSocket"
```

---

### Task 4: Verify Backend Integration

- [ ] **Step 1: Test engine API starts**

```bash
cd C:\Users\User\Desktop\DaveLovable\backend
python -c "from app.api.engine import router; print('Engine router OK')"
python -c "from app.services.engine_service import EngineService; projects = EngineService.list_projects(); print(f'Found {len(projects)} engine projects')"
```

Expected: Router imports cleanly, at least 1 engine project found.

- [ ] **Step 2: Commit if any fixes needed**

---

## Chunk 2: Frontend Foundation (Tasks 5–8)

### Task 5: Engine API Client

**Files:**
- Create: `front/src/services/engineApi.ts`

- [ ] **Step 1: Create engine API client**

```typescript
// front/src/services/engineApi.ts
import { API_URL } from './api';

// Types
export interface EngineProject {
  name: string;
  path: string;
  service_count: number;
  endpoint_count: number;
  story_count: number;
  type: 'engine' | 'vibe';
}

export interface EngineProjectDetail extends EngineProject {
  services: Array<{
    name: string;
    port: number;
    endpoint_count: number;
    entity_count: number;
    story_count: number;
  }>;
  generation_order: string[];
  dependency_graph: Record<string, string[]>;
}

export type AgentStatus = 'running' | 'done' | 'queued' | 'failed';
export type GenerationPhase = 'idle' | 'parsing' | 'skeleton' | 'generation' | 'validation' | 'integration' | 'complete' | 'failed';

export interface AgentInfo {
  name: string;
  status: AgentStatus;
  task: string;
  elapsed_seconds: number;
}

export interface EpicInfo {
  id: string;
  name: string;
  progress_pct: number;
  tasks_total: number;
  tasks_complete: number;
}

export interface GenerationStatus {
  project_name: string;
  phase: GenerationPhase;
  progress_pct: number;
  agents: AgentInfo[];
  epics: EpicInfo[];
  service_count: number;
  endpoint_count: number;
}

// REST API
export const engineApi = {
  listProjects: async (): Promise<EngineProject[]> => {
    const res = await fetch(`${API_URL}/engine/projects`);
    if (!res.ok) throw new Error(`Failed to list engine projects: ${res.status}`);
    return res.json();
  },

  getProject: async (name: string): Promise<EngineProjectDetail> => {
    const res = await fetch(`${API_URL}/engine/projects/${encodeURIComponent(name)}`);
    if (!res.ok) throw new Error(`Failed to get engine project: ${res.status}`);
    return res.json();
  },

  getStatus: async (name: string): Promise<GenerationStatus> => {
    const res = await fetch(`${API_URL}/engine/projects/${encodeURIComponent(name)}/status`);
    if (!res.ok) throw new Error(`Failed to get generation status: ${res.status}`);
    return res.json();
  },

  startGeneration: async (name: string, skeletonOnly = false): Promise<GenerationStatus> => {
    const res = await fetch(`${API_URL}/engine/projects/${encodeURIComponent(name)}/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ skeleton_only: skeletonOnly }),
    });
    if (!res.ok) throw new Error(`Failed to start generation: ${res.status}`);
    return res.json();
  },

  stopGeneration: async (name: string): Promise<GenerationStatus> => {
    const res = await fetch(`${API_URL}/engine/projects/${encodeURIComponent(name)}/stop`, {
      method: 'POST',
    });
    if (!res.ok) throw new Error(`Failed to stop generation: ${res.status}`);
    return res.json();
  },
};

// WebSocket connection
export function createEngineWebSocket(
  onEvent: (type: string, data: any) => void,
): WebSocket {
  const wsUrl = API_URL.replace('http', 'ws').replace('/api/v1', '') + '/api/v1/engine/ws';
  const ws = new WebSocket(wsUrl);

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      onEvent(msg.type, msg.data);
    } catch (e) {
      console.error('Failed to parse engine WS message:', e);
    }
  };

  ws.onerror = (e) => console.error('Engine WS error:', e);
  ws.onclose = () => console.log('Engine WS closed');

  return ws;
}
```

- [ ] **Step 2: Commit**

```bash
git add front/src/services/engineApi.ts
git commit -m "feat: add engine API client with REST + WebSocket"
```

---

### Task 6: Engine React Query Hooks

**Files:**
- Create: `front/src/hooks/useEngine.ts`

- [ ] **Step 1: Create engine hooks**

```typescript
// front/src/hooks/useEngine.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { engineApi, type EngineProject, type EngineProjectDetail, type GenerationStatus } from '@/services/engineApi';

export const engineKeys = {
  all: ['engine'] as const,
  projects: () => [...engineKeys.all, 'projects'] as const,
  project: (name: string) => [...engineKeys.all, 'project', name] as const,
  status: (name: string) => [...engineKeys.all, 'status', name] as const,
};

export function useEngineProjects() {
  return useQuery({
    queryKey: engineKeys.projects(),
    queryFn: () => engineApi.listProjects(),
    staleTime: 60000,
    refetchOnWindowFocus: false,
  });
}

export function useEngineProject(name: string, enabled = true) {
  return useQuery({
    queryKey: engineKeys.project(name),
    queryFn: () => engineApi.getProject(name),
    enabled: enabled && !!name,
    staleTime: 60000,
  });
}

export function useGenerationStatus(name: string, enabled = true) {
  return useQuery({
    queryKey: engineKeys.status(name),
    queryFn: () => engineApi.getStatus(name),
    enabled: enabled && !!name,
    refetchInterval: 3000, // Poll every 3s while generation running
  });
}

export function useStartGeneration() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ name, skeletonOnly }: { name: string; skeletonOnly?: boolean }) =>
      engineApi.startGeneration(name, skeletonOnly),
    onSuccess: (status) => {
      queryClient.setQueryData(engineKeys.status(status.project_name), status);
      queryClient.invalidateQueries({ queryKey: engineKeys.projects() });
    },
  });
}

export function useStopGeneration() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => engineApi.stopGeneration(name),
    onSuccess: (status) => {
      queryClient.setQueryData(engineKeys.status(status.project_name), status);
    },
  });
}
```

- [ ] **Step 2: Commit**

```bash
git add front/src/hooks/useEngine.ts
git commit -m "feat: add React Query hooks for engine API"
```

---

### Task 7: Zustand Engine Store (WebSocket State)

**Files:**
- Create: `front/src/stores/engineStore.ts`

- [ ] **Step 1: Install zustand**

```bash
cd C:\Users\User\Desktop\DaveLovable\front
npm install zustand
```

- [ ] **Step 2: Create engine store**

```typescript
// front/src/stores/engineStore.ts
import { create } from 'zustand';
import type { AgentInfo, EpicInfo, GenerationPhase } from '@/services/engineApi';
import { createEngineWebSocket } from '@/services/engineApi';

interface EngineState {
  // Connection
  connected: boolean;
  ws: WebSocket | null;

  // Active generation
  activeProject: string | null;
  phase: GenerationPhase;
  progressPct: number;
  agents: AgentInfo[];
  epics: EpicInfo[];

  // Actions
  connect: () => void;
  disconnect: () => void;
  setActiveProject: (name: string | null) => void;
}

export const useEngineStore = create<EngineState>((set, get) => ({
  connected: false,
  ws: null,
  activeProject: null,
  phase: 'idle',
  progressPct: 0,
  agents: [],
  epics: [],

  connect: () => {
    if (get().ws) return; // Already connected

    const ws = createEngineWebSocket((type, data) => {
      switch (type) {
        case 'engine:agent_status':
          set((s) => ({
            agents: s.agents.map((a) =>
              a.name === data.name ? { ...a, ...data } : a
            ),
          }));
          break;
        case 'engine:epic_progress':
          set((s) => ({
            epics: s.epics.map((e) =>
              e.id === data.id ? { ...e, ...data } : e
            ),
          }));
          break;
        case 'engine:progress':
          set({ progressPct: data.progress_pct, phase: data.phase });
          break;
        case 'engine:phase_change':
          set({ phase: data.phase });
          break;
        default:
          break;
      }
    });

    ws.onopen = () => set({ connected: true });
    ws.onclose = () => set({ connected: false, ws: null });

    set({ ws });
  },

  disconnect: () => {
    const { ws } = get();
    if (ws) {
      ws.close();
      set({ ws: null, connected: false });
    }
  },

  setActiveProject: (name) => set({ activeProject: name }),
}));
```

- [ ] **Step 3: Commit**

```bash
git add front/src/stores/engineStore.ts
git commit -m "feat: add Zustand engine store for WebSocket state"
```

---

### Task 8: Update App Routes + Navbar

**Files:**
- Modify: `front/src/App.tsx`
- Modify: `front/src/components/Navbar.tsx`
- Create: `front/src/pages/Marketplace.tsx`
- Create: `front/src/components/engine/EngineStatusPill.tsx`

- [ ] **Step 1: Create Marketplace placeholder page**

```typescript
// front/src/pages/Marketplace.tsx
const Marketplace = () => {
  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto px-8 py-12">
        <h1 className="text-3xl font-bold mb-2">Marketplace</h1>
        <p className="text-muted-foreground">
          Templates, starter packs, and service blueprints. Coming soon.
        </p>
      </div>
    </div>
  );
};

export default Marketplace;
```

- [ ] **Step 2: Create EngineStatusPill component**

```typescript
// front/src/components/engine/EngineStatusPill.tsx
import { useEngineStore } from '@/stores/engineStore';

export function EngineStatusPill() {
  const { connected, phase, progressPct, activeProject } = useEngineStore();

  if (phase === 'idle' || !activeProject) return null;

  const isRunning = !['idle', 'complete', 'failed'].includes(phase);

  return (
    <div className={`flex items-center gap-2 text-xs px-3 py-1.5 rounded-full border ${
      isRunning
        ? 'bg-green-500/10 text-green-400 border-green-500/25'
        : phase === 'complete'
        ? 'bg-blue-500/10 text-blue-400 border-blue-500/25'
        : 'bg-red-500/10 text-red-400 border-red-500/25'
    }`}>
      {isRunning && (
        <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
      )}
      <span>Engine · {progressPct}% · {phase}</span>
    </div>
  );
}
```

- [ ] **Step 3: Update App.tsx routes**

Add imports and routes for Marketplace and EngineEditor (EngineEditor will be created in Task 10):

```typescript
// Add to imports in App.tsx
import Marketplace from './pages/Marketplace';

// Add to Routes:
<Route path="/marketplace" element={<Marketplace />} />
```

- [ ] **Step 4: Update Navbar.tsx**

Replace the existing `navLinks` array and add EngineStatusPill. The Navbar should use the same DaveLovable aesthetic but with the unified navigation:

Update the nav links to:
```typescript
const navLinks = [
  { label: "Projects", href: "/projects" },
  { label: "Marketplace", href: "/marketplace" },
  { label: "Docs", href: "/docs" },
];
```

Import and add `<EngineStatusPill />` in the right section of the nav, before the user avatar/sign-in button.

- [ ] **Step 5: Commit**

```bash
git add front/src/App.tsx front/src/components/Navbar.tsx front/src/pages/Marketplace.tsx front/src/components/engine/EngineStatusPill.tsx
git commit -m "feat: add unified nav with Marketplace route and EngineStatusPill"
```

---

## Chunk 3: Engine Components (Tasks 9–12)

### Task 9: VNC Preview Panel

**Files:**
- Create: `front/src/components/engine/VncPreview.tsx`

- [ ] **Step 1: Create VNC preview component**

```typescript
// front/src/components/engine/VncPreview.tsx
import { useState, useEffect } from 'react';

interface VncPreviewProps {
  vncUrl?: string;
  projectName: string;
}

export function VncPreview({ vncUrl, projectName }: VncPreviewProps) {
  const [status, setStatus] = useState<'connecting' | 'connected' | 'error'>('connecting');

  useEffect(() => {
    if (!vncUrl) {
      setStatus('connecting');
      return;
    }
    // Health check
    const check = setInterval(async () => {
      try {
        const res = await fetch(vncUrl.replace('/vnc.html', '/'), { mode: 'no-cors' });
        setStatus('connected');
      } catch {
        setStatus('connecting');
      }
    }, 3000);
    return () => clearInterval(check);
  }, [vncUrl]);

  return (
    <div className="flex flex-col h-full border-l border-border/30">
      <div className="flex items-center gap-2 px-3 py-2 border-b border-border/30">
        <span className="text-sm text-muted-foreground font-medium">🖥 Live Preview</span>
        <span className={`ml-auto text-[10px] px-2 py-0.5 rounded-full border ${
          status === 'connected'
            ? 'bg-green-500/10 text-green-400 border-green-500/25'
            : 'bg-yellow-500/10 text-yellow-400 border-yellow-500/25'
        }`}>
          {status === 'connected' ? '● Connected' : '○ Connecting...'}
        </span>
      </div>
      <div className="flex-1 bg-black m-1.5 rounded-md overflow-hidden">
        {vncUrl ? (
          <iframe
            src={vncUrl}
            className="w-full h-full border-0"
            title={`Preview: ${projectName}`}
            sandbox="allow-same-origin allow-scripts allow-forms"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-muted-foreground text-sm">
            <div className="text-center">
              <p>Waiting for preview...</p>
              <p className="text-xs mt-1">Start generation to see live output</p>
            </div>
          </div>
        )}
      </div>
      <div className="px-3 py-1.5 text-[10px] text-muted-foreground bg-background/50 flex items-center gap-2">
        <span>↻</span>
        <span className="bg-muted/50 px-2 py-0.5 rounded flex-1">
          {vncUrl || 'localhost:6080/vnc.html'}
        </span>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add front/src/components/engine/VncPreview.tsx
git commit -m "feat: add VncPreview component with health check and iframe"
```

---

### Task 10: Generation Monitor Components

**Files:**
- Create: `front/src/components/engine/ProgressHeader.tsx`
- Create: `front/src/components/engine/AgentList.tsx`
- Create: `front/src/components/engine/EpicSidebar.tsx`
- Create: `front/src/components/engine/GenerationMonitor.tsx`

- [ ] **Step 1: Create ProgressHeader**

```typescript
// front/src/components/engine/ProgressHeader.tsx
import type { GenerationPhase } from '@/services/engineApi';

interface ProgressHeaderProps {
  projectName: string;
  phase: GenerationPhase;
  progressPct: number;
  serviceCount: number;
  endpointCount: number;
}

export function ProgressHeader({ projectName, phase, progressPct, serviceCount, endpointCount }: ProgressHeaderProps) {
  return (
    <div className="h-9 bg-background/50 border-b border-border/30 flex items-center px-4 gap-3 shrink-0">
      <span className="text-sm font-semibold text-primary">📱 {projectName}</span>
      <span className="text-xs text-muted-foreground capitalize">Phase: {phase}</span>
      <div className="flex items-center gap-2">
        <div className="w-32 h-1 bg-muted rounded-full">
          <div
            className="h-full rounded-full bg-gradient-to-r from-primary to-green-500 transition-all"
            style={{ width: `${progressPct}%` }}
          />
        </div>
        <span className="text-xs font-semibold text-green-400">{progressPct}%</span>
      </div>
      <span className="ml-auto text-xs text-muted-foreground">
        {serviceCount} services · {endpointCount} endpoints
      </span>
    </div>
  );
}
```

- [ ] **Step 2: Create AgentList**

```typescript
// front/src/components/engine/AgentList.tsx
import type { AgentInfo } from '@/services/engineApi';

interface AgentListProps {
  agents: AgentInfo[];
}

export function AgentList({ agents }: AgentListProps) {
  return (
    <div className="flex-1 p-3 overflow-y-auto">
      {agents.map((agent) => (
        <div key={agent.name} className="flex items-center gap-2 py-1.5 text-xs border-b border-border/10 last:border-0">
          <span className={`w-2 h-2 rounded-full shrink-0 ${
            agent.status === 'running' ? 'bg-green-500 animate-pulse'
            : agent.status === 'done' ? 'bg-primary'
            : agent.status === 'failed' ? 'bg-red-500'
            : 'bg-muted-foreground/30'
          }`} />
          <span className="font-medium text-foreground w-32 shrink-0">{agent.name}</span>
          <span className="text-muted-foreground flex-1 truncate">{agent.task}</span>
          <span className="text-muted-foreground/60 shrink-0">
            {agent.elapsed_seconds > 0 ? `${Math.floor(agent.elapsed_seconds / 60)}m ${Math.floor(agent.elapsed_seconds % 60)}s` : '—'}
          </span>
        </div>
      ))}
      {agents.length === 0 && (
        <div className="text-center text-muted-foreground text-sm py-8">
          No agents running. Start generation to see activity.
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Create EpicSidebar**

```typescript
// front/src/components/engine/EpicSidebar.tsx
import type { EpicInfo } from '@/services/engineApi';

interface EpicSidebarProps {
  epics: EpicInfo[];
}

export function EpicSidebar({ epics }: EpicSidebarProps) {
  return (
    <div className="w-60 border-l border-border/30 p-3 overflow-y-auto">
      {epics.map((epic) => (
        <div key={epic.id} className="bg-muted/30 rounded-lg p-2.5 mb-2">
          <div className="flex justify-between text-xs">
            <span className="font-medium text-foreground">{epic.name}</span>
            <span className="font-semibold text-green-400">{epic.progress_pct}%</span>
          </div>
          <div className="h-0.5 bg-background rounded-full mt-1.5">
            <div
              className="h-full rounded-full bg-gradient-to-r from-primary to-green-500"
              style={{ width: `${epic.progress_pct}%` }}
            />
          </div>
          <div className="text-[10px] text-muted-foreground mt-1">
            {epic.tasks_complete}/{epic.tasks_total} tasks
          </div>
        </div>
      ))}
      {epics.length === 0 && (
        <div className="text-center text-muted-foreground text-xs py-4">
          No epics loaded yet.
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Create GenerationMonitor container**

```typescript
// front/src/components/engine/GenerationMonitor.tsx
import { useState } from 'react';
import { useGenerationStatus } from '@/hooks/useEngine';
import { ProgressHeader } from './ProgressHeader';
import { AgentList } from './AgentList';
import { EpicSidebar } from './EpicSidebar';

interface GenerationMonitorProps {
  projectName: string;
}

const SUB_TABS = ['Agents', 'Epics', 'Tasks', 'Dependencies', 'Logs', 'Validation', 'Traceability'] as const;

export function GenerationMonitor({ projectName }: GenerationMonitorProps) {
  const { data: status } = useGenerationStatus(projectName);
  const [activeTab, setActiveTab] = useState<string>('Agents');

  if (!status) return null;

  return (
    <div className="flex flex-col h-full">
      <ProgressHeader
        projectName={projectName}
        phase={status.phase}
        progressPct={status.progress_pct}
        serviceCount={status.service_count}
        endpointCount={status.endpoint_count}
      />
      <div className="flex border-b border-border/30 px-2">
        {SUB_TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-3 py-1.5 text-[11px] border-b-2 transition-colors ${
              activeTab === tab
                ? 'text-primary border-primary'
                : 'text-muted-foreground border-transparent hover:text-foreground'
            }`}
          >
            {tab}
            {tab === 'Agents' && status.agents.length > 0 && (
              <span className="ml-1 text-[9px] bg-primary/10 text-primary px-1.5 rounded">
                {status.agents.length}
              </span>
            )}
          </button>
        ))}
      </div>
      <div className="flex flex-1 overflow-hidden">
        {activeTab === 'Agents' && <AgentList agents={status.agents} />}
        {activeTab !== 'Agents' && (
          <div className="flex-1 flex items-center justify-center text-muted-foreground text-sm">
            {activeTab} view coming soon
          </div>
        )}
        <EpicSidebar epics={status.epics} />
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Commit**

```bash
git add front/src/components/engine/ProgressHeader.tsx front/src/components/engine/AgentList.tsx front/src/components/engine/EpicSidebar.tsx front/src/components/engine/GenerationMonitor.tsx
git commit -m "feat: add Generation Monitor with agents, epics, and progress"
```

---

### Task 11: Work Tabs Switcher

**Files:**
- Create: `front/src/components/engine/WorkTabs.tsx`

- [ ] **Step 1: Create WorkTabs component**

```typescript
// front/src/components/engine/WorkTabs.tsx
import { useState } from 'react';
import { useEngineStore } from '@/stores/engineStore';

interface WorkTabsProps {
  children: {
    vibeCoder: React.ReactNode;
    generationMonitor: React.ReactNode;
  };
}

export function WorkTabs({ children }: WorkTabsProps) {
  const [activeTab, setActiveTab] = useState<'vibe' | 'monitor'>('vibe');
  const { phase, agents } = useEngineStore();
  const isRunning = !['idle', 'complete', 'failed'].includes(phase);

  return (
    <div className="flex flex-col h-full">
      <div className="h-8 bg-background flex items-center px-2 gap-1 border-b border-border/30 shrink-0">
        <button
          onClick={() => setActiveTab('vibe')}
          className={`px-3 py-1 rounded text-xs transition-colors ${
            activeTab === 'vibe'
              ? 'bg-primary/10 text-primary'
              : 'text-muted-foreground hover:text-foreground'
          }`}
        >
          💬 Vibe Coder
        </button>
        <button
          onClick={() => setActiveTab('monitor')}
          className={`px-3 py-1 rounded text-xs transition-colors flex items-center gap-1.5 ${
            activeTab === 'monitor'
              ? 'bg-primary/10 text-primary'
              : 'text-muted-foreground hover:text-foreground'
          }`}
        >
          {isRunning && <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />}
          Generation Monitor
          {agents.length > 0 && (
            <span className="text-[9px] bg-primary/10 text-primary px-1.5 rounded">
              {agents.length}
            </span>
          )}
        </button>
      </div>
      <div className="flex-1 overflow-hidden">
        <div className={activeTab === 'vibe' ? 'h-full' : 'hidden'}>
          {children.vibeCoder}
        </div>
        <div className={activeTab === 'monitor' ? 'h-full' : 'hidden'}>
          {children.generationMonitor}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add front/src/components/engine/WorkTabs.tsx
git commit -m "feat: add WorkTabs switcher for Vibe Coder / Generation Monitor"
```

---

### Task 12: Engine Editor Page

**Files:**
- Create: `front/src/pages/EngineEditor.tsx`
- Modify: `front/src/App.tsx`

- [ ] **Step 1: Create EngineEditor page**

This is the main unified editor page for Engine projects. It reuses existing ChatPanel, CodeEditor, FileExplorer from DaveLovable, and adds VncPreview + GenerationMonitor.

```typescript
// front/src/pages/EngineEditor.tsx
import { useParams } from 'react-router-dom';
import { useEngineProject, useGenerationStatus, useStartGeneration } from '@/hooks/useEngine';
import { WorkTabs } from '@/components/engine/WorkTabs';
import { VncPreview } from '@/components/engine/VncPreview';
import { GenerationMonitor } from '@/components/engine/GenerationMonitor';
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from '@/components/ui/resizable';

const EngineEditor = () => {
  const { projectName } = useParams<{ projectName: string }>();
  const { data: project, isLoading } = useEngineProject(projectName || '');
  const { data: status } = useGenerationStatus(projectName || '');
  const startGen = useStartGeneration();

  if (!projectName) return <div>No project selected</div>;
  if (isLoading) return <div className="flex items-center justify-center h-screen text-muted-foreground">Loading project...</div>;

  return (
    <div className="h-screen flex flex-col bg-background">
      {/* Main content */}
      <div className="flex-1 flex overflow-hidden">
        <ResizablePanelGroup direction="horizontal">
          {/* Left: Work Area */}
          <ResizablePanel defaultSize={70} minSize={50}>
            <WorkTabs>
              {{
                vibeCoder: (
                  <div className="h-full flex flex-col items-center justify-center text-muted-foreground">
                    <p className="text-lg mb-2">💬 Vibe Coder</p>
                    <p className="text-sm">Chat + Code Editor for live adjustments</p>
                    <p className="text-xs mt-4">
                      This will be connected to the existing ChatPanel + CodeEditor
                      <br />once we wire up engine file serving.
                    </p>
                    {status?.phase === 'idle' && (
                      <button
                        onClick={() => startGen.mutate({ name: projectName, skeletonOnly: true })}
                        className="mt-4 px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm"
                      >
                        ▶ Start Skeleton Generation
                      </button>
                    )}
                  </div>
                ),
                generationMonitor: (
                  <GenerationMonitor projectName={projectName} />
                ),
              }}
            </WorkTabs>
          </ResizablePanel>

          <ResizableHandle withHandle />

          {/* Right: VNC Preview (Always Visible) */}
          <ResizablePanel defaultSize={30} minSize={20}>
            <VncPreview projectName={projectName} />
          </ResizablePanel>
        </ResizablePanelGroup>
      </div>
    </div>
  );
};

export default EngineEditor;
```

- [ ] **Step 2: Add route to App.tsx**

```typescript
// Add import
import EngineEditor from './pages/EngineEditor';

// Add route
<Route path="/engine-editor/:projectName" element={<EngineEditor />} />
```

- [ ] **Step 3: Commit**

```bash
git add front/src/pages/EngineEditor.tsx front/src/App.tsx
git commit -m "feat: add EngineEditor page with WorkTabs, VNC preview, and generation monitor"
```

---

## Chunk 4: Unified Projects + Polish (Tasks 13–16)

### Task 13: Unified Project Card

**Files:**
- Create: `front/src/components/projects/UnifiedProjectCard.tsx`
- Create: `front/src/components/projects/ProjectFilters.tsx`

- [ ] **Step 1: Create UnifiedProjectCard**

```typescript
// front/src/components/projects/UnifiedProjectCard.tsx
import { useNavigate } from 'react-router-dom';
import type { Project } from '@/services/api';
import type { EngineProject } from '@/services/engineApi';

type CardProject = {
  type: 'engine' | 'vibe';
  name: string;
  description: string;
  stats: { label: string; value: string | number }[];
  status: string;
  progressPct?: number;
  navigateTo: string;
};

function toCardProject(project: Project): CardProject {
  return {
    type: 'vibe',
    name: project.name,
    description: project.description || 'Vibe project',
    stats: [
      { label: '📄', value: `${project.files?.length || 0} files` },
    ],
    status: project.status || 'active',
    navigateTo: `/editor/${project.id}`,
  };
}

function engineToCardProject(project: EngineProject): CardProject {
  return {
    type: 'engine',
    name: project.name.replace(/_\d+$/, '').replace(/-/g, ' '),
    description: `${project.service_count} microservices`,
    stats: [
      { label: '📊', value: `${project.endpoint_count} endpoints` },
      { label: '📋', value: `${project.story_count} stories` },
    ],
    status: 'ready',
    navigateTo: `/engine-editor/${encodeURIComponent(project.name)}`,
  };
}

interface UnifiedProjectCardProps {
  project?: Project;
  engineProject?: EngineProject;
}

export function UnifiedProjectCard({ project, engineProject }: UnifiedProjectCardProps) {
  const navigate = useNavigate();
  const card = project ? toCardProject(project) : engineProject ? engineToCardProject(engineProject) : null;
  if (!card) return null;

  return (
    <div
      onClick={() => navigate(card.navigateTo)}
      className="bg-card rounded-xl overflow-hidden border border-border/30 hover:border-primary/40 transition-all cursor-pointer hover:-translate-y-0.5"
    >
      <div className={`h-24 flex items-center justify-center relative ${
        card.type === 'engine'
          ? 'bg-gradient-to-br from-blue-950/50 to-background'
          : 'bg-gradient-to-br from-purple-950/50 to-background'
      }`}>
        <span className={`absolute top-2 right-2 text-[10px] font-semibold px-2 py-0.5 rounded border ${
          card.type === 'engine'
            ? 'bg-blue-500/10 text-blue-400 border-blue-500/30'
            : 'bg-purple-500/10 text-purple-400 border-purple-500/30'
        }`}>
          {card.type === 'engine' ? '⚡ Engine' : '💜 Vibe'}
        </span>
      </div>
      {card.progressPct !== undefined && (
        <div className="h-0.5 bg-muted">
          <div className="h-full bg-gradient-to-r from-primary to-green-500" style={{ width: `${card.progressPct}%` }} />
        </div>
      )}
      <div className="p-3">
        <h3 className="text-sm font-semibold capitalize">{card.name}</h3>
        <p className="text-[11px] text-muted-foreground mt-0.5">{card.description}</p>
        <div className="flex gap-3 mt-2 text-[10px] text-muted-foreground">
          {card.stats.map((s, i) => (
            <span key={i}>{s.label} {s.value}</span>
          ))}
        </div>
      </div>
    </div>
  );
}

export { toCardProject, engineToCardProject };
```

- [ ] **Step 2: Create ProjectFilters**

```typescript
// front/src/components/projects/ProjectFilters.tsx
interface ProjectFiltersProps {
  active: string;
  onChange: (filter: string) => void;
}

const FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'engine', label: '⚡ Engine' },
  { key: 'vibe', label: '💜 Vibe' },
  { key: 'running', label: '▶ Running' },
];

export function ProjectFilters({ active, onChange }: ProjectFiltersProps) {
  return (
    <div className="flex gap-2">
      {FILTERS.map((f) => (
        <button
          key={f.key}
          onClick={() => onChange(f.key)}
          className={`px-3 py-1 rounded-md text-xs border transition-colors ${
            active === f.key
              ? 'bg-primary/10 border-primary/40 text-primary'
              : 'border-border/30 text-muted-foreground hover:text-foreground'
          }`}
        >
          {f.label}
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add front/src/components/projects/UnifiedProjectCard.tsx front/src/components/projects/ProjectFilters.tsx
git commit -m "feat: add UnifiedProjectCard and ProjectFilters components"
```

---

### Task 14: Update Projects Page

**Files:**
- Modify: `front/src/pages/Projects.tsx`

- [ ] **Step 1: Update Projects page to show both project types**

Import and use `useEngineProjects`, `UnifiedProjectCard`, and `ProjectFilters`. Keep the existing DaveLovable project listing but add engine projects alongside them. Add the filter bar at the top.

Key changes:
- Import `useEngineProjects` from `@/hooks/useEngine`
- Import `UnifiedProjectCard` and `ProjectFilters`
- Add `filter` state (default: 'all')
- Combine both project lists, sorted by type then name
- Replace existing ProjectCard with UnifiedProjectCard
- Add filter bar below the page header

- [ ] **Step 2: Verify Projects page loads both types**

```bash
cd C:\Users\User\Desktop\DaveLovable\front
npm run build
```

Expected: No TypeScript errors.

- [ ] **Step 3: Commit**

```bash
git add front/src/pages/Projects.tsx
git commit -m "feat: unify Projects page with Engine + Vibe projects and filters"
```

---

### Task 15: Navbar Redesign

**Files:**
- Modify: `front/src/components/Navbar.tsx`

- [ ] **Step 1: Update Navbar with new tab-based navigation**

Replace the current Navbar with the unified design:
- Logo on the left
- Tab-style navigation: Projects | Marketplace | Docs (Editor is opened via project click)
- Right side: EngineStatusPill + user avatar
- Keep mobile menu support
- Use the same DaveLovable styling (glass effect, gradients)

Import `EngineStatusPill` from `@/components/engine/EngineStatusPill`.
Use `NavLink` from react-router-dom for active tab styling.

- [ ] **Step 2: Commit**

```bash
git add front/src/components/Navbar.tsx
git commit -m "feat: redesign Navbar with unified tabs and engine status"
```

---

### Task 16: End-to-End Smoke Test

- [ ] **Step 1: Start backend**

```bash
cd C:\Users\User\Desktop\DaveLovable\backend
python -m uvicorn app.main:app --reload --port 8000
```

- [ ] **Step 2: Start frontend**

```bash
cd C:\Users\User\Desktop\DaveLovable\front
npm run dev
```

- [ ] **Step 3: Verify in browser**

1. Open `http://localhost:5173/projects` — should see both Engine and Vibe project cards
2. Click an Engine project card — should navigate to `/engine-editor/{name}`
3. Engine Editor should show WorkTabs (Vibe Coder / Generation Monitor) + VNC Preview
4. Click "Start Skeleton Generation" — should trigger backend generation
5. Switch between Vibe Coder and Generation Monitor tabs — VNC stays visible
6. Navigate to `/marketplace` — should show placeholder page
7. Navigate to `/docs` — should show Documentation page
8. EngineStatusPill in nav should reflect generation state

- [ ] **Step 4: Fix any issues found**

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "fix: resolve smoke test issues"
```

---

## Summary

| Chunk | Tasks | What it delivers |
|-------|-------|-----------------|
| **1: Backend Engine API** | 1–4 | REST endpoints + WebSocket for engine projects and generation |
| **2: Frontend Foundation** | 5–8 | API client, hooks, Zustand store, routes, Navbar |
| **3: Engine Components** | 9–12 | VNC Preview, Generation Monitor, WorkTabs, EngineEditor page |
| **4: Projects + Polish** | 13–16 | Unified project cards, filters, Navbar redesign, smoke test |

**Total: 16 tasks, ~14 new files, ~5 modified files**

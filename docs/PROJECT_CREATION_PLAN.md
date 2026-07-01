# OSA Project Creation Feature — Implementation Plan

**Status:** Design phase  
**Last Updated:** 2026-07-01  
**Owner:** AgenticOS team  
**Phase:** 11 (post-Phase 10)

---

## Executive Summary

Enable OSA to scaffold new Codehome projects end-to-end:
- Interactive form (drawer panel from SysOps) with project name, tech stack template, optional description, and subfolder selection
- Auto-create folder structure in correct subfolder
- Auto-create Python virtual environment (via `uv venv` for Python projects)
- Auto-detect next available port (no collisions)
- Auto-generate starter files (README, .gitignore, pyproject.toml, app.json)
- **UV integration for Python templates:** Modern dependency management via `uv` + `pyproject.toml` + `uv.lock`
- Create GitHub repo via API (requires GitHub token in Settings)
- Register app in OSA's app registry (MySQL `apps` table)

**Design decisions (from interview):**
- **UI:** Drawer panel (right sidebar) with form
- **Tech stack:** Template-based selection (FastAPI, React, Node.js, etc.)
- **GitHub:** All-in-one flow; requires pre-configured token in Settings
- **Subfolders:** Auto-scan Codehome for patterns (agents/, apps/, tools/); offer dropdown
- **Ports:** Auto-assign next free port (no user intervention)
- **Form fields:** Advanced mode (name, template, description, subfolder, custom port optional)
- **Files:** Always generate starter files per template

---

## User Journey

```
1. User clicks "New Project" button in SysOps > CODEHOME HUB
   ↓
2. Drawer slides in from right with form:
   - Project name (required, slug-friendly validation)
   - Tech stack template (FastAPI, React, Node.js, etc.) (required)
   - Description (optional)
   - Subfolder (auto-detected dropdown or custom)
   - Custom port (optional; if blank, auto-assigned)
   ↓
3. User fills form → "Create Project" button
   ↓
4. OSA workflow (in sidecar):
   ✓ Validate inputs (name, port availability, GitHub token)
   ✓ Create folder: ~/Codehome/<subfolder>/<project-name>/
   ✓ Create Python venv: <project>/.venv
   ✓ Generate starter files (template-specific)
   ✓ Allocate port in `ports` table (auto-increment if collision)
   ✓ Create app.json with metadata
   ✓ Create GitHub repo via API
   ✓ git init + initial commit
   ✓ Register in `apps` table
   ↓
5. Success message → drawer closes
   App now appears in SysOps app list
```

---

## Architecture

### UI Layer (React - Tauri GUI)

**New component:** `gui/desktop/src/components/ProjectCreationDrawer.jsx`

- Triggered by button in SysOps > CODEHOME HUB panel
- Form with validation
- Streams progress updates during creation
- Success/error toast messages

**State flow:**
```
Form submission → POST /api/projects/create (streaming WebSocket)
                → Progress updates: "Creating folder...", "Setting venv...", "Creating GitHub..."
                → Success or error with details
```

### Sidecar Layer (FastAPI)

**New modules:**

1. **`gui/sidecar/project_manager.py`** — orchestration
   - `create_project()` — main state machine
   - Validation, folder creation, venv setup
   - GitHub repo creation
   - Database registration

2. **`gui/sidecar/template_registry.py`** — template definitions
   - Predefined templates (FastAPI, React, Node.js, etc.)
   - Starter file content (README, .gitignore, requirements.txt, app.json)
   - Dependency lists per template

3. **`gui/sidecar/routes/api_projects.py`** — REST endpoints
   - `GET /api/projects/templates` — list available templates
   - `GET /api/projects/subfolders` — auto-scanned Codehome structure
   - `GET /api/projects/port-check?port=5200` — check port availability
   - `POST /api/projects/create` — streaming endpoint (WebSocket or SSE)

4. **`gui/sidecar/github_integration.py`** — GitHub API wrapper
   - Read GitHub token from Settings
   - Create repo via GitHub REST API
   - Set up remote in local git
   - Handle 2FA / auth errors gracefully

### Database Layer (MySQL)

**New table:** `projects` (tracks all projects created via OSA)

```sql
CREATE TABLE projects (
  id VARCHAR(128) PRIMARY KEY,
  name VARCHAR(255) NOT NULL,
  description TEXT,
  path VARCHAR(512) NOT NULL UNIQUE,
  subfolder VARCHAR(128) COMMENT 'agents, apps, tools, etc.',
  template VARCHAR(128) NOT NULL COMMENT 'fastapi, react, nodejs, etc.',
  port INT UNSIGNED,
  github_repo_url VARCHAR(512),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  created_by VARCHAR(255),
  INDEX idx_subfolder (subfolder),
  INDEX idx_template (template)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**Relationship:**
- Each project → entry in `projects` table
- When project is started → entry in `apps` table (auto-created by app scanner)

---

## Templates

### Template Structure

Each template defines:
- Name, description, icon
- Default dependencies (Python packages, npm packages, etc.)
- Starter files (README, .gitignore, requirements.txt/package.json, app.json)

### Built-in Templates (10 total)

#### Python Backends

##### 1. **FastAPI Backend** (UV-powered)
- Python 3.10+
- Package manager: `uv` (fast, modern)
- Dependencies: fastapi, uvicorn, pydantic, SQLAlchemy
- Files:
  - `pyproject.toml` (UV project config + dependencies)
  - `uv.lock` (generated lockfile for reproducibility)
  - `README.md` (project-specific)
  - `.gitignore` (Python)
  - `app.json` (agent_block with sidecar metadata)
  - `src/main.py` (starter app)
- Venv: Created via `uv venv`; dependencies installed via `uv pip install`

##### 2. **Django + REST Framework** (UV-powered)
- Python 3.10+
- Package manager: `uv`
- Dependencies: django, djangorestframework, python-dotenv
- Files:
  - `pyproject.toml`
  - `uv.lock`
  - `README.md`
  - `.gitignore`
  - `app.json`
  - `manage.py` (Django management)
  - `config/settings.py` (Django config)
- Venv: Created via `uv venv`

#### Frontend & Full-Stack

##### 3. **React + Vite**
- Node 18+
- Dependencies: react, react-dom, vite
- Files:
  - `package.json` (generated)
  - `README.md`
  - `.gitignore` (Node)
  - `app.json`
  - `src/App.jsx` (starter)
  - `vite.config.js`

##### 4. **Next.js**
- Node 18+
- Dependencies: next, react, react-dom
- Files:
  - `package.json`
  - `README.md`
  - `.gitignore`
  - `app.json`
  - `app/page.jsx` (App Router)
  - `next.config.js`
  - Built-in API routes at `app/api/`

##### 5. **Svelte + Vite**
- Node 18+
- Dependencies: svelte, vite
- Files:
  - `package.json`
  - `README.md`
  - `.gitignore`
  - `app.json`
  - `src/App.svelte` (starter)
  - `vite.config.js`

##### 6. **Astro**
- Node 18+
- Dependencies: astro
- Files:
  - `package.json`
  - `README.md`
  - `.gitignore`
  - `app.json`
  - `src/pages/index.astro` (starter)
  - `astro.config.mjs`
  - Built-in API routes at `src/pages/api/`

#### Backend + Misc

##### 7. **Node.js + Express**
- Node 18+
- Dependencies: express, dotenv, cors
- Files:
  - `package.json`
  - `README.md`
  - `.gitignore`
  - `app.json`
  - `src/server.js` (starter)

##### 8. **Full-Stack (FastAPI + React)** (Backend with UV)
- Folder structure:
  ```
  my-project/
  ├── backend/
  │   ├── pyproject.toml
  │   ├── uv.lock
  │   └── src/main.py
  ├── frontend/
  │   ├── package.json
  │   └── src/App.jsx
  ├── docker-compose.yml
  └── README.md
  ```
- Backend uses `uv` for dependency management
- Frontend uses npm/Vite

##### 9. **Python CLI Tool** (UV-powered)
- Python 3.10+
- Package manager: `uv`
- Dependencies: click, typer
- Entry point in `app.json::scripts`
- Files:
  - `pyproject.toml`
  - `uv.lock`
  - `README.md`
  - `.gitignore`
  - `app.json`
  - `src/cli.py` (starter with click/typer)
- Venv: Created via `uv venv`

##### 10. **Monorepo (empty structure)**
- No predefined tech
- Just folder structure + README
- User fills in apps/services

---

## Implementation Details

### Phase 1: Foundation (Week 1)

#### 1.1 Template Registry
**File:** `gui/sidecar/template_registry.py`

```python
TEMPLATES = {
    "fastapi": {
        "name": "FastAPI Backend",
        "description": "Python async API with Pydantic models (UV-powered)",
        "python_version": "3.10+",
        "package_manager": "uv",
        "dependencies": ["fastapi", "uvicorn", "pydantic", "sqlalchemy"],
        "files": {
            "pyproject.toml": "...",  # UV project config with dependencies
            "uv.lock": "...",  # Auto-generated lockfile
            "README.md": "...",
            ".gitignore": "...",
            "app.json": {...},
            "src/main.py": "..."
        }
    },
    "django": {
        "name": "Django + REST Framework",
        "description": "Full-featured Django API (UV-powered)",
        "python_version": "3.10+",
        "package_manager": "uv",
        "dependencies": ["django", "djangorestframework", "python-dotenv"],
        "files": {
            "pyproject.toml": "...",
            "uv.lock": "...",
            "README.md": "...",
            ".gitignore": "...",
            "app.json": {...},
            "manage.py": "...",
            "config/settings.py": "..."
        }
    },
    "react": {...},
    ...
}

def get_template(name: str) -> dict:
    """Return template definition."""
    if name not in TEMPLATES:
        raise ValueError(f"Unknown template: {name}")
    return TEMPLATES[name]

def generate_files(template_name: str, project_name: str, description: str) -> dict:
    """Render template files with project-specific values."""
    template = get_template(template_name)
    files = {}
    for filename, content in template["files"].items():
        # Substitute {project_name}, {description}, etc.
        files[filename] = content.format(
            project_name=project_name,
            description=description or "A Codehome project",
            year=2026
        )
    
    # For Python templates, generate pyproject.toml from template
    if template_name in PYTHON_TEMPLATES:
        files["pyproject.toml"] = generate_pyproject_toml(
            project_name=project_name,
            description=description,
            dependencies=template.get("dependencies", [])
        )
    
    return files

def generate_pyproject_toml(project_name: str, description: str, dependencies: list) -> str:
    """
    Generate pyproject.toml for Python projects (UV-compatible).
    Example output:
    ```toml
    [project]
    name = "my-project"
    version = "0.1.0"
    description = "A cool API"
    requires-python = ">=3.10"
    dependencies = [
        "fastapi>=0.100",
        "uvicorn>=0.24",
        ...
    ]

    [tool.uv]
    dev-dependencies = [
        "pytest>=7.0",
        "black>=23.0",
        "ruff>=0.1.0",
    ]
    ```
    """
    deps_str = "\n    ".join(f'"{d}>="' for d in dependencies)
    
    return f"""[project]
name = "{project_name}"
version = "0.1.0"
description = "{description}"
requires-python = ">=3.10"
dependencies = [
    {deps_str}
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.uv]
dev-dependencies = [
    "pytest>=7.0",
    "black>=23.0",
    "ruff>=0.1.0",
    "mypy>=1.0",
]
"""
```

#### 1.2 Subfolder Detection
**File:** `gui/sidecar/project_manager.py`

```python
def scan_codehome_structure() -> dict:
    """
    Auto-detect folder structure under ~/Codehome.
    Returns: {
        "suggested": ["agents", "apps", "tools"],  # most common
        "all": ["agents", "apps", "tools", "data", "scripts", "lib"],
        "custom_available": True  # user can create new subfolder
    }
    """
    codehome = Path.home() / "Codehome"
    if not codehome.exists():
        return {"suggested": [], "all": [], "custom_available": True}
    
    folders = {d.name for d in codehome.iterdir() if d.is_dir()}
    suggested = [f for f in ["agents", "apps", "tools"] if f in folders]
    
    return {
        "suggested": suggested or ["apps"],
        "all": sorted(folders),
        "custom_available": True
    }
```

#### 1.3 Port Allocation
**File:** `gui/sidecar/project_manager.py`

```python
def allocate_port(app_id: str, preferred_port: int = None, session: Session = None) -> int:
    """
    Allocate port from DB. If preferred_port taken, auto-assign next free.
    """
    from gui.sidecar.database import SessionLocal
    if session is None:
        session = SessionLocal()
    
    if preferred_port:
        existing = session.query(Port).filter(Port.port == preferred_port).first()
        if not existing:
            port = Port(app_id=app_id, port=preferred_port, status='allocated')
            session.add(port)
            session.commit()
            return preferred_port
    
    # Auto-assign next free port
    used = {p.port for p in session.query(Port.port).all()}
    for candidate in range(5200, 6000):
        if candidate not in used:
            port = Port(app_id=app_id, port=candidate, status='allocated')
            session.add(port)
            session.commit()
            return candidate
    
    raise RuntimeError("No free ports available")
```

#### 1.4 Folder Creation
**File:** `gui/sidecar/project_manager.py`

```python
def create_project_folder(subfolder: str, project_name: str) -> Path:
    """
    Create ~/Codehome/<subfolder>/<project_name>/
    If subfolder doesn't exist, create it.
    """
    codehome = Path.home() / "Codehome"
    codehome.mkdir(parents=True, exist_ok=True)
    
    folder = codehome / subfolder / project_name
    folder.mkdir(parents=True, exist_ok=True)
    
    return folder
```

#### 1.5 Virtual Environment Setup (UV-powered)
**File:** `gui/sidecar/project_manager.py`

```python
def create_venv(project_path: Path, template_name: str) -> str:
    """
    Create .venv in project folder using UV (modern, fast).
    For Python templates, UV also syncs dependencies from pyproject.toml.
    Returns: path to venv activation script
    """
    venv_path = project_path / ".venv"
    
    # Check if UV is available; fall back to venv if not
    try:
        subprocess.run(["uv", "--version"], check=True, capture_output=True)
        use_uv = True
    except (FileNotFoundError, subprocess.CalledProcessError):
        use_uv = False
    
    if use_uv and template_name in PYTHON_TEMPLATES:
        # UV venv creation + dependency sync in one step
        subprocess.run(
            ["uv", "venv", str(venv_path)],
            cwd=project_path,
            check=True
        )
        # UV sync installs dependencies from pyproject.toml
        subprocess.run(
            ["uv", "pip", "install", "-e", "."],
            cwd=project_path,
            check=True
        )
    else:
        # Fallback to standard venv if UV not available
        subprocess.run([sys.executable, "-m", "venv", str(venv_path)], check=True)
        
        if template_name in PYTHON_TEMPLATES:
            pip_path = venv_path / "bin" / "pip"
            subprocess.run(
                [str(pip_path), "install", "-e", "."],
                cwd=project_path,
                check=True
            )
    
    return str(venv_path / "bin" / "activate")
```

#### 1.6 app.json Generation
**File:** `gui/sidecar/template_registry.py`

```python
def generate_app_json(project_name: str, template: str, port: int, description: str) -> dict:
    """
    Generate app.json for the project.
    """
    return {
        "id": project_name,
        "name": project_name.replace("-", " ").title(),
        "description": description or f"A {template} project",
        "port": port,
        "agent": {
            "api_base": f"http://localhost:{port}/api",
            "tools": TEMPLATES[template].get("agent_tools", [])
        }
    }
```

### Phase 2: GitHub Integration (Week 2)

#### 2.1 GitHub API Client
**File:** `gui/sidecar/github_integration.py`

```python
import requests
from typing import Optional

class GitHubClient:
    def __init__(self, token: str):
        self.token = token
        self.base_url = "https://api.github.com"
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }
    
    def create_repo(self, repo_name: str, description: str = None, private: bool = False) -> dict:
        """Create a new GitHub repo."""
        response = requests.post(
            f"{self.base_url}/user/repos",
            headers=self.headers,
            json={
                "name": repo_name,
                "description": description,
                "private": private,
                "auto_init": False
            }
        )
        response.raise_for_status()
        return response.json()  # Returns: {html_url, clone_url, ssh_url, ...}

    def get_auth_user(self) -> dict:
        """Verify token and get username."""
        response = requests.get(
            f"{self.base_url}/user",
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()

    def check_token_valid(self) -> bool:
        """Test if GitHub token is valid."""
        try:
            self.get_auth_user()
            return True
        except:
            return False
```

#### 2.2 Git Init + Initial Commit
**File:** `gui/sidecar/project_manager.py`

```python
def init_git_repo(project_path: Path, remote_url: str = None) -> None:
    """
    Initialize git repo and make initial commit.
    """
    subprocess.run(["git", "init"], cwd=project_path, check=True)
    subprocess.run(
        ["git", "config", "user.name", "AgenticOS"],
        cwd=project_path, check=True
    )
    subprocess.run(
        ["git", "config", "user.email", "agentic@codehome.local"],
        cwd=project_path, check=True
    )
    
    # Add all generated files
    subprocess.run(["git", "add", "."], cwd=project_path, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial project scaffold"],
        cwd=project_path, check=True
    )
    
    # Add remote if provided
    if remote_url:
        subprocess.run(
            ["git", "remote", "add", "origin", remote_url],
            cwd=project_path, check=True
        )
```

### Phase 3: REST API + Sidecar Integration (Week 3)

#### 3.1 API Endpoints
**File:** `gui/sidecar/routes/api_projects.py`

```python
from fastapi import APIRouter, WebSocket, HTTPException
from gui.sidecar.project_manager import create_project_full
from gui.sidecar.template_registry import TEMPLATES, scan_codehome_structure

router = APIRouter(prefix="/api/projects", tags=["projects"])

@router.get("/templates")
async def list_templates():
    """List all available project templates (10 total)."""
    return {
        "templates": [
            {
                "id": name,
                "name": t["name"],
                "description": t["description"],
                "icon": t.get("icon", "📦"),
                "category": t.get("category", "misc")  # python, node, fullstack, etc.
            }
            for name, t in TEMPLATES.items()
        ],
        "total": len(TEMPLATES)
    }

@router.get("/subfolders")
async def get_subfolders():
    """Get auto-detected subfolders + suggestions."""
    return scan_codehome_structure()

@router.get("/port-check")
async def check_port(port: int):
    """Check if port is available."""
    from gui.sidecar.database import SessionLocal
    db = SessionLocal()
    existing = db.query(Port).filter(Port.port == port).first()
    db.close()
    return {"port": port, "available": existing is None}

@router.websocket("/ws/create")
async def create_project_stream(websocket: WebSocket):
    """
    Streaming project creation via WebSocket.
    Client sends: {name, template, subfolder, description, custom_port?}
    Server streams: {step, status, message, error?}
    """
    await websocket.accept()
    try:
        data = await websocket.receive_json()
        
        # Validation
        await websocket.send_json({"step": "validating", "status": "in_progress"})
        # ... validate inputs ...
        await websocket.send_json({"step": "validating", "status": "complete"})
        
        # Create project
        result = await create_project_full(
            name=data["name"],
            template=data["template"],
            subfolder=data["subfolder"],
            description=data.get("description"),
            custom_port=data.get("custom_port"),
            websocket=websocket
        )
        
        await websocket.send_json({"step": "complete", "status": "success", "result": result})
    
    except Exception as e:
        await websocket.send_json({"step": "error", "status": "failed", "error": str(e)})
    finally:
        await websocket.close()
```

#### 3.2 Orchestration (Full Flow)
**File:** `gui/sidecar/project_manager.py`

```python
async def create_project_full(
    name: str,
    template: str,
    subfolder: str,
    description: str = None,
    custom_port: int = None,
    websocket: WebSocket = None
) -> dict:
    """
    Full project creation workflow with lenient error handling.
    Critical steps (folder, venv, files, port) must succeed.
    Optional steps (GitHub, git) degrade gracefully with warnings.
    Streams progress to WebSocket.
    """
    
    async def emit(step: str, status: str, message: str = None):
        if websocket:
            await websocket.send_json({
                "step": step,
                "status": status,
                "message": message
            })
    
    warnings = []
    
    try:
        # ===== CRITICAL STEPS (must succeed) =====
        
        # 1. Validate inputs
        await emit("validate", "in_progress", "Validating project name and template...")
        if not validate_project_name(name):
            raise ValueError("Invalid project name")
        if template not in TEMPLATES:
            raise ValueError(f"Unknown template: {template}")
        await emit("validate", "complete")
        
        # 2. Create folder structure
        await emit("folder", "in_progress", f"Creating folder: ~/{subfolder}/{name}/...")
        project_path = create_project_folder(subfolder, name)
        await emit("folder", "complete")
        
        # 3. Create venv (Python templates)
        if template in PYTHON_TEMPLATES:
            await emit("venv", "in_progress", "Creating Python virtual environment...")
            try:
                create_venv(project_path, template)
                await emit("venv", "complete")
            except Exception as e:
                warnings.append(f"venv creation failed: {str(e)}. Continuing without venv.")
                await emit("venv", "warning", warnings[-1])
        
        # 4. Generate starter files
        await emit("files", "in_progress", "Generating starter files...")
        files = generate_files(template, name, description)
        for filename, content in files.items():
            filepath = project_path / filename
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(content)
        await emit("files", "complete")
        
        # 5. Allocate port
        await emit("port", "in_progress", "Allocating port...")
        db = SessionLocal()
        port = allocate_port(app_id=name, preferred_port=custom_port, session=db)
        await emit("port", "complete", f"Allocated port {port}")
        
        # 6. Create app.json
        await emit("app_json", "in_progress", "Creating app.json...")
        app_json = generate_app_json(name, template, port, description)
        (project_path / "app.json").write_text(json.dumps(app_json, indent=2))
        await emit("app_json", "complete")
        
        # ===== OPTIONAL STEPS (best-effort) =====
        
        github_url = None
        
        # 7. Create GitHub repo (optional)
        await emit("github_repo", "in_progress", "Creating GitHub repository...")
        try:
            if settings.github.token is None:
                warnings.append("GitHub token not configured. Skipping GitHub repo creation.")
                await emit("github_repo", "warning", warnings[-1])
            else:
                github = GitHubClient(settings.github.token)
                if not github.check_token_valid():
                    warnings.append("GitHub token invalid. Skipping GitHub repo creation.")
                    await emit("github_repo", "warning", warnings[-1])
                else:
                    github_data = github.create_repo(
                        repo_name=name,
                        description=description or f"A {template} project",
                        private=False
                    )
                    github_url = github_data["html_url"]
                    await emit("github_repo", "complete", f"Created {github_url}")
        except Exception as e:
            warnings.append(f"GitHub repo creation failed: {str(e)}. Project created locally.")
            await emit("github_repo", "warning", warnings[-1])
        
        # 8. Init git + initial commit (optional, but attempt)
        await emit("git", "in_progress", "Initializing git repository...")
        try:
            init_git_repo(project_path, github_url if github_url else None)
            await emit("git", "complete")
        except Exception as e:
            warnings.append(f"Git initialization failed: {str(e)}. You can git init later.")
            await emit("git", "warning", warnings[-1])
        
        # 9. Register in projects table
        await emit("register", "in_progress", "Registering project in OSA...")
        project = Project(
            id=name,
            name=name,
            description=description,
            path=str(project_path),
            subfolder=subfolder,
            template=template,
            port=port,
            github_repo_url=github_url
        )
        db.add(project)
        db.commit()
        db.close()
        await emit("register", "complete")
        
        # Return success with warnings
        return {
            "project_id": name,
            "path": str(project_path),
            "port": port,
            "github_url": github_url,
            "warnings": warnings,
            "success": True
        }
    
    except Exception as e:
        # CRITICAL step failed; abort
        await emit("error", "failed", str(e))
        raise
```

### Phase 4: GUI Integration (Week 4)

#### 4.1 Drawer Component
**File:** `gui/desktop/src/components/ProjectCreationDrawer.jsx`

```jsx
import React, { useState } from 'react';
import { useWebSocket } from '../hooks/useWebSocket';

export default function ProjectCreationDrawer({ isOpen, onClose }) {
  const [formData, setFormData] = useState({
    name: '',
    template: 'fastapi',
    subfolder: 'apps',
    description: '',
    customPort: null
  });
  
  const [templates, setTemplates] = useState([]);
  const [subfolders, setSubfolders] = useState([]);
  const [progress, setProgress] = useState(null);
  const [isCreating, setIsCreating] = useState(false);

  React.useEffect(() => {
    if (isOpen) {
      fetch('/api/projects/templates').then(r => r.json()).then(d => setTemplates(d.templates));
      fetch('/api/projects/subfolders').then(r => r.json()).then(d => setSubfolders(d.suggested));
    }
  }, [isOpen]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsCreating(true);
    
    const ws = new WebSocket('ws://localhost:5130/api/projects/ws/create');
    
    ws.onopen = () => {
      ws.send(JSON.stringify(formData));
    };
    
    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      setProgress(msg);
      
      if (msg.step === 'complete' && msg.status === 'success') {
        setTimeout(() => {
          setIsCreating(false);
          onClose();
        }, 1500);
      }
    };
    
    ws.onerror = (e) => {
      setProgress({ status: 'error', message: 'Connection failed' });
      setIsCreating(false);
    };
  };

  return (
    <div className={`drawer ${isOpen ? 'open' : ''}`}>
      <div className="drawer-header">
        <h2>Create New Project</h2>
        <button onClick={onClose}>×</button>
      </div>
      
      <form onSubmit={handleSubmit} className="drawer-body">
        <div className="form-group">
          <label>Project Name *</label>
          <input
            type="text"
            value={formData.name}
            onChange={(e) => setFormData({...formData, name: e.target.value})}
            placeholder="my-project"
            required
            disabled={isCreating}
          />
        </div>
        
        <div className="form-group">
          <label>Tech Stack Template *</label>
          <select
            value={formData.template}
            onChange={(e) => setFormData({...formData, template: e.target.value})}
            disabled={isCreating}
          >
            {templates.map(t => (
              <option key={t.id} value={t.id}>{t.name}</option>
            ))}
          </select>
        </div>
        
        <div className="form-group">
          <label>Subfolder</label>
          <select
            value={formData.subfolder}
            onChange={(e) => setFormData({...formData, subfolder: e.target.value})}
            disabled={isCreating}
          >
            {subfolders.map(s => (
              <option key={s} value={s}>{s}</option>
            ))}
            <option value="">Custom...</option>
          </select>
        </div>
        
        <div className="form-group">
          <label>Description</label>
          <textarea
            value={formData.description}
            onChange={(e) => setFormData({...formData, description: e.target.value})}
            placeholder="What does this project do?"
            disabled={isCreating}
          />
        </div>
        
        <div className="form-group">
          <label>Custom Port (optional)</label>
          <input
            type="number"
            value={formData.customPort || ''}
            onChange={(e) => setFormData({...formData, customPort: e.target.value ? parseInt(e.target.value) : null})}
            placeholder="Leave blank to auto-assign"
            min="1000"
            max="65535"
            disabled={isCreating}
          />
        </div>
        
        {progress && (
          <div className="progress">
            <div className="progress-item">
              <span>{progress.step}</span>
              <span className={`status ${progress.status}`}>{progress.status}</span>
            </div>
            {progress.message && <p>{progress.message}</p>}
          </div>
        )}
        
        <div className="drawer-footer">
          <button type="button" onClick={onClose} disabled={isCreating}>Cancel</button>
          <button type="submit" disabled={isCreating || !formData.name || !formData.template}>
            {isCreating ? 'Creating...' : 'Create Project'}
          </button>
        </div>
      </form>
    </div>
  );
}
```

#### 4.2 Trigger Button in SysOps
**File:** `gui/desktop/src/components/SysOpsDashboard.jsx`

```jsx
// In the CODEHOME HUB panel section
<button 
  className="primary"
  onClick={() => setShowProjectCreation(true)}
>
  + New Project
</button>

{showProjectCreation && (
  <ProjectCreationDrawer 
    isOpen={showProjectCreation}
    onClose={() => setShowProjectCreation(false)}
  />
)}
```

---

## Database Schema (new)

```sql
-- Add to app_registry schema

CREATE TABLE projects (
  id VARCHAR(128) PRIMARY KEY,
  name VARCHAR(255) NOT NULL,
  description TEXT,
  path VARCHAR(512) NOT NULL UNIQUE,
  subfolder VARCHAR(128),
  template VARCHAR(128) NOT NULL,
  port INT UNSIGNED,
  github_repo_url VARCHAR(512),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  created_by VARCHAR(255) DEFAULT 'osa',
  INDEX idx_subfolder (subfolder),
  INDEX idx_template (template),
  INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Foreign key: projects.id → apps.id (when app is discovered)
-- Link: projects.port → ports.port
```

---

## Settings Configuration

Add to `config/settings.yaml`:

```yaml
github:
  token: ${GITHUB_TOKEN}  # or null; user sets in GUI Settings
  username: null          # auto-populated on first GitHub call
  api_base: https://api.github.com

project_defaults:
  python_version: "3.10"
  node_version: "18"
  port_range:
    start: 5200
    end: 6000
  use_uv: true            # Use UV for Python projects (auto-detect if available)
  uv_sync_dev: true       # Include dev dependencies in uv.lock
```

**UV Prerequisites:**
- `uv` must be installed on the system: `pip install uv` or `brew install uv`
- Fallback: If `uv` not found, template creation falls back to standard `python -m venv`
- OSA detects UV availability at project creation time (no silent failures)

**GUI Settings update:**
- Add "GitHub Settings" section with token input
- Test token validity on save
- Display GitHub username if configured

---

## Error Handling & Graceful Degradation

**Policy: Lenient (create project locally; warn on GitHub/UV failures)**

| Scenario | Behavior |
|---|---|
| GitHub token missing | ⚠️ Warn user; create project locally; offer to configure token later in Settings |
| GitHub API rate limit | ⚠️ Warn user; project created locally; suggest retry in 1 hour |
| GitHub repo creation fails (network, auth, etc.) | ⚠️ Warn user; project created locally; skip git remote setup |
| UV not installed (Python template) | ⚠️ Warn user; fall back to `python -m venv`; project still created |
| UV venv creation fails | ⚠️ Fall back to standard venv; project still created |
| Port range exhausted | Fail (critical); suggest deleting unused projects |
| Folder already exists | Warn; allow overwrite (dangerous) or new name |
| venv creation fails (e.g., Python not found) | ⚠️ Warn user; skip venv; project still created (user can manually create venv) |
| Git init fails | ⚠️ Warn; project still created (user can git init later) |

**Summary:** Folder + files + app.json + port allocation ALWAYS succeed. UV, GitHub, and git operations are best-effort; failures don't block project creation. Fallbacks ensure robust scaffolding.

---

## Acceptance Criteria

| # | Criterion | Status |
|---|-----------|--------|
| 1 | Form captures: name, template, subfolder, description, custom port | Design ✅ |
| 2 | Auto-scan Codehome for subfolder suggestions | Design ✅ |
| 3 | Create folder structure in correct subfolder | Design ✅ |
| 4 | Create Python venv (for Python templates) | Design ✅ |
| 5 | Auto-detect/allocate free port (no collisions) | Design ✅ |
| 6 | Generate starter files per template | Design ✅ |
| 7 | Create app.json with port + metadata | Design ✅ |
| 8 | Create GitHub repo (requires token in Settings) | Design ✅ |
| 9 | git init + initial commit | Design ✅ |
| 10 | Register project in `projects` + `apps` tables | Design ✅ |
| 11 | Streaming progress updates via WebSocket | Design ✅ |
| 12 | Error handling + graceful fallbacks | Design ✅ |

---

## Risk Mitigation

| Risk | Mitigation |
|---|---|
| GitHub token leaks in logs | Store in environment variable; never log token; mask in responses |
| Folder creation race (two requests simultaneously) | Use DB transaction + UNIQUE constraint on path; fs-level locking |
| Port collision during creation | Transaction isolation + atomic allocate_port() with retry logic |
| Venv creation fails (Python missing) | Log warning to user; project still created (venv is optional) |
| User cancels mid-creation | Partial folder created; user can delete manually (idempotent) |
| GitHub rate limit hit | Graceful degradation; warn user; suggest retry in 1 hour |
| Git remote configuration fails | Log warning; local repo still usable; user can add remote later |
| Multiple projects with same name | DB UNIQUE constraint on `projects.path` prevents duplicates |

---

## Implementation Timeline

- **Week 1 (Phase 11a):** Template registry + subfolder detection + venv setup
- **Week 2 (Phase 11b):** GitHub API client + git integration
- **Week 3 (Phase 11c):** REST API + orchestration flow
- **Week 4 (Phase 11d):** GUI drawer + integration with SysOps
- **Week 5 (validation):** End-to-end testing + edge cases

---

## Open Questions & Notes

1. **Should we allow editing projects after creation?** (Scope: Phase 12+)
2. **Should we support project templates from Git (custom repos)?** (Future)
3. **Should subfolders be user-creatable via the form?** (Scope: allow "New subfolder" option)
4. **GitHub org vs personal repo?** (Design: default to personal; org selection in future)

---

**Status:** Ready for Phase 11 implementation  
**Next step:** Begin Phase 11a (template registry + subfolder detection)

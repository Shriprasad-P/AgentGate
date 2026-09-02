import json
import time
from datetime import datetime
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import settings
from app.database import (
    Agent,
    AgentStatus,
    AuditEventType,
    AuditLog,
    get_db,
    init_db,
)
from app.runner import AgentRunner
from app.schemas import (
    AgentCreate,
    AgentResponse,
    AgentRunRequest,
    AgentRunResponse,
    AgentStatusUpdate,
    AgentUpdate,
    AuditLogResponse,
    ChatCompletionChoice,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
)

app = FastAPI(
    title="AgentGate",
    description="Agent-level control plane for coding agents",
    version="0.1.0"
)

# Templates for dashboard
templates = Jinja2Templates(directory="app/templates")

# Initialize database on startup
@app.on_event("startup")
def startup_event():
    init_db()
    seed_agents()


def seed_agents():
    """Seed initial demo agents if database is empty."""
    db = next(get_db())
    
    # Check if agents already exist
    if db.query(Agent).count() > 0:
        return
    
    demo_agents = [
        {
            "name": "forge-coder",
            "owner": "platform",
            "purpose": "Isolated code edits in sandboxed environments",
            "risk_tier": "high",
            "tools_allowed": ["files", "git", "shell"],
            "model_name": "gpt-4"
        },
        {
            "name": "doc-weaver",
            "owner": "platform",
            "purpose": "Documentation generation and maintenance",
            "risk_tier": "medium",
            "tools_allowed": ["files"],
            "model_name": "gpt-3.5-turbo"
        },
        {
            "name": "web-scout",
            "owner": "platform",
            "purpose": "Web research and data gathering",
            "risk_tier": "high",
            "tools_allowed": ["network", "browser"],
            "model_name": "gpt-4"
        }
    ]
    
    for agent_data in demo_agents:
        agent = Agent(
            name=agent_data["name"],
            owner=agent_data["owner"],
            purpose=agent_data["purpose"],
            risk_tier=agent_data["risk_tier"],
            tools_allowed=",".join(agent_data["tools_allowed"]),
            model_name=agent_data.get("model_name"),
            status=AgentStatus.ENABLED
        )
        db.add(agent)
        
        # Log registration
        audit = AuditLog(
            agent_id=None,
            agent_name=agent.name,
            event_type=AuditEventType.REGISTER,
            details=json.dumps(agent_data),
            triggered_by="seed"
        )
        db.add(audit)
    
    db.commit()
    db.close()


# Security: Simple token authentication
async def verify_token(request: Request):
    """Verify API token from header."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header"
        )
    
    token = auth_header.replace("Bearer ", "")
    if token != settings.gateway_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )


# Dashboard (no auth for demo simplicity)
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    """Main dashboard view."""
    agents = db.query(Agent).order_by(Agent.created_at.desc()).all()
    audit_logs = (
        db.query(AuditLog)
        .order_by(AuditLog.timestamp.desc())
        .limit(50)
        .all()
    )
    
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "agents": agents,
            "audit_logs": audit_logs,
            "RiskTier": {"low": "low", "medium": "medium", "high": "high"},
            "AgentStatus": {"enabled": "enabled", "killed": "killed"}
        }
    )


# Agent CRUD endpoints
def agent_to_response(agent: Agent) -> dict:
    """Convert Agent model to response dict with tools_allowed as list."""
    return {
        "id": agent.id,
        "name": agent.name,
        "owner": agent.owner,
        "purpose": agent.purpose,
        "risk_tier": agent.risk_tier,
        "tools_allowed": agent.get_tools_list(),
        "model_name": agent.model_name,
        "status": agent.status,
        "created_at": agent.created_at,
        "updated_at": agent.updated_at
    }


@app.get("/api/agents", response_model=list[AgentResponse])
async def list_agents(db: Session = Depends(get_db)):
    """List all agents."""
    agents = db.query(Agent).order_by(Agent.created_at.desc()).all()
    return [agent_to_response(agent) for agent in agents]


@app.get("/api/agents/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: int, db: Session = Depends(get_db)):
    """Get a specific agent."""
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent_to_response(agent)


@app.post("/api/agents", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    agent_data: AgentCreate,
    db: Session = Depends(get_db),
    _: None = Depends(verify_token)
):
    """Create a new agent."""
    # Check if name already exists
    existing = db.query(Agent).filter(Agent.name == agent_data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Agent name already exists")
    
    agent = Agent(
        name=agent_data.name,
        owner=agent_data.owner,
        purpose=agent_data.purpose,
        risk_tier=agent_data.risk_tier,
        tools_allowed=",".join(agent_data.tools_allowed),
        model_name=agent_data.model_name,
        status=AgentStatus.ENABLED
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    
    # Log registration
    audit = AuditLog(
        agent_id=agent.id,
        agent_name=agent.name,
        event_type=AuditEventType.REGISTER,
        details=json.dumps({
            "owner": agent.owner,
            "risk_tier": agent.risk_tier.value,
            "tools": agent_data.tools_allowed
        }),
        triggered_by="api"
    )
    db.add(audit)
    db.commit()
    
    return agent_to_response(agent)


@app.patch("/api/agents/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: int,
    agent_update: AgentUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(verify_token)
):
    """Update an agent."""
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    update_data = agent_update.model_dump(exclude_unset=True)
    
    if "tools_allowed" in update_data:
        update_data["tools_allowed"] = ",".join(update_data["tools_allowed"])
    
    for field, value in update_data.items():
        setattr(agent, field, value)
    
    db.commit()
    db.refresh(agent)
    
    return agent_to_response(agent)


@app.delete("/api/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(verify_token)
):
    """Delete an agent."""
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    db.delete(agent)
    db.commit()
    
    return None


# Agent control endpoints
@app.post("/api/agents/{agent_id}/kill")
async def kill_agent(
    agent_id: int,
    db: Session = Depends(get_db)
):
    """Kill an agent (fail-closed)."""
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    if agent.status == AgentStatus.KILLED:
        return {"message": "Agent already killed", "agent_id": agent_id}
    
    agent.status = AgentStatus.KILLED
    db.commit()
    
    # Log kill event
    audit = AuditLog(
        agent_id=agent.id,
        agent_name=agent.name,
        event_type=AuditEventType.KILL,
        details=json.dumps({"previous_status": "enabled"}),
        triggered_by="api"
    )
    db.add(audit)
    db.commit()
    
    return {"message": "Agent killed successfully", "agent_id": agent_id}


@app.post("/api/agents/{agent_id}/enable")
async def enable_agent(
    agent_id: int,
    db: Session = Depends(get_db)
):
    """Enable a killed agent."""
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    if agent.status == AgentStatus.ENABLED:
        return {"message": "Agent already enabled", "agent_id": agent_id}
    
    agent.status = AgentStatus.ENABLED
    db.commit()
    
    # Log enable event
    audit = AuditLog(
        agent_id=agent.id,
        agent_name=agent.name,
        event_type=AuditEventType.ENABLE,
        details=json.dumps({"previous_status": "killed"}),
        triggered_by="api"
    )
    db.add(audit)
    db.commit()
    
    return {"message": "Agent enabled successfully", "agent_id": agent_id}


# Agent runner endpoint
@app.post("/api/agents/{agent_id}/run", response_model=AgentRunResponse)
async def run_agent(
    agent_id: int,
    run_request: AgentRunRequest,
    db: Session = Depends(get_db)
):
    """Run an agent task (simulated)."""
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    runner = AgentRunner(db)
    result = runner.run_task(agent, run_request.task, triggered_by="api")
    
    return result


# Audit log endpoints
@app.get("/api/audit", response_model=list[AuditLogResponse])
async def list_audit_logs(
    limit: int = 100,
    agent_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """List audit logs."""
    query = db.query(AuditLog)
    
    if agent_id:
        query = query.filter(AuditLog.agent_id == agent_id)
    
    logs = query.order_by(AuditLog.timestamp.desc()).limit(limit).all()
    return logs


# OpenAI-compatible chat endpoint (optional, secondary)
@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(
    request: ChatCompletionRequest,
    db: Session = Depends(get_db),
    _: None = Depends(verify_token)
):
    """
    OpenAI-compatible chat completions endpoint.
    Checks agent status if agent_id provided.
    """
    # Check agent status if specified
    if request.agent_id:
        agent = db.query(Agent).filter(Agent.id == request.agent_id).first()
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        if agent.status == AgentStatus.KILLED:
            raise HTTPException(
                status_code=403,
                detail="Agent is killed and cannot make requests"
            )
        
        # Log chat event
        audit = AuditLog(
            agent_id=agent.id,
            agent_name=agent.name,
            event_type=AuditEventType.CHAT,
            details=json.dumps({
                "model": request.model,
                "message_count": len(request.messages)
            }),
            triggered_by="chat_api"
        )
        db.add(audit)
        db.commit()
    
    # Mock response (not calling real LLM)
    response_message = ChatMessage(
        role="assistant",
        content="This is a mock response. In production, this would call the specified model."
    )
    
    return ChatCompletionResponse(
        id=f"chatcmpl-{int(time.time())}",
        created=int(time.time()),
        model=request.model,
        choices=[
            ChatCompletionChoice(
                index=0,
                message=response_message,
                finish_reason="stop"
            )
        ]
    )


# Health check
@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "service": "agentgate"}

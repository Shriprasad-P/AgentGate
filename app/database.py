from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SQLEnum,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

Base = declarative_base()


class RiskTier(str, Enum):
    """Agent risk classification."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AgentStatus(str, Enum):
    """Agent operational status."""
    ENABLED = "enabled"
    KILLED = "killed"


class AuditEventType(str, Enum):
    """Types of auditable events."""
    REGISTER = "register"
    KILL = "kill"
    ENABLE = "enable"
    TOOL_CALL = "tool_call"
    TOOL_DENIED = "tool_denied"
    CHAT = "chat"


class Agent(Base):
    """Agent model representing a coding agent under management."""
    
    __tablename__ = "agents"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    owner = Column(String(100), nullable=False)
    purpose = Column(Text, nullable=False)
    risk_tier = Column(SQLEnum(RiskTier), nullable=False)
    status = Column(SQLEnum(AgentStatus), nullable=False, default=AgentStatus.ENABLED)
    
    # Tool allowlist stored as comma-separated string
    tools_allowed = Column(String(500), nullable=False)
    
    # Optional model name this agent may call
    model_name = Column(String(100), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    def get_tools_list(self) -> list[str]:
        """Parse tools_allowed string into a list."""
        if not self.tools_allowed:
            return []
        return [tool.strip() for tool in self.tools_allowed.split(",")]
    
    def set_tools_list(self, tools: list[str]) -> None:
        """Set tools_allowed from a list."""
        self.tools_allowed = ",".join(tools)
    
    def is_tool_allowed(self, tool: str) -> bool:
        """Check if a tool is in the allowlist."""
        return tool in self.get_tools_list()


class AuditLog(Base):
    """Append-only audit log for agent operations."""
    
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, nullable=True, index=True)
    agent_name = Column(String(100), nullable=True, index=True)
    event_type = Column(SQLEnum(AuditEventType), nullable=False, index=True)
    
    # Event details in JSON-compatible format
    details = Column(Text, nullable=True)
    
    # Who/what triggered this event
    triggered_by = Column(String(100), nullable=True)
    
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    def __repr__(self):
        return f"<AuditLog {self.event_type} agent={self.agent_name} at {self.timestamp}>"


# Database setup
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """Dependency to get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database tables."""
    Base.metadata.create_all(bind=engine)

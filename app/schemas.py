from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_serializer, model_serializer

from app.database import AgentStatus, AuditEventType, RiskTier


# Agent schemas
class AgentBase(BaseModel):
    """Base agent schema."""
    name: str = Field(..., min_length=1, max_length=100)
    owner: str = Field(..., min_length=1, max_length=100)
    purpose: str = Field(..., min_length=1)
    risk_tier: RiskTier
    tools_allowed: list[str] = Field(..., min_items=0)
    model_name: Optional[str] = Field(None, max_length=100)


class AgentCreate(AgentBase):
    """Schema for creating an agent."""
    pass


class AgentUpdate(BaseModel):
    """Schema for updating an agent."""
    owner: Optional[str] = None
    purpose: Optional[str] = None
    risk_tier: Optional[RiskTier] = None
    tools_allowed: Optional[list[str]] = None
    model_name: Optional[str] = None


class AgentResponse(BaseModel):
    """Schema for agent response."""
    id: int
    name: str
    owner: str
    purpose: str
    risk_tier: RiskTier
    tools_allowed: list[str]
    model_name: Optional[str]
    status: AgentStatus
    created_at: datetime
    updated_at: datetime


# Agent control schemas
class AgentStatusUpdate(BaseModel):
    """Schema for updating agent status."""
    status: AgentStatus


# Agent runner schemas
class AgentRunRequest(BaseModel):
    """Schema for running an agent task."""
    task: str = Field(..., min_length=1, max_length=5000)


class ToolCallResult(BaseModel):
    """Result of a single tool call."""
    tool: str
    allowed: bool
    executed: bool
    result: Optional[str] = None
    reason: Optional[str] = None


class AgentRunResponse(BaseModel):
    """Response from agent run."""
    agent_id: int
    agent_name: str
    task: str
    status: str
    plan: list[str]
    tool_calls: list[ToolCallResult]
    message: str


# Audit log schemas
class AuditLogResponse(BaseModel):
    """Schema for audit log response."""
    id: int
    agent_id: Optional[int]
    agent_name: Optional[str]
    event_type: AuditEventType
    details: Optional[str]
    triggered_by: Optional[str]
    timestamp: datetime
    
    class Config:
        from_attributes = True


# Chat completion schemas (OpenAI-compatible)
class ChatMessage(BaseModel):
    """Chat message."""
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    """OpenAI-compatible chat completion request."""
    model: str
    messages: list[ChatMessage]
    temperature: Optional[float] = 1.0
    max_tokens: Optional[int] = None
    agent_id: Optional[int] = None


class ChatCompletionChoice(BaseModel):
    """Chat completion choice."""
    index: int
    message: ChatMessage
    finish_reason: str


class ChatCompletionResponse(BaseModel):
    """OpenAI-compatible chat completion response."""
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[ChatCompletionChoice]
    usage: dict = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

"""Tests for chat completions endpoint."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import Agent, AgentStatus, AuditEventType, AuditLog, RiskTier


def test_chat_completion_with_enabled_agent(client: TestClient, auth_headers: dict, db: Session):
    """Test chat completion with an enabled agent."""
    agent = Agent(
        name="chat-agent",
        owner="owner",
        purpose="Test chat",
        risk_tier=RiskTier.LOW,
        tools_allowed="files",
        status=AgentStatus.ENABLED,
        model_name="gpt-4"
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    
    chat_data = {
        "model": "gpt-4",
        "messages": [
            {"role": "user", "content": "Hello, world!"}
        ],
        "agent_id": agent.id
    }
    
    response = client.post("/v1/chat/completions", json=chat_data, headers=auth_headers)
    assert response.status_code == 200
    
    data = response.json()
    assert data["object"] == "chat.completion"
    assert "choices" in data
    assert len(data["choices"]) > 0
    
    # Verify audit log
    audit = db.query(AuditLog).filter(
        AuditLog.agent_id == agent.id,
        AuditLog.event_type == AuditEventType.CHAT
    ).first()
    assert audit is not None


def test_chat_completion_with_killed_agent(client: TestClient, auth_headers: dict, db: Session):
    """Test that killed agent cannot make chat requests."""
    agent = Agent(
        name="killed-chat",
        owner="owner",
        purpose="Test killed chat",
        risk_tier=RiskTier.MEDIUM,
        tools_allowed="files",
        status=AgentStatus.KILLED
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    
    chat_data = {
        "model": "gpt-4",
        "messages": [
            {"role": "user", "content": "Hello"}
        ],
        "agent_id": agent.id
    }
    
    response = client.post("/v1/chat/completions", json=chat_data, headers=auth_headers)
    assert response.status_code == 403
    assert "killed" in response.json()["detail"].lower()


def test_chat_completion_without_agent_id(client: TestClient, auth_headers: dict):
    """Test chat completion without agent ID (should work but not check status)."""
    chat_data = {
        "model": "gpt-4",
        "messages": [
            {"role": "user", "content": "Hello"}
        ]
    }
    
    response = client.post("/v1/chat/completions", json=chat_data, headers=auth_headers)
    assert response.status_code == 200


def test_chat_completion_requires_auth(client: TestClient):
    """Test that chat completion requires authentication."""
    chat_data = {
        "model": "gpt-4",
        "messages": [
            {"role": "user", "content": "Hello"}
        ]
    }
    
    response = client.post("/v1/chat/completions", json=chat_data)
    assert response.status_code == 401

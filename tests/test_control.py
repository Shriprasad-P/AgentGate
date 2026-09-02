"""Tests for agent control operations (kill/enable)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import Agent, AgentStatus, AuditEventType, AuditLog, RiskTier


def test_kill_agent(client: TestClient, db: Session):
    """Test killing an agent."""
    agent = Agent(
        name="kill-test",
        owner="owner",
        purpose="Test kill",
        risk_tier=RiskTier.HIGH,
        tools_allowed="files,git,shell",
        status=AgentStatus.ENABLED
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    
    response = client.post(f"/api/agents/{agent.id}/kill")
    assert response.status_code == 200
    assert "killed successfully" in response.json()["message"]
    
    # Verify agent is killed
    db.refresh(agent)
    assert agent.status == AgentStatus.KILLED
    
    # Verify audit log
    audit = db.query(AuditLog).filter(
        AuditLog.agent_id == agent.id,
        AuditLog.event_type == AuditEventType.KILL
    ).first()
    assert audit is not None
    assert audit.agent_name == "kill-test"


def test_kill_already_killed_agent(client: TestClient, db: Session):
    """Test killing an already killed agent."""
    agent = Agent(
        name="already-killed",
        owner="owner",
        purpose="Test",
        risk_tier=RiskTier.MEDIUM,
        tools_allowed="files",
        status=AgentStatus.KILLED
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    
    response = client.post(f"/api/agents/{agent.id}/kill")
    assert response.status_code == 200
    assert "already killed" in response.json()["message"]


def test_enable_agent(client: TestClient, db: Session):
    """Test enabling a killed agent."""
    agent = Agent(
        name="enable-test",
        owner="owner",
        purpose="Test enable",
        risk_tier=RiskTier.LOW,
        tools_allowed="files",
        status=AgentStatus.KILLED
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    
    response = client.post(f"/api/agents/{agent.id}/enable")
    assert response.status_code == 200
    assert "enabled successfully" in response.json()["message"]
    
    # Verify agent is enabled
    db.refresh(agent)
    assert agent.status == AgentStatus.ENABLED
    
    # Verify audit log
    audit = db.query(AuditLog).filter(
        AuditLog.agent_id == agent.id,
        AuditLog.event_type == AuditEventType.ENABLE
    ).first()
    assert audit is not None


def test_enable_already_enabled_agent(client: TestClient, db: Session):
    """Test enabling an already enabled agent."""
    agent = Agent(
        name="already-enabled",
        owner="owner",
        purpose="Test",
        risk_tier=RiskTier.MEDIUM,
        tools_allowed="files",
        status=AgentStatus.ENABLED
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    
    response = client.post(f"/api/agents/{agent.id}/enable")
    assert response.status_code == 200
    assert "already enabled" in response.json()["message"]


def test_kill_and_enable_cycle(client: TestClient, db: Session):
    """Test killing and then enabling an agent."""
    agent = Agent(
        name="cycle-test",
        owner="owner",
        purpose="Test cycle",
        risk_tier=RiskTier.HIGH,
        tools_allowed="files,git",
        status=AgentStatus.ENABLED
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    
    # Kill
    kill_response = client.post(f"/api/agents/{agent.id}/kill")
    assert kill_response.status_code == 200
    db.refresh(agent)
    assert agent.status == AgentStatus.KILLED
    
    # Enable
    enable_response = client.post(f"/api/agents/{agent.id}/enable")
    assert enable_response.status_code == 200
    db.refresh(agent)
    assert agent.status == AgentStatus.ENABLED
    
    # Check audit trail
    audits = db.query(AuditLog).filter(
        AuditLog.agent_id == agent.id
    ).order_by(AuditLog.timestamp).all()
    
    assert len(audits) >= 2
    assert audits[-2].event_type == AuditEventType.KILL
    assert audits[-1].event_type == AuditEventType.ENABLE

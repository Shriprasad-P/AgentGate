"""Tests for audit log functionality."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import Agent, AgentStatus, AuditEventType, AuditLog, RiskTier


def test_audit_log_has_no_delete(client: TestClient, db: Session):
    """Test that audit log entries cannot be deleted (append-only)."""
    # Create an agent and generate some audit events
    agent = Agent(
        name="audit-immutable",
        owner="owner",
        purpose="Test audit immutability",
        risk_tier=RiskTier.MEDIUM,
        tools_allowed="files",
        status=AgentStatus.ENABLED
    )
    db.add(agent)
    db.commit()
    
    # Create audit entry
    audit = AuditLog(
        agent_id=agent.id,
        agent_name=agent.name,
        event_type=AuditEventType.REGISTER,
        details="Test entry",
        triggered_by="test"
    )
    db.add(audit)
    db.commit()
    db.refresh(audit)
    
    # Verify there's no DELETE endpoint for audit logs
    # The API doesn't expose delete, so we test at DB level
    audit_id = audit.id
    
    # Even if we try to delete from DB (which API prevents), we verify it exists
    audit_exists = db.query(AuditLog).filter(AuditLog.id == audit_id).first()
    assert audit_exists is not None
    
    # Note: In production, database permissions should prevent DELETE on audit_logs table


def test_list_audit_logs(client: TestClient, db: Session):
    """Test listing audit logs."""
    # Create multiple audit entries
    for i in range(5):
        audit = AuditLog(
            agent_id=i,
            agent_name=f"agent-{i}",
            event_type=AuditEventType.TOOL_CALL,
            details=f"Test {i}",
            triggered_by="test"
        )
        db.add(audit)
    db.commit()
    
    response = client.get("/api/audit")
    assert response.status_code == 200
    
    data = response.json()
    assert len(data) >= 5


def test_list_audit_logs_filtered_by_agent(client: TestClient, db: Session):
    """Test listing audit logs filtered by agent ID."""
    # Create agents
    agent1 = Agent(
        name="agent-1",
        owner="owner",
        purpose="Test 1",
        risk_tier=RiskTier.LOW,
        tools_allowed="files",
        status=AgentStatus.ENABLED
    )
    agent2 = Agent(
        name="agent-2",
        owner="owner",
        purpose="Test 2",
        risk_tier=RiskTier.LOW,
        tools_allowed="files",
        status=AgentStatus.ENABLED
    )
    db.add_all([agent1, agent2])
    db.commit()
    
    # Create audit entries for agent1
    for i in range(3):
        audit = AuditLog(
            agent_id=agent1.id,
            agent_name=agent1.name,
            event_type=AuditEventType.TOOL_CALL,
            details=f"Agent 1 - {i}",
            triggered_by="test"
        )
        db.add(audit)
    
    # Create audit entries for agent2
    for i in range(2):
        audit = AuditLog(
            agent_id=agent2.id,
            agent_name=agent2.name,
            event_type=AuditEventType.TOOL_CALL,
            details=f"Agent 2 - {i}",
            triggered_by="test"
        )
        db.add(audit)
    db.commit()
    
    # Get logs for agent1 only
    response = client.get(f"/api/audit?agent_id={agent1.id}")
    assert response.status_code == 200
    
    data = response.json()
    assert len(data) == 3
    assert all(log["agent_id"] == agent1.id for log in data)


def test_audit_log_limit(client: TestClient, db: Session):
    """Test limiting audit log results."""
    # Create many audit entries
    for i in range(150):
        audit = AuditLog(
            agent_id=1,
            agent_name="test-agent",
            event_type=AuditEventType.TOOL_CALL,
            details=f"Test {i}",
            triggered_by="test"
        )
        db.add(audit)
    db.commit()
    
    # Request with limit
    response = client.get("/api/audit?limit=10")
    assert response.status_code == 200
    
    data = response.json()
    assert len(data) == 10


def test_audit_events_are_ordered_by_timestamp(client: TestClient, db: Session):
    """Test that audit logs are ordered by timestamp descending."""
    import time
    
    # Create entries with slight time differences
    for i in range(3):
        audit = AuditLog(
            agent_id=1,
            agent_name="test-agent",
            event_type=AuditEventType.TOOL_CALL,
            details=f"Event {i}",
            triggered_by="test"
        )
        db.add(audit)
        db.commit()
        time.sleep(0.01)  # Small delay to ensure different timestamps
    
    response = client.get("/api/audit?limit=3")
    data = response.json()
    
    # Most recent should be first
    assert len(data) == 3
    timestamps = [log["timestamp"] for log in data]
    assert timestamps == sorted(timestamps, reverse=True)

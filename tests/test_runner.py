"""Tests for agent runner and tool execution."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import Agent, AgentStatus, AuditEventType, AuditLog, RiskTier


def test_run_agent_task(client: TestClient, db: Session):
    """Test running a task with an enabled agent."""
    agent = Agent(
        name="runner-test",
        owner="owner",
        purpose="Test runner",
        risk_tier=RiskTier.MEDIUM,
        tools_allowed="files,git",
        status=AgentStatus.ENABLED
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    
    task_data = {"task": "Read the config file and check git status"}
    
    response = client.post(f"/api/agents/{agent.id}/run", json=task_data)
    assert response.status_code == 200
    
    data = response.json()
    assert data["agent_id"] == agent.id
    assert data["agent_name"] == "runner-test"
    assert data["task"] == task_data["task"]
    assert data["status"] in ["completed", "stopped"]
    assert "tool_calls" in data
    assert len(data["tool_calls"]) > 0


def test_killed_agent_cannot_run_tools(client: TestClient, db: Session):
    """Test that a killed agent cannot execute tool calls."""
    agent = Agent(
        name="killed-runner",
        owner="owner",
        purpose="Test killed runner",
        risk_tier=RiskTier.HIGH,
        tools_allowed="files,git,shell",
        status=AgentStatus.KILLED
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    
    task_data = {"task": "Run shell commands and edit files"}
    
    response = client.post(f"/api/agents/{agent.id}/run", json=task_data)
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] == "stopped"
    
    # All tool calls should be denied
    for tool_call in data["tool_calls"]:
        assert tool_call["allowed"] is False
        assert tool_call["executed"] is False
        assert "killed" in tool_call["reason"].lower()
    
    # Verify audit logs for denials
    denials = db.query(AuditLog).filter(
        AuditLog.agent_id == agent.id,
        AuditLog.event_type == AuditEventType.TOOL_DENIED
    ).all()
    assert len(denials) > 0


def test_disallowed_tool_denied(client: TestClient, db: Session):
    """Test that tools not in allowlist are denied."""
    agent = Agent(
        name="restricted-agent",
        owner="owner",
        purpose="Only files allowed",
        risk_tier=RiskTier.LOW,
        tools_allowed="files",  # Only files, no shell
        status=AgentStatus.ENABLED
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    
    task_data = {"task": "Run shell commands to install packages"}
    
    response = client.post(f"/api/agents/{agent.id}/run", json=task_data)
    assert response.status_code == 200
    
    data = response.json()
    
    # Check if any shell tools were denied
    shell_calls = [tc for tc in data["tool_calls"] if "shell" in tc["tool"]]
    if shell_calls:
        for shell_call in shell_calls:
            assert shell_call["allowed"] is False
            assert "not in allowlist" in shell_call["reason"]
    
    # Verify tool_denied audit events
    denials = db.query(AuditLog).filter(
        AuditLog.agent_id == agent.id,
        AuditLog.event_type == AuditEventType.TOOL_DENIED
    ).all()
    
    if shell_calls:
        assert len(denials) > 0


def test_enable_restores_tool_execution(client: TestClient, db: Session):
    """Test that enabling a killed agent restores tool execution."""
    agent = Agent(
        name="restore-test",
        owner="owner",
        purpose="Test restore",
        risk_tier=RiskTier.MEDIUM,
        tools_allowed="files,git",
        status=AgentStatus.KILLED
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    
    task_data = {"task": "Read files and check git"}
    
    # First run while killed - should fail
    response1 = client.post(f"/api/agents/{agent.id}/run", json=task_data)
    data1 = response1.json()
    denied_count_1 = sum(1 for tc in data1["tool_calls"] if not tc["allowed"])
    assert denied_count_1 > 0
    
    # Enable agent
    client.post(f"/api/agents/{agent.id}/enable")
    db.refresh(agent)
    assert agent.status == AgentStatus.ENABLED
    
    # Second run while enabled - should succeed
    response2 = client.post(f"/api/agents/{agent.id}/run", json=task_data)
    data2 = response2.json()
    
    executed_count = sum(1 for tc in data2["tool_calls"] if tc["executed"])
    assert executed_count > 0


def test_demo_run_writes_tool_call_events(client: TestClient, db: Session):
    """Test that demo runs write tool_call events to audit log."""
    agent = Agent(
        name="audit-test",
        owner="owner",
        purpose="Test audit",
        risk_tier=RiskTier.LOW,
        tools_allowed="files,git",
        status=AgentStatus.ENABLED
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    
    # Run task
    task_data = {"task": "Read config and check git status"}
    response = client.post(f"/api/agents/{agent.id}/run", json=task_data)
    assert response.status_code == 200
    
    # Check audit log for tool_call events
    tool_calls = db.query(AuditLog).filter(
        AuditLog.agent_id == agent.id,
        AuditLog.event_type == AuditEventType.TOOL_CALL
    ).all()
    
    assert len(tool_calls) > 0
    
    # Each tool call should have details
    for log in tool_calls:
        assert log.details is not None
        assert "tool" in log.details


def test_run_nonexistent_agent(client: TestClient):
    """Test running a task with non-existent agent."""
    task_data = {"task": "Some task"}
    response = client.post("/api/agents/99999/run", json=task_data)
    assert response.status_code == 404

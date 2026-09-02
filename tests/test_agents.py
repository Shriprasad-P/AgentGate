"""Tests for agent CRUD operations."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import Agent, AgentStatus, RiskTier


def test_create_agent(client: TestClient, auth_headers: dict):
    """Test creating a new agent."""
    agent_data = {
        "name": "test-agent",
        "owner": "test-user",
        "purpose": "Testing purposes",
        "risk_tier": "medium",
        "tools_allowed": ["files", "git"],
        "model_name": "gpt-4"
    }
    
    response = client.post("/api/agents", json=agent_data, headers=auth_headers)
    assert response.status_code == 201
    
    data = response.json()
    assert data["name"] == "test-agent"
    assert data["owner"] == "test-user"
    assert data["status"] == "enabled"
    assert data["risk_tier"] == "medium"
    assert "id" in data


def test_create_agent_duplicate_name(client: TestClient, auth_headers: dict, db: Session):
    """Test creating an agent with duplicate name fails."""
    # Create first agent
    agent = Agent(
        name="duplicate",
        owner="user1",
        purpose="Test",
        risk_tier=RiskTier.LOW,
        tools_allowed="files",
        status=AgentStatus.ENABLED
    )
    db.add(agent)
    db.commit()
    
    # Try to create duplicate
    agent_data = {
        "name": "duplicate",
        "owner": "user2",
        "purpose": "Another test",
        "risk_tier": "low",
        "tools_allowed": ["files"]
    }
    
    response = client.post("/api/agents", json=agent_data, headers=auth_headers)
    assert response.status_code == 400
    assert "already exists" in response.json()["detail"]


def test_create_agent_without_auth(client: TestClient):
    """Test creating an agent without authentication fails."""
    agent_data = {
        "name": "test-agent",
        "owner": "test-user",
        "purpose": "Testing purposes",
        "risk_tier": "medium",
        "tools_allowed": ["files"]
    }
    
    response = client.post("/api/agents", json=agent_data)
    assert response.status_code == 401


def test_list_agents(client: TestClient, db: Session):
    """Test listing agents."""
    # Create test agents
    for i in range(3):
        agent = Agent(
            name=f"agent-{i}",
            owner=f"owner-{i}",
            purpose=f"Purpose {i}",
            risk_tier=RiskTier.MEDIUM,
            tools_allowed="files,git",
            status=AgentStatus.ENABLED
        )
        db.add(agent)
    db.commit()
    
    response = client.get("/api/agents")
    assert response.status_code == 200
    
    data = response.json()
    assert len(data) == 3
    assert all(agent["name"].startswith("agent-") for agent in data)


def test_get_agent(client: TestClient, db: Session):
    """Test getting a specific agent."""
    agent = Agent(
        name="specific-agent",
        owner="owner",
        purpose="Specific purpose",
        risk_tier=RiskTier.HIGH,
        tools_allowed="files,git,shell",
        status=AgentStatus.ENABLED
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    
    response = client.get(f"/api/agents/{agent.id}")
    assert response.status_code == 200
    
    data = response.json()
    assert data["name"] == "specific-agent"
    assert data["owner"] == "owner"
    assert data["risk_tier"] == "high"


def test_get_agent_not_found(client: TestClient):
    """Test getting a non-existent agent."""
    response = client.get("/api/agents/99999")
    assert response.status_code == 404


def test_update_agent(client: TestClient, auth_headers: dict, db: Session):
    """Test updating an agent."""
    agent = Agent(
        name="update-agent",
        owner="original-owner",
        purpose="Original purpose",
        risk_tier=RiskTier.LOW,
        tools_allowed="files",
        status=AgentStatus.ENABLED
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    
    update_data = {
        "owner": "new-owner",
        "tools_allowed": ["files", "git", "shell"]
    }
    
    response = client.patch(
        f"/api/agents/{agent.id}",
        json=update_data,
        headers=auth_headers
    )
    assert response.status_code == 200
    
    data = response.json()
    assert data["owner"] == "new-owner"
    assert "files" in data["tools_allowed"]
    assert "git" in data["tools_allowed"]


def test_delete_agent(client: TestClient, auth_headers: dict, db: Session):
    """Test deleting an agent."""
    agent = Agent(
        name="delete-agent",
        owner="owner",
        purpose="To be deleted",
        risk_tier=RiskTier.MEDIUM,
        tools_allowed="files",
        status=AgentStatus.ENABLED
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    
    response = client.delete(f"/api/agents/{agent.id}", headers=auth_headers)
    assert response.status_code == 204
    
    # Verify deletion
    get_response = client.get(f"/api/agents/{agent.id}")
    assert get_response.status_code == 404

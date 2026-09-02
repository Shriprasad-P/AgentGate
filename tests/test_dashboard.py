"""Tests for dashboard and other endpoints."""

import pytest
from fastapi.testclient import TestClient


def test_dashboard_loads(client: TestClient):
    """Test that dashboard loads successfully."""
    response = client.get("/")
    assert response.status_code == 200
    assert "AgentGate" in response.text
    assert "Shriprasad Patil" in response.text


def test_health_check(client: TestClient):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "agentgate"

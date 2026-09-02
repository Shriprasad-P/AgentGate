"""
Agent runner: simulates a coding agent executing tool calls.
This is a mock implementation for demonstration purposes.
"""

import json
from typing import Optional

from sqlalchemy.orm import Session

from app.database import Agent, AgentStatus, AuditEventType, AuditLog
from app.schemas import AgentRunResponse, ToolCallResult


class AgentRunner:
    """Simulates a coding agent executing tasks with tool calls."""
    
    # Available tools that agents might request
    AVAILABLE_TOOLS = ["shell", "git", "files", "network", "browser"]
    
    def __init__(self, db: Session):
        self.db = db
    
    def generate_plan(self, task: str, agent: Agent) -> list[str]:
        """
        Generate a simple plan of tool calls based on the task.
        This is a mock - in production this would use an LLM.
        """
        plan = []
        task_lower = task.lower()
        
        # Simple keyword-based planning
        if "read" in task_lower or "check" in task_lower or "list" in task_lower:
            plan.append("files.read")
        
        if "write" in task_lower or "create" in task_lower or "edit" in task_lower:
            plan.append("files.write")
        
        if "git" in task_lower or "commit" in task_lower or "status" in task_lower:
            plan.append("git.status")
        
        if "run" in task_lower or "execute" in task_lower or "command" in task_lower:
            plan.append("shell.exec")
        
        if "search" in task_lower or "fetch" in task_lower or "download" in task_lower:
            plan.append("network.request")
        
        if "browse" in task_lower or "scrape" in task_lower:
            plan.append("browser.navigate")
        
        # Default plan if nothing matched
        if not plan:
            plan = ["files.read", "git.status"]
        
        return plan
    
    def execute_tool_call(
        self,
        agent: Agent,
        tool_name: str,
        triggered_by: str = "runner"
    ) -> ToolCallResult:
        """
        Execute a single tool call with permission checks.
        Records audit events for each call.
        """
        # Extract base tool name (e.g., "files" from "files.read")
        base_tool = tool_name.split(".")[0]
        
        # Check if agent is killed
        if agent.status == AgentStatus.KILLED:
            self._log_audit(
                agent=agent,
                event_type=AuditEventType.TOOL_DENIED,
                details=json.dumps({
                    "tool": tool_name,
                    "reason": "agent_killed"
                }),
                triggered_by=triggered_by
            )
            return ToolCallResult(
                tool=tool_name,
                allowed=False,
                executed=False,
                reason="Agent is killed"
            )
        
        # Check if tool is in allowlist
        if not agent.is_tool_allowed(base_tool):
            self._log_audit(
                agent=agent,
                event_type=AuditEventType.TOOL_DENIED,
                details=json.dumps({
                    "tool": tool_name,
                    "reason": "not_in_allowlist"
                }),
                triggered_by=triggered_by
            )
            return ToolCallResult(
                tool=tool_name,
                allowed=False,
                executed=False,
                reason=f"Tool '{base_tool}' not in allowlist"
            )
        
        # Tool is allowed - simulate execution
        mock_result = self._simulate_tool_execution(tool_name)
        
        self._log_audit(
            agent=agent,
            event_type=AuditEventType.TOOL_CALL,
            details=json.dumps({
                "tool": tool_name,
                "result": mock_result
            }),
            triggered_by=triggered_by
        )
        
        return ToolCallResult(
            tool=tool_name,
            allowed=True,
            executed=True,
            result=mock_result
        )
    
    def _simulate_tool_execution(self, tool_name: str) -> str:
        """Simulate tool execution with mock results."""
        simulations = {
            "files.read": "Read 3 files successfully",
            "files.write": "Wrote changes to app.py",
            "git.status": "On branch main. Working tree clean.",
            "git.commit": "Committed changes with message",
            "shell.exec": "Command executed: exit code 0",
            "network.request": "HTTP 200: fetched data",
            "browser.navigate": "Navigated to page successfully"
        }
        return simulations.get(tool_name, f"Executed {tool_name}")
    
    def _log_audit(
        self,
        agent: Agent,
        event_type: AuditEventType,
        details: Optional[str] = None,
        triggered_by: str = "system"
    ):
        """Log an audit event."""
        log_entry = AuditLog(
            agent_id=agent.id,
            agent_name=agent.name,
            event_type=event_type,
            details=details,
            triggered_by=triggered_by
        )
        self.db.add(log_entry)
        self.db.commit()
    
    def run_task(
        self,
        agent: Agent,
        task: str,
        triggered_by: str = "api"
    ) -> AgentRunResponse:
        """
        Run a complete agent task with planning and tool execution.
        """
        # Generate plan
        plan = self.generate_plan(task, agent)
        
        # Execute each tool call in the plan
        tool_results = []
        execution_status = "completed"
        
        for tool_call in plan:
            result = self.execute_tool_call(agent, tool_call, triggered_by)
            tool_results.append(result)
            
            # If agent was killed or tool denied, may stop early
            if not result.executed:
                execution_status = "stopped"
                # Continue to show what would have been attempted
        
        # Determine final message
        denied_count = sum(1 for r in tool_results if not r.allowed)
        executed_count = sum(1 for r in tool_results if r.executed)
        
        if agent.status == AgentStatus.KILLED:
            message = f"Agent killed. {denied_count}/{len(tool_results)} tool calls denied."
        elif denied_count > 0:
            message = f"Completed with {denied_count} denied tool calls. {executed_count} executed successfully."
        else:
            message = f"All {executed_count} tool calls executed successfully."
        
        return AgentRunResponse(
            agent_id=agent.id,
            agent_name=agent.name,
            task=task,
            status=execution_status,
            plan=plan,
            tool_calls=tool_results,
            message=message
        )

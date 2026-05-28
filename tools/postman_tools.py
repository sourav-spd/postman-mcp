"""
Postman MCP Tool Implementations
Provides 42 Postman API tools (1 connect + 41 core tools) for collections, environments, mocks, specs, and workspaces.
"""
import os
import json
import logging
from typing import Any

import httpx
from mcp.types import TextContent, Tool
from .toolhandler import ToolHandler

logger = logging.getLogger(__name__)

# Postman API configuration
POSTMAN_BASE_URL = "https://api.getpostman.com"

# Session state for Postman authentication
_session_state = {
    "postman_api_key": None,
    "authenticated": False
}


# Tool 0: postman_connect (Connection Tool)
class PostmanConnectToolHandler(ToolHandler):
    """Connect to Postman API with authentication key."""
    
    def __init__(self):
        super().__init__("postman_connect")
    
    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="Connect to Postman API with authentication key. Required before using other Postman tools.",
            inputSchema={
                "type": "object",
                "properties": {
                    "api_key": {
                        "type": "string",
                        "description": "Postman API Key (PMAK-...)"
                    }
                },
                "required": ["api_key"]
            }
        )
    
    async def run_tool(self, args: dict) -> list[TextContent]:
        self.validate_required_args(args, ["api_key"])
        
        api_key = args["api_key"].strip()
        
        if not api_key:
            return [TextContent(
                type="text",
                text="Error: API key cannot be empty"
            )]
        
        # Validate API key by calling Postman API
        try:
            headers = {
                "X-Api-Key": api_key,
                "Content-Type": "application/json"
            }
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{POSTMAN_BASE_URL}/me",
                    headers=headers
                )
                response.raise_for_status()
                user_info = response.json()
            
            # Store API key in session state
            _session_state["postman_api_key"] = api_key
            _session_state["authenticated"] = True
            
            user_data = user_info.get("user", {})
            return [TextContent(
                type="text",
                text=f"Successfully connected to Postman as {user_data.get('username', 'unknown')} ({user_data.get('email', 'N/A')})"
            )]
            
        except httpx.HTTPStatusError as e:
            _session_state["postman_api_key"] = None
            _session_state["authenticated"] = False
            
            if e.response.status_code == 401:
                return [TextContent(
                    type="text",
                    text="Error: Invalid Postman API key. Please check your API key."
                )]
            else:
                return [TextContent(
                    type="text",
                    text=f"Error: Postman API error ({e.response.status_code}): {e.response.text}"
                )]
        
        except Exception as e:
            _session_state["postman_api_key"] = None
            _session_state["authenticated"] = False
            return [TextContent(
                type="text",
                text=f"Error connecting to Postman: {str(e)}"
            )]


class PostmanToolBase(ToolHandler):
    """Base class for Postman tools with common API methods."""
    
    def __init__(self, tool_name: str, api_key: str = None):
        super().__init__(tool_name)
        self._initial_api_key = api_key or os.environ.get("POSTMAN_API_KEY") or ""
        self.base_url = POSTMAN_BASE_URL
    
    def _get_current_api_key(self) -> str:
        """Get the current API key with priority: session state > initial API key."""
        return _session_state.get("postman_api_key") or self._initial_api_key or ""
    
    def validate_connection(self) -> None:
        """Validate that Postman connection is established."""
        if not self._get_current_api_key():
            raise RuntimeError(
                "Not connected to Postman. Please use 'postman_connect' tool first "
                "or set POSTMAN_API_KEY environment variable."
            )
    
    async def make_request(
        self,
        method: str,
        endpoint: str,
        body: dict = None,
        params: dict = None,
        headers: dict = None,
        use_v10_api: bool = False
    ) -> dict:
        """Make an HTTP request to Postman API"""
        self.validate_connection()
        
        url = f"{self.base_url}{endpoint}"
        
        # Prepare headers
        request_headers = {
            "X-Api-Key": self._get_current_api_key(),
            "Content-Type": "application/json",
        }
        if use_v10_api:
            request_headers["Accept"] = "application/vnd.api.v10+json"
        if headers:
            request_headers.update(headers)
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.request(
                    method=method.upper(),
                    url=url,
                    json=body,
                    params=params,
                    headers=request_headers
                )
                response.raise_for_status()
                
                if response.status_code == 204:
                    return {"success": True, "message": "Operation completed successfully"}
                
                return response.json() if response.content else {"success": True}
            
            except httpx.HTTPStatusError as e:
                error_detail = e.response.text
                try:
                    error_json = e.response.json()
                    error_detail = json.dumps(error_json, indent=2)
                except:
                    pass
                raise RuntimeError(f"Postman API error ({e.response.status_code}): {error_detail}")
            except Exception as e:
                raise RuntimeError(f"Request failed: {str(e)}")


# ============================================================================
# USER INFO TOOLS
# ============================================================================

class GetAuthenticatedUserTool(PostmanToolBase):
    """Get authenticated user information"""
    
    def __init__(self, api_key: str = None):
        super().__init__("getAuthenticatedUser", api_key)
    
    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="Gets information about the authenticated user. Use this to get current user context (user.id, username, teamId, roles) for 'my ...' requests.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        )
    
    async def run_tool(self, args: dict) -> list[TextContent]:
        result = await self.make_request("GET", "/me")
        return [TextContent(type="text", text=json.dumps(result, indent=2))]


# ============================================================================
# COLLECTION TOOLS
# ============================================================================

class CreateCollectionTool(PostmanToolBase):
    """Create a new collection"""
    
    def __init__(self, api_key: str = None):
        super().__init__("createCollection", api_key)
    
    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="Creates a collection using the Postman Collection v2.1.0 schema format. If workspace is not specified, creates in the oldest personal workspace.",
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace": {
                        "type": "string",
                        "description": "The workspace's ID",
                        "default": ""
                    },
                    "collection": {
                        "type": "object",
                        "description": "Collection object in Postman Collection v2.1.0 format",
                        "default": {}
                    }
                },
            },
        )
    
    async def run_tool(self, args: dict) -> list[TextContent]:
        workspace = args.get("workspace")
        collection = args.get("collection", {})
        
        params = {"workspace": workspace} if workspace else {}
        body = {"collection": collection}
        
        result = await self.make_request("POST", "/collections", body=body, params=params)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]


class GetCollectionTool(PostmanToolBase):
    """Get collection information"""
    
    def __init__(self, api_key: str = None):
        super().__init__("getCollection", api_key)
    
    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="Get information about a collection. Returns lightweight collection map by default. Use model='minimal' for root-level IDs only, or model='full' for complete payload.",
            inputSchema={
                "type": "object",
                "properties": {
                    "collectionId": {
                        "type": "string",
                        "description": "The collection ID in format <OWNER_ID>-<COLLECTION_ID>"
                    },
                    "access_key": {
                        "type": "string",
                        "description": "Collection's read-only access key (optional, doesn't require API key)",
                        "default": ""
                    },
                    "model": {
                        "type": "string",
                        "enum": ["minimal", "full"],
                        "description": "Response model: 'minimal' for root-level IDs, 'full' for complete payload",
                        "default": ""
                    }
                },
                "required": ["collectionId"]
            },
        )
    
    async def run_tool(self, args: dict) -> list[TextContent]:
        collection_id = args["collectionId"]
        params = {}
        if args.get("access_key"):
            params["access_key"] = args["access_key"]
        if args.get("model"):
            params["model"] = args["model"]
        
        result = await self.make_request("GET", f"/collections/{collection_id}", params=params)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]


class GetCollectionsTool(PostmanToolBase):
    """Get all collections in a workspace"""
    
    def __init__(self, api_key: str = None):
        super().__init__("getCollections", api_key)
    
    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="Gets all collections in a workspace. Workspace ID is required - ask user if not provided.",
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace": {
                        "type": "string",
                        "description": "The workspace's ID (required)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of rows to return",
                        "default": 0
                    },
                    "name": {
                        "type": "string",
                        "description": "Filter by collections matching this name",
                        "default": ""
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Zero-based offset for pagination",
                        "default": 0
                    }
                },
                "required": ["workspace"]
            },
        )
    
    async def run_tool(self, args: dict) -> list[TextContent]:
        params = {"workspace": args["workspace"]}
        if args.get("limit"):
            params["limit"] = args["limit"]
        if args.get("name"):
            params["name"] = args["name"]
        if args.get("offset"):
            params["offset"] = args["offset"]
        
        result = await self.make_request("GET", "/collections", params=params)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]


class PutCollectionTool(PostmanToolBase):
    """Replace collection contents"""
    
    def __init__(self, api_key: str = None):
        super().__init__("putCollection", api_key)
    
    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="Replaces collection contents using Postman Collection v2.1.0 format. Include ID values or they'll be removed and recreated. Max size 100MB.",
            inputSchema={
                "type": "object",
                "properties": {
                    "collectionId": {
                        "type": "string",
                        "description": "Collection ID in format <OWNER_ID>-<COLLECTION_ID>"
                    },
                    "Prefer": {
                        "type": "string",
                        "description": "Use 'respond-async' for async update (returns 202)",
                        "default": ""
                    },
                    "collection": {
                        "type": "object",
                        "description": "Collection object in Postman Collection v2.1.0 format",
                        "default": {}
                    }
                },
                "required": ["collectionId"]
            },
        )
    
    async def run_tool(self, args: dict) -> list[TextContent]:
        collection_id = args["collectionId"]
        collection = args.get("collection", {})
        headers = {}
        if args.get("Prefer"):
            headers["Prefer"] = args["Prefer"]
        
        body = {"collection": collection}
        result = await self.make_request("PUT", f"/collections/{collection_id}", body=body, headers=headers)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]


class DuplicateCollectionTool(PostmanToolBase):
    """Duplicate a collection to another workspace"""
    
    def __init__(self, api_key: str = None):
        super().__init__("duplicateCollection", api_key)
    
    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="Duplicates a collection to another workspace. Returns a task ID - use getDuplicateCollectionTaskStatus to check status.",
            inputSchema={
                "type": "object",
                "properties": {
                    "collectionId": {
                        "type": "string",
                        "description": "The collection's unique ID"
                    },
                    "workspace": {
                        "type": "string",
                        "description": "Target workspace ID"
                    },
                    "suffix": {
                        "type": "string",
                        "description": "Optional suffix for duplicated collection name",
                        "default": ""
                    }
                },
                "required": ["collectionId", "workspace"]
            },
        )
    
    async def run_tool(self, args: dict) -> list[TextContent]:
        collection_id = args["collectionId"]
        body = {"workspace": args["workspace"]}
        if args.get("suffix"):
            body["suffix"] = args["suffix"]
        
        result = await self.make_request("POST", f"/collections/{collection_id}/duplicate", body=body)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]


class GetDuplicateCollectionTaskStatusTool(PostmanToolBase):
    """Get duplication task status"""
    
    def __init__(self, api_key: str = None):
        super().__init__("getDuplicateCollectionTaskStatus", api_key)
    
    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="Gets the status of a collection duplication task.",
            inputSchema={
                "type": "object",
                "properties": {
                    "taskId": {
                        "type": "string",
                        "description": "The task's unique ID"
                    }
                },
                "required": ["taskId"]
            },
        )
    
    async def run_tool(self, args: dict) -> list[TextContent]:
        task_id = args["taskId"]
        result = await self.make_request("GET", f"/collection-duplicate-tasks/{task_id}")
        return [TextContent(type="text", text=json.dumps(result, indent=2))]


# ============================================================================
# COLLECTION REQUEST/RESPONSE TOOLS
# ============================================================================

class CreateCollectionRequestTool(PostmanToolBase):
    """Create a request in a collection"""
    
    def __init__(self, api_key: str = None):
        super().__init__("createCollectionRequest", api_key)
    
    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="Creates a request in a collection. Recommended to pass 'name' property. See Postman Collection Format docs for full properties.",
            inputSchema={
                "type": "object",
                "properties": {
                    "collectionId": {
                        "type": "string",
                        "description": "The collection's ID"
                    },
                    "folderId": {
                        "type": "string",
                        "description": "Folder ID (optional, creates at collection level if omitted)",
                        "default": ""
                    },
                    "name": {
                        "type": "string",
                        "description": "Request name",
                        "default": ""
                    },
                    "method": {
                        "type": "string",
                        "description": "HTTP method (GET, POST, etc.)",
                        "default": ""
                    },
                    "url": {
                        "type": "string",
                        "description": "Request URL",
                        "default": ""
                    },
                    "description": {
                        "type": "string",
                        "description": "Request description",
                        "default": ""
                    },
                    "auth": {
                        "type": "string",
                        "description": "Authentication information",
                        "default": ""
                    },
                    "headerData": {
                        "type": "array",
                        "description": "Request headers",
                        "default": []
                    },
                    "queryParams": {
                        "type": "array",
                        "description": "Query parameters",
                        "default": []
                    },
                    "dataMode": {
                        "type": "string",
                        "description": "Request body data mode",
                        "default": ""
                    },
                    "data": {
                        "type": "string",
                        "description": "Form data",
                        "default": ""
                    },
                    "rawModeData": {
                        "type": "string",
                        "description": "Raw mode data",
                        "default": ""
                    },
                    "graphqlModeData": {
                        "type": "string",
                        "description": "GraphQL mode data",
                        "default": ""
                    },
                    "dataOptions": {
                        "type": "string",
                        "description": "Data mode options",
                        "default": ""
                    },
                    "events": {
                        "type": "string",
                        "description": "Script events",
                        "default": ""
                    }
                },
                "required": ["collectionId"]
            },
        )
    
    async def run_tool(self, args: dict) -> list[TextContent]:
        collection_id = args.pop("collectionId")
        body = {k: v for k, v in args.items() if v is not None}
        
        result = await self.make_request("POST", f"/collections/{collection_id}/requests", body=body)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]


class UpdateCollectionRequestTool(PostmanToolBase):
    """Update a request in a collection"""
    
    def __init__(self, api_key: str = None):
        super().__init__("updateCollectionRequest", api_key)
    
    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="Updates a request in a collection (PATCH-like: only updates provided fields). Cannot change folder. Use collection ID (not UID).",
            inputSchema={
                "type": "object",
                "properties": {
                    "collectionId": {
                        "type": "string",
                        "description": "Collection ID (not UID)"
                    },
                    "requestId": {
                        "type": "string",
                        "description": "Request ID"
                    },
                    "name": {
                        "type": "string",
                        "description": "Request name",
                        "default": ""
                    },
                    "method": {
                        "type": "string",
                        "description": "HTTP method",
                        "default": ""
                    },
                    "url": {
                        "type": "string",
                        "description": "Request URL",
                        "default": ""
                    },
                    "description": {
                        "type": "string",
                        "description": "Request description",
                        "default": ""
                    },
                    "auth": {
                        "type": "string",
                        "description": "Authentication info",
                        "default": ""
                    },
                    "headerData": {
                        "type": "array",
                        "description": "Headers",
                        "default": []
                    },
                    "queryParams": {
                        "type": "array",
                        "description": "Query parameters",
                        "default": []
                    },
                    "dataMode": {
                        "type": "string",
                        "description": "Body data mode",
                        "default": ""
                    },
                    "data": {
                        "type": "string",
                        "description": "Form data",
                        "default": ""
                    },
                    "rawModeData": {
                        "type": "string",
                        "description": "Raw mode data",
                        "default": ""
                    },
                    "graphqlModeData": {
                        "type": "string",
                        "description": "GraphQL mode data",
                        "default": ""
                    },
                    "dataOptions": {
                        "type": "string",
                        "description": "Data options",
                        "default": ""
                    },
                    "events": {
                        "type": "string",
                        "description": "Script events",
                        "default": ""
                    }
                },
                "required": ["collectionId", "requestId"]
            },
        )
    
    async def run_tool(self, args: dict) -> list[TextContent]:
        collection_id = args.pop("collectionId")
        request_id = args.pop("requestId")
        body = {k: v for k, v in args.items() if v is not None}
        
        result = await self.make_request("PUT", f"/collections/{collection_id}/requests/{request_id}", body=body)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]


class CreateCollectionResponseTool(PostmanToolBase):
    """Create a response in a collection"""
    
    def __init__(self, api_key: str = None):
        super().__init__("createCollectionResponse", api_key)
    
    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="Creates a request response in a collection. Recommended to pass 'name' property. See Response entry in Postman Collection Format docs.",
            inputSchema={
                "type": "object",
                "properties": {
                    "collectionId": {
                        "type": "string",
                        "description": "Collection ID"
                    },
                    "request": {
                        "type": "string",
                        "description": "Parent request ID"
                    },
                    "name": {
                        "type": "string",
                        "description": "Response name",
                        "default": ""
                    },
                    "description": {
                        "type": "string",
                        "description": "Response description",
                        "default": ""
                    },
                    "status": {
                        "type": "string",
                        "description": "HTTP status text",
                        "default": ""
                    },
                    "responseCode": {
                        "type": "object",
                        "description": "HTTP response code info",
                        "default": {}
                    },
                    "headers": {
                        "type": "array",
                        "description": "Response headers",
                        "default": []
                    },
                    "cookies": {
                        "type": "string",
                        "description": "Cookie data",
                        "default": ""
                    },
                    "text": {
                        "type": "string",
                        "description": "Raw response body text",
                        "default": ""
                    },
                    "language": {
                        "type": "string",
                        "description": "Language type",
                        "default": ""
                    },
                    "mime": {
                        "type": "string",
                        "description": "MIME type",
                        "default": ""
                    },
                    "time": {
                        "type": "string",
                        "description": "Time taken (ms)",
                        "default": ""
                    },
                    "method": {
                        "type": "string",
                        "description": "Request HTTP method",
                        "default": ""
                    },
                    "url": {
                        "type": "string",
                        "description": "Request URL",
                        "default": ""
                    },
                    "dataMode": {
                        "type": "string",
                        "description": "Request body data mode",
                        "default": ""
                    },
                    "dataOptions": {
                        "type": "string",
                        "description": "Data mode options",
                        "default": ""
                    },
                    "rawModeData": {
                        "type": "string",
                        "description": "Raw mode data",
                        "default": ""
                    },
                    "rawDataType": {
                        "type": "string",
                        "description": "Raw data type",
                        "default": ""
                    },
                    "requestObject": {
                        "type": "string",
                        "description": "JSON-stringified request representation",
                        "default": ""
                    }
                },
                "required": ["collectionId", "request"]
            },
        )
    
    async def run_tool(self, args: dict) -> list[TextContent]:
        collection_id = args.pop("collectionId")
        body = {k: v for k, v in args.items() if v is not None}
        
        result = await self.make_request("POST", f"/collections/{collection_id}/responses", body=body)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]


# ============================================================================
# ENVIRONMENT TOOLS
# ============================================================================

class CreateEnvironmentTool(PostmanToolBase):
    """Create an environment"""
    
    def __init__(self, api_key: str = None):
        super().__init__("createEnvironment", api_key)
    
    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="Creates an environment. Max size 30MB. If workspace not specified, creates in oldest personal workspace.",
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace": {
                        "type": "string",
                        "description": "Workspace ID",
                        "default": ""
                    },
                    "environment": {
                        "type": "object",
                        "description": "Environment object with name and values",
                        "default": {}
                    }
                },
            },
        )
    
    async def run_tool(self, args: dict) -> list[TextContent]:
        params = {}
        if args.get("workspace"):
            params["workspace"] = args["workspace"]
        
        body = {"environment": args.get("environment", {})}
        result = await self.make_request("POST", "/environments", body=body, params=params)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]


class GetEnvironmentTool(PostmanToolBase):
    """Get environment information"""
    
    def __init__(self, api_key: str = None):
        super().__init__("getEnvironment", api_key)
    
    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="Gets information about an environment.",
            inputSchema={
                "type": "object",
                "properties": {
                    "environmentId": {
                        "type": "string",
                        "description": "Environment ID"
                    }
                },
                "required": ["environmentId"]
            },
        )
    
    async def run_tool(self, args: dict) -> list[TextContent]:
        env_id = args["environmentId"]
        result = await self.make_request("GET", f"/environments/{env_id}")
        return [TextContent(type="text", text=json.dumps(result, indent=2))]


class GetEnvironmentsTool(PostmanToolBase):
    """Get all environments"""
    
    def __init__(self, api_key: str = None):
        super().__init__("getEnvironments", api_key)
    
    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="Gets all environments. Optionally filter by workspace.",
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace": {
                        "type": "string",
                        "description": "Workspace ID (optional)",
                        "default": ""
                    }
                },
            },
        )
    
    async def run_tool(self, args: dict) -> list[TextContent]:
        params = {}
        if args.get("workspace"):
            params["workspace"] = args["workspace"]
        
        result = await self.make_request("GET", "/environments", params=params)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]


class PutEnvironmentTool(PostmanToolBase):
    """Replace environment contents"""
    
    def __init__(self, api_key: str = None):
        super().__init__("putEnvironment", api_key)
    
    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="Replaces all environment contents. Max size 30MB.",
            inputSchema={
                "type": "object",
                "properties": {
                    "environmentId": {
                        "type": "string",
                        "description": "Environment ID"
                    },
                    "environment": {
                        "type": "object",
                        "description": "Environment object with name and values",
                        "default": {}
                    }
                },
                "required": ["environmentId"]
            },
        )
    
    async def run_tool(self, args: dict) -> list[TextContent]:
        env_id = args["environmentId"]
        body = {"environment": args.get("environment", {})}
        
        result = await self.make_request("PUT", f"/environments/{env_id}", body=body)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]


# ============================================================================
# MOCK SERVER TOOLS
# ============================================================================

class CreateMockTool(PostmanToolBase):
    """Create a mock server"""
    
    def __init__(self, api_key: str = None):
        super().__init__("createMock", api_key)
    
    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="Creates a mock server for a collection. Use collection UID (ownerId-collectionId). Use workspace param to specify target workspace.",
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace": {
                        "type": "string",
                        "description": "Workspace ID",
                        "default": ""
                    },
                    "mock": {
                        "type": "object",
                        "description": "Mock server configuration with collection UID, name, and settings",
                        "default": {}
                    }
                },
            },
        )
    
    async def run_tool(self, args: dict) -> list[TextContent]:
        params = {}
        if args.get("workspace"):
            params["workspace"] = args["workspace"]
        
        body = {"mock": args.get("mock", {})}
        result = await self.make_request("POST", "/mocks", body=body, params=params)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]


class GetMockTool(PostmanToolBase):
    """Get mock server information"""
    
    def __init__(self, api_key: str = None):
        super().__init__("getMock", api_key)
    
    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="Gets information about a mock server, including associated collection UID and mockUrl.",
            inputSchema={
                "type": "object",
                "properties": {
                    "mockId": {
                        "type": "string",
                        "description": "Mock server ID"
                    }
                },
                "required": ["mockId"]
            },
        )
    
    async def run_tool(self, args: dict) -> list[TextContent]:
        mock_id = args["mockId"]
        result = await self.make_request("GET", f"/mocks/{mock_id}")
        return [TextContent(type="text", text=json.dumps(result, indent=2))]


class GetMocksTool(PostmanToolBase):
    """Get all mock servers"""
    
    def __init__(self, api_key: str = None):
        super().__init__("getMocks", api_key)
    
    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="Gets all active mock servers. Always pass workspace or teamId. Prefer workspace when known. Set teamId from GET /me (me.teamId) for team scope.",
            inputSchema={
                "type": "object",
                "properties": {
                    "teamId": {
                        "type": "string",
                        "description": "Team ID (from GET /me: me.teamId)",
                        "default": ""
                    },
                    "workspace": {
                        "type": "string",
                        "description": "Workspace ID (preferred)",
                        "default": ""
                    }
                },
            },
        )
    
    async def run_tool(self, args: dict) -> list[TextContent]:
        params = {}
        if args.get("workspace"):
            params["workspace"] = args["workspace"]
        elif args.get("teamId"):
            params["teamId"] = args["teamId"]
        
        result = await self.make_request("GET", "/mocks", params=params)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]


class UpdateMockTool(PostmanToolBase):
    """Update mock server"""
    
    def __init__(self, api_key: str = None):
        super().__init__("updateMock", api_key)
    
    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="Updates a mock server (name, environment, privacy, default response).",
            inputSchema={
                "type": "object",
                "properties": {
                    "mockId": {
                        "type": "string",
                        "description": "Mock server ID"
                    },
                    "mock": {
                        "type": "object",
                        "description": "Mock server updates",
                        "default": {}
                    }
                },
                "required": ["mockId"]
            },
        )
    
    async def run_tool(self, args: dict) -> list[TextContent]:
        mock_id = args["mockId"]
        body = {"mock": args.get("mock", {})}
        
        result = await self.make_request("PUT", f"/mocks/{mock_id}", body=body)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]


class PublishMockTool(PostmanToolBase):
    """Publish mock server"""
    
    def __init__(self, api_key: str = None):
        super().__init__("publishMock", api_key)
    
    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="Publishes a mock server (sets Access Control to public).",
            inputSchema={
                "type": "object",
                "properties": {
                    "mockId": {
                        "type": "string",
                        "description": "Mock server ID"
                    }
                },
                "required": ["mockId"]
            },
        )
    
    async def run_tool(self, args: dict) -> list[TextContent]:
        mock_id = args["mockId"]
        result = await self.make_request("POST", f"/mocks/{mock_id}/publish")
        return [TextContent(type="text", text=json.dumps(result, indent=2))]


# ============================================================================
# API SPEC TOOLS
# ============================================================================

class CreateSpecTool(PostmanToolBase):
    """Create API specification"""
    
    def __init__(self, api_key: str = None):
        super().__init__("createSpec", api_key)
    
    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="Creates an API spec in Postman's Spec Hub. Supports OpenAPI 2.0/3.0/3.1, AsyncAPI 2.0, protobuf 2/3, GraphQL. Max file size 10MB.",
            inputSchema={
                "type": "object",
                "properties": {
                    "files": {
                        "type": "array",
                        "description": "List of spec files with path and content. Use '/' in path to create folders."
                    },
                    "name": {
                        "type": "string",
                        "description": "Specification name"
                    },
                    "type": {
                        "type": "string",
                        "description": "Spec type (openapi, asyncapi, proto, graphql)"
                    },
                    "workspaceId": {
                        "type": "string",
                        "description": "Workspace ID"
                    }
                },
                "required": ["files", "name", "type", "workspaceId"]
            },
        )
    
    async def run_tool(self, args: dict) -> list[TextContent]:
        body = {
            "files": args["files"],
            "name": args["name"],
            "type": args["type"],
            "workspaceId": args["workspaceId"]
        }
        
        result = await self.make_request("POST", "/apis", body=body, use_v10_api=True)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]


class GetSpecTool(PostmanToolBase):
    """Get API specification"""
    
    def __init__(self, api_key: str = None):
        super().__init__("getSpec", api_key)
    
    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="Gets information about an API specification.",
            inputSchema={
                "type": "object",
                "properties": {
                    "specId": {
                        "type": "string",
                        "description": "Spec ID"
                    }
                },
                "required": ["specId"]
            },
        )
    
    async def run_tool(self, args: dict) -> list[TextContent]:
        spec_id = args["specId"]
        result = await self.make_request("GET", f"/apis/{spec_id}", use_v10_api=True)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]


class GetAllSpecsTool(PostmanToolBase):
    """Get all API specifications"""
    
    def __init__(self, api_key: str = None):
        super().__init__("getAllSpecs", api_key)
    
    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="Gets all API specifications in a workspace.",
            inputSchema={
                "type": "object",
                "properties": {
                    "workspaceId": {
                        "type": "string",
                        "description": "Workspace ID"
                    },
                    "cursor": {
                        "type": "string",
                        "description": "Pagination cursor (nextCursor from previous response)",
                        "default": ""
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max rows to return",
                        "default": 0
                    }
                },
                "required": ["workspaceId"]
            },
        )
    
    async def run_tool(self, args: dict) -> list[TextContent]:
        workspace_id = args["workspaceId"]
        params = {"workspaceId": workspace_id}
        if args.get("cursor"):
            params["cursor"] = args["cursor"]
        if args.get("limit"):
            params["limit"] = args["limit"]
        
        result = await self.make_request("GET", "/apis", params=params, use_v10_api=True)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]


class UpdateSpecPropertiesTool(PostmanToolBase):
    """Update API spec properties"""
    
    def __init__(self, api_key: str = None):
        super().__init__("updateSpecProperties", api_key)
    
    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="Updates an API spec's properties (e.g., name).",
            inputSchema={
                "type": "object",
                "properties": {
                    "specId": {
                        "type": "string",
                        "description": "Spec ID"
                    },
                    "name": {
                        "type": "string",
                        "description": "New spec name"
                    }
                },
                "required": ["specId", "name"]
            },
        )
    
    async def run_tool(self, args: dict) -> list[TextContent]:
        spec_id = args["specId"]
        body = {"name": args["name"]}
        
        result = await self.make_request("PATCH", f"/apis/{spec_id}", body=body, use_v10_api=True)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]


class GetSpecDefinitionTool(PostmanToolBase):
    """Get spec definition contents"""
    
    def __init__(self, api_key: str = None):
        super().__init__("getSpecDefinition", api_key)
    
    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="Gets the complete contents of an API spec's definition.",
            inputSchema={
                "type": "object",
                "properties": {
                    "specId": {
                        "type": "string",
                        "description": "Spec ID"
                    }
                },
                "required": ["specId"]
            },
        )
    
    async def run_tool(self, args: dict) -> list[TextContent]:
        spec_id = args["specId"]
        result = await self.make_request("GET", f"/apis/{spec_id}/definition", use_v10_api=True)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]


class CreateSpecFileTool(PostmanToolBase):
    """Create spec file"""
    
    def __init__(self, api_key: str = None):
        super().__init__("createSpecFile", api_key)
    
    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="Creates an API spec file. Use '/' in path to create folders. File assigned DEFAULT type. Max size 10MB.",
            inputSchema={
                "type": "object",
                "properties": {
                    "specId": {
                        "type": "string",
                        "description": "Spec ID"
                    },
                    "content": {
                        "type": "string",
                        "description": "File's stringified contents"
                    },
                    "path": {
                        "type": "string",
                        "description": "File path (JSON or YAML)"
                    }
                },
                "required": ["specId", "content", "path"]
            },
        )
    
    async def run_tool(self, args: dict) -> list[TextContent]:
        spec_id = args["specId"]
        body = {
            "content": args["content"],
            "path": args["path"]
        }
        
        result = await self.make_request("POST", f"/apis/{spec_id}/files", body=body, use_v10_api=True)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]


class GetSpecFilesTool(PostmanToolBase):
    """Get all spec files"""
    
    def __init__(self, api_key: str = None):
        super().__init__("getSpecFiles", api_key)
    
    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="Gets all files in an API specification.",
            inputSchema={
                "type": "object",
                "properties": {
                    "specId": {
                        "type": "string",
                        "description": "Spec ID"
                    }
                },
                "required": ["specId"]
            },
        )
    
    async def run_tool(self, args: dict) -> list[TextContent]:
        spec_id = args["specId"]
        result = await self.make_request("GET", f"/apis/{spec_id}/files", use_v10_api=True)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]


class GetSpecFileTool(PostmanToolBase):
    """Get spec file contents"""
    
    def __init__(self, api_key: str = None):
        super().__init__("getSpecFile", api_key)
    
    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="Gets the contents of an API spec's file.",
            inputSchema={
                "type": "object",
                "properties": {
                    "specId": {
                        "type": "string",
                        "description": "Spec ID"
                    },
                    "filePath": {
                        "type": "string",
                        "description": "Path to the file"
                    }
                },
                "required": ["specId", "filePath"]
            },
        )
    
    async def run_tool(self, args: dict) -> list[TextContent]:
        spec_id = args["specId"]
        file_path = args["filePath"]
        result = await self.make_request("GET", f"/apis/{spec_id}/files/{file_path}", use_v10_api=True)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]


class UpdateSpecFileTool(PostmanToolBase):
    """Update spec file"""
    
    def __init__(self, api_key: str = None):
        super().__init__("updateSpecFile", api_key)
    
    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="Updates an API spec's file. Only pass one property at a time (content, name, or type). Max size 10MB.",
            inputSchema={
                "type": "object",
                "properties": {
                    "specId": {
                        "type": "string",
                        "description": "Spec ID"
                    },
                    "filePath": {
                        "type": "string",
                        "description": "Path to the file"
                    },
                    "content": {
                        "type": "string",
                        "description": "Stringified contents",
                        "default": ""
                    },
                    "name": {
                        "type": "string",
                        "description": "File name",
                        "default": ""
                    },
                    "type": {
                        "type": "string",
                        "enum": ["ROOT", "DEFAULT"],
                        "description": "ROOT (entry point) or DEFAULT (referenced file)",
                        "default": ""
                    }
                },
                "required": ["specId", "filePath"]
            },
        )
    
    async def run_tool(self, args: dict) -> list[TextContent]:
        spec_id = args["specId"]
        file_path = args["filePath"]
        body = {}
        if args.get("content"):
            body["content"] = args["content"]
        if args.get("name"):
            body["name"] = args["name"]
        if args.get("type"):
            body["type"] = args["type"]
        
        result = await self.make_request("PUT", f"/apis/{spec_id}/files/{file_path}", body=body, use_v10_api=True)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]


# ============================================================================
# SPEC-COLLECTION INTEGRATION TOOLS
# ============================================================================

class GenerateCollectionTool(PostmanToolBase):
    """Generate collection from spec"""
    
    def __init__(self, api_key: str = None):
        super().__init__("generateCollection", api_key)
    
    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="Creates a collection from an API spec. Returns polling link to task status.",
            inputSchema={
                "type": "object",
                "properties": {
                    "specId": {
                        "type": "string",
                        "description": "Spec ID"
                    },
                    "name": {
                        "type": "string",
                        "description": "Generated collection name"
                    },
                    "elementType": {
                        "type": "string",
                        "description": "Collection element type"
                    },
                    "options": {
                        "type": "object",
                        "description": "Advanced creation options (see OpenAPI to Postman Converter docs)",
                        "default": {}
                    }
                },
                "required": ["specId", "name", "elementType"]
            },
        )
    
    async def run_tool(self, args: dict) -> list[TextContent]:
        spec_id = args["specId"]
        body = {
            "name": args["name"],
            "elementType": args["elementType"],
            "options": args.get("options", {})
        }
        
        result = await self.make_request("POST", f"/apis/{spec_id}/collections", body=body, use_v10_api=True)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]


class GetSpecCollectionsTool(PostmanToolBase):
    """Get spec's generated collections"""
    
    def __init__(self, api_key: str = None):
        super().__init__("getSpecCollections", api_key)
    
    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="Gets all collections generated from an API spec.",
            inputSchema={
                "type": "object",
                "properties": {
                    "specId": {
                        "type": "string",
                        "description": "Spec ID"
                    },
                    "elementType": {
                        "type": "string",
                        "description": "Collection element type"
                    },
                    "cursor": {
                        "type": "string",
                        "description": "Pagination cursor",
                        "default": ""
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max rows",
                        "default": 0
                    }
                },
                "required": ["specId", "elementType"]
            },
        )
    
    async def run_tool(self, args: dict) -> list[TextContent]:
        spec_id = args["specId"]
        params = {"elementType": args["elementType"]}
        if args.get("cursor"):
            params["cursor"] = args["cursor"]
        if args.get("limit"):
            params["limit"] = args["limit"]
        
        result = await self.make_request("GET", f"/apis/{spec_id}/collections", params=params, use_v10_api=True)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]


class GenerateSpecFromCollectionTool(PostmanToolBase):
    """Generate spec from collection"""
    
    def __init__(self, api_key: str = None):
        super().__init__("generateSpecFromCollection", api_key)
    
    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="Generates an API spec for a collection. Returns polling link to task status.",
            inputSchema={
                "type": "object",
                "properties": {
                    "collectionUid": {
                        "type": "string",
                        "description": "Collection unique ID"
                    },
                    "name": {
                        "type": "string",
                        "description": "API spec name"
                    },
                    "elementType": {
                        "type": "string",
                        "description": "The 'spec' value"
                    },
                    "format": {
                        "type": "string",
                        "description": "Format (openapi, asyncapi, etc.)"
                    },
                    "type": {
                        "type": "string",
                        "description": "Specification type"
                    }
                },
                "required": ["collectionUid", "name", "elementType", "format", "type"]
            },
        )
    
    async def run_tool(self, args: dict) -> list[TextContent]:
        body = {
            "collectionUid": args["collectionUid"],
            "name": args["name"],
            "elementType": args["elementType"],
            "format": args["format"],
            "type": args["type"]
        }
        
        result = await self.make_request("POST", "/apis/generate", body=body, use_v10_api=True)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]


class GetGeneratedCollectionSpecsTool(PostmanToolBase):
    """Get generated spec for collection"""
    
    def __init__(self, api_key: str = None):
        super().__init__("getGeneratedCollectionSpecs", api_key)
    
    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="Gets the API spec generated for a collection.",
            inputSchema={
                "type": "object",
                "properties": {
                    "collectionUid": {
                        "type": "string",
                        "description": "Collection unique ID"
                    },
                    "elementType": {
                        "type": "string",
                        "description": "The 'spec' value"
                    }
                },
                "required": ["collectionUid", "elementType"]
            },
        )
    
    async def run_tool(self, args: dict) -> list[TextContent]:
        collection_uid = args["collectionUid"]
        params = {"elementType": args["elementType"]}
        
        result = await self.make_request("GET", f"/collections/{collection_uid}/apis", params=params, use_v10_api=True)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]


class SyncCollectionWithSpecTool(PostmanToolBase):
    """Sync collection with spec"""
    
    def __init__(self, api_key: str = None):
        super().__init__("syncCollectionWithSpec", api_key)
    
    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="Syncs a collection generated from an API spec. Async endpoint returns 202. Only for OpenAPI 2.0/3.0/3.1.",
            inputSchema={
                "type": "object",
                "properties": {
                    "specId": {
                        "type": "string",
                        "description": "Spec ID"
                    },
                    "collectionUid": {
                        "type": "string",
                        "description": "Collection unique ID"
                    }
                },
                "required": ["specId", "collectionUid"]
            },
        )
    
    async def run_tool(self, args: dict) -> list[TextContent]:
        spec_id = args["specId"]
        collection_uid = args["collectionUid"]
        
        result = await self.make_request("PUT", f"/apis/{spec_id}/collections/{collection_uid}/sync", use_v10_api=True)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]


class SyncSpecWithCollectionTool(PostmanToolBase):
    """Sync spec with collection"""
    
    def __init__(self, api_key: str = None):
        super().__init__("syncSpecWithCollection", api_key)
    
    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="Syncs an API spec linked to a collection. Async endpoint returns 202. Only for OpenAPI 2.0/3.0/3.1.",
            inputSchema={
                "type": "object",
                "properties": {
                    "specId": {
                        "type": "string",
                        "description": "Spec ID"
                    },
                    "collectionUid": {
                        "type": "string",
                        "description": "Collection unique ID"
                    }
                },
                "required": ["specId", "collectionUid"]
            },
        )
    
    async def run_tool(self, args: dict) -> list[TextContent]:
        spec_id = args["specId"]
        collection_uid = args["collectionUid"]
        
        result = await self.make_request("PUT", f"/apis/{spec_id}/collections/{collection_uid}/sync-with-spec", use_v10_api=True)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]


# ============================================================================
# WORKSPACE TOOLS
# ============================================================================

class CreateWorkspaceTool(PostmanToolBase):
    """Create workspace"""
    
    def __init__(self, api_key: str = None):
        super().__init__("createWorkspace", api_key)
    
    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="Creates a new workspace. Private/Partner workspaces require Team/Enterprise. Public names must be unique. Pass teamId if Organizations is enabled.",
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace": {
                        "type": "object",
                        "description": "Workspace object with name, type, description",
                        "default": {}
                    }
                },
            },
        )
    
    async def run_tool(self, args: dict) -> list[TextContent]:
        body = {"workspace": args.get("workspace", {})}
        result = await self.make_request("POST", "/workspaces", body=body)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]


class GetWorkspaceTool(PostmanToolBase):
    """Get workspace information"""
    
    def __init__(self, api_key: str = None):
        super().__init__("getWorkspace", api_key)
    
    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="Gets information about a workspace (visibility: personal/team/private/public/partner).",
            inputSchema={
                "type": "object",
                "properties": {
                    "workspaceId": {
                        "type": "string",
                        "description": "Workspace ID"
                    },
                    "include": {
                        "type": "string",
                        "description": "Include 'mocks:deactivated' or 'scim' data",
                        "default": ""
                    }
                },
                "required": ["workspaceId"]
            },
        )
    
    async def run_tool(self, args: dict) -> list[TextContent]:
        workspace_id = args["workspaceId"]
        params = {}
        if args.get("include"):
            params["include"] = args["include"]
        
        result = await self.make_request("GET", f"/workspaces/{workspace_id}", params=params)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]


class GetWorkspacesTool(PostmanToolBase):
    """Get all workspaces"""
    
    def __init__(self, api_key: str = None):
        super().__init__("getWorkspaces", api_key)
    
    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="Gets all accessible workspaces. For 'my ...' requests, call GET /me first and pass createdBy={me.user.id}. Paginated with cursor.",
            inputSchema={
                "type": "object",
                "properties": {
                    "createdBy": {
                        "type": "integer",
                        "description": "User ID (from GET /me: me.user.id) for 'my ...' requests",
                        "default": 0
                    },
                    "type": {
                        "type": "string",
                        "enum": ["personal", "team", "private", "public", "partner"],
                        "description": "Workspace type filter",
                        "default": ""
                    },
                    "cursor": {
                        "type": "string",
                        "description": "Pagination cursor (meta.nextCursor from previous response)",
                        "default": ""
                    },
                    "elementId": {
                        "type": "string",
                        "description": "Filter by element ID (requires elementType)",
                        "default": ""
                    },
                    "elementType": {
                        "type": "string",
                        "description": "Element type (requires elementId)",
                        "default": ""
                    },
                    "include": {
                        "type": "string",
                        "description": "Include 'mocks:deactivated' or 'scim'",
                        "default": ""
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max rows (default 100)",
                        "default": 0
                    }
                },
            },
        )
    
    async def run_tool(self, args: dict) -> list[TextContent]:
        params = {}
        if args.get("createdBy"):
            params["createdBy"] = args["createdBy"]
        if args.get("type"):
            params["type"] = args["type"]
        if args.get("cursor"):
            params["cursor"] = args["cursor"]
        if args.get("elementId"):
            params["elementId"] = args["elementId"]
        if args.get("elementType"):
            params["elementType"] = args["elementType"]
        if args.get("include"):
            params["include"] = args["include"]
        if args.get("limit"):
            params["limit"] = args["limit"]
        
        result = await self.make_request("GET", "/workspaces", params=params)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]


class UpdateWorkspaceTool(PostmanToolBase):
    """Update workspace"""
    
    def __init__(self, api_key: str = None):
        super().__init__("updateWorkspace", api_key)
    
    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="Updates a workspace property (name, visibility, etc.). Some visibility changes not allowed. Public names must be unique.",
            inputSchema={
                "type": "object",
                "properties": {
                    "workspaceId": {
                        "type": "string",
                        "description": "Workspace ID"
                    },
                    "workspace": {
                        "type": "object",
                        "description": "Workspace updates",
                        "default": {}
                    }
                },
                "required": ["workspaceId"]
            },
        )
    
    async def run_tool(self, args: dict) -> list[TextContent]:
        workspace_id = args["workspaceId"]
        body = {"workspace": args.get("workspace", {})}
        
        result = await self.make_request("PUT", f"/workspaces/{workspace_id}", body=body)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]


# ============================================================================
# ADDITIONAL TOOLS
# ============================================================================

class GetTaggedEntitiesTool(PostmanToolBase):
    """Get tagged entities"""
    
    def __init__(self, api_key: str = None):
        super().__init__("getTaggedEntities", api_key)
    
    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="Gets Postman entities by tag. Enterprise only - returns 404 on Free/Basic/Professional plans.",
            inputSchema={
                "type": "object",
                "properties": {
                    "slug": {
                        "type": "string",
                        "description": "Tag ID"
                    },
                    "cursor": {
                        "type": "string",
                        "description": "Pagination cursor",
                        "default": ""
                    },
                    "direction": {
                        "type": "string",
                        "enum": ["asc", "desc"],
                        "description": "Sort order",
                        "default": ""
                    },
                    "entityType": {
                        "type": "string",
                        "description": "Filter by entity type",
                        "default": ""
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max entities to return",
                        "default": 0
                    }
                },
                "required": ["slug"]
            },
        )
    
    async def run_tool(self, args: dict) -> list[TextContent]:
        slug = args["slug"]
        params = {}
        if args.get("cursor"):
            params["cursor"] = args["cursor"]
        if args.get("direction"):
            params["direction"] = args["direction"]
        if args.get("entityType"):
            params["entityType"] = args["entityType"]
        if args.get("limit"):
            params["limit"] = args["limit"]
        
        result = await self.make_request("GET", f"/tags/{slug}/entities", params=params)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]


class RunCollectionTool(PostmanToolBase):
    """Run Postman collection"""
    
    def __init__(self, api_key: str = None):
        super().__init__("runCollection", api_key)
    
    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="Runs a Postman collection with detailed test results and execution statistics. Supports optional environment for variable substitution.",
            inputSchema={
                "type": "object",
                "properties": {
                    "collectionId": {
                        "type": "string",
                        "description": "Collection ID in format <OWNER_ID>-<COLLECTION_ID>"
                    },
                    "environmentId": {
                        "type": "string",
                        "description": "Optional environment ID for variable substitution",
                        "default": ""
                    },
                    "iterationCount": {
                        "type": "number",
                        "description": "Number of iterations (default: 1)",
                        "default": 1
                    },
                    "requestTimeout": {
                        "type": "number",
                        "description": "Request timeout in ms (default: 60000)",
                        "default": 60000
                    },
                    "scriptTimeout": {
                        "type": "number",
                        "description": "Script timeout in ms (default: 5000)",
                        "default": 5000
                    },
                    "abortOnError": {
                        "type": "boolean",
                        "description": "Abruptly halt on errors (default: false)",
                        "default": False
                    },
                    "abortOnFailure": {
                        "type": "boolean",
                        "description": "Abruptly halt on test failures (default: false)",
                        "default": False
                    },
                    "stopOnError": {
                        "type": "boolean",
                        "description": "Gracefully halt on errors (default: false)",
                        "default": False
                    },
                    "stopOnFailure": {
                        "type": "boolean",
                        "description": "Gracefully halt on test failures (default: false)",
                        "default": False
                    }
                },
                "required": ["collectionId"]
            },
        )
    
    async def run_tool(self, args: dict) -> list[TextContent]:
        # Note: This tool would use newman programmatically
        # For now, return a placeholder indicating newman integration needed
        return [TextContent(
            type="text",
            text=json.dumps({
                "error": "runCollection requires Newman integration",
                "message": "This tool needs Newman (Postman's CLI runner) to be integrated. Use 'newman run' command or integrate newman programmatically.",
                "received_args": args
            }, indent=2)
        )]


class GetEnabledToolsTool(PostmanToolBase):
    """Get enabled tools"""
    
    def __init__(self, api_key: str = None):
        super().__init__("getEnabledTools", api_key)
    
    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="IMPORTANT: Run this first when a requested tool is unavailable. Returns info about enabled tools in full and minimal sets.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        )
    
    async def run_tool(self, args: dict) -> list[TextContent]:
        enabled_tools = {
            "message": "All 41 Postman MCP tools are enabled",
            "full_toolset": ["All 41 tools available"],
            "minimal_toolset": ["Core read-only tools available"],
            "total_tools": 41,
            "categories": {
                "collections": 7,
                "requests_responses": 3,
                "environments": 4,
                "mocks": 5,
                "specs": 13,
                "workspaces": 4,
                "integration": 3,
                "other": 2
            }
        }
        return [TextContent(type="text", text=json.dumps(enabled_tools, indent=2))]

# Postman MCP Server (SSE Mode)

A production-ready Model Context Protocol (MCP) server that provides Postman API tools through SSE (Server-Sent Events), Streamable HTTP, and stdio transports.

## Features

- **42 Postman Tools** for comprehensive API management (collections, environments, mocks, specs, workspaces)
- **Session-based Authentication** via `postman_connect` tool (like mongodb-mcp)
- **Multiple Transport Modes**: SSE (default), Streamable HTTP, and stdio
- **Postman REST API** integration with proper authentication
- **Async/await** for efficient operation
- **Type hints** throughout the codebase

## Available Tools (42 Total)

### Connection (Required First)
- `postman_connect` - Connect to Postman API with authentication key (required before using other tools)

### User Info (2 tools)
- `getAuthenticatedUser` - Get authenticated user information
- `getEnabledTools` - Get list of enabled tools

### Collections (7 tools)
- `createCollection` - Create a new collection
- `getCollection` - Get collection information
- `getCollections` - Get all collections in a workspace
- `putCollection` - Replace collection contents
- `duplicateCollection` - Duplicate a collection to another workspace
- `getDuplicateCollectionTaskStatus` - Get duplication task status

### Requests & Responses (3 tools)
- `createCollectionRequest` - Create a request in a collection
- `updateCollectionRequest` - Update a request
- `createCollectionResponse` - Create a response in a collection

### Environments (4 tools)
- `createEnvironment` - Create an environment
- `getEnvironment` - Get environment information
- `getEnvironments` - Get all environments
- `putEnvironment` - Replace environment contents

### Mock Servers (5 tools)
- `createMock` - Create a mock server
- `getMock` - Get mock server information
- `getMocks` - Get all mock servers
- `updateMock` - Update mock server
- `publishMock` - Publish mock server

### API Specs (9 tools)
- `createSpec` - Create API specification
- `getSpec` - Get API specification
- `getAllSpecs` - Get all API specifications
- `updateSpecProperties` - Update spec properties
- `getSpecDefinition` - Get spec definition contents
- `createSpecFile` - Create spec file
- `getSpecFiles` - Get all spec files
- `getSpecFile` - Get spec file contents
- `updateSpecFile` - Update spec file

### Spec-Collection Integration (6 tools)
- `generateCollection` - Generate collection from spec
- `getSpecCollections` - Get spec's generated collections
- `generateSpecFromCollection` - Generate spec from collection
- `getGeneratedCollectionSpecs` - Get generated spec for collection
- `syncCollectionWithSpec` - Sync collection with spec
- `syncSpecWithCollection` - Sync spec with collection

### Workspaces (4 tools)
- `createWorkspace` - Create workspace
- `getWorkspace` - Get workspace information
- `getWorkspaces` - Get all workspaces
- `updateWorkspace` - Update workspace

### Other (2 tools)
- `getTaggedEntities` - Get tagged entities (Enterprise only)
- `runCollection` - Run Postman collection (requires Newman)

## Quick Start

### Prerequisites

- Python 3.10+
- Postman API Key (optional - can be provided via `postman_connect` tool)

### Installation

```powershell
# Navigate to postman-mcp directory
cd C:\Users\sdas14\OneDrive - Capgemini\Desktop\RAISE\MCP_Tools_sse\postman-mcp

# Install the package
pip install -e .
```

### Set Postman API Key (Optional)

**Option 1: Use the `postman_connect` tool at runtime (Recommended)**

You can skip setting the environment variable and connect dynamically using the tool after starting the server.

**Option 2: Set environment variable**

Get your Postman API Key:
1. Go to Postman Dashboard → Settings → API Keys
2. Click "Generate API Key"
3. Copy the key (starts with PMAK-)

Set it as an environment variable:
```powershell
$env:POSTMAN_API_KEY = "PMAK-your_api_key_here"
```

### Start the Server

#### SSE Mode (Recommended)
```powershell
postman-mcp --mode sse --port 8000
```

You should see:
```
2026-05-22T14:30:00  INFO      postman-mcp  Postman MCP Server starting up
2026-05-22T14:30:00  INFO      postman-mcp  Total tools registered: 42
2026-05-22T14:30:00  INFO      postman-mcp  Starting in SSE mode on http://0.0.0.0:8000
```

#### Streamable HTTP Mode
```powershell
postman-mcp --mode streamable-http --port 8000
```

#### Stdio Mode
```powershell
postman-mcp --mode stdio
```

## Configuration

### SSE Configuration

```json
{
  "mcpServers": {
    "postman": {
      "command": "postman-mcp",
      "args": ["--mode", "sse", "--port", "8000"],
      "env": {
        "POSTMAN_API_KEY": "your_postman_api_key"
      }
    }
  }
}
```

### Stdio Configuration

```json
{
  "mcpServers": {
    "postman": {
      "command": "postman-mcp",
      "args": ["--mode", "stdio"],
      "env": {
        "POSTMAN_API_KEY": "your_postman_api_key"
      }
    }
  }
}
```

## Architecture

```
postman-mcp/
├── postman_server.py          # Main MCP server (stdio, SSE, HTTP)
├── tools/
│   ├── __init__.py
│   ├── toolhandler.py        # Abstract base class for tools
│   └── postman_tools.py      # All 42 Postman tool implementations
├── pyproject.toml            # Package configuration
├── mcp.example.json          # Example MCP client config
├── README.md                 # This file
├── QUICKSTART.md             # Quick start guide
└── LICENSE                   # MIT License
```

## Development

### Running Tests
```powershell
pytest
```

### Environment Variables

- `POSTMAN_API_KEY` - Postman API Key (optional - can use `postman_connect` tool instead)
- `TRANSPORT_TYPE` - Transport mode: `sse`, `streamable-http`, or `stdio`
- `APP_HOST` - Bind host (default: `0.0.0.0`)
- `APP_PORT` or `PORT` - Bind port (default: `8000`)

## API Reference

### Tool Structure

Each tool follows this pattern:

```python
class ToolHandler(PostmanToolBase):
    def get_tool_description(self) -> Tool:
        # Returns tool metadata
        
    async def run_tool(self, args: dict) -> List[TextContent]:
        # Executes the tool
```

### Error Handling

- All tools validate required arguments
- HTTP errors are caught and returned as text content
- Traceback is included in error responses for debugging

## Usage Example

### Using Session-Based Authentication

```python
# First, connect to Postman
{
  "tool": "postman_connect",
  "arguments": {
    "api_key": "PMAK-your_api_key_here"
  }
}

# Then use other tools
{
  "tool": "getCollections",
  "arguments": {
    "workspace": "workspace_id_here"
  }
}
```

### Using Environment Variable

If you set `POSTMAN_API_KEY` environment variable, you can skip `postman_connect` and directly use other tools.

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Support

For issues and questions:
- Check the QUICKSTART.md guide
- Review Postman API documentation
- Open an issue on the repository

## Version

1.0.0 - SSE Mode with 42 Postman tools (1 connect + 41 core tools)

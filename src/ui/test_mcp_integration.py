#!/usr/bin/env python3
"""Test MCP Integration for UI using FastMCP (like examples)

This script tests the MCP client helper to ensure it can connect to the
MCP server and retrieve namespaces before using it in the Streamlit UI.
"""

import os
import sys
import logging

# Add the parent directories to the path to import from core and ui modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.dirname(__file__))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



def test_mcp_server_health():
    """Test if MCP server is healthy"""
    print("=" * 60)
    print("🔍 Testing MCP Server Health")
    print("=" * 60)
    
    try:
        from mcp_client_helper import mcp_client
        
        health = mcp_client.check_server_health()
        if health:
            print("✅ MCP Server is healthy and reachable")
            return True
        else:
            print("❌ MCP Server health check failed")
            return False
    except Exception as e:
        print(f"❌ Error testing health: {e}")
        return False

def test_mcp_sync_tool():
    """Test HTTP-based MCP tool call"""
    print("\n" + "=" * 60)
    print("🔧 Testing HTTP MCP Tool Call")
    print("=" * 60)
    
    try:
        from mcp_client_helper import mcp_client
        
        print("Calling list_namespaces tool (HTTP)...")
        result = mcp_client.call_tool_sync("list_namespaces")
        
        if result:
            print("✅ HTTP tool call successful")
            print("Raw MCP response:")
            print(f"   Type: {type(result)}")
            if isinstance(result, list) and len(result) > 0:
                text_content = result[0].get("text", "")
                print(f"   Text preview: {text_content[:200]}...")
            return True
        else:
            print("❌ HTTP tool call returned no result")
            return False
            
    except Exception as e:
        print(f"❌ Error in HTTP tool call: {e}")
        return False

def test_mcp_namespaces():
    """Test MCP namespace retrieval through helper function"""
    print("\n" + "=" * 60)
    print("📋 Testing MCP Namespace Retrieval")
    print("=" * 60)
    
    try:
        from mcp_client_helper import get_namespaces_mcp
        
        print("Calling get_namespaces_mcp()...")
        namespaces = get_namespaces_mcp()
        
        if namespaces:
            print(f"✅ Successfully retrieved {len(namespaces)} namespaces:")
            for i, ns in enumerate(namespaces[:10], 1):  # Show first 10
                print(f"   {i}. {ns}")
            if len(namespaces) > 10:
                print(f"   ... and {len(namespaces) - 10} more")
            return True
        else:
            print("⚠️ No namespaces returned from MCP")
            return False
            
    except Exception as e:
        print(f"❌ Error testing namespaces: {e}")
        return False

def main():
    """Run all MCP integration tests"""
    print("🚀 MCP Integration Test Suite (FastMCP)")
    print(f"MCP Server URL: {os.getenv('MCP_SERVER_URL', 'http://localhost:8085')}")
    
    # Test results using fastmcp client
    tests = [
        ("Server Health", test_mcp_server_health),
        ("Sync Tool Call", test_mcp_sync_tool),
        ("Namespace Retrieval", test_mcp_namespaces),
    ]
    
    results = {}
    for test_name, test_func in tests:
        try:
            results[test_name] = test_func()
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
            results[test_name] = False
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Test Results Summary")
    print("=" * 60)
    
    passed = sum(results.values())
    total = len(results)
    
    for test_name, passed_test in results.items():
        status = "✅ PASS" if passed_test else "❌ FAIL"
        print(f"{status} {test_name}")
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! FastMCP integration is ready for UI.")
        return 0
    else:
        print("⚠️ Some tests failed. Check MCP server status and configuration.")
        print("\nTroubleshooting:")
        print("1. Ensure MCP server is running:")
        print("   cd src && MCP_TRANSPORT_PROTOCOL=http python -m mcp_server.main")
        print("2. Check MCP_SERVER_URL environment variable")
        print("3. Verify server health at: http://localhost:8085/health")
        print("4. Verify MCP endpoint at: http://localhost:8085/mcp")
        return 1

if __name__ == "__main__":
    sys.exit(main())
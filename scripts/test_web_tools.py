#!/usr/bin/env python3
"""
Test script for CH8 Web Tools
"""

import sys
import json
sys.path.insert(0, '/data/ch8-agent')

from tools.web_tools import web_search, web_extract

def test_web_search():
    print("=== Testing web_search ===")
    result = web_search("CH8 cluster infrastructure", max_results=3)
    print(json.dumps(result, indent=2))
    print()
    
    if result["success"]:
        print(f"✓ Found {result['count']} results")
        for i, r in enumerate(result["results"], 1):
            print(f"  {i}. {r['title']}")
            print(f"     {r['url']}")
    else:
        print(f"✗ Error: {result.get('error')}")
    print()

def test_web_extract():
    print("=== Testing web_extract ===")
    result = web_extract("https://github.com")
    
    if result["success"]:
        print(f"✓ Extracted content from {result['url']}")
        print(f"  Title: {result['title']}")
        print(f"  Length: {result['length']} chars")
        print(f"  Method: {result['method']}")
        print(f"  Preview: {result['content'][:200]}...")
    else:
        print(f"✗ Error: {result.get('error')}")
    print()

if __name__ == "__main__":
    try:
        test_web_search()
        test_web_extract()
        print("=== All Tests Complete ===")
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()

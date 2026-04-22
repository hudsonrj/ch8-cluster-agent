"""
Simple Android Node Example - Minimal setup
"""

import asyncio
import sys
sys.path.append('..')

from node import AndroidNode, OperationMode


async def main():
    print("🤖 Starting Simple Android Node")
    print("-" * 40)

    # Create node with simple config
    node = AndroidNode()
    node.config = {
        'mode': 'cloud',
        'cloud': {
            'provider': 'groq',
            'api_key': 'YOUR_GROQ_API_KEY',
            'model': 'llama3-8b-8192'
        },
        'battery': {
            'optimization': True,
            'min_battery_level': 20
        }
    }

    # Test generation
    print("\n📝 Testing text generation...")

    prompt = "Explain quantum computing in simple terms"
    response = await node.generate(prompt)

    print(f"\nPrompt: {prompt}")
    print(f"Response: {response}")

    print("\n✅ Test completed!")


if __name__ == '__main__':
    asyncio.run(main())

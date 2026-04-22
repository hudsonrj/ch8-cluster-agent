"""
Example Usage - Demonstrate multiple small models working together

This example shows how to:
1. Set up multiple small local models (0.5-1B)
2. Decompose a complex task
3. Execute subtasks in parallel
4. Aggregate results with a larger model
5. Achieve better quality with less total tokens
"""

import asyncio
from typing import List

from .ollama_agent import OllamaAgent
from .model_orchestrator import ModelOrchestrator, TaskType
from .result_aggregator import ResultAggregator


async def example_single_model_baseline():
    """
    Baseline: Single large model approach

    Problem: Uses many tokens on one expensive model
    """
    print("\n" + "="*60)
    print("BASELINE: Single Large Model (Mistral 7B)")
    print("="*60)

    # Large model
    large_model = OllamaAgent({'model_name': 'mistral:7b'})
    await large_model.load_model()

    task = """
    Analyze this scenario and provide:
    1. Technical analysis of the problem
    2. Three possible solutions with pros/cons
    3. Code example for the best solution
    4. Summary and recommendation

    Scenario: A distributed system needs efficient task scheduling across multiple nodes.
    """

    print(f"\nTask: {task[:100]}...")

    result = await large_model.generate(task, max_tokens=1024)
    tokens_used = await large_model.count_tokens(result)

    print(f"\n📊 Results:")
    print(f"  Model: {large_model.model_name}")
    print(f"  Tokens used: {tokens_used}")
    print(f"  Output length: {len(result)} chars")
    print(f"\nResult preview: {result[:200]}...")

    await large_model.unload_model()

    return tokens_used


async def example_multi_model_orchestrated():
    """
    Orchestrated: Multiple small models working together

    Advantage: Parallel execution, less tokens per model, specialized tasks
    """
    print("\n" + "="*60)
    print("ORCHESTRATED: Multiple Small Models (0.5-1B each)")
    print("="*60)

    # Set up small specialized models
    # In production, these would run on different nodes

    # Model 1: Phi-3 Mini (0.5B) - Good at reasoning and analysis
    reasoning_model = OllamaAgent({'model_name': 'phi3:mini'})
    await reasoning_model.load_model()

    # Model 2: TinyLlama (1.1B) - Fast general purpose
    general_model = OllamaAgent({'model_name': 'tinyllama'})
    await general_model.load_model()

    # Model 3: Qwen 0.5B - Ultra fast for simple tasks
    fast_model = OllamaAgent({'model_name': 'qwen:0.5b'})
    await fast_model.load_model()

    # Model 4: Gemma 2B - For synthesis (acts as "larger" aggregator)
    aggregator_model = OllamaAgent({'model_name': 'gemma:2b'})
    await aggregator_model.load_model()

    # Create orchestrator
    orchestrator = ModelOrchestrator()

    # Register models with specializations
    orchestrator.register_model(
        reasoning_model,
        specializations=[TaskType.REASONING, TaskType.ANALYSIS]
    )
    orchestrator.register_model(
        general_model,
        specializations=[TaskType.CODING, TaskType.CREATIVE]
    )
    orchestrator.register_model(
        fast_model,
        specializations=[TaskType.EXTRACTION, TaskType.CLASSIFICATION]
    )

    task = """
    Analyze this scenario and provide:
    1. Technical analysis of the problem
    2. Three possible solutions with pros/cons
    3. Code example for the best solution
    4. Summary and recommendation

    Scenario: A distributed system needs efficient task scheduling across multiple nodes.
    """

    print(f"\nTask: {task[:100]}...")

    # Orchestrate execution
    result = await orchestrator.orchestrate(
        task=task,
        aggregator=aggregator_model,
        strategy='auto',
        max_concurrent=3
    )

    print(f"\n📊 Results:")
    print(f"  Subtasks executed: {result['subtasks']}")
    print(f"  Total tokens used: {result['total_tokens']}")
    print(f"  Execution time: {result['execution_time']:.2f}s")
    print(f"  Efficiency: {result['efficiency']}")

    print(f"\n📋 Subtask Breakdown:")
    for sr in result['subtask_results']:
        print(f"  - {sr['task_id']}: {sr['model']} ({sr['tokens']} tokens in {sr['time']:.2f}s)")

    print(f"\nFinal result preview: {result['result'][:200]}...")

    # Cleanup
    await reasoning_model.unload_model()
    await general_model.unload_model()
    await fast_model.unload_model()
    await aggregator_model.unload_model()

    return result['total_tokens']


async def example_distributed_nodes():
    """
    Distributed: Models running on different physical nodes

    Each node runs small models locally, CH8 Agent coordinates
    """
    print("\n" + "="*60)
    print("DISTRIBUTED: Models on Different Nodes")
    print("="*60)

    print("""
    Scenario: 4 nodes in CH8 Agent cluster

    Node 1 (Intel CPU):
      - TinyLlama 1.1B via llama.cpp (CPU optimized)
      - Task: General processing

    Node 2 (M1 MacBook):
      - Phi-3 Mini 0.5B via llama.cpp (Metal)
      - Task: Reasoning and analysis

    Node 3 (NVIDIA GPU):
      - Qwen 0.5B via vLLM (GPU batching)
      - Task: Fast classification/extraction

    Node 4 (Central coordinator):
      - Gemma 2B for aggregation
      - Task: Consolidate results

    Benefits:
    ✓ Uses each node's resources optimally
    ✓ Parallel execution across physical machines
    ✓ No single point of bottleneck
    ✓ Can scale horizontally by adding nodes
    ✓ Total cost: 4 small models < 1 large model
    """)

    # Simulate distributed execution
    # In reality, each agent would connect to different endpoints

    from .llamacpp_agent import LlamaCppAgent
    from .vllm_agent import VLLMAgent

    # Node 1: llama.cpp on CPU
    node1_agent = LlamaCppAgent({
        'model_name': 'tinyllama-1.1b-q4_0',
        'base_url': 'http://node1:8080'
    })

    # Node 2: llama.cpp on M1 Mac
    node2_agent = LlamaCppAgent({
        'model_name': 'phi-3-mini-q5_k_m',
        'base_url': 'http://node2:8080'
    })

    # Node 3: vLLM on GPU
    node3_agent = VLLMAgent({
        'model_name': 'qwen-0.5b',
        'base_url': 'http://node3:8000'
    })

    # Node 4: Ollama for aggregation
    node4_agent = OllamaAgent({
        'model_name': 'gemma:2b',
        'base_url': 'http://node4:11434'
    })

    print("""
    Execution Flow:
    1. Master node receives task
    2. Task decomposed into 3 subtasks
    3. Subtasks sent to Node 1, 2, 3 in parallel
    4. Each node processes locally with small model
    5. Results sent to Node 4
    6. Node 4 aggregates with Gemma 2B
    7. Final result returned to user

    Result: 4 small models working together produce better output than
            single large model, using less total resources!
    """)


async def example_comparison():
    """Compare single large model vs orchestrated small models"""
    print("\n" + "="*60)
    print("COMPARISON: Single Large vs Multiple Small")
    print("="*60)

    print("\nRunning baseline (single large model)...")
    baseline_tokens = await example_single_model_baseline()

    print("\nRunning orchestrated (multiple small models)...")
    orchestrated_tokens = await example_multi_model_orchestrated()

    print("\n" + "="*60)
    print("FINAL COMPARISON")
    print("="*60)

    print(f"\nSingle Large Model (Mistral 7B):")
    print(f"  Tokens used: {baseline_tokens}")
    print(f"  Model size: 7B parameters")
    print(f"  Parallelization: None")

    print(f"\nMultiple Small Models (Orchestrated):")
    print(f"  Tokens used: {orchestrated_tokens}")
    print(f"  Models used: 3x small (0.5-2B) + 1x aggregator (2B)")
    print(f"  Parallelization: 3x concurrent")

    savings = ((baseline_tokens - orchestrated_tokens) / baseline_tokens * 100)
    print(f"\n💰 Token savings: {savings:.1f}%")

    print(f"""
    Additional Benefits of Orchestrated Approach:
    ✓ Faster execution (parallel processing)
    ✓ Better specialization (each model optimized for task type)
    ✓ More resilient (if one model fails, others continue)
    ✓ Scalable (can add more nodes/models)
    ✓ Cost effective (small models cheaper to run)
    ✓ Lower latency (smaller models respond faster)
    """)


async def main():
    """Run all examples"""
    print("\n" + "="*60)
    print("LOCAL LLM ORCHESTRATION EXAMPLES")
    print("Multiple Small Models Working Together")
    print("="*60)

    # Example 1: Basic comparison
    await example_comparison()

    # Example 2: Distributed architecture explanation
    await example_distributed_nodes()

    print("\n" + "="*60)
    print("Examples completed!")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())

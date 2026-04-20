# Model Selection Guide

## Overview

CH8 Cluster Agent supports flexible model selection, allowing each worker to use different models based on task requirements, privacy concerns, and user preferences.

## Key Features

### 🎯 Flexible Model Choice
- **User can specify model:** "Use GPT-4o for this task"
- **Auto-routing:** System picks best model automatically
- **Privacy-aware:** Force local models for sensitive data
- **Cost-conscious:** Prefer free local models for small tasks

### 🔒 Privacy Levels

**HIGH:** Data never leaves worker machine
- Only local models (Ollama, LM Studio)
- Example: Medical records, passwords, confidential contracts

**MEDIUM:** Prefer local, use API if needed
- Try local first, fallback to API
- Example: General analysis, code generation

**LOW:** Any model acceptable
- Can use external APIs
- Example: Public data summarization, web content

### 💰 Cost Awareness

**Local models:** $0 per token
- Phi-3-mini (3.8B)
- Gemma-2B
- Llama-3-8B
- Mistral-7B

**API models:** Variable cost
- Groq: ~$0.0005/1K tokens (fast, cheap)
- OpenRouter: $0.001-0.003/1K tokens
- OpenAI: $0.01-0.03/1K tokens

## Configuration

### Worker Configuration

```yaml
# config/worker.yaml
models:
  default: "ollama/phi-3-mini"
  
  available:
    - name: "ollama/phi-3-mini"
      type: "local"
      context_length: 4096
      cost_per_1k_tokens: 0
      privacy: "high"
      speed: "fast"
      
    - name: "ollama/llama3-8b"
      type: "local"
      context_length: 8192
      cost_per_1k_tokens: 0
      privacy: "high"
      speed: "medium"
      
    - name: "openrouter/anthropic/claude-sonnet-4"
      type: "api"
      context_length: 200000
      cost_per_1k_tokens: 0.003
      privacy: "low"
      speed: "medium"
      api_key_env: "OPENROUTER_API_KEY"
  
  # Automatic routing
  routing:
    small_tasks:
      max_tokens: 500
      model: "ollama/phi-3-mini"
    
    sensitive:
      privacy_required: "high"
      model: "ollama/llama3-8b"
      force_local: true
    
    complex:
      min_steps: 3
      model: "openrouter/anthropic/claude-sonnet-4"
```

### Task Submission

```python
from cluster.master import TaskRequest
from cluster.model_manager import PrivacyLevel

# Example 1: Let system choose
task = TaskRequest(
    description="Summarize this article",
    context={"article": "..."}
)

# Example 2: User specifies model
task = TaskRequest(
    description="Analyze this code",
    model_preference="ollama/llama3-8b",
    context={"code": "..."}
)

# Example 3: High privacy requirement
task = TaskRequest(
    description="Process medical records",
    privacy_level=PrivacyLevel.HIGH,  # Forces local model
    context={"records": "..."}
)

# Example 4: Complex reasoning
task = TaskRequest(
    description="Multi-step analysis with deep reasoning",
    complexity="complex",  # Will use Claude/GPT-4
    context={"data": "..."}
)
```

## Selection Logic

The system selects models in this priority order:

### 1. User Preference (Highest Priority)
If user specifies a model and it meets privacy requirements, use it.

```python
task.model_preference = "ollama/llama3-8b"
# System will use llama3-8b if available
```

### 2. Privacy Requirements
If `privacy_level = HIGH`, only local models are considered.

```python
task.privacy_level = PrivacyLevel.HIGH
# System will NEVER use API models
```

### 3. Routing Rules
Based on task characteristics:

**Small tasks** (< 500 tokens):
- Use lightweight local model (Phi-3-mini)
- Fast, free, good enough for simple tasks

**Sensitive tasks** (keywords detected):
- Keywords: "password", "CPF", "confidential", "medical"
- Force local model automatically

**Complex tasks** (multi-step reasoning):
- Use powerful API model (Claude, GPT-4)
- Better reasoning, worth the cost

### 4. Default Model (Lowest Priority)
If no other rule applies, use worker's default model.

## Examples by Use Case

### Use Case 1: Old Notebook (4GB RAM)
```yaml
# worker-laptop.yaml
models:
  default: "ollama/phi-3-mini"
  available:
    - "ollama/phi-3-mini"  # Only lightweight model
  routing:
    small_tasks:
      model: "ollama/phi-3-mini"
```

**Result:** All tasks use Phi-3-mini, runs smoothly on old hardware.

### Use Case 2: Raspberry Pi (No local LLM)
```yaml
# worker-rpi.yaml
models:
  default: "groq/llama-3-70b"  # API only
  available:
    - "groq/llama-3-70b"
    - "openrouter/claude-sonnet"
  routing:
    small_tasks:
      model: "groq/llama-3-70b"  # Fast & cheap
```

**Result:** Uses API models (no local compute needed).

### Use Case 3: Powerful Server (16GB RAM)
```yaml
# worker-server.yaml
models:
  default: "ollama/llama3-8b"
  available:
    - "ollama/phi-3-mini"
    - "ollama/llama3-8b"
    - "ollama/mixtral-8x7b"
    - "openrouter/claude-sonnet-4"
  routing:
    small_tasks:
      model: "ollama/phi-3-mini"
    sensitive:
      model: "ollama/llama3-8b"
    complex:
      model: "openrouter/claude-sonnet-4"
```

**Result:** Optimal mix of local and API models.

### Use Case 4: Privacy-Critical Worker
```yaml
# worker-secure.yaml
models:
  default: "ollama/llama3-8b"
  available:
    - "ollama/llama3-8b"  # Only local models
    - "ollama/mixtral-8x7b"
  routing:
    sensitive:
      force_local: true
```

**Result:** Never uses external APIs, all data stays on-premise.

## Cost Estimation

The system tracks costs automatically:

```python
from cluster.model_manager import ModelManager

manager = ModelManager(config)

# Estimate cost before execution
cost = manager.estimate_cost("openrouter/claude-sonnet-4", tokens=5000)
print(f"Estimated cost: ${cost:.4f}")
# Output: Estimated cost: $0.0150

# Compare costs
local_cost = manager.estimate_cost("ollama/llama3-8b", tokens=5000)
print(f"Local cost: ${local_cost:.4f}")
# Output: Local cost: $0.0000
```

## Best Practices

### 1. Start Local, Scale to API
- Default to local models
- Add API models only when needed
- Monitor costs and performance

### 2. Privacy First
- Mark sensitive tasks explicitly
- Use `privacy_level=HIGH` for confidential data
- Never log sensitive context

### 3. Right Model for the Job
- Simple tasks: Phi-3-mini (fast, free)
- Code analysis: Llama-3-8B (good at code)
- Deep reasoning: Claude/GPT-4 (worth the cost)

### 4. Test on Cheap Hardware
- If it works on a $5 VPS, it works anywhere
- Optimize for minimal resource usage
- Use local models aggressively

## Troubleshooting

**Problem:** Model not found
```
ERROR: Model "ollama/llama3-8b" not available
```
**Solution:** Make sure Ollama is running and model is pulled:
```bash
ollama pull llama3-8b
```

**Problem:** Privacy violation
```
ERROR: Model rejected due to privacy requirements
```
**Solution:** Task requires local model, but you specified an API model. Either:
- Change model to a local one
- Lower privacy requirements (if appropriate)

**Problem:** High costs
```
WARNING: Monthly API costs exceeded $50
```
**Solution:**
- Review routing rules
- Increase use of local models for small tasks
- Set cost limits per worker

## Future Enhancements

- [ ] **Cost budgets:** Per-worker monthly spending limits
- [ ] **Model benchmarking:** Automatic quality scoring
- [ ] **Dynamic routing:** Learn from task outcomes
- [ ] **Model quantization:** Smaller local models (4-bit, 8-bit)
- [ ] **Hybrid execution:** Start local, escalate to API if needed

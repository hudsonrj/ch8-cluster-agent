"""
Model Orchestrator - Coordinates multiple small models working together
"""

from typing import Dict, Any, List, Optional, Tuple
import structlog
import asyncio
from dataclasses import dataclass
from enum import Enum

from .base_llm import BaseLocalLLM

logger = structlog.get_logger()


class TaskType(Enum):
    """Task types for model specialization"""
    REASONING = "reasoning"
    CODING = "coding"
    CREATIVE = "creative"
    FACTUAL = "factual"
    SUMMARIZATION = "summarization"
    CLASSIFICATION = "classification"
    EXTRACTION = "extraction"
    ANALYSIS = "analysis"


@dataclass
class SubTask:
    """Subtask definition"""
    task_id: str
    task_type: TaskType
    prompt: str
    model: Optional[BaseLocalLLM] = None
    priority: int = 0


@dataclass
class SubTaskResult:
    """Subtask result"""
    task_id: str
    result: str
    model_name: str
    tokens_used: int
    execution_time: float


class ModelOrchestrator:
    """
    Orchestrates multiple small models to work on tasks together

    Strategy:
    1. Decompose large task into subtasks
    2. Assign subtasks to specialized small models
    3. Execute in parallel across multiple models
    4. Aggregate results using a larger model or voting
    5. Return consolidated result

    Benefits:
    - Parallel execution (faster)
    - Less tokens per model (efficient)
    - Specialized models per task type (better quality)
    - Distributed across nodes (scalable)
    """

    def __init__(self, models: Optional[List[BaseLocalLLM]] = None):
        self.models = models or []
        self.model_assignments = {}  # task_type -> model mapping

    def register_model(self, model: BaseLocalLLM,
                      specializations: Optional[List[TaskType]] = None):
        """
        Register a model with optional specializations

        Args:
            model: Model agent to register
            specializations: Task types this model is good at
        """
        self.models.append(model)

        if specializations:
            for task_type in specializations:
                if task_type not in self.model_assignments:
                    self.model_assignments[task_type] = []
                self.model_assignments[task_type].append(model)

        logger.info(
            f"Registered model {model.model_name}",
            specializations=specializations
        )

    async def decompose_task(self,
                            task: str,
                            strategy: str = "auto") -> List[SubTask]:
        """
        Decompose a large task into subtasks

        Args:
            task: Original task description
            strategy: Decomposition strategy (auto, manual, sequential, parallel)

        Returns:
            List of subtasks
        """
        if strategy == "auto":
            # Automatic decomposition based on task analysis
            return await self._auto_decompose(task)
        elif strategy == "manual":
            # User-provided decomposition
            return []
        else:
            # Simple split
            return await self._simple_decompose(task)

    async def _auto_decompose(self, task: str) -> List[SubTask]:
        """
        Automatically decompose task based on content analysis

        Examples:
        - "Write code and explain it" -> [CODING, ANALYSIS]
        - "Summarize and extract facts" -> [SUMMARIZATION, EXTRACTION]
        - "Create story and review" -> [CREATIVE, ANALYSIS]
        """
        subtasks = []

        # Analyze task for keywords
        task_lower = task.lower()

        # Detect reasoning tasks
        if any(kw in task_lower for kw in ['analyze', 'think', 'reason', 'why', 'how']):
            subtasks.append(SubTask(
                task_id=f"reasoning_{len(subtasks)}",
                task_type=TaskType.REASONING,
                prompt=f"Analyze and reason about: {task}",
                priority=1
            ))

        # Detect coding tasks
        if any(kw in task_lower for kw in ['code', 'program', 'script', 'function', 'algorithm']):
            subtasks.append(SubTask(
                task_id=f"coding_{len(subtasks)}",
                task_type=TaskType.CODING,
                prompt=f"Write code for: {task}",
                priority=2
            ))

        # Detect creative tasks
        if any(kw in task_lower for kw in ['create', 'write', 'story', 'creative', 'generate']):
            subtasks.append(SubTask(
                task_id=f"creative_{len(subtasks)}",
                task_type=TaskType.CREATIVE,
                prompt=f"Create creative content for: {task}",
                priority=1
            ))

        # Detect factual tasks
        if any(kw in task_lower for kw in ['fact', 'what is', 'define', 'explain']):
            subtasks.append(SubTask(
                task_id=f"factual_{len(subtasks)}",
                task_type=TaskType.FACTUAL,
                prompt=f"Provide factual information about: {task}",
                priority=1
            ))

        # Detect summarization
        if any(kw in task_lower for kw in ['summarize', 'summary', 'brief', 'tldr']):
            subtasks.append(SubTask(
                task_id=f"summary_{len(subtasks)}",
                task_type=TaskType.SUMMARIZATION,
                prompt=f"Summarize: {task}",
                priority=1
            ))

        # Detect extraction
        if any(kw in task_lower for kw in ['extract', 'find', 'get', 'list']):
            subtasks.append(SubTask(
                task_id=f"extraction_{len(subtasks)}",
                task_type=TaskType.EXTRACTION,
                prompt=f"Extract information from: {task}",
                priority=2
            ))

        # If no specific type detected, treat as analysis
        if not subtasks:
            subtasks.append(SubTask(
                task_id="analysis_0",
                task_type=TaskType.ANALYSIS,
                prompt=task,
                priority=1
            ))

        return subtasks

    async def _simple_decompose(self, task: str) -> List[SubTask]:
        """Simple task decomposition by sentences"""
        # Split by periods or newlines
        parts = [p.strip() for p in task.split('.') if p.strip()]

        subtasks = []
        for i, part in enumerate(parts):
            subtasks.append(SubTask(
                task_id=f"subtask_{i}",
                task_type=TaskType.ANALYSIS,
                prompt=part,
                priority=1
            ))

        return subtasks

    def assign_models(self, subtasks: List[SubTask]) -> List[SubTask]:
        """
        Assign models to subtasks based on specialization

        Args:
            subtasks: List of subtasks to assign

        Returns:
            Subtasks with assigned models
        """
        for subtask in subtasks:
            # Find specialized models for this task type
            specialized = self.model_assignments.get(subtask.task_type, [])

            if specialized:
                # Use specialized model
                subtask.model = specialized[0]  # Could use load balancing here
            elif self.models:
                # Use any available model
                subtask.model = self.models[0]
            else:
                logger.warning(f"No model available for subtask {subtask.task_id}")

        return subtasks

    async def execute_parallel(self,
                              subtasks: List[SubTask],
                              max_concurrent: int = 4) -> List[SubTaskResult]:
        """
        Execute subtasks in parallel

        Args:
            subtasks: Subtasks to execute
            max_concurrent: Maximum concurrent executions

        Returns:
            List of results
        """
        # Sort by priority (higher first)
        subtasks = sorted(subtasks, key=lambda x: x.priority, reverse=True)

        # Execute in batches
        results = []
        semaphore = asyncio.Semaphore(max_concurrent)

        async def execute_one(subtask: SubTask) -> SubTaskResult:
            async with semaphore:
                if not subtask.model:
                    logger.error(f"No model assigned to {subtask.task_id}")
                    return SubTaskResult(
                        task_id=subtask.task_id,
                        result="Error: No model assigned",
                        model_name="none",
                        tokens_used=0,
                        execution_time=0
                    )

                try:
                    import time
                    start_time = time.time()

                    # Get optimized params for task type
                    params = await subtask.model.optimize_for_task(subtask.task_type.value)

                    # Generate
                    result = await subtask.model.generate(
                        subtask.prompt,
                        **params
                    )

                    execution_time = time.time() - start_time
                    tokens_used = await subtask.model.count_tokens(result)

                    logger.info(
                        f"Executed subtask {subtask.task_id}",
                        model=subtask.model.model_name,
                        tokens=tokens_used,
                        time=execution_time
                    )

                    return SubTaskResult(
                        task_id=subtask.task_id,
                        result=result,
                        model_name=subtask.model.model_name,
                        tokens_used=tokens_used,
                        execution_time=execution_time
                    )

                except Exception as e:
                    logger.error(f"Error executing subtask {subtask.task_id}", error=str(e))
                    return SubTaskResult(
                        task_id=subtask.task_id,
                        result=f"Error: {str(e)}",
                        model_name=subtask.model.model_name,
                        tokens_used=0,
                        execution_time=0
                    )

        # Execute all subtasks
        tasks = [execute_one(st) for st in subtasks]
        results = await asyncio.gather(*tasks)

        return results

    async def orchestrate(self,
                         task: str,
                         aggregator: Optional[BaseLocalLLM] = None,
                         strategy: str = "auto",
                         max_concurrent: int = 4) -> Dict[str, Any]:
        """
        Main orchestration workflow

        Args:
            task: Original task
            aggregator: Model to aggregate results (can be larger model)
            strategy: Decomposition strategy
            max_concurrent: Max parallel executions

        Returns:
            Dict with final result and metadata
        """
        # Step 1: Decompose
        logger.info(f"Decomposing task", strategy=strategy)
        subtasks = await self.decompose_task(task, strategy)

        if not subtasks:
            return {
                'result': 'Error: No subtasks generated',
                'subtasks': [],
                'total_tokens': 0,
                'execution_time': 0
            }

        # Step 2: Assign models
        logger.info(f"Assigning models to {len(subtasks)} subtasks")
        subtasks = self.assign_models(subtasks)

        # Step 3: Execute in parallel
        logger.info(f"Executing {len(subtasks)} subtasks in parallel")
        import time
        start_time = time.time()

        results = await self.execute_parallel(subtasks, max_concurrent)

        execution_time = time.time() - start_time

        # Step 4: Aggregate results
        logger.info("Aggregating results")
        from .result_aggregator import ResultAggregator

        aggregator_instance = ResultAggregator(aggregator)
        final_result = await aggregator_instance.aggregate(
            original_task=task,
            results=results
        )

        # Calculate totals
        total_tokens = sum(r.tokens_used for r in results)

        return {
            'result': final_result,
            'subtasks': len(subtasks),
            'subtask_results': [
                {
                    'task_id': r.task_id,
                    'model': r.model_name,
                    'tokens': r.tokens_used,
                    'time': r.execution_time
                }
                for r in results
            ],
            'total_tokens': total_tokens,
            'execution_time': execution_time,
            'efficiency': f"{total_tokens/execution_time:.0f} tokens/sec" if execution_time > 0 else "N/A"
        }

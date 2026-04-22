"""
Result Aggregator - Consolidates results from multiple small models
"""

from typing import Dict, Any, List, Optional
import structlog
from collections import Counter

from .base_llm import BaseLocalLLM

logger = structlog.get_logger()


class ResultAggregator:
    """
    Aggregates results from multiple models using various strategies

    Strategies:
    - SYNTHESIS: Use larger model to synthesize results
    - VOTING: Majority voting for classification tasks
    - RANKING: Rank results by quality metrics
    - CONCATENATION: Simple concatenation
    - BEST: Select best result based on heuristics
    """

    def __init__(self, aggregator_model: Optional[BaseLocalLLM] = None):
        self.aggregator_model = aggregator_model

    async def aggregate(self,
                       original_task: str,
                       results: List[Any],
                       strategy: str = "auto") -> str:
        """
        Aggregate results using specified strategy

        Args:
            original_task: Original task description
            results: List of SubTaskResult objects
            strategy: Aggregation strategy

        Returns:
            Final aggregated result
        """
        if not results:
            return "No results to aggregate"

        # Auto-select strategy
        if strategy == "auto":
            strategy = self._select_strategy(results)

        logger.info(f"Aggregating {len(results)} results using {strategy} strategy")

        if strategy == "synthesis":
            return await self._synthesize(original_task, results)
        elif strategy == "voting":
            return self._vote(results)
        elif strategy == "ranking":
            return self._rank(results)
        elif strategy == "concatenation":
            return self._concatenate(results)
        elif strategy == "best":
            return self._select_best(results)
        else:
            return self._concatenate(results)

    def _select_strategy(self, results: List[Any]) -> str:
        """Auto-select best aggregation strategy"""
        num_results = len(results)

        # If we have aggregator model, use synthesis for better quality
        if self.aggregator_model:
            return "synthesis"

        # If multiple similar results, use voting
        if num_results >= 3 and self._are_similar(results):
            return "voting"

        # If few results, concatenate
        if num_results <= 2:
            return "concatenation"

        # Default to ranking
        return "ranking"

    async def _synthesize(self, original_task: str, results: List[Any]) -> str:
        """
        Use aggregator model to synthesize results

        This is the best quality but requires a larger model
        """
        if not self.aggregator_model:
            logger.warning("No aggregator model available, falling back to concatenation")
            return self._concatenate(results)

        # Build synthesis prompt
        results_text = "\n\n".join([
            f"Result {i+1} (from {r.model_name}):\n{r.result}"
            for i, r in enumerate(results)
        ])

        synthesis_prompt = f"""You are synthesizing results from multiple AI models working on different aspects of a task.

Original Task: {original_task}

Results from different models:
{results_text}

Your task is to:
1. Analyze all the results
2. Identify the best insights from each
3. Combine them into a single, coherent, high-quality response
4. Ensure consistency and remove contradictions
5. Provide a complete answer to the original task

Synthesized Response:"""

        try:
            # Use aggregator model to synthesize
            synthesized = await self.aggregator_model.generate(
                synthesis_prompt,
                max_tokens=1024,
                temperature=0.3
            )

            logger.info("Synthesis completed", aggregator=self.aggregator_model.model_name)
            return synthesized

        except Exception as e:
            logger.error("Synthesis failed", error=str(e))
            return self._concatenate(results)

    def _vote(self, results: List[Any]) -> str:
        """
        Majority voting - useful for classification/yes-no tasks

        Returns the most common result
        """
        # Extract result texts
        result_texts = [r.result.strip().lower() for r in results]

        # Count occurrences
        counter = Counter(result_texts)
        most_common = counter.most_common(1)[0][0]

        # Find original result (with proper casing)
        for r in results:
            if r.result.strip().lower() == most_common:
                logger.info(f"Voting selected: {r.result}", votes=counter[most_common])
                return r.result

        return results[0].result

    def _rank(self, results: List[Any]) -> str:
        """
        Rank results by quality heuristics

        Quality metrics:
        - Length (longer often better for detailed tasks)
        - Token efficiency
        - Execution time (faster sometimes better)
        """
        scored_results = []

        for r in results:
            score = 0

            # Length score (normalized)
            length_score = min(len(r.result) / 1000, 1.0) * 30

            # Token efficiency score
            if r.execution_time > 0:
                efficiency = r.tokens_used / r.execution_time
                efficiency_score = min(efficiency / 100, 1.0) * 30
            else:
                efficiency_score = 0

            # Content quality heuristics
            quality_score = 0
            if len(r.result) > 100:
                quality_score += 10
            if '\n' in r.result:  # Has structure
                quality_score += 10
            if any(char in r.result for char in ['.', '!', '?']):
                quality_score += 10

            total_score = length_score + efficiency_score + quality_score

            scored_results.append((total_score, r))

        # Sort by score (highest first)
        scored_results.sort(key=lambda x: x[0], reverse=True)

        best_result = scored_results[0][1]
        logger.info(
            f"Ranking selected result from {best_result.model_name}",
            score=scored_results[0][0]
        )

        return best_result.result

    def _concatenate(self, results: List[Any]) -> str:
        """
        Simple concatenation of results

        Useful when results are complementary parts
        """
        concatenated = "\n\n".join([
            f"{r.result}"
            for r in results
        ])

        logger.info(f"Concatenated {len(results)} results")
        return concatenated

    def _select_best(self, results: List[Any]) -> str:
        """
        Select single best result based on simple heuristics

        Useful for tasks where only one result should be returned
        """
        # Prefer longer, more detailed results
        best = max(results, key=lambda r: len(r.result))

        logger.info(f"Selected best result from {best.model_name}")
        return best.result

    def _are_similar(self, results: List[Any]) -> bool:
        """Check if results are similar (for voting)"""
        if len(results) < 2:
            return False

        # Simple similarity check: compare first 100 chars
        first_result = results[0].result[:100].lower()

        similar_count = sum(
            1 for r in results[1:]
            if r.result[:100].lower() == first_result
        )

        # If more than half are similar, consider them similar
        return similar_count >= len(results) // 2

    async def aggregate_with_confidence(self,
                                       original_task: str,
                                       results: List[Any]) -> Dict[str, Any]:
        """
        Aggregate with confidence scoring

        Returns:
            Dict with 'result' and 'confidence' score
        """
        aggregated = await self.aggregate(original_task, results)

        # Calculate confidence based on result consistency
        confidence = self._calculate_confidence(results)

        return {
            'result': aggregated,
            'confidence': confidence,
            'num_models': len(results),
            'models_used': [r.model_name for r in results]
        }

    def _calculate_confidence(self, results: List[Any]) -> float:
        """
        Calculate confidence score (0.0 - 1.0)

        Based on:
        - Number of models (more = higher confidence)
        - Result consistency (similar results = higher confidence)
        - Model diversity (different models agreeing = higher confidence)
        """
        if not results:
            return 0.0

        confidence = 0.0

        # Number of models factor (max 0.4)
        num_models = len(results)
        confidence += min(num_models / 5, 0.4)

        # Consistency factor (max 0.4)
        if self._are_similar(results):
            confidence += 0.4

        # Diversity factor (max 0.2)
        unique_models = len(set(r.model_name for r in results))
        if unique_models > 1:
            confidence += min(unique_models / 5, 0.2)

        return min(confidence, 1.0)

    async def meta_aggregate(self,
                           strategies: List[str],
                           original_task: str,
                           results: List[Any]) -> str:
        """
        Meta-aggregation: Use multiple strategies and aggregate their results

        This is the highest quality but slowest approach
        """
        if not self.aggregator_model:
            logger.warning("Meta-aggregation requires aggregator model")
            return await self.aggregate(original_task, results)

        # Run multiple strategies
        strategy_results = []

        for strategy in strategies:
            result = await self.aggregate(original_task, results, strategy)
            strategy_results.append({
                'strategy': strategy,
                'result': result
            })

        # Use aggregator to pick best
        meta_prompt = f"""Multiple aggregation strategies were used on AI model results for this task: {original_task}

Strategy Results:
{chr(10).join([f"{i+1}. {sr['strategy'].upper()}: {sr['result']}" for i, sr in enumerate(strategy_results)])}

Select and return ONLY the best result, or synthesize a better one from these options.

Best Result:"""

        return await self.aggregator_model.generate(
            meta_prompt,
            max_tokens=1024,
            temperature=0.2
        )

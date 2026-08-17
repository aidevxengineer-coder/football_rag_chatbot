import json
import re
from typing import Any

from services.llm_gateway.config import settings
from services.llm_gateway.prompt_loader import get_prompt_parts
from services.llm_gateway.provider import (
    MODEL_DECISION,
    MODEL_GENERATOR,
    MODEL_ORCHESTRATOR,
    invoke_llm,
    parse_snapshot_json,
)
from services.llm_gateway.token_budget import (
    build_context_text_within_budget,
    fit_messages_for_prompt,
    trim_preserve_edges,
)


def build_context_text(
    chunks: list[dict[str, Any]],
    tool_results: list[dict[str, Any]] | None = None,
    *,
    max_tokens: int | None = None,
) -> str:
    budget = max_tokens if max_tokens is not None else settings.llm_context_token_budget
    return build_context_text_within_budget(
        chunks,
        tool_results,
        max_tokens=budget,
    )


class SnapshotCompressor:
    def compress_incremental(
        self,
        existing_snapshot: str,
        new_messages: list[dict[str, str]],
        run_logger=None,
    ) -> str:
        newly_aged_text = "\n".join(
            f"{m['role']}: {m['content']}" for m in new_messages
        )
        system_prompt, user_template = get_prompt_parts("COMPRESSOR")
        system_prompt = system_prompt.format(max_tokens=settings.snapshot_max_tokens)
        user_content = user_template.format(
            existing_snapshot=existing_snapshot.strip() or "{}",
            newly_aged_messages=newly_aged_text,
        )
        result = invoke_llm(
            user_content,
            model_name=MODEL_GENERATOR,
            step="compressor",
            run_logger=run_logger,
            iteration=0,
            system_prompt=system_prompt,
        )
        return parse_snapshot_json(result, existing_snapshot)


class QueryRewriter:
    def rewrite(
        self,
        query: str,
        context_messages: list[dict[str, str]],
        snapshot: str = "",
        judge_feedback: str = "",
        run_logger=None,
        iteration: int = 0,
    ) -> str:
        fitted_snapshot = trim_preserve_edges(
            snapshot or "{}",
            max(256, settings.llm_rewriter_context_budget // 3),
        )
        history_text = fit_messages_for_prompt(
            context_messages,
            max_tokens=max(256, settings.llm_rewriter_context_budget // 2),
        )
        feedback_text = trim_preserve_edges(
            judge_feedback.strip(),
            max(128, settings.llm_rewriter_context_budget // 4),
        )
        system_prompt, user_template = get_prompt_parts("REWRITER")
        user_content = user_template.format(
            snapshot=fitted_snapshot,
            history_text=history_text,
            query=query,
            judge_feedback=feedback_text or "None",
        )
        return invoke_llm(
            user_content,
            model_name=MODEL_GENERATOR,
            step="rewriter",
            run_logger=run_logger,
            iteration=iteration,
            system_prompt=system_prompt,
        )


class Orchestrator:
    def classify(self, query: str, run_logger=None, iteration: int = 0) -> str:
        system_prompt, user_template = get_prompt_parts("ORCHESTRATOR")
        user_content = user_template.format(query=query)
        classification = invoke_llm(
            user_content,
            model_name=MODEL_ORCHESTRATOR,
            step="orchestrator",
            run_logger=run_logger,
            iteration=iteration,
            system_prompt=system_prompt,
        ).upper()
        if "TOOL" in classification:
            return "TOOL"
        if "KNOWLEDGE" in classification:
            return "KNOWLEDGE"
        return "SIMPLE"


class ToolPlanner:
    def plan(
        self,
        query: str,
        tools_catalog: str,
        run_logger=None,
        iteration: int = 0,
    ) -> list[dict[str, Any]]:
        system_prompt, user_template = get_prompt_parts("TOOL_PLANNER")
        user_content = user_template.format(query=query, tools_catalog=tools_catalog)
        raw = invoke_llm(
            user_content,
            model_name=MODEL_GENERATOR,
            step="tool_planner",
            run_logger=run_logger,
            iteration=iteration,
            system_prompt=system_prompt,
        )
        text = raw.strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE | re.MULTILINE)
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [p for p in parsed if isinstance(p, dict) and p.get("tool")]
        except json.JSONDecodeError:
            pass
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group())
                if isinstance(parsed, list):
                    return [p for p in parsed if isinstance(p, dict) and p.get("tool")]
            except json.JSONDecodeError:
                pass
        return []


class DraftGenerator:
    def generate(
        self,
        query: str,
        chunks: list[dict[str, Any]],
        tool_results: list[dict[str, Any]] | None = None,
        run_logger=None,
        iteration: int = 0,
    ) -> str:
        context_text = build_context_text(chunks, tool_results)
        system_prompt, user_template = get_prompt_parts("DRAFT_GENERATOR")
        user_content = user_template.format(context_text=context_text, query=query)
        return invoke_llm(
            user_content,
            model_name=MODEL_GENERATOR,
            step="drafter",
            run_logger=run_logger,
            iteration=iteration,
            system_prompt=system_prompt,
        )


class DecisionJudge:
    def evaluate(
        self,
        query: str,
        draft: str,
        chunks: list[dict[str, Any]],
        tool_results: list[dict[str, Any]] | None = None,
        run_logger=None,
        iteration: int = 0,
    ) -> dict[str, str]:
        context_text = build_context_text(chunks, tool_results)
        trimmed_draft = trim_preserve_edges(
            draft,
            settings.llm_judge_draft_token_budget,
        )
        system_prompt, user_template = get_prompt_parts("DECISION_JUDGE")
        user_content = user_template.format(
            context_text=context_text, query=query, draft=trimmed_draft
        )
        result = invoke_llm(
            user_content,
            model_name=MODEL_DECISION,
            step="judge",
            run_logger=run_logger,
            iteration=iteration,
            system_prompt=system_prompt,
        )
        try:
            json_match = re.search(r"\{.*?\}", result, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            raise ValueError("No JSON found")
        except Exception:
            status = (
                "FAIL"
                if "FAIL" in result.upper() and "PASS" not in result.upper()
                else "PASS"
            )
            return {"status": status, "reasoning": "Fallback parsing applied."}

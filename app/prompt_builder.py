"""
Prompt Builder module for Manus MCP.

Constructs optimized prompts for different task modes (web_search, plan, coding)
to guide the Manus agent toward the desired behavior and output format.
"""

from typing import Optional


def build_web_search_prompt(query: str) -> str:
    """
    Build a prompt for web_search mode.

    The goal is to get a direct, concise answer backed by web search results.
    Manus should act purely as a search engine: find, summarize, and cite.
    """
    return (
        f"You are acting as a web search assistant. Your ONLY job is to search the web "
        f"and provide a direct, factual answer to the following query. "
        f"Do NOT perform any planning, coding, or file creation. "
        f"Do NOT ask follow-up questions.\n\n"
        f"Instructions:\n"
        f"1. Search the web for the most relevant and up-to-date information.\n"
        f"2. Synthesize the findings into a clear, concise answer.\n"
        f"3. Include source URLs for all key claims.\n"
        f"4. If the query is ambiguous, provide the most likely interpretation.\n\n"
        f"Query: {query}"
    )


def build_plan_prompt(topic: str, context: Optional[str] = None) -> str:
    """
    Build a prompt for plan mode.

    The goal is deep research, fact-checking, and a structured professional plan.
    """
    context_section = ""
    if context:
        context_section = f"\nAdditional Context:\n{context}\n"

    return (
        f"You are acting as a professional research and planning agent. "
        f"Your job is to thoroughly research the given topic, verify facts from "
        f"multiple sources, and produce a comprehensive, actionable plan.\n\n"
        f"Instructions:\n"
        f"1. Conduct thorough web research on the topic.\n"
        f"2. Cross-reference findings from multiple authoritative sources.\n"
        f"3. Identify key challenges, risks, and opportunities.\n"
        f"4. Produce a structured plan with clear phases, milestones, and deliverables.\n"
        f"5. Include a summary of research findings with source citations.\n"
        f"6. Provide pros/cons analysis where applicable.\n"
        f"7. Save the final plan as a Markdown file.\n\n"
        f"Topic: {topic}"
        f"{context_section}"
    )


def build_coding_prompt(
    prompt: str,
    git_repo_url: Optional[str] = None,
    language: Optional[str] = None,
) -> str:
    """
    Build a prompt for coding mode.

    The goal is to create code from scratch or work with an existing repository.
    """
    repo_section = ""
    if git_repo_url:
        repo_section = (
            f"\nExisting Repository: {git_repo_url}\n"
            f"You MUST clone this repository first, understand its structure, "
            f"and then make the requested changes. Commit and describe your changes clearly.\n"
        )

    lang_section = ""
    if language:
        lang_section = f"\nPreferred Language/Framework: {language}\n"

    return (
        f"You are acting as a professional software engineer. "
        f"Your job is to write clean, well-documented, production-quality code "
        f"that fulfills the following requirements.\n\n"
        f"Instructions:\n"
        f"1. Analyze the requirements carefully before writing any code.\n"
        f"2. Create a clear project structure with appropriate files.\n"
        f"3. Write clean, well-commented code following best practices.\n"
        f"4. Include error handling and input validation.\n"
        f"5. Add a README.md with setup and usage instructions.\n"
        f"6. If tests are appropriate, include them.\n"
        f"7. Save all files and provide a summary of what was created.\n\n"
        f"Requirements: {prompt}"
        f"{repo_section}"
        f"{lang_section}"
    )

CATEGORY_CRITERIA = {
    "AI Coding": (
        "AI coding assistants, code generation, developer tools and AI-assisted software "
        "development. Coding-specific agents belong here rather than Agent Frameworks."
    ),
    "Agent Frameworks": (
        "General agent platforms, orchestration, tool use and multi-agent workflows. "
        "Exclude coding-specific assistants, retrieval systems and security-focused reports."
    ),
    "RAG & Data Systems": (
        "Retrieval-augmented generation, embeddings, vector databases, knowledge bases "
        "and retrieval pipelines. Exclude GPU/inference performance and evaluation tooling."
    ),
    "Security": (
        "AI security, vulnerabilities, prompt injection, attacks, defenses and content "
        "provenance. Security-focused reports belong here even if they involve agents or RAG."
    ),
    "QA & Observability": (
        "AI/LLM evaluation, testing, reliability, hallucination measurement, tracing "
        "and monitoring. Incidental benchmark results in a model release are not enough."
    ),
    "Infrastructure": (
        "AI compute, GPUs, inference, serving, training infrastructure and performance. "
        "Exclude retrieval pipelines and coding assistants."
    ),
    "Business & Product": (
        "Model and product releases, AI adoption, companies, funding, partnerships, "
        "regulation and general research that does not primarily fit another category."
    ),
}
CATEGORY_ORDER = tuple(CATEGORY_CRITERIA)

# Legacy rubric remains pinned; new saved topics are separately readable/filterable.
REENRICH_TOPIC_ORDER = (
    "Models & Research", "AI Coding", "Agent Frameworks", "RAG & Data Systems",
    "QA & Observability", "Security & Safety", "Infrastructure", "AI Applications",
    "Business & Industry", "Policy & Regulation",
)
READABLE_CATEGORIES = frozenset(CATEGORY_ORDER) | frozenset(REENRICH_TOPIC_ORDER)

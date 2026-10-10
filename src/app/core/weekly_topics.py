"""Frozen initial topic registry. Taxonomy changes require full-window replay."""

from dataclasses import asdict, dataclass

TAXONOMY_VERSION = "weekly-topics-1"


@dataclass(frozen=True)
class Topic:
    id: str
    label: str
    definition: str
    exclusions: str
    aliases: tuple[str, ...]
    parent_category: str


TOPICS = (
    Topic("coding-agents", "Coding agents", "Autonomous software engineering and coding tools",
          "General enterprise workflows", ("code agents", "coding assistants"), "AI Agents"),
    Topic("enterprise-agents", "Enterprise agents", "Agents executing business workflows",
          "Software engineering agents", ("workflow agents", "copilots"), "AI Agents"),
    Topic("agent-tooling", "Agent tooling", "Agent orchestration, protocols and tool integration",
          "Individual agent product releases", ("MCP", "agent frameworks"), "AI Agents"),
    Topic("inference", "Inference infrastructure", "Serving, optimization and inference systems",
          "Training-only infrastructure", ("serving", "quantization"), "Infrastructure"),
    Topic("training", "Training infrastructure", "Distributed training and training systems",
          "Model serving", ("training clusters",), "Infrastructure"),
    Topic("chips", "AI chips", "Accelerators, chips and AI hardware architectures",
          "General consumer electronics", ("GPU", "NPU"), "Infrastructure"),
    Topic("datacenters", "AI datacenters", "Datacenters, energy and capacity for AI computing",
          "Chip design", ("AI compute capacity",), "Infrastructure"),
    Topic("open-models", "Open-weight models", "Openly released model weights and ecosystems",
          "Closed-only model releases", ("open source models",), "Models"),
    Topic("language-models", "Language models", "General text language model capabilities",
          "Open-weight releases or multimodal-specific news", ("LLM",), "Models"),
    Topic("multimodal", "Multimodal models", "Models integrating multiple input/output modalities",
          "Single modality generation", ("vision-language",), "Models"),
    Topic("reasoning", "Reasoning models", "Model reasoning, planning and test-time computation",
          "General text generation", ("chain of thought",), "Models"),
    Topic("image", "Image generation", "Image generation and editing models",
          "Video generation", ("text to image",), "Models"),
    Topic("video", "Video generation", "Video generation and editing models",
          "Still images", ("text to video",), "Models"),
    Topic("audio", "Speech and audio AI", "Speech recognition, synthesis and audio generation",
          "Text-only chat", ("voice AI",), "Models"),
    Topic("robotics", "AI robotics", "Embodied AI, autonomous robots and physical reasoning",
          "Software-only agents", ("physical AI",), "Applications"),
    Topic("search", "AI search", "AI-powered search and information discovery",
          "Retrieval infrastructure alone", ("answer engines",), "Applications"),
    Topic("retrieval", "Retrieval and AI data", "Retrieval, vector databases and data pipelines",
          "Consumer search products", ("RAG", "embeddings"), "Infrastructure"),
    Topic("health", "AI in healthcare", "Clinical, medical and healthcare uses of AI",
          "General scientific research", ("medical AI",), "Applications"),
    Topic("science", "AI for science", "Scientific discovery and research using AI",
          "Clinical deployment", ("AI discovery",), "Applications"),
    Topic("education", "AI in education", "Teaching, learning and educational uses of AI",
          "Workforce training alone", ("AI tutors",), "Applications"),
    Topic("regulation", "AI regulation", "Laws, public policy and governance of AI",
          "Private model safety research", ("AI Act",), "Policy"),
    Topic("security", "AI security", "AI cyber threats, defensive security and prompt attacks",
          "General societal safety", ("prompt injection",), "Safety"),
    Topic("safety", "AI safety", "Model alignment, societal harms and safety evaluations",
          "Cybersecurity-specific attacks", ("alignment",), "Safety"),
    Topic("copyright", "AI copyright", "Copyright, licensing and intellectual property in AI",
          "Other AI legislation", ("training rights",), "Policy"),
    Topic("workforce", "AI and work", "Employment and workplace effects of AI",
          "Agent implementation details", ("jobs", "productivity"), "Applications"),
)


def topic_registry() -> list[dict]:
    ids = [topic.id for topic in TOPICS]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate topic IDs")
    parents = {"AI Agents": "Agent Frameworks", "Models": "Business & Product",
               "Applications": "Business & Product", "Policy": "Business & Product",
               "Safety": "Security", "Infrastructure": "Infrastructure"}
    overrides = {"coding-agents": "AI Coding", "retrieval": "RAG & Data Systems"}
    return [{**asdict(topic), "parent_category": overrides.get(
        topic.id, parents[topic.parent_category])} for topic in TOPICS]

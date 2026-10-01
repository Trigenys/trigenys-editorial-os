from editorial_os_api.vertical_packs.contracts import (
    SeoRules,
    SourceRules,
    VerticalPack,
    VisualRules,
    VoiceRules,
)


def generic_demo_pack() -> VerticalPack:
    return VerticalPack(
        key="generic-demo",
        version="1",
        display_name="Generic Editorial Demo",
        audience="General readers who want clear, sourced explanatory reporting.",
        locales=["en"],
        default_locale="en",
        formats=["article", "brief"],
        default_format="article",
        voice=VoiceRules(
            tone=["clear", "neutral", "concise"],
            style_notes=[
                "Prefer concrete language.",
                "Separate sourced fact from analysis.",
            ],
            prohibited_phrases=[
                "as an ai language model",
                "in today's rapidly evolving digital landscape",
            ],
            max_headline_chars=100,
            max_deck_chars=220,
            min_sections=1,
        ),
        source_rules=SourceRules(),
        seo=SeoRules(),
        visual=VisualRules(
            assets_required=False,
            allowed_kinds=["IMAGE", "INFOGRAPHIC"],
            allowed_aspect_ratios=["16:9", "1:1"],
            max_assets=3,
            require_alt_text=True,
            require_caption=True,
            allow_external_assets=True,
            allow_generated_assets=True,
        ),
        internal_link_topics=["background", "explainer"],
        metadata={"kind": "demo"},
    )


def trigenys_insight_pack() -> VerticalPack:
    return VerticalPack(
        key="trigenys-insight",
        version="1",
        display_name="Trigenys Insight",
        audience=(
            "Cameroonian and African readers who want useful technology, business, "
            "startup and digital-economy reporting grounded in local realities."
        ),
        locales=["fr", "en"],
        default_locale="fr",
        formats=["article", "brief", "analysis"],
        default_format="article",
        voice=VoiceRules(
            tone=["professional", "direct", "lively", "locally grounded"],
            style_notes=[
                "Use natural coordinating and subordinating conjunctions.",
                "Use clear logical transitions rather than stacked short sentences.",
                "Prefer concrete Cameroon/Africa context when supported by evidence.",
                "Use restrained storytelling or humour only when it improves clarity.",
                "Avoid generic AI-marketing filler and empty superlatives.",
            ],
            prohibited_phrases=[
                "as an ai language model",
                "dans le paysage numérique en constante évolution",
                "in today's rapidly evolving digital landscape",
                "game-changer",
                "révolutionnaire sans précédent",
            ],
            max_headline_chars=110,
            max_deck_chars=230,
            min_sections=2,
        ),
        source_rules=SourceRules(
            require_citations_for_material_claims=True,
            allow_reviewed_contested_claims=True,
            include_source_urls_in_prompt=True,
        ),
        seo=SeoRules(
            title_max_chars=65,
            description_max_chars=165,
            require_keywords=True,
        ),
        visual=VisualRules(
            assets_required=False,
            allowed_kinds=["IMAGE", "INFOGRAPHIC"],
            allowed_aspect_ratios=["16:9", "1:1"],
            max_assets=5,
            require_alt_text=True,
            require_caption=True,
            allow_external_assets=True,
            allow_generated_assets=True,
        ),
        internal_link_topics=[
            "Cameroon digital economy",
            "African startups",
            "cybersecurity",
            "cloud",
            "e-commerce",
        ],
        metadata={"kind": "pilot"},
    )


def trigenys_insight_pilot_pack() -> VerticalPack:
    return VerticalPack(
        key="trigenys-insight",
        version="2026.10-pilot.1",
        display_name="Trigenys Insight — Staging Pilot",
        audience=(
            "Cameroonian and African readers who want practical technology, business, "
            "startup and digital-economy reporting grounded in local evidence."
        ),
        locales=["fr", "en"],
        default_locale="fr",
        formats=["article", "brief", "analysis"],
        default_format="article",
        voice=VoiceRules(
            tone=["professional", "direct", "lively", "locally grounded"],
            style_notes=[
                "Write for a Cameroonian audience before a generic international audience.",
                "Use coordinating and subordinating conjunctions to keep prose natural.",
                "Use explicit logical transitions instead of stacked short sentences.",
                "Prefer concrete Cameroon/Africa context when the evidence supports it.",
                "Use restrained storytelling, metaphor or humour only when it clarifies.",
                "Distinguish sourced facts, attributed claims and analysis.",
                "Avoid generic AI-marketing filler, empty superlatives and faux certainty.",
            ],
            prohibited_phrases=[
                "as an ai language model",
                "dans le paysage numérique en constante évolution",
                "in today's rapidly evolving digital landscape",
                "game-changer",
                "révolutionnaire sans précédent",
                "il est important de noter que",
            ],
            max_headline_chars=96,
            max_deck_chars=220,
            min_sections=3,
        ),
        source_rules=SourceRules(
            require_citations_for_material_claims=True,
            allow_reviewed_contested_claims=True,
            include_source_urls_in_prompt=True,
        ),
        seo=SeoRules(
            title_max_chars=62,
            description_max_chars=160,
            require_keywords=True,
        ),
        visual=VisualRules(
            assets_required=True,
            allowed_kinds=["IMAGE", "INFOGRAPHIC"],
            allowed_aspect_ratios=["16:9", "1:1"],
            max_assets=5,
            require_alt_text=True,
            require_caption=True,
            allow_external_assets=True,
            allow_generated_assets=True,
        ),
        internal_link_topics=[
            "Cameroon digital economy",
            "African startups",
            "cybersecurity",
            "cloud",
            "e-commerce",
            "digital infrastructure",
            "offline and low-bandwidth technology",
        ],
        metadata={
            "kind": "staging-pilot",
            "pilot": "insight-e2e-2026-10",
            "publication_mode": "payload-staging-only",
        },
    )


_BUILTINS = {
    ("generic-demo", "1"): generic_demo_pack,
    ("trigenys-insight", "1"): trigenys_insight_pack,
    ("trigenys-insight", "2026.10-pilot.1"): trigenys_insight_pilot_pack,
}


def get_builtin_vertical_pack(key: str, version: str) -> VerticalPack:
    try:
        factory = _BUILTINS[(key, version)]
    except KeyError as exc:
        raise KeyError(f"Unknown built-in vertical pack {key!r} version {version!r}.") from exc
    return factory()

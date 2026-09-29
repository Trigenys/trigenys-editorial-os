from editorial_os_api.vertical_packs.contracts import (
    SeoRules,
    SourceRules,
    VerticalPack,
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
        internal_link_topics=[
            "Cameroon digital economy",
            "African startups",
            "cybersecurity",
            "cloud",
            "e-commerce",
        ],
        metadata={"kind": "pilot"},
    )


_BUILTINS = {
    ("generic-demo", "1"): generic_demo_pack,
    ("trigenys-insight", "1"): trigenys_insight_pack,
}


def get_builtin_vertical_pack(key: str, version: str) -> VerticalPack:
    try:
        factory = _BUILTINS[(key, version)]
    except KeyError as exc:
        raise KeyError(f"Unknown built-in vertical pack {key!r} version {version!r}.") from exc
    return factory()

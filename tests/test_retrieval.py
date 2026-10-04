from repopilot.ingestion import SourceFile
from repopilot.parsing import parse_python
from repopilot.retrieval import KeywordRetriever


def test_symbol_terms_outweigh_incidental_content() -> None:
    chunks = parse_python(
        SourceFile(
            "config.py",
            "def load_environment_config():\n"
            "    return {}\n"
            "\n"
            "def print_message():\n"
            "    # environment config is mentioned here\n"
            "    return None\n",
        ),
        "sample",
    )
    matches = KeywordRetriever().search("environment config", chunks, 2)
    assert matches[0].chunk.symbol_name == "load_environment_config"
    assert matches[0].score > matches[1].score

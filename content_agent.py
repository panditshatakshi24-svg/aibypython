"""
content_agent.py — a small, broad content-suggestion agent.

What it does, in plain words:
  1. Reads WHO you are (profile.json)
  2. Remembers what you've already posted (library.json)
  3. Looks at what's going on right now (trends.json)
  4. Makes a batch of content ideas
  5. Sorts them and shows you the best few

It runs in two modes:
  - MOCK mode (default): no API key needed. Uses simple built-in logic so you
    can see the whole thing work end to end.
  - LLM mode: if you set an API key + URL in the environment, it calls a real
    language model instead. See README.md.

Run it:
    python3 content_agent.py
    python3 content_agent.py --n 5          # show top 5 instead of 3
    python3 content_agent.py --profile profile.json
"""

import argparse
import json
import os
import re
import sys
import urllib.request


# ---------------------------------------------------------------------------
# 0. Tiny helpers
# ---------------------------------------------------------------------------

STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with",
    "is", "are", "was", "be", "as", "at", "by", "it", "this", "that",
    "i", "we", "you", "your", "my", "our", "me", "us", "they", "them",
}


def words(text):
    """Break text into meaningful lowercase words."""
    found = re.findall(r"[a-z0-9]+", text.lower())
    return [w for w in found if w not in STOPWORDS and len(w) > 2]


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# 1. RETRIEVE — pull the past posts that are most relevant to this profile
# ---------------------------------------------------------------------------

def retrieve(profile, library, k=4):
    """
    A dead-simple 'search'. We score each past post by how many words it
    shares with the profile (who you are + what you care about). The top k
    come back. A real system would use embeddings here, but this works and
    has zero dependencies.
    """
    query_words = set(
        words(profile.get("who", ""))
        + words(" ".join(profile.get("audience", [])))
        + words(" ".join(profile.get("goals", [])))
    )

    scored = []
    for item in library:
        post_words = set(words(item.get("title", "") + " " + item.get("text", "")))
        overlap = len(query_words & post_words)
        # Nudge good-performing posts upward so the agent learns from winners.
        performance = item.get("metrics", {}).get("engagement", 0)
        score = overlap + (performance / 1000.0)
        scored.append((score, item))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored[:k]]


# ---------------------------------------------------------------------------
# 2. GENERATE — turn profile + retrieved posts + trends into candidate ideas
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a content strategist. Given a creator's profile,
their past posts, and current trends, suggest content ideas.

Return ONLY a JSON array. Each item must have exactly these keys:
  "title"    : a short, specific idea (not generic)
  "angle"    : one sentence on why it works / what it covers
  "format"   : one of the profile's formats
  "audience" : who it's for

Make each idea specific to this creator. No generic filler."""

DRAFT_SYSTEM_PROMPT = """You are an expert content editor for social media.
Create a useful first draft from the selected idea. Follow the requested
format, audience, voice, and language. Keep technical claims accurate and
avoid inventing statistics, benchmarks, or sources. Return only the draft."""


def build_user_prompt(profile, retrieved, trends):
    return json.dumps(
        {
            "profile": profile,
            "past_posts": [{"title": p["title"], "text": p.get("text", "")} for p in retrieved],
            "current_trends": trends,
            "task": "Suggest 8 content ideas.",
        },
        ensure_ascii=False,
        indent=2,
    )


def generate(profile, retrieved, trends, *, allow_fallback=True):
    """Try a real LLM if configured; otherwise use the built-in mock."""
    api_key = os.environ.get("CONTENT_AGENT_API_KEY")
    api_url = os.environ.get("CONTENT_AGENT_API_URL")
    model = os.environ.get("CONTENT_AGENT_MODEL", "gpt-4o-mini")

    if api_key and api_url:
        try:
            return _call_llm(api_url, api_key, model, profile, retrieved, trends)
        except Exception as exc:  # noqa: BLE001 - fall back rather than crash
            if not allow_fallback:
                raise RuntimeError(f"LLM idea generation failed: {exc}") from exc
            print(f"[note] LLM call failed ({exc}); using built-in mock instead.\n")

    return _mock_generate(profile, retrieved, trends)


def _call_llm(api_url, api_key, model, profile, retrieved, trends):
    """Call any OpenAI-compatible chat endpoint (OpenAI, Sarvam, etc.)."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(profile, retrieved, trends)},
        ],
        "temperature": 0.8,
    }
    req = urllib.request.Request(
        api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    content = body["choices"][0]["message"]["content"]
    return _parse_json_array(content)


def generate_draft(idea, profile, format_name, topic):
    """Create a first draft with the configured model or a local template."""
    api_key = os.environ.get("CONTENT_AGENT_API_KEY")
    api_url = os.environ.get("CONTENT_AGENT_API_URL")
    model = os.environ.get("CONTENT_AGENT_MODEL", "gpt-4o-mini")

    if not api_key or not api_url:
        return _mock_draft(idea, profile, format_name, topic)

    user_prompt = json.dumps(
        {
            "creator": profile,
            "topic": topic,
            "selected_idea": idea,
            "format": format_name,
            "requirements": [
                "Make the opening engaging and specific.",
                "Explain technical concepts for the stated audience.",
                "Use a practical Python example when it fits.",
                "Do not claim unsupported results or include fabricated facts.",
                "End with a natural call to action.",
            ],
        },
        ensure_ascii=False,
        indent=2,
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": DRAFT_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.7,
    }
    req = urllib.request.Request(
        api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return body["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        raise RuntimeError(f"LLM draft generation failed: {exc}") from exc


def _mock_draft(idea, profile, format_name, topic):
    """Provide an editable, structured draft without requiring an API key."""
    title = idea.get("title", topic or "A practical AI concept")
    angle = idea.get("angle", f"Explain {topic} with a practical example.")

    if "carousel" in format_name.lower():
        return (
            f"Slide 1 — {title}\n"
            f"Slide 2 — The simple explanation: {angle}\n"
            "Slide 3 — Why it matters: connect the idea to a real task.\n"
            "Slide 4 — Python example: show a small, runnable example.\n"
            "Slide 5 — Key takeaway: summarize the one thing to remember.\n"
            "Slide 6 — Save this and comment with the next concept to explain.\n\n"
            f"Caption: {title}. Follow along for practical AI and Python "
            "explanations."
        )
    if "caption" in format_name.lower():
        return (
            f"{title}\n\n{angle}\n\n"
            "In this post, we break the idea down and connect it to a small "
            "Python example. Save this for your next build and comment with "
            "the topic you want explained next."
        )
    return (
        f"Hook (0–3s): {title}\n\n"
        f"Explain (3–15s): {angle}\n\n"
        "Demo (15–30s): Show a small Python example on screen. Explain what "
        "goes in, what happens, and what comes out.\n\n"
        "Close: Follow for practical AI and Python. What should we build next?"
    )


def _parse_json_array(text):
    """Models sometimes wrap JSON in prose or code fences. Dig it out."""
    text = text.strip()
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        raise ValueError("model did not return a JSON array")
    return json.loads(text[start:end + 1])


def _mock_generate(profile, retrieved, trends):
    """
    Built-in fallback so the agent runs with no API key. It's not clever —
    it stitches together trends, your voice, and what you've posted before —
    but it proves the whole pipeline works.
    """
    formats = profile.get("formats") or ["post"]
    audience = ", ".join(profile.get("audience", [])) or "your audience"
    past_titles = [p["title"] for p in retrieved]

    ideas = []

    # Turn each topic into distinct, usable directions in the local demo mode.
    for trend in trends:
        topic = trend.strip()
        directions = [
            (f"{topic}: the beginner-friendly explanation",
             f"Explain '{topic}' in plain language, then show one practical example."),
            (f"Build a small Python project with {topic}",
             f"Walk through a small, testable Python example that demonstrates '{topic}'."),
            (f"One common misconception about {topic}",
             f"Correct a common misunderstanding about '{topic}' with a clear example."),
        ]
        for i, (title, angle) in enumerate(directions):
            fmt = formats[i % len(formats)]
            ideas.append({
                "title": title,
                "angle": angle,
                "format": fmt,
                "audience": audience,
            })

    # Ideas that build on what already worked for you.
    for i, title in enumerate(past_titles[:3]):
        fmt = formats[(i + 1) % len(formats)]
        ideas.append({
            "title": f"A follow-up to '{title}'",
            "angle": "Doubles down on a topic your audience already responded to.",
            "format": fmt,
            "audience": audience,
        })

    # A couple of evergreen staples every creator can use.
    ideas.append({
        "title": f"A behind-the-scenes {formats[0]}",
        "angle": "Shows the human side; reliably high engagement.",
        "format": formats[0],
        "audience": audience,
    })
    ideas.append({
        "title": "Answer the question you get asked most",
        "angle": "Directly useful, and easy to make.",
        "format": formats[-1],
        "audience": audience,
    })

    return ideas


# ---------------------------------------------------------------------------
# 3. RANK — put the best ideas on top
# ---------------------------------------------------------------------------

def rank(candidates, profile, library):
    """
    Give every idea a score from three things:
      relevance  — how well it fits your profile
      novelty    — how different it is from what you've already posted
      engagement — a rough guess at how well it'll do
    Higher is better. This is what turns a list into a recommendation.
    """
    profile_words = set(words(json.dumps(profile)))
    existing = [set(words(p.get("title", "") + " " + p.get("text", ""))) for p in library]
    hot_formats = set(profile.get("formats", []))

    ranked = []
    for c in candidates:
        c_words = set(words(c.get("title", "") + " " + c.get("angle", "")))

        relevance = len(profile_words & c_words) / (len(c_words) or 1)

        if existing:
            most_similar = max(len(c_words & e) / (len(c_words) or 1) for e in existing)
            novelty = 1.0 - most_similar
        else:
            novelty = 1.0

        engagement = 0.5
        if c.get("format") in hot_formats:
            engagement += 0.2
        if any(g in " ".join(profile.get("goals", [])).lower()
               for g in ["engagement", "reach", "growth"]):
            engagement += 0.1

        total = 0.4 * relevance + 0.35 * novelty + 0.25 * engagement
        ranked.append((round(total, 3), c))

    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return ranked


# ---------------------------------------------------------------------------
# 4. The main flow — put the pieces together
# ---------------------------------------------------------------------------

def suggest(profile, library, trends, n=3, *, allow_fallback=True):
    retrieved = retrieve(profile, library)
    candidates = generate(
        profile, retrieved, trends, allow_fallback=allow_fallback
    )
    return rank(candidates, profile, library)[:n]


def main():
    parser = argparse.ArgumentParser(description="A small content-suggestion agent.")
    parser.add_argument("--profile", default="profile.json")
    parser.add_argument("--library", default="library.json")
    parser.add_argument("--trends", default="trends.json")
    parser.add_argument("--n", type=int, default=3, help="how many ideas to show")
    args = parser.parse_args()

    try:
        profile = load_json(args.profile)
        library = load_json(args.library)
        trends = load_json(args.trends)
    except FileNotFoundError as exc:
        print(f"Could not find {exc.filename}. Run this from the folder with the .json files.")
        sys.exit(1)

    mode = "LLM" if os.environ.get("CONTENT_AGENT_API_KEY") else "mock (no API key set)"
    print(f"\nContent ideas for: {profile.get('name', 'you')}")
    print(f"Mode: {mode}")
    print("-" * 60)

    results = suggest(profile, library, trends, n=args.n)

    for i, (score, c) in enumerate(results, 1):
        print(f"\n{i}. {c['title']}   [score {score}]")
        print(f"   Why:    {c['angle']}")
        print(f"   Format: {c['format']}  |  For: {c['audience']}")

    print("\n" + "-" * 60)
    print("Tip: change profile.json to 'who you are' and re-run — same agent,")
    print("any kind of creator. That's what makes it broad.\n")


if __name__ == "__main__":
    main()

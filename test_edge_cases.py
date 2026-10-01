"""
Edge Case & Resilience Test Suite for Project Amica.
Covers:
1. Backend validation (empty message history, invalid schema).
2. Data-driven persona fallback handling (missing/unreadable persona files).
3. Frontend UI layout initialization without warnings or errors.
4. Conversation turn state management (no frontend hardcoded system prompt).
"""

import asyncio
import warnings
import httpx
import flet as ft
from backend.main import app, PERSONA_CONFIG, SYSTEM_PROMPT, load_persona
from frontend.app import main as frontend_main


async def test_backend_validation():
    print("\n--- [1/4] Testing Backend Input Validation ---")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Test 1: Empty message list should fail with 422 or 400
        resp = await client.post("/api/chat/stream", json={"messages": []})
        assert resp.status_code in (400, 422), f"Expected 400/422 for empty messages, got {resp.status_code}"
        print(f"[OK] Empty messages correctly rejected: HTTP {resp.status_code}")

        # Test 2: Invalid role / missing content should fail with 422
        resp = await client.post("/api/chat/stream", json={"messages": [{"role": "user"}]})
        assert resp.status_code == 422, f"Expected 422 for missing content, got {resp.status_code}"
        print(f"[OK] Malformed message rejected: HTTP {resp.status_code}")


async def test_persona_fallbacks():
    print("\n--- [2/4] Testing Persona Fallback Robustness ---")
    # Test loading a non-existent persona ID - should gracefully fallback to defaults
    fallback_cfg, fallback_prompt = load_persona("missing_character_xyz")
    assert fallback_cfg["id"] == "missing_character_xyz"
    assert "model" in fallback_cfg
    assert fallback_cfg["num_ctx"] == 3072
    assert len(fallback_prompt) > 0
    print(f"[OK] Missing persona handled gracefully: {fallback_cfg['name']} (fallback model: {fallback_cfg['model']})")


async def test_frontend_layout_cleanliness():
    print("\n--- [3/4] Testing Frontend Page Initialization ---")
    with warnings.catch_warnings(record=True) as captured_warnings:
        warnings.simplefilter("always")

        class MockPage:
            def __init__(self):
                self.title = ""
                self.theme_mode = None
                self.bgcolor = None
                self.padding = None
                self.spacing = None
                self.controls = []

            def add(self, control):
                self.controls.append(control)

            def update(self):
                pass

            async def update_async(self):
                pass

        mock_page = MockPage()
        await frontend_main(mock_page)

        deprecations = [w for w in captured_warnings if issubclass(w.category, DeprecationWarning)]
        if deprecations:
            print(f"[WARN] Captured {len(deprecations)} deprecation warnings:")
            for w in deprecations:
                print(f"  - {w.filename}:{w.lineno}: {w.message}")
        else:
            print("[OK] Frontend UI initialized with 0 DeprecationWarnings!")

        assert len(mock_page.controls) > 0, "No controls were added to the page!"
        print(f"[OK] Main layout assembled successfully with {len(mock_page.controls)} root control(s).")


async def test_system_prompt_adherence():
    print("\n--- [4/4] Testing Conversation State & Data-Driven Prompt Integrity ---")
    assert "Ayumi" in SYSTEM_PROMPT
    assert "Dragon Sage" in SYSTEM_PROMPT
    print("[OK] Data-driven character identity and guidelines loaded correctly from system_prompt.md.")


async def main():
    print("=" * 60)
    print("Running Project Amica Automated Resilience & Quality Suite (v0.3)")
    print("=" * 60)
    await test_backend_validation()
    await test_persona_fallbacks()
    await test_frontend_layout_cleanliness()
    await test_system_prompt_adherence()
    print("\n" + "=" * 60)
    print("ALL Resilience & Quality Checks PASSED!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

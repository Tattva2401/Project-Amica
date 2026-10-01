"""
===============================================================================
Project Amica - Milestone v0.1: The Living Core
===============================================================================
A desktop client built with Flet and Python connecting directly to a local
Ollama instance running `dolphin-llama3:latest`.

Key Architectural Highlights:
1. Split-Pane Layout:
   - Left Stage (35% width): Visual sprite stage placeholder with dark
     contrasting theme (#181825 / #000000) and character info.
   - Right Stage (65% width): Interactive chat interface with scrollable history,
     user message bubbles (accented, right-aligned), Ayumi bubbles (dark gray/blue,
     left-aligned), and bottom input row.
2. Direct Ollama LLM Connection:
   - REST endpoint: `http://localhost:11434/api/chat`
   - Hardcoded context window: `num_ctx = 3072` (derived from M3 benchmark)
   - Personality: Ayumi, the Dragon Sage (witty, sarcastic, tsundere)
3. Asynchronous Streaming & UI Updates:
   - Uses `httpx.AsyncClient` with streaming enabled (`stream: True`)
   - Real-time typewriter effect appending chunks to Markdown control
   - Input lock/unlock during inference to prevent race conditions
4. Compatibility:
   - Supports both `python app.py` and `flet run app.py` across Flet versions.
===============================================================================
"""

import asyncio
import inspect
import json
import flet as ft
import httpx

# =============================================================================
# CROSS-VERSION STYLING ADAPTERS (Flet 0.x vs Flet 1.x)
# =============================================================================
# In Flet 1.0+, styling factories are capitalized classes (Border, BorderRadius, Padding)
Border = getattr(ft, "Border", None)
if not Border or not hasattr(Border, "all"):
    Border = getattr(ft, "border", Border)

BorderRadius = getattr(ft, "BorderRadius", None)
if not BorderRadius or not hasattr(BorderRadius, "only"):
    BorderRadius = getattr(ft, "border_radius", BorderRadius)

Padding = getattr(ft, "Padding", None)
if not Padding or not hasattr(Padding, "symmetric"):
    Padding = getattr(ft, "padding", Padding)

ALIGN_CENTER = getattr(ft.Alignment, "CENTER", getattr(ft.alignment, "center", ft.Alignment(0, 0)))

# =============================================================================
# CONSTANTS & CONFIGURATION
# =============================================================================
OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"
TARGET_MODEL = "dolphin-llama3:latest"
CONTEXT_WINDOW_SIZE = 3072  # Hardcoded based on empirical M3 MacBook Pro 8GB benchmarks

SYSTEM_PROMPT = (
    "You are Ayumi, the Dragon Sage. You are a witty, sharp-tongued, and "
    "tsundere-leaning companion. You speak casually, with dry sarcasm and teasing "
    "insults, but you secretly care. Keep responses concise."
)

# Catppuccin Mocha / Dark Minimal Palette
COLOR_BG_PAGE = "#11111B"       # Deep dark base
COLOR_BG_STAGE = "#181825"      # Contrasting dark surface for sprite stage
COLOR_BG_CARD = "#1e1e2e"       # Card / bubble background
COLOR_BORDER = "#313244"        # Subtle outline
COLOR_ACCENT_USER = "#89b4fa"   # User accent blue
COLOR_USER_BUBBLE = "#313244"   # User message bubble container
COLOR_AYUMI_BUBBLE = "#1e1e2e"  # Ayumi message bubble container
COLOR_AYUMI_ACCENT = "#cba6f7"  # Ayumi label mauve
COLOR_TEXT_PRIMARY = "#cdd6f4"  # Main text
COLOR_TEXT_MUTED = "#6c7086"    # Secondary text
COLOR_ONLINE_GREEN = "#a6e3a1"  # Status green


# =============================================================================
# MAIN APPLICATION LOGIC
# =============================================================================
async def main(page: ft.Page):
    """
    Main Flet application entrypoint. Sets up window dimensions, UI stages,
    message history state, and asynchronous streaming handlers.
    """
    # -------------------------------------------------------------------------
    # 1. Window & Page Settings
    # -------------------------------------------------------------------------
    page.title = "Project Amica - The Living Core (v0.1)"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = COLOR_BG_PAGE
    page.padding = 0
    page.spacing = 0

    # Configure desktop window size: 1000x800 resolution
    if hasattr(page, "window") and page.window is not None:
        page.window.width = 1000
        page.window.height = 800
        page.window.min_width = 800
        page.window.min_height = 600
    elif hasattr(page, "window_width"):
        page.window_width = 1000
        page.window_height = 800
        page.window_min_width = 800
        page.window_min_height = 600

    # Polyfill page.update_async for seamless compatibility across Flet releases
    if not hasattr(page, "update_async"):
        async def _update_async_shim(*args, **kwargs):
            res = page.update(*args, **kwargs)
            if inspect.isawaitable(res):
                await res
        page.update_async = _update_async_shim

    async def focus_control(ctrl):
        if hasattr(ctrl, "focus"):
            res = ctrl.focus()
            if inspect.isawaitable(res):
                await res

    # -------------------------------------------------------------------------
    # 2. Conversation State
    # -------------------------------------------------------------------------
    # Full message history sent to Ollama on each turn
    message_history = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]

    # Flag to prevent multiple concurrent generations
    is_generating = False

    # -------------------------------------------------------------------------
    # 3. Left Stage (35% Width): Visual Sprite Placeholder
    # -------------------------------------------------------------------------
    sprite_stage_card = ft.Container(
        expand=True,
        bgcolor="#11111B",
        border=Border.all(1, COLOR_BORDER),
        border_radius=16,
        padding=24,
        alignment=ALIGN_CENTER,
        content=ft.Column(
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=14,
            controls=[
                # Avatar Icon / Silhouette
                ft.Container(
                    width=90,
                    height=90,
                    border_radius=45,
                    bgcolor="#181825",
                    border=Border.all(2, COLOR_AYUMI_ACCENT),
                    alignment=ALIGN_CENTER,
                    content=ft.Icon(
                        ft.Icons.AUTO_AWESOME_ROUNDED,
                        size=44,
                        color=COLOR_AYUMI_ACCENT,
                    ),
                ),
                # Sprite Stage Placeholder Label
                ft.Text(
                    "[ Sprite Stage ]",
                    size=20,
                    weight=ft.FontWeight.BOLD,
                    color=COLOR_TEXT_PRIMARY,
                ),
                ft.Text(
                    "Live2D / Visual Sprite Placeholder\nReserved for interactive avatar rendering",
                    size=12,
                    color=COLOR_TEXT_MUTED,
                    text_align=ft.TextAlign.CENTER,
                ),
            ],
        ),
    )

    left_stage = ft.Container(
        expand=35,  # 35% horizontal width in split pane
        bgcolor=COLOR_BG_STAGE,
        border=Border.only(right=ft.BorderSide(1, COLOR_BORDER)),
        padding=16,
        content=ft.Column(
            expand=True,
            spacing=16,
            controls=[
                # Character Info Header
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Column(
                            spacing=2,
                            controls=[
                                ft.Text(
                                    "AYUMI",
                                    size=17,
                                    weight=ft.FontWeight.W_800,
                                    color=COLOR_AYUMI_ACCENT,
                                ),
                                ft.Text(
                                    "The Dragon Sage",
                                    size=12,
                                    weight=ft.FontWeight.W_500,
                                    color=COLOR_TEXT_MUTED,
                                ),
                            ],
                        ),
                        # Online Status Badge
                        ft.Container(
                            bgcolor="#1e1e2e",
                            border=Border.all(1, COLOR_BORDER),
                            border_radius=12,
                            padding=Padding.symmetric(horizontal=10, vertical=4),
                            content=ft.Row(
                                spacing=6,
                                alignment=ft.MainAxisAlignment.CENTER,
                                controls=[
                                    ft.Container(
                                        width=8,
                                        height=8,
                                        border_radius=4,
                                        bgcolor=COLOR_ONLINE_GREEN,
                                    ),
                                    ft.Text(
                                        "ONLINE",
                                        size=11,
                                        weight=ft.FontWeight.BOLD,
                                        color=COLOR_ONLINE_GREEN,
                                    ),
                                ],
                            ),
                        ),
                    ],
                ),
                # The Centered Placeholder Box
                sprite_stage_card,
                # Hardware & Runtime Telemetry Card
                ft.Container(
                    bgcolor="#11111B",
                    border=Border.all(1, COLOR_BORDER),
                    border_radius=12,
                    padding=12,
                    content=ft.Column(
                        spacing=4,
                        controls=[
                            ft.Text(
                                "M3 RUNTIME PROFILE",
                                size=10,
                                weight=ft.FontWeight.BOLD,
                                color=COLOR_TEXT_MUTED,
                            ),
                            ft.Row(
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                controls=[
                                    ft.Text("Model:", size=11, color=COLOR_TEXT_MUTED),
                                    ft.Text(TARGET_MODEL, size=11, color=COLOR_TEXT_PRIMARY, weight=ft.FontWeight.W_600),
                                ],
                            ),
                            ft.Row(
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                controls=[
                                    ft.Text("Context:", size=11, color=COLOR_TEXT_MUTED),
                                    ft.Text(f"{CONTEXT_WINDOW_SIZE} tokens", size=11, color=COLOR_TEXT_PRIMARY, weight=ft.FontWeight.W_600),
                                ],
                            ),
                            ft.Row(
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                controls=[
                                    ft.Text("Mode:", size=11, color=COLOR_TEXT_MUTED),
                                    ft.Text("Async Streaming", size=11, color=COLOR_ONLINE_GREEN, weight=ft.FontWeight.W_600),
                                ],
                            ),
                        ],
                    ),
                ),
            ],
        ),
    )

    # -------------------------------------------------------------------------
    # 4. Right Stage (65% Width): Chat Interface
    # -------------------------------------------------------------------------
    # Scrollable list for all messages
    chat_list = ft.ListView(
        expand=True,
        spacing=16,
        padding=20,
        auto_scroll=True,
    )

    # Input controls
    text_input = ft.TextField(
        expand=True,
        hint_text="Speak with Ayumi... (Press Enter to send)",
        hint_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=13),
        text_style=ft.TextStyle(color=COLOR_TEXT_PRIMARY, size=14),
        bgcolor=COLOR_BG_CARD,
        border_color=COLOR_BORDER,
        focused_border_color=COLOR_ACCENT_USER,
        border_radius=12,
        content_padding=Padding.symmetric(horizontal=16, vertical=12),
        multiline=False,
        shift_enter=False,
    )

    send_button = ft.IconButton(
        icon=ft.Icons.SEND_ROUNDED,
        icon_color=COLOR_ACCENT_USER,
        tooltip="Send Message (Enter)",
    )

    progress_indicator = ft.ProgressRing(
        width=18,
        height=18,
        stroke_width=2.5,
        color=COLOR_AYUMI_ACCENT,
        visible=False,
    )

    # -------------------------------------------------------------------------
    # 5. Helper Functions: Message Bubble Builders
    # -------------------------------------------------------------------------
    def create_user_bubble(text: str) -> ft.Control:
        """Constructs an accent-styled, right-aligned bubble for user messages."""
        return ft.Row(
            alignment=ft.MainAxisAlignment.END,
            controls=[
                ft.Container(
                    bgcolor=COLOR_USER_BUBBLE,
                    border=Border.all(1, "#45475a"),
                    border_radius=BorderRadius.only(
                        top_left=16, top_right=4, bottom_left=16, bottom_right=16
                    ),
                    padding=Padding.symmetric(horizontal=16, vertical=12),
                    content=ft.Column(
                        horizontal_alignment=ft.CrossAxisAlignment.END,
                        spacing=4,
                        controls=[
                            ft.Text(
                                "You",
                                size=11,
                                weight=ft.FontWeight.BOLD,
                                color=COLOR_ACCENT_USER,
                            ),
                            ft.Text(
                                text,
                                size=14,
                                color=COLOR_TEXT_PRIMARY,
                                selectable=True,
                            ),
                        ],
                    ),
                ),
            ],
        )

    def create_ayumi_bubble() -> tuple[ft.Control, ft.Markdown]:
        """
        Constructs a dark gray/blue, left-aligned bubble for Ayumi's response.
        Returns the container row and the Markdown control to be updated during streaming.
        """
        markdown_control = ft.Markdown(
            value="",
            selectable=True,
            extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
            code_theme="atom-one-dark",
        )

        bubble_row = ft.Row(
            alignment=ft.MainAxisAlignment.START,
            vertical_alignment=ft.CrossAxisAlignment.START,
            spacing=10,
            controls=[
                # Ayumi Avatar Pip
                ft.Container(
                    width=32,
                    height=32,
                    border_radius=16,
                    bgcolor=COLOR_AYUMI_ACCENT,
                    alignment=ALIGN_CENTER,
                    content=ft.Text(
                        "A",
                        size=14,
                        weight=ft.FontWeight.BOLD,
                        color="#11111B",
                    ),
                ),
                # Message Content Container
                ft.Container(
                    bgcolor=COLOR_AYUMI_BUBBLE,
                    border=Border.all(1, COLOR_BORDER),
                    border_radius=BorderRadius.only(
                        top_left=4, top_right=16, bottom_left=16, bottom_right=16
                    ),
                    padding=Padding.symmetric(horizontal=16, vertical=12),
                    expand=True,
                    content=ft.Column(
                        horizontal_alignment=ft.CrossAxisAlignment.START,
                        spacing=4,
                        controls=[
                            ft.Text(
                                "Ayumi (Dragon Sage)",
                                size=11,
                                weight=ft.FontWeight.BOLD,
                                color=COLOR_AYUMI_ACCENT,
                            ),
                            markdown_control,
                        ],
                    ),
                ),
            ],
        )
        return bubble_row, markdown_control

    # -------------------------------------------------------------------------
    # 6. Asynchronous LLM Streaming Engine
    # -------------------------------------------------------------------------
    async def send_message(_=None):
        """
        Handles sending the user query to the local Ollama instance and
        asynchronously streams response tokens directly to the Flet UI.
        """
        nonlocal is_generating
        user_text = text_input.value.strip()

        # Disallow sending while generation is active or if input is empty
        if not user_text or is_generating:
            return

        is_generating = True

        # 1. Update UI: clear input, show progress, lock input controls
        text_input.value = ""
        text_input.disabled = True
        send_button.disabled = True
        progress_indicator.visible = True

        # 2. Append User Message to UI & state
        chat_list.controls.append(create_user_bubble(user_text))
        message_history.append({"role": "user", "content": user_text})

        # 3. Create Ayumi placeholder bubble in UI
        ayumi_bubble, markdown_control = create_ayumi_bubble()
        chat_list.controls.append(ayumi_bubble)
        await page.update_async()

        # 4. Stream response tokens from Ollama
        accumulated_response = ""
        payload = {
            "model": TARGET_MODEL,
            "messages": message_history,
            "stream": True,
            "options": {
                "num_ctx": CONTEXT_WINDOW_SIZE,
            },
        }

        try:
            # Connect via asynchronous HTTP streaming
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream(
                    "POST",
                    OLLAMA_CHAT_URL,
                    json=payload,
                ) as response:
                    # Validate HTTP status
                    if response.status_code != 200:
                        error_text = await response.aread()
                        accumulated_response = (
                            f"*[Ayumi raises an eyebrow: Ollama error {response.status_code} - "
                            f"{error_text.decode('utf-8', errors='ignore')}]*"
                        )
                        markdown_control.value = accumulated_response
                        await page.update_async()
                    else:
                        # Iterate through newline-delimited JSON chunks
                        async for raw_line in response.aiter_lines():
                            line = raw_line.strip()
                            if not line:
                                continue

                            try:
                                chunk_data = json.loads(line)
                                token = chunk_data.get("message", {}).get("content", "")
                                if token:
                                    accumulated_response += token
                                    markdown_control.value = accumulated_response
                                    # Real-time UI refresh (typewriter effect)
                                    await page.update_async()

                                if chunk_data.get("done", False):
                                    break
                            except json.JSONDecodeError:
                                continue

            # 5. Record final assistant response in history
            if accumulated_response:
                message_history.append({"role": "assistant", "content": accumulated_response})
            else:
                markdown_control.value = "*[Ayumi stays silent, crossing her arms.]*"
                await page.update_async()

        except httpx.ConnectError:
            err_msg = (
                "*[Connection Error: Could not reach Ollama at http://localhost:11434. "
                "Ensure Ollama is running and has dolphin-llama3:latest installed.]*"
            )
            markdown_control.value = err_msg
            await page.update_async()

        except Exception as exc:
            err_msg = f"*[Unexpected Error: {str(exc)}]*"
            markdown_control.value = err_msg
            await page.update_async()

        finally:
            # 6. Restore UI input state
            is_generating = False
            text_input.disabled = False
            send_button.disabled = False
            progress_indicator.visible = False
            await page.update_async()
            await focus_control(text_input)

    # Wire up input trigger events
    text_input.on_submit = send_message
    send_button.on_click = send_message

    # Clear chat callback
    async def clear_chat(_):
        if is_generating:
            return
        chat_list.controls.clear()
        message_history.clear()
        message_history.append({"role": "system", "content": SYSTEM_PROMPT})
        # Add friendly greeting
        greeting_bubble, greeting_md = create_ayumi_bubble()
        greeting_md.value = (
            "Well, what do you want? Don't just stand there looking lost. "
            "I'm listening, so make it quick."
        )
        chat_list.controls.append(greeting_bubble)
        message_history.append({"role": "assistant", "content": greeting_md.value})
        await page.update_async()

    # Initial Welcome message from Ayumi
    initial_bubble, initial_md = create_ayumi_bubble()
    initial_md.value = (
        "Hmph. You actually managed to boot up the system? Color me surprised. "
        "I'm Ayumi. Ask whatever you need, but don't expect me to hold your hand."
    )
    chat_list.controls.append(initial_bubble)
    message_history.append({"role": "assistant", "content": initial_md.value})

    # -------------------------------------------------------------------------
    # 7. Right Stage Construction
    # -------------------------------------------------------------------------
    right_stage = ft.Container(
        expand=65,  # 65% horizontal width in split pane
        bgcolor=COLOR_BG_PAGE,
        content=ft.Column(
            expand=True,
            spacing=0,
            controls=[
                # Top App Bar for Chat Pane
                ft.Container(
                    bgcolor=COLOR_BG_STAGE,
                    border=Border.only(bottom=ft.BorderSide(1, COLOR_BORDER)),
                    padding=Padding.symmetric(horizontal=20, vertical=12),
                    content=ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Row(
                                spacing=10,
                                controls=[
                                    ft.Icon(ft.Icons.CHAT_BUBBLE_OUTLINE_ROUNDED, size=20, color=COLOR_ACCENT_USER),
                                    ft.Text(
                                        "Live Interaction Channel",
                                        size=14,
                                        weight=ft.FontWeight.W_600,
                                        color=COLOR_TEXT_PRIMARY,
                                    ),
                                ],
                            ),
                            ft.Row(
                                spacing=8,
                                controls=[
                                    ft.IconButton(
                                        icon=ft.Icons.REFRESH_ROUNDED,
                                        icon_color=COLOR_TEXT_MUTED,
                                        tooltip="Reset Conversation",
                                        on_click=clear_chat,
                                    ),
                                ],
                            ),
                        ],
                    ),
                ),
                # Scrollable Chat History
                ft.Container(
                    expand=True,
                    content=chat_list,
                ),
                # Bottom Input Container
                ft.Container(
                    bgcolor=COLOR_BG_STAGE,
                    border=Border.only(top=ft.BorderSide(1, COLOR_BORDER)),
                    padding=Padding.symmetric(horizontal=16, vertical=12),
                    content=ft.Row(
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=10,
                        controls=[
                            progress_indicator,
                            text_input,
                            send_button,
                        ],
                    ),
                ),
            ],
        ),
    )

    # -------------------------------------------------------------------------
    # 8. Main Split-Pane Layout Assembly
    # -------------------------------------------------------------------------
    main_layout = ft.Row(
        expand=True,
        spacing=0,
        controls=[
            left_stage,   # 35%
            right_stage,  # 65%
        ],
    )

    page.add(main_layout)
    await page.update_async()
    await focus_control(text_input)


# =============================================================================
# ENTRY POINT
# =============================================================================
# Ensure compatibility with `python app.py` and `flet run app.py` across Flet versions.
if not hasattr(ft, "app") and hasattr(ft, "run"):
    # Alias ft.app to ft.run for legacy CLI runners
    ft.app = ft.run

if __name__ == "__main__":
    if hasattr(ft, "run"):
        ft.run(main)
    elif hasattr(ft, "app"):
        ft.app(target=main)

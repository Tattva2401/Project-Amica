"""
===============================================================================
Project Amica - Milestone v0.2: Decoupled Flet Desktop Client
===============================================================================
A desktop client built with Flet and Python serving as the "Face" of
Project Amica. It connects to the local FastAPI "Brain" service.

Key Architectural Highlights:
1. Split-Pane Layout (Preserved from v0.1):
   - Left Stage (35% width): Visual sprite stage placeholder with dark
     contrasting theme (#181825), character info, and system telemetry.
   - Right Stage (65% width): Interactive chat interface with scrollable history,
     user message bubbles (accented, right-aligned), Ayumi bubbles (dark gray/blue,
     left-aligned), and bottom input row.
2. Decoupled Network Architecture:
   - Backend Endpoint: `http://127.0.0.1:8000/api/chat/stream`
   - Relies on FastAPI to communicate with Ollama and enforce generation parameters.
3. System Prompt & Personality:
   - Ayumi, the Dragon Sage: "You are Ayumi, the Dragon Sage. You are witty,
     sharp-tongued, and tsundere-leaning. Keep responses between 2 to 4 sentences.
     Be punchy, but elaborate when offering comfort or roasting the user's logic."
4. Asynchronous Streaming:
   - Uses `httpx.AsyncClient` streaming against the FastAPI backend.
   - Iterates through `response.aiter_text()` with real-time UI typewriter effect.
   - Disables input field during active generation to prevent state races.
===============================================================================
"""

import asyncio
import inspect
import flet as ft
import httpx

# =============================================================================
# CROSS-VERSION STYLING ADAPTERS (Flet 0.x vs Flet 1.x)
# =============================================================================
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
BACKEND_STREAM_URL = "http://127.0.0.1:8000/api/chat/stream"

# Specified v0.2 System Prompt
SYSTEM_PROMPT = (
    "You are Ayumi, the Dragon Sage. You are witty, sharp-tongued, and "
    "tsundere-leaning. Keep responses between 2 to 4 sentences. "
    "Be punchy, but elaborate when offering comfort or roasting the user's logic."
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
    Main Flet application entrypoint. Sets up the split-pane desktop interface,
    maintains conversation history with system prompt injection, and manages
    asynchronous streaming from the FastAPI backend.
    """
    # -------------------------------------------------------------------------
    # 1. Window & Page Settings
    # -------------------------------------------------------------------------
    page.title = "Project Amica - The Living Core (v0.2 Decoupled)"
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
        """Safely awaits control focus across sync and async Flet versions."""
        try:
            if hasattr(ctrl, "focus"):
                res = ctrl.focus()
                if inspect.isawaitable(res):
                    await res
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # 2. Conversation State Management
    # -------------------------------------------------------------------------
    # System prompt is prepended at the root of the history list
    message_history = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]

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
                # Centered Sprite Stage Placeholder
                sprite_stage_card,
                # Decoupled Architecture Telemetry Card
                ft.Container(
                    bgcolor="#11111B",
                    border=Border.all(1, COLOR_BORDER),
                    border_radius=12,
                    padding=12,
                    content=ft.Column(
                        spacing=4,
                        controls=[
                            ft.Text(
                                "SYSTEM ARCHITECTURE (v0.2)",
                                size=10,
                                weight=ft.FontWeight.BOLD,
                                color=COLOR_TEXT_MUTED,
                            ),
                            ft.Row(
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                controls=[
                                    ft.Text("Backend:", size=11, color=COLOR_TEXT_MUTED),
                                    ft.Text("FastAPI (8000)", size=11, color=COLOR_TEXT_PRIMARY, weight=ft.FontWeight.W_600),
                                ],
                            ),
                            ft.Row(
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                controls=[
                                    ft.Text("Model:", size=11, color=COLOR_TEXT_MUTED),
                                    ft.Text("dolphin-llama3", size=11, color=COLOR_TEXT_PRIMARY, weight=ft.FontWeight.W_600),
                                ],
                            ),
                            ft.Row(
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                controls=[
                                    ft.Text("Context / Predict:", size=11, color=COLOR_TEXT_MUTED),
                                    ft.Text("3072 / 200 ctx", size=11, color=COLOR_TEXT_PRIMARY, weight=ft.FontWeight.W_600),
                                ],
                            ),
                            ft.Row(
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                controls=[
                                    ft.Text("Stream Channel:", size=11, color=COLOR_TEXT_MUTED),
                                    ft.Text("HTTP Streaming", size=11, color=COLOR_ONLINE_GREEN, weight=ft.FontWeight.W_600),
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
    chat_list = ft.ListView(
        expand=True,
        spacing=16,
        padding=20,
        auto_scroll=True,
    )

    border_default = ft.OutlineInputBorder(
        border_radius=12,
        side=ft.BorderSide(1, COLOR_BORDER),
    )
    border_focused = ft.OutlineInputBorder(
        border_radius=12,
        side=ft.BorderSide(1, COLOR_ACCENT_USER),
    )

    text_input = ft.TextField(
        expand=True,
        hint_text="Speak with Ayumi... (Press Enter to send)",
        hint_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=13),
        text_style=ft.TextStyle(color=COLOR_TEXT_PRIMARY, size=14),
        bgcolor=COLOR_BG_CARD,
        border={
            ft.ControlState.DEFAULT: border_default,
            ft.ControlState.FOCUSED: border_focused,
        },
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
        Returns the container row and the Markdown control to update during streaming.
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

    async def scroll_to_bottom():
        """Safely scrolls the chat viewport to the newest message."""
        try:
            if hasattr(chat_list, "scroll_to"):
                res = chat_list.scroll_to(offset=-1, duration=0)
                if inspect.isawaitable(res):
                    await res
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # 6. Asynchronous Streaming Engine via FastAPI Backend
    # -------------------------------------------------------------------------
    async def send_message(_=None):
        """
        Submits the conversation history to the FastAPI backend service
        and asynchronously streams incoming tokens into the chat interface.
        """
        nonlocal is_generating
        user_text = text_input.value.strip()

        # Prevent sending empty text or concurrent requests
        if not user_text or is_generating:
            return

        is_generating = True

        # 1. Update UI: lock inputs and show activity indicator
        text_input.value = ""
        text_input.disabled = True
        send_button.disabled = True
        progress_indicator.visible = True

        # 2. Append user message to UI and history state
        chat_list.controls.append(create_user_bubble(user_text))
        message_history.append({"role": "user", "content": user_text})

        # 3. Create placeholder bubble for Ayumi
        ayumi_bubble, markdown_control = create_ayumi_bubble()
        chat_list.controls.append(ayumi_bubble)
        await page.update_async()
        await scroll_to_bottom()

        # 4. Ensure system prompt is explicitly prepended at index 0
        outgoing_messages = list(message_history)
        if not outgoing_messages or outgoing_messages[0].get("role") != "system":
            outgoing_messages.insert(0, {"role": "system", "content": SYSTEM_PROMPT})
        else:
            outgoing_messages[0] = {"role": "system", "content": SYSTEM_PROMPT}

        accumulated_response = ""
        request_payload = {
            "messages": outgoing_messages
        }
        has_error = False

        try:
            # Query decoupled FastAPI backend
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    BACKEND_STREAM_URL,
                    json=request_payload,
                ) as response:
                    # Validate HTTP status from backend
                    if response.status_code != 200:
                        has_error = True
                        error_text = await response.aread()
                        accumulated_response = (
                            f"*[Ayumi narrows her eyes: Backend service error ({response.status_code}) - "
                            f"{error_text.decode('utf-8', errors='ignore')}]*"
                        )
                        markdown_control.value = accumulated_response
                        await page.update_async()
                        await scroll_to_bottom()
                    else:
                        # Iterate through raw text token chunks
                        async for chunk in response.aiter_text():
                            if chunk:
                                accumulated_response += chunk
                                markdown_control.value = accumulated_response
                                # Real-time typewriter UI refresh and auto-scroll
                                await page.update_async()
                                await scroll_to_bottom()

                        # Check if backend relayed an internal Ollama/connection error
                        if accumulated_response.startswith("[Backend Error:") or accumulated_response.startswith("[Ollama Error:"):
                            has_error = True

            # Record final valid response in client history (skip recording errors)
            if accumulated_response and not has_error:
                message_history.append({"role": "assistant", "content": accumulated_response})
            elif not accumulated_response and not has_error:
                markdown_control.value = "*[Ayumi scoffs quietly, offering no reply.]*"
                await page.update_async()
                await scroll_to_bottom()

        except httpx.ConnectError:
            err_msg = (
                "*[Connection Error: Could not connect to Project Amica backend at http://127.0.0.1:8000. "
                "Ensure the FastAPI service is running via `python run.py`.]*"
            )
            markdown_control.value = err_msg
            if message_history and message_history[-1].get("role") == "user":
                message_history.pop()
            await page.update_async()
            await scroll_to_bottom()

        except Exception as exc:
            err_msg = f"*[Unexpected Client Error: {str(exc)}]*"
            markdown_control.value = err_msg
            if message_history and message_history[-1].get("role") == "user":
                message_history.pop()
            await page.update_async()
            await scroll_to_bottom()

        finally:
            # Restore interactive UI controls
            is_generating = False
            text_input.disabled = False
            send_button.disabled = False
            progress_indicator.visible = False
            await page.update_async()
            await focus_control(text_input)

    # Wire up input triggers
    text_input.on_submit = send_message
    send_button.on_click = send_message

    # Reset conversation callback
    async def clear_chat(_):
        if is_generating:
            return
        chat_list.controls.clear()
        message_history.clear()
        message_history.append({"role": "system", "content": SYSTEM_PROMPT})
        
        greeting_bubble, greeting_md = create_ayumi_bubble()
        greeting_md.value = (
            "Reset already? Fine by me. Just don't waste my time with boring questions."
        )
        chat_list.controls.append(greeting_bubble)
        message_history.append({"role": "assistant", "content": greeting_md.value})
        await page.update_async()

    # Initial Welcome message from Ayumi
    initial_bubble, initial_md = create_ayumi_bubble()
    initial_md.value = (
        "Hmph. You actually got the decoupled architecture online? Not bad for an amateur. "
        "I'm Ayumi. Ask what you need, but keep it brief—I don't have all day."
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
                                        "Live Interaction Channel (Decoupled)",
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
if not hasattr(ft, "app") and hasattr(ft, "run"):
    ft.app = ft.run

if __name__ == "__main__":
    if hasattr(ft, "run"):
        ft.run(main)
    elif hasattr(ft, "app"):
        ft.app(target=main)

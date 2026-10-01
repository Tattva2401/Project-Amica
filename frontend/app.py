"""
===============================================================================
Project Amica - Milestone v0.3: Data-Driven Desktop Client
===============================================================================
A desktop client built with Flet and Python serving as the "Face" of
Project Amica. It connects to the local FastAPI "Brain" service.

Key Architectural Highlights for v0.3:
1. Split-Pane Layout:
   - Left Stage (35% width): Visual sprite stage placeholder, dynamic persona info,
     and runtime architecture telemetry.
   - Right Stage (65% width): Interactive chat interface with scrollable history,
     typewriter streaming, and auto-scrolling viewport.
2. Data-Driven Persona Decoupling:
   - Frontend stores NO hardcoded system prompts in `message_history`.
   - Sends strictly user and assistant turns, delegating persona enforcement to the backend.
   - Dynamically polls `/api/persona` on launch to display the active character name,
     title, model, and context parameters.
3. Asynchronous Streaming:
   - Queries `http://127.0.0.1:8000/api/chat/stream` with httpx.
   - Renders tokens in real time with auto-scroll and input locking.
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
BACKEND_PERSONA_URL = "http://127.0.0.1:8000/api/persona"
BACKEND_HEALTH_URL = "http://127.0.0.1:8000/health"

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
    queries dynamic persona data from the FastAPI backend, and manages asynchronous
    streaming.
    """
    # -------------------------------------------------------------------------
    # 1. Window & Page Settings
    # -------------------------------------------------------------------------
    page.title = "Project Amica - Ayumi (v0.3 Data-Driven)"
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
    # 2. Conversation State Management (v0.3: Zero Hardcoded System Prompts)
    # -------------------------------------------------------------------------
    # Message history only stores conversational turns (user / assistant).
    # The backend injects the declarative persona system prompt on each request.
    message_history: list[dict[str, str]] = []

    # Dynamic character state (polled from backend)
    active_persona = {
        "id": "ayumi",
        "name": "Ayumi",
        "model": "dolphin-llama3:latest",
        "num_ctx": 3072,
        "num_predict": 200,
    }
    is_generating = False

    # -------------------------------------------------------------------------
    # 3. Dynamic UI Controls & Left Stage (35% Width)
    # -------------------------------------------------------------------------
    char_name_text = ft.Text(
        active_persona["name"].upper(),
        size=17,
        weight=ft.FontWeight.W_800,
        color=COLOR_AYUMI_ACCENT,
    )
    char_title_text = ft.Text(
        "Data-Driven Persona",
        size=12,
        weight=ft.FontWeight.W_500,
        color=COLOR_TEXT_MUTED,
    )
    chat_header_text = ft.Text(
        f"Live Interaction Channel ({active_persona['name']})",
        size=14,
        weight=ft.FontWeight.W_600,
        color=COLOR_TEXT_PRIMARY,
    )
    telemetry_model_text = ft.Text(
        active_persona["model"].split(":")[0],
        size=11,
        color=COLOR_TEXT_PRIMARY,
        weight=ft.FontWeight.W_600,
    )
    telemetry_ctx_text = ft.Text(
        f"{active_persona['num_ctx']} / {active_persona['num_predict']} ctx",
        size=11,
        color=COLOR_TEXT_PRIMARY,
        weight=ft.FontWeight.W_600,
    )

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
                # Dynamic Character Info Header
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Column(
                            spacing=2,
                            controls=[
                                char_name_text,
                                char_title_text,
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
                # Decoupled Architecture & Persona Telemetry Card
                ft.Container(
                    bgcolor="#11111B",
                    border=Border.all(1, COLOR_BORDER),
                    border_radius=12,
                    padding=12,
                    content=ft.Column(
                        spacing=4,
                        controls=[
                            ft.Text(
                                "DATA-DRIVEN PERSONA (v0.3)",
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
                                    telemetry_model_text,
                                ],
                            ),
                            ft.Row(
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                controls=[
                                    ft.Text("Context / Predict:", size=11, color=COLOR_TEXT_MUTED),
                                    telemetry_ctx_text,
                                ],
                            ),
                            ft.Row(
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                controls=[
                                    ft.Text("Config Source:", size=11, color=COLOR_TEXT_MUTED),
                                    ft.Text("persona.yaml", size=11, color=COLOR_ONLINE_GREEN, weight=ft.FontWeight.W_600),
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
    # 5. Helper Functions: Message Bubble Builders & Auto-Scroll
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

    def create_persona_bubble(persona_name: str = "Ayumi") -> tuple[ft.Control, ft.Markdown]:
        """
        Constructs a styled, left-aligned bubble for the persona's response.
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
                # Persona Avatar Pip
                ft.Container(
                    width=32,
                    height=32,
                    border_radius=16,
                    bgcolor=COLOR_AYUMI_ACCENT,
                    alignment=ALIGN_CENTER,
                    content=ft.Text(
                        persona_name[0].upper() if persona_name else "A",
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
                                persona_name,
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
        Submits conversational turns (user/assistant only) to the FastAPI backend.
        The backend injects the persona system prompt and streams incoming tokens.
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

        # 2. Append user message to UI and history state (no system prompt!)
        chat_list.controls.append(create_user_bubble(user_text))
        message_history.append({"role": "user", "content": user_text})

        # 3. Create placeholder bubble for the persona
        p_name = active_persona.get("name", "Ayumi")
        persona_bubble, markdown_control = create_persona_bubble(p_name)
        chat_list.controls.append(persona_bubble)
        await page.update_async()
        await scroll_to_bottom()

        accumulated_response = ""
        request_payload = {
            "messages": list(message_history)
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
                            f"*[{p_name} narrows her eyes: Backend service error ({response.status_code}) - "
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

                        # Check if backend relayed an internal Ollama error
                        if accumulated_response.startswith("[Backend Error:") or accumulated_response.startswith("[Ollama Error:"):
                            has_error = True

            # Record final valid response in client history (skip recording errors)
            if accumulated_response and not has_error:
                message_history.append({"role": "assistant", "content": accumulated_response})
            elif not accumulated_response and not has_error:
                markdown_control.value = f"*[{p_name} scoffs quietly, offering no reply.]*"
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
        
        p_name = active_persona.get("name", "Ayumi")
        greeting_bubble, greeting_md = create_persona_bubble(p_name)
        greeting_md.value = (
            f"Reset already? Fine by me. Just don't waste my time with boring questions."
        )
        chat_list.controls.append(greeting_bubble)
        message_history.append({"role": "assistant", "content": greeting_md.value})
        await page.update_async()

    # Initial Welcome message
    initial_bubble, initial_md = create_persona_bubble(active_persona.get("name", "Ayumi"))
    initial_md.value = (
        f"Hmph. You loaded the data-driven persona configuration? Not bad for an amateur. "
        f"I'm {active_persona.get('name', 'Ayumi')}. Ask what you need, but keep it brief."
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
                                    chat_header_text,
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

    # -------------------------------------------------------------------------
    # 9. Asynchronously Query Backend Persona Info to Reflect Dynamic Config
    # -------------------------------------------------------------------------
    async def sync_persona_metadata():
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                res = await client.get(BACKEND_PERSONA_URL)
                if res.status_code == 200:
                    data = res.json()
                    name = data.get("name", "Ayumi")
                    model = data.get("model", "dolphin-llama3:latest")
                    num_ctx = data.get("num_ctx", 3072)
                    num_predict = data.get("num_predict", 200)

                    active_persona.update(data)
                    char_name_text.value = name.upper()
                    chat_header_text.value = f"Live Interaction Channel ({name})"
                    page.title = f"Project Amica - {name} (v0.3 Data-Driven)"
                    telemetry_model_text.value = model.split(":")[0]
                    telemetry_ctx_text.value = f"{num_ctx} / {num_predict} ctx"
                    text_input.hint_text = f"Speak with {name}... (Press Enter to send)"
                    await page.update_async()
        except Exception:
            # Backend not reachable yet or offline; fallback defaults preserved
            pass

    asyncio.create_task(sync_persona_metadata())


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

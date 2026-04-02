"""Muninn UI — Terminal Widget.

B-UI-19: Terminal basique (QTextEdit + QLineEdit, history, Ctrl+L, flash).
B-UI-20: LLM connection (QThread, streaming, breathing indicator, stop).
B-UI-21: Multi-provider AI (Claude/GPT/Ollama/Off) + config + mycelium boost.

Rules: R1 (ownership), R3 (worker pattern), R5 (repaint throttle),
R8 (empty state), bug #61 (maxBlockCount 5000), bug #20 (no QMessageBox in slot).
"""

import time
from typing import Optional

from PyQt6.QtCore import (
    Qt, QTimer, QThread, QPropertyAnimation, QEasingCurve,
    pyqtSignal, QObject,
)
from PyQt6.QtGui import (
    QFont, QColor, QTextCursor, QTextCharFormat, QPalette,
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QLineEdit,
    QPushButton, QLabel, QGraphicsOpacityEffect, QComboBox,
)

from muninn.ui.theme import (
    BG_1DP, BG_2DP, ACCENT_CYAN_HEX, ACCENT_GREEN, TEXT_PRIMARY,
    TEXT_SECONDARY, FONT_CODE, FONT_BODY,
)
from muninn.ui.ai_config import (
    PROVIDERS, load_config, save_config,
    get_active_provider, set_active_provider,
    get_active_model, set_active_model,
    get_api_key, set_api_key,
    get_mycelium_boost, set_mycelium_boost,
    create_provider,
)


class LLMWorker(QObject):
    """Background worker for LLM API calls (R3, B-UI-20, B-UI-21).

    Uses LLMProvider.stream() for real streaming across all providers.
    Falls back to echo mode if provider is None/off.
    """

    chunk_ready = pyqtSignal(str)   # One chunk of text
    route_info = pyqtSignal(str)   # Which model was picked (smart router)
    full_response = pyqtSignal(str) # Complete response (for mycelium boost)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, prompt: str, context: str = "",
                 provider=None):
        super().__init__()
        self._stop = False
        self._prompt = prompt
        self._context = context
        self._provider = provider

    def run(self):
        """Execute LLM call via provider streaming."""
        try:
            if self._provider is None:
                self.chunk_ready.emit(f"[echo] {self._prompt}\n")
                self.chunk_ready.emit("(Configure a provider: /provider claude|openai|ollama)")
                self.full_response.emit(f"[echo] {self._prompt}")
                self.finished.emit()
                return

            system = self._context or "You are Muninn, a memory compression assistant. Answer concisely in the user's language."

            # Emit route info for smart router
            if hasattr(self._provider, 'last_route'):
                from muninn.ui.ai_router import pick_model, get_route_label
                model = pick_model(self._prompt)
                self.route_info.emit(get_route_label(model))

            chunks = []
            try:
                for text in self._provider.stream(
                    self._prompt, system=system,
                    max_tokens=1024, temperature=0.3,
                ):
                    if self._stop:
                        return
                    self.chunk_ready.emit(text)
                    chunks.append(text)
            except Exception as e:
                self.error.emit(str(e))
                return

            self.full_response.emit("".join(chunks))
            self.finished.emit()

        except Exception as e:
            self.error.emit(str(e))


class TerminalWidget(QWidget):
    """Terminal panel with command input, history, and multi-provider LLM.

    B-UI-19: basic terminal (history, Ctrl+L, flash, maxBlockCount).
    B-UI-20: LLM streaming with breathing indicator and stop button.
    B-UI-21: Provider selector dropdown, /config, /provider commands, mycelium boost.
    """

    command_entered = pyqtSignal(str)  # Raw command text

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(200, 150)
        self.setAccessibleName("Terminal")

        # History
        self._history: list[str] = []
        self._history_pos = -1

        # LLM state
        self._llm_thread: Optional[QThread] = None
        self._llm_worker: Optional[LLMWorker] = None
        self._context: str = ""

        # Current prompt (for mycelium boost)
        self._current_prompt: str = ""

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # Provider toolbar (B-UI-21)
        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)

        ai_label = QLabel("AI:")
        ai_label.setFont(QFont(FONT_CODE, 10))
        ai_label.setStyleSheet(f"color: {TEXT_SECONDARY};")
        toolbar.addWidget(ai_label)

        self._provider_combo = QComboBox()
        self._provider_combo.setFont(QFont(FONT_CODE, 10))
        _combo_ss = (
            f"QComboBox {{ background: {BG_1DP}; color: {TEXT_PRIMARY}; "
            f"border: 1px solid rgba(255,255,255,0.08); border-radius: 4px; "
            f"padding: 2px 8px; min-width: 100px; }}"
            f"QComboBox::drop-down {{ border: none; }}"
        )
        self._provider_combo.setStyleSheet(_combo_ss)
        self._style_combo_popup(self._provider_combo)
        for key, info in PROVIDERS.items():
            self._provider_combo.addItem(info["label"], key)
        # Set current from config
        current = get_active_provider()
        for i in range(self._provider_combo.count()):
            if self._provider_combo.itemData(i) == current:
                self._provider_combo.setCurrentIndex(i)
                break
        self._provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        toolbar.addWidget(self._provider_combo)

        # Model selector
        self._model_combo = QComboBox()
        self._model_combo.setFont(QFont(FONT_CODE, 10))
        self._model_combo.setStyleSheet(
            f"QComboBox {{ background: {BG_1DP}; color: {TEXT_PRIMARY}; "
            f"border: 1px solid rgba(255,255,255,0.08); border-radius: 4px; "
            f"padding: 2px 8px; min-width: 140px; }}"
            f"QComboBox::drop-down {{ border: none; }}"
        )
        self._style_combo_popup(self._model_combo)
        self._model_combo.currentIndexChanged.connect(self._on_model_changed)
        toolbar.addWidget(self._model_combo)
        self._refresh_models()

        # Status dot — green=connected, red=no key, grey=off
        self._status_dot = QLabel("\u2022")
        self._status_dot.setFont(QFont(FONT_BODY, 16))
        toolbar.addWidget(self._status_dot)
        self._update_status_dot()

        toolbar.addStretch()
        layout.addLayout(toolbar)

        # Output area
        self._output = QTextEdit()
        self._output.setReadOnly(True)
        self._output.setFont(QFont(FONT_CODE, 12))
        self._output.setStyleSheet(
            f"QTextEdit {{ background: {BG_1DP}; color: {ACCENT_GREEN}; "
            f"border: 1px solid rgba(255,255,255,0.06); border-radius: 8px; "
            f"padding: 8px; }}"
        )
        self._output.document().setMaximumBlockCount(5000)  # bug #61
        layout.addWidget(self._output, 1)

        # Breathing indicator (B-UI-20)
        self._breathing = QLabel("\u2022")  # dot
        self._breathing.setFont(QFont(FONT_BODY, 20))
        self._breathing.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._breathing.setStyleSheet(f"color: {ACCENT_CYAN_HEX};")
        self._breathing.setFixedHeight(24)
        self._breathing.hide()

        self._breath_effect = QGraphicsOpacityEffect(self._breathing)
        self._breath_effect.setOpacity(1.0)
        self._breathing.setGraphicsEffect(self._breath_effect)

        self._breath_anim = QPropertyAnimation(self._breath_effect, b"opacity", self)
        self._breath_anim.setDuration(2000)
        self._breath_anim.setStartValue(0.4)
        self._breath_anim.setEndValue(1.0)
        self._breath_anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._breath_anim.setLoopCount(-1)  # Infinite loop

        layout.addWidget(self._breathing)

        # Input area
        input_layout = QHBoxLayout()
        input_layout.setSpacing(4)

        self._prompt_label = QLabel(">")
        self._prompt_label.setFont(QFont(FONT_CODE, 12))
        self._prompt_label.setStyleSheet(f"color: {ACCENT_CYAN_HEX};")
        input_layout.addWidget(self._prompt_label)

        self._input = QLineEdit()
        self._input.setFont(QFont(FONT_CODE, 12))
        self._input.setPlaceholderText("Type a command or ask a question...")
        self._input.setStyleSheet(
            f"QLineEdit {{ background: {BG_1DP}; color: {TEXT_PRIMARY}; "
            f"border: 1px solid rgba(255,255,255,0.06); border-radius: 8px; "
            f"padding: 8px; }}"
        )
        self._input.returnPressed.connect(self._on_enter)
        input_layout.addWidget(self._input, 1)

        # Stop button (B-UI-20)
        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setStyleSheet(
            f"QPushButton {{ background: rgba(239,68,68,0.2); color: #EF4444; "
            f"border: 1px solid #EF4444; border-radius: 8px; padding: 4px 12px; }}"
        )
        self._stop_btn.clicked.connect(self._stop_llm)
        self._stop_btn.hide()
        input_layout.addWidget(self._stop_btn)

        layout.addLayout(input_layout)

        # Flash timer for input line
        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.setInterval(150)
        self._flash_timer.timeout.connect(self._flash_reset)

    # --- Combo popup fix (Windows ignores QSS on popup) ---

    def _style_combo_popup(self, combo: QComboBox):
        """Force dark theme on QComboBox popup via QPalette (Windows fix).

        UX: popup must appear directly below the combo, same width or wider.
        On Windows, stylesheet alone doesn't work on the popup — must use palette.
        Do NOT touch window flags — breaks native positioning.
        """
        bg = QColor(BG_1DP)
        fg = QColor(TEXT_PRIMARY)
        hl = QColor(255, 255, 255, 25)

        # Style the view (list inside popup)
        view = combo.view()
        pal = view.palette()
        pal.setColor(QPalette.ColorRole.Base, bg)
        pal.setColor(QPalette.ColorRole.Window, bg)
        pal.setColor(QPalette.ColorRole.Text, fg)
        pal.setColor(QPalette.ColorRole.WindowText, fg)
        pal.setColor(QPalette.ColorRole.Highlight, hl)
        pal.setColor(QPalette.ColorRole.HighlightedText, fg)
        view.setPalette(pal)

        # Style the popup container (the frame around the list)
        container = view.parentWidget()
        if container:
            cpal = container.palette()
            cpal.setColor(QPalette.ColorRole.Window, bg)
            cpal.setColor(QPalette.ColorRole.Base, bg)
            container.setPalette(cpal)
            container.setStyleSheet(
                f"background: {BG_1DP}; border: 1px solid rgba(255,255,255,0.1);"
            )

    # --- Provider UI ---

    def _on_provider_changed(self, index: int):
        """User changed provider in dropdown."""
        name = self._provider_combo.itemData(index)
        if name:
            set_active_provider(name)
            self._refresh_models()
            self._update_status_dot()
            pinfo = PROVIDERS.get(name, {})
            self._append_text(f"[AI] Provider: {pinfo.get('label', name)}", color=ACCENT_CYAN_HEX)
            if pinfo.get("needs_key") and not get_api_key(name):
                self._append_text(
                    f"  API key needed. Use: /key {name} sk-your-key-here",
                    color="#F59E0B",
                )

    def _on_model_changed(self, index: int):
        """User changed model in dropdown."""
        model = self._model_combo.currentText()
        provider = get_active_provider()
        if model and provider != "off":
            set_active_model(provider, model)

    def _refresh_models(self):
        """Populate model combo for current provider."""
        self._model_combo.blockSignals(True)
        self._model_combo.clear()
        provider = get_active_provider()
        pinfo = PROVIDERS.get(provider, {})
        models = pinfo.get("models", [])

        if provider == "ollama":
            # Try to detect live Ollama models
            try:
                p = create_provider("ollama")
                if p:
                    live = p.list_models()
                    if live:
                        models = live
            except Exception:
                pass

        for m in models:
            self._model_combo.addItem(m)

        # Set current
        current = get_active_model()
        idx = self._model_combo.findText(current)
        if idx >= 0:
            self._model_combo.setCurrentIndex(idx)

        self._model_combo.setVisible(provider not in ("off", "ollama-smart"))
        self._model_combo.blockSignals(False)

    def _update_status_dot(self):
        """Update status dot color based on provider readiness."""
        provider = get_active_provider()
        if provider == "off":
            self._status_dot.setStyleSheet("color: #666;")
            self._status_dot.setToolTip("AI off")
        elif PROVIDERS.get(provider, {}).get("needs_key") and not get_api_key(provider):
            self._status_dot.setStyleSheet("color: #EF4444;")
            self._status_dot.setToolTip(f"No API key for {provider}")
        elif provider in ("ollama", "ollama-smart"):
            # Check if Ollama is actually running
            try:
                from muninn.ui.ai_router import get_available_models
                models = get_available_models()
                if models:
                    self._status_dot.setStyleSheet("color: #32CD32;")
                    self._status_dot.setToolTip(f"{provider} ready ({len(models)} models)")
                else:
                    self._status_dot.setStyleSheet("color: #EF4444;")
                    self._status_dot.setToolTip("Ollama: no models installed")
            except Exception:
                self._status_dot.setStyleSheet("color: #EF4444;")
                self._status_dot.setToolTip("Ollama: not running")
        else:
            self._status_dot.setStyleSheet("color: #32CD32;")
            self._status_dot.setToolTip(f"{provider} ready")

    # --- Commands ---

    def _on_enter(self):
        """Handle Enter key: process command."""
        text = self._input.text().strip()
        if not text:
            return

        # Add to history
        self._history.append(text)
        self._history_pos = len(self._history)

        # Flash input line yellow
        self._input.setStyleSheet(
            f"QLineEdit {{ background: rgba(245,158,11,0.3); color: {TEXT_PRIMARY}; "
            f"border: 1px solid rgba(255,255,255,0.06); border-radius: 8px; "
            f"padding: 8px; }}"
        )
        self._flash_timer.start()

        self._input.clear()

        # Display command
        self._append_text(f"> {text}", color=ACCENT_CYAN_HEX)

        # Emit signal
        self.command_entered.emit(text)

        # Check if it's a local command or LLM query
        if text.startswith("/"):
            self._handle_command(text)
        else:
            self._start_llm(text)

    def _handle_command(self, cmd: str):
        """Handle local commands."""
        parts = cmd.split(None, 2)
        base = parts[0].lower()

        if base == "/clear":
            self._output.clear()
        elif base == "/help":
            self._append_text(
                "Commands:\n"
                "  /clear              — Clear terminal\n"
                "  /help               — Show this help\n"
                "  /scan               — Scan current repo\n"
                "  /status             — Show Muninn status\n"
                "  /provider <name>    — Switch AI (claude/openai/ollama/off)\n"
                "  /model <name>       — Switch model\n"
                "  /key <provider> <k> — Set API key\n"
                "  /boost              — Toggle mycelium boost\n"
                "  /ai                 — Show AI config\n"
                "  (text)              — Ask the AI",
                color=TEXT_SECONDARY,
            )
        elif base == "/scan":
            self._run_scan()
        elif base == "/status":
            self._run_status()
        elif base == "/provider":
            self._cmd_provider(parts)
        elif base == "/model":
            self._cmd_model(parts)
        elif base == "/key":
            self._cmd_key(parts)
        elif base == "/boost":
            self._cmd_boost()
        elif base == "/ai":
            self._cmd_ai_status()
        else:
            self._append_text(f"Unknown command: {cmd}. /help for list.", color="#EF4444")

    def _cmd_provider(self, parts: list):
        """Switch AI provider."""
        if len(parts) < 2:
            self._append_text(
                f"Current: {get_active_provider()}\n"
                f"Usage: /provider claude|openai|ollama|off",
                color=TEXT_SECONDARY,
            )
            return
        name = parts[1].lower()
        if name not in PROVIDERS:
            self._append_text(f"Unknown provider: {name}. Options: {', '.join(PROVIDERS.keys())}", color="#EF4444")
            return
        set_active_provider(name)
        # Update dropdown
        for i in range(self._provider_combo.count()):
            if self._provider_combo.itemData(i) == name:
                self._provider_combo.setCurrentIndex(i)
                break

    def _cmd_model(self, parts: list):
        """Switch model."""
        if len(parts) < 2:
            self._append_text(f"Current: {get_active_model()}", color=TEXT_SECONDARY)
            return
        model = parts[1]
        provider = get_active_provider()
        set_active_model(provider, model)
        self._refresh_models()
        self._append_text(f"[AI] Model: {model}", color=ACCENT_CYAN_HEX)

    def _cmd_key(self, parts: list):
        """Set API key for a provider."""
        if len(parts) < 3:
            self._append_text("Usage: /key <provider> <api-key>", color=TEXT_SECONDARY)
            return
        provider = parts[1].lower()
        key = parts[2].strip()
        if provider not in PROVIDERS:
            self._append_text(f"Unknown provider: {provider}", color="#EF4444")
            return
        set_api_key(provider, key)
        self._update_status_dot()
        # Show masked key
        masked = key[:8] + "..." + key[-4:] if len(key) > 16 else "***"
        self._append_text(f"[AI] Key saved for {provider}: {masked}", color="#32CD32")

    def _cmd_boost(self):
        """Toggle mycelium boost."""
        current = get_mycelium_boost()
        set_mycelium_boost(not current)
        state = "ON" if not current else "OFF"
        self._append_text(f"[AI] Mycelium boost: {state}", color=ACCENT_CYAN_HEX)

    def _cmd_ai_status(self):
        """Show AI configuration status."""
        provider = get_active_provider()
        model = get_active_model()
        boost = get_mycelium_boost()
        pinfo = PROVIDERS.get(provider, {})
        has_key = bool(get_api_key(provider)) if pinfo.get("needs_key") else True

        lines = [
            f"Provider : {pinfo.get('label', provider)}",
            f"Model    : {model or 'N/A'}",
            f"API Key  : {'OK' if has_key else 'MISSING'}",
            f"Boost    : {'ON' if boost else 'OFF'} (AI feeds mycelium)",
        ]
        if provider in ("ollama", "ollama-smart"):
            try:
                p = create_provider("ollama")
                if p:
                    models = p.list_models()
                    lines.append(f"Ollama   : {len(models)} models ({', '.join(models)})")
            except Exception:
                lines.append("Ollama   : NOT RUNNING")
        if provider == "ollama-smart":
            lines.append("Router   : code->deepseek-coder, general->mistral")
        self._append_text("\n".join(lines), color=TEXT_SECONDARY)

    def _run_scan(self):
        """Run muninn scan on current repo."""
        import subprocess
        import sys
        self._append_text("Scanning repo...", color=TEXT_SECONDARY)
        try:
            result = subprocess.run(
                [sys.executable, "-m", "muninn", "scan", "."],
                capture_output=True, text=True, timeout=30, cwd="."
            )
            if result.returncode == 0:
                self._append_text(result.stdout.strip() or "Scan complete.", color="#32CD32")
            else:
                self._append_text(result.stderr.strip() or "Scan failed.", color="#EF4444")
        except Exception as e:
            self._append_text(f"Scan error: {e}", color="#EF4444")

    def _run_status(self):
        """Run muninn status."""
        import subprocess
        import sys
        try:
            result = subprocess.run(
                [sys.executable, "-m", "muninn", "status"],
                capture_output=True, text=True, timeout=10, cwd="."
            )
            self._append_text(result.stdout.strip() or "No status available.", color=TEXT_SECONDARY)
        except Exception as e:
            self._append_text(f"Status error: {e}", color="#EF4444")

    # --- LLM ---

    def _start_llm(self, prompt: str):
        """Launch LLM query in background thread (R3, B-UI-20, B-UI-21)."""
        # Disconnect old worker signals before stopping (prevent stale signal race)
        if self._llm_worker is not None:
            try:
                self._llm_worker.finished.disconnect()
                self._llm_worker.error.disconnect()
                self._llm_worker.chunk_ready.disconnect()
            except (TypeError, RuntimeError):
                pass  # Already disconnected
        self._stop_llm()  # Cancel previous
        self._current_prompt = prompt

        # Create provider from config
        provider = create_provider()

        self._llm_thread = QThread()
        self._llm_worker = LLMWorker(prompt, self._context, provider=provider)
        self._llm_worker.moveToThread(self._llm_thread)
        self._llm_thread.started.connect(self._llm_worker.run)
        self._llm_worker.chunk_ready.connect(self._on_chunk)
        self._llm_worker.route_info.connect(self._on_route_info)
        self._llm_worker.full_response.connect(self._on_full_response)
        self._llm_worker.finished.connect(self._on_llm_done)
        self._llm_worker.error.connect(self._on_llm_error)
        self._llm_worker.finished.connect(self._llm_thread.quit)
        self._llm_worker.error.connect(self._llm_thread.quit)

        # Show breathing + stop button
        self._breathing.show()
        self._breath_anim.start()
        self._stop_btn.show()

        self._llm_thread.start()

    def _stop_llm(self):
        """Cancel running LLM query (R12)."""
        if self._llm_worker is not None:
            self._llm_worker._stop = True
        if self._llm_thread is not None and self._llm_thread.isRunning():
            self._llm_thread.quit()
            self._llm_thread.wait(2000)
        self._llm_worker = None
        self._llm_thread = None
        self._breathing.hide()
        self._breath_anim.stop()
        self._stop_btn.hide()

    def _on_route_info(self, route: str):
        """Show which model the smart router picked."""
        self._append_text(f"[router -> {route}]", color=TEXT_SECONDARY)

    def _on_chunk(self, text: str):
        """Append streaming LLM chunk."""
        cursor = self._output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(TEXT_PRIMARY))
        cursor.insertText(text, fmt)
        self._output.setTextCursor(cursor)
        self._output.ensureCursorVisible()

    def _on_full_response(self, response: str):
        """Feed AI response + prompt to mycelium if boost is ON (background thread)."""
        if not get_mycelium_boost() or not response:
            return
        import threading
        prompt = self._current_prompt

        def _feed():
            try:
                from engine.core.mycelium import Mycelium
                m = Mycelium()
                m.observe_text(f"{prompt}\n{response}")
            except Exception:
                pass  # Mycelium boost is best-effort

        threading.Thread(target=_feed, daemon=True).start()

    def _on_llm_done(self):
        """LLM finished."""
        self._append_text("")  # New line
        self._stop_llm()

    def _on_llm_error(self, msg: str):
        """LLM error (bug #20: no QMessageBox here). Clean up raw API errors."""
        # Extract clean message from API error dumps
        clean = msg
        if "'message':" in msg:
            import re
            m = re.search(r"'message':\s*'([^']+)'", msg)
            if m:
                clean = m.group(1)
        elif "message=" in msg:
            import re
            m = re.search(r"message=['\"]([^'\"]+)['\"]", msg)
            if m:
                clean = m.group(1)
        self._append_text(f"Error: {clean}", color="#EF4444")
        self._stop_llm()

    def _append_text(self, text: str, color: str = ACCENT_GREEN):
        """Append colored text to output."""
        cursor = self._output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        cursor.insertText(text + "\n", fmt)
        self._output.setTextCursor(cursor)
        self._output.ensureCursorVisible()

    def _flash_reset(self):
        """Reset input style after flash."""
        self._input.setStyleSheet(
            f"QLineEdit {{ background: {BG_1DP}; color: {TEXT_PRIMARY}; "
            f"border: 1px solid rgba(255,255,255,0.06); border-radius: 8px; "
            f"padding: 8px; }}"
        )

    def keyPressEvent(self, event):
        """Handle keyboard shortcuts."""
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            if event.key() == Qt.Key.Key_L:
                self._output.clear()
                return
        # History navigation
        if event.key() == Qt.Key.Key_Up and self._input.hasFocus():
            if self._history and self._history_pos > 0:
                self._history_pos -= 1
                self._input.setText(self._history[self._history_pos])
            return
        if event.key() == Qt.Key.Key_Down and self._input.hasFocus():
            if self._history_pos < len(self._history) - 1:
                self._history_pos += 1
                self._input.setText(self._history[self._history_pos])
            else:
                self._history_pos = len(self._history)
                self._input.clear()
            return
        super().keyPressEvent(event)

    def set_context(self, context: str):
        """Set LLM system context (selected neuron info, etc.)."""
        self._context = context

    def closeEvent(self, event):
        self._stop_llm()
        super().closeEvent(event)

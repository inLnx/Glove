import os
import subprocess
import json
import requests
import base64
import time
import threading
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QTextEdit, QLabel, QMessageBox, QSizePolicy
)
from PyQt5.QtGui import QPixmap, QImage, QColor, QFont
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QThread
from PIL import Image, ImageQt # Import Pillow for image handling

# --- Gemini API Configuration ---
# IMPORTANT: When running LOCALLY, you MUST replace the empty string below
# with your actual Gemini API Key. Get it from Google AI Studio.
# Example: API_KEY = "YOUR_GEMINI_API_KEY_HERE"
API_KEY = "AIzaSyC0iXmXyUU_rMXFLCF8T63_mUDIgzCl8Io"
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

# --- Core Logic Functions (remain largely the same) ---

def get_adb_commands_from_gemini(overall_task: str, base64_image_data: str = None) -> dict:
    """
    Sends the overall task and optional image data to the Gemini API,
    requesting a structured JSON response with the next ADB command and task status.

    Args:
        overall_task: The high-level task the user wants to accomplish.
        base64_image_data: Optional base64 encoded string of a screenshot.

    Returns:
        A dictionary containing the generated command, status ('continue'/'done'),
        and a reason, or an error dictionary.
    """
    system_instruction = (
        "You are an intelligent Android automation assistant. Your goal is to break down a user's overall task "
        "into a sequence of single ADB commands. After each command, you will be provided with a new screenshot. "
        "Based on the current screenshot and the overall task, determine the *next single logical ADB command* "
        "to move closer to completing the task. "
        "You must respond with a JSON object containing the following keys: "
        "`command` (string): The single ADB command to execute (e.g., `input tap 100 200`, `am start -a android.intent.action.VIEW -d http://example.com`). "
        "`status` (string): 'continue' if more steps are needed to complete the overall task, or 'done' if the task is complete. "
        "`reason` (string): A brief explanation for the chosen command or why the task is considered done. "
        "Do not include any other text outside the JSON object. "
        "If the task is already complete based on the provided screenshot, set `status` to 'done' and provide a `reason`. "
        "If you need to type text, use `input text 'your text'`. For tapping, use `input tap X Y`. For scrolling, use `input swipe X1 Y1 X2 Y2 [duration_ms]`."
        "\n\n"
        "Specific instructions for navigation and app interaction:\n"
        "- To reach control center, swipe down, then at notification center, swipe down again.\n"
        "- If a command isn't seen, swipe to the left until you see it.\n"
        "- If Gmail is opened and there is a current email opened, click the arrow in the corner (assume coordinates if needed).\n"
        "- Stop if you have done more than 5 steps for a sub-task, and report 'done' for that sub-task.\n"
        "\n"
        "Example JSON output for continuing:\n"
        "```json\n"
        "{\n"
        "  \"command\": \"am start -n com.android.settings/.Settings\",\n"
        "  \"status\": \"continue\",\n"
        "  \"reason\": \"Opening Android settings to begin configuration.\"\n"
        "}\n"
        "```\n"
        "Example JSON output for task completion:\n"
        "```json\n"
        "{\n"
        "  \"command\": \"echo 'Task complete'\",\n"
        "  \"status\": \"done\",\n"
        "  \"reason\": \"Successfully navigated to the target page.\"\n"
        "}\n"
        "```"
    )

    content_parts = [{"text": system_instruction + "\nOverall Task: " + overall_task}]

    if base64_image_data:
        content_parts.append({
            "inlineData": {
                "mimeType": "image/png",
                "data": base64_image_data
            }
        })

    payload = {
        "contents": [
            {"role": "user", "parts": content_parts}
        ],
        "generationConfig": {
            "temperature": 0.1,
            "topK": 1,
            "topP": 1,
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "OBJECT",
                "properties": {
                    "command": {"type": "STRING"},
                    "status": {"type": "STRING", "enum": ["continue", "done"]},
                    "reason": {"type": "STRING"}
                },
                "required": ["command", "status", "reason"]
            }
        }
    }

    headers = {
        'Content-Type': 'application/json'
    }

    api_url_with_key = f"{GEMINI_API_URL}?key={API_KEY}"

    try:
        response = requests.post(api_url_with_key, headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        result = response.json()

        if result.get("candidates") and result["candidates"][0].get("content") and result["candidates"][0]["content"].get("parts"):
            json_text = result["candidates"][0]["content"]["parts"][0]["text"].strip()
            if json_text.startswith("```json") and json_text.endswith("```"):
                json_text = json_text[len("```json"): -len("```")].strip()
            
            try:
                return json.loads(json_text)
            except json.JSONDecodeError:
                return {"error": f"Gemini returned invalid JSON: {json_text}", "raw_response": json.dumps(result, indent=2)}
        else:
            return {"error": "No content generated by Gemini. Check API response structure.", "response": json.dumps(result, indent=2)}
    except requests.exceptions.RequestException as e:
        return {"error": f"Error communicating with Gemini API: {e}"}
    except Exception as e:
        return {"error": f"An unexpected error occurred: {e}"}

def capture_and_encode_screenshot(filename="current_screenshot.png", log_callback=None, image_display_callback=None) -> str | None:
    """
    Captures a screenshot from the Android device using ADB and encodes it to base64.
    Also updates the GUI with the captured image.
    This function is designed to be run on a LOCAL machine with ADB installed.
    """
    if log_callback:
        log_callback(f"\nAttempting to capture and pull '{filename}' from device via ADB...")
    try:
        subprocess.run(
            ["adb", "shell", "screencap", "-p", f"/sdcard/{filename}"],
            capture_output=True,
            text=True,
            check=True
        )
        if log_callback:
            log_callback(f"Screenshot captured on device: /sdcard/{filename}")
        time.sleep(1)

        subprocess.run(
            ["adb", "pull", f"/sdcard/{filename}", "."],
            capture_output=True,
            text=True,
            check=True
        )
        if log_callback:
            log_callback(f"Screenshot pulled to local directory: {filename}")

        with open(filename, 'rb') as f:
            image_data = f.read()
            encoded_string = base64.b64encode(image_data).decode('utf-8')
        if log_callback:
            log_callback(f"Screenshot encoded to base64.")

        if image_display_callback:
            try:
                image = Image.open(filename)
                # Resize image to fit in the GUI, maintaining aspect ratio
                max_width = 300
                max_height = 400
                image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
                image_display_callback(ImageQt.toqpixmap(image)) # Changed to emit QPixmap directly
            except Exception as e:
                if log_callback:
                    log_callback(f"Error displaying image in GUI: {e}")

        try:
            os.remove(filename)
            if log_callback:
                log_callback(f"Cleaned up local file: {filename}")
        except OSError as e:
            if log_callback:
                log_callback(f"Error removing local screenshot file {filename}: {e}")

        return encoded_string

    except subprocess.CalledProcessError as e:
        error_msg = (
            f"Error executing ADB command: {e.cmd}\n"
            f"Stdout: {e.stdout.strip()}\n"
            f"Stderr: {e.stderr.strip()}\n"
            "Please ensure ADB is installed, your device is connected, and USB debugging is enabled."
        )
        if log_callback:
            log_callback(error_msg)
        return None
    except FileNotFoundError:
        error_msg = "Error: ADB command not found. Is ADB installed and in your system's PATH?"
        if log_callback:
            log_callback(error_msg)
        return None
    except Exception as e:
        error_msg = f"An unexpected error occurred during screenshot capture/encoding: {e}"
        if log_callback:
            log_callback(error_msg)
        return None

def execute_adb_command(command: str, log_callback=None) -> bool:
    """
    Executes a single ADB command using subprocess.
    Determines if it's an 'adb shell' command or a direct 'adb' command.
    """
    command_parts = command.strip().split(maxsplit=1)

    if not command_parts:
        return False

    if command_parts[0] in ["screencap", "pull", "install", "push", "devices", "logcat"]:
        full_cmd = ["adb"] + command.strip().split()
    else:
        full_cmd = ["adb", "shell"] + command.strip().split()

    if log_callback:
        log_callback(f"Executing: {' '.join(full_cmd)}")
    try:
        result = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            check=True
        )
        if log_callback:
            log_callback(f"Command output: {result.stdout.strip()}")
            if result.stderr:
                log_callback(f"Command error: {result.stderr.strip()}")
        return True
    except subprocess.CalledProcessError as e:
        error_msg = (
            f"Error executing command '{' '.join(full_cmd)}':\n"
            f"  Return Code: {e.returncode}\n"
            f"  Stdout: {e.stdout.strip()}\n"
            f"  Stderr: {e.stderr.strip()}"
        )
        if log_callback:
            log_callback(error_msg)
        return False
    except FileNotFoundError:
        error_msg = "Error: 'adb' command not found. Ensure ADB is installed and in your system's PATH."
        if log_callback:
            log_callback(error_msg)
        return False
    except Exception as e:
        error_msg = f"An unexpected error occurred during command execution: {e}"
        if log_callback:
            log_callback(error_msg)
        return False

# --- Worker Thread for Automation ---
class AutomationWorker(QObject):
    # Signals to update the GUI from the worker thread
    log_message_signal = pyqtSignal(str)
    update_screenshot_signal = pyqtSignal(QPixmap) # Changed to QPixmap
    automation_finished_signal = pyqtSignal()
    show_error_signal = pyqtSignal(str, str)

    def __init__(self, overall_task):
        super().__init__()
        self.overall_task = overall_task
        self._is_running = True

    def stop(self):
        self._is_running = False

    def run(self):
        max_steps = 20
        current_step = 0
        try:
            while self._is_running and current_step < max_steps:
                current_step += 1
                self.log_message_signal.emit(f"\n--- Step {current_step} ---")

                # Step 1: Capture screenshot and encode it for Gemini
                current_screenshot_base64 = capture_and_encode_screenshot(
                    log_callback=self.log_message_signal.emit,
                    image_display_callback=self.update_screenshot_signal.emit # Now emits QPixmap directly
                )

                if not self._is_running:
                    self.log_message_signal.emit("Automation stopped during screenshot capture.")
                    break

                if current_screenshot_base64 is None:
                    self.log_message_signal.emit("Failed to get screenshot. Cannot proceed with AI context for this command.")
                    self.log_message_signal.emit("Please resolve the screenshot issue (check ADB, device connection, USB debugging).")
                    self.show_error_signal.emit("Automation Error", "Failed to get screenshot. Check ADB setup and device connection.")
                    self._is_running = False
                    break

                self.log_message_signal.emit("Thinking... (AI analyzing screen and determining next action)")
                # Step 2: Call Gemini to get the next ADB command and task status
                gemini_response = get_adb_commands_from_gemini(self.overall_task, current_screenshot_base64)

                if not self._is_running:
                    self.log_message_signal.emit("Automation stopped during Gemini API call.")
                    break

                if "error" in gemini_response:
                    error_detail = gemini_response.get('error', 'Unknown API Error')
                    self.log_message_signal.emit(f"Error from Gemini API: {error_detail}")
                    self.log_message_signal.emit("Please check your API key, network connection, or Gemini API response structure.")
                    self.show_error_signal.emit("Automation Error", f"Gemini API Error: {error_detail}")
                    self._is_running = False
                    break

                command_to_execute = gemini_response.get("command")
                task_status = gemini_response.get("status")
                reason = gemini_response.get("reason", "No reason provided.")

                self.log_message_signal.emit(f"AI's Reason: {reason}")
                self.log_message_signal.emit(f"AI's Status: {task_status}")

                if not command_to_execute:
                    self.log_message_signal.emit("Gemini did not provide a command. This might indicate an issue or task completion.")
                    if task_status == "done":
                        self.log_message_signal.emit("Task reported as done by AI, but no final command. Ending task.")
                    else:
                        self.log_message_signal.emit("No command, but task not done. Ending due to potential issue.")
                    self._is_running = False
                    break

                self.log_message_signal.emit(f"Generated command: '{command_to_execute}'")
                # Step 3: Execute the generated ADB command
                success = execute_adb_command(command_to_execute, log_callback=self.log_message_signal.emit)

                if not self._is_running:
                    self.log_message_signal.emit("Automation stopped during command execution.")
                    break

                if not success:
                    self.log_message_signal.emit(f"Failed to execute command: '{command_to_execute}'")
                    self.log_message_signal.emit("AI might be stuck or generated an incorrect command. Ending task.")
                    self.show_error_signal.emit("Automation Error", f"Failed to execute ADB command: '{command_to_execute}'")
                    self._is_running = False
                    break

                time.sleep(2) # Give the device time to process the command and update screen

                # Step 4: Check if the task is done
                if task_status == "done":
                    self.log_message_signal.emit(f"\n--- Task Completed ---")
                    self.log_message_signal.emit(f"AI reported task '{self.overall_task}' as done. Reason: {reason}")
                    self._is_running = False
                    break

            if self._is_running: # If loop finished because max_steps was reached
                self.log_message_signal.emit(f"\n--- Task Limit Reached ---")
                self.log_message_signal.emit(f"Task '{self.overall_task}' did not complete within {max_steps} steps.")
                self.log_message_signal.emit("The AI might be stuck or unable to complete the task. Please review the last steps.")
                self._is_running = False

        finally:
            self.automation_finished_signal.emit()
            self.log_message_signal.emit("\nAutomation session ended.")


class AndroidAutomationApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI Android Automation")
        self.setGeometry(100, 100, 500, 800) # Increased height for screenshot
        self.setStyleSheet("background-color: white;")

        self.running_task = False
        self.automation_thread = None
        self.worker = None
        self.current_screenshot_pixmap = None # To hold the QPixmap reference

        self._placeholder_text = "Enter command"

        self.init_ui()
        self.display_initial_instructions()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(30, 30, 30, 30) # Add margin to the main layout
        main_layout.setSpacing(15) # Spacing between widgets

        # Task Entry (QLineEdit)
        self.task_entry = QLineEdit(self)
        self.task_entry.setFont(QFont("Arial", 16, QFont.Bold))
        self.task_entry.setStyleSheet(
            "background-color: #64B446; color: white; border: none; "
            "padding: 15px 20px; border-radius: 25px;" # Rounded corners, padding
        )
        self.task_entry.setAlignment(Qt.AlignCenter)
        self.task_entry.setText(self._placeholder_text)
        self.task_entry.setPlaceholderText(self._placeholder_text) # For visual consistency
        self.task_entry.textChanged.connect(self._handle_text_change) # Connect text change signal
        main_layout.addWidget(self.task_entry, alignment=Qt.AlignCenter)

        # Do Button (QPushButton)
        self.start_button = QPushButton("Do", self)
        self.start_button.setFont(QFont("Arial", 14, QFont.Bold))
        self.start_button.setStyleSheet(
            "background-color: #64B446; color: white; border: none; "
            "padding: 10px 30px; border-radius: 20px;" # Rounded corners, padding
        )
        self.start_button.setFixedSize(120, 50) # Fixed size for the button
        self.start_button.clicked.connect(self.start_automation)
        main_layout.addWidget(self.start_button, alignment=Qt.AlignCenter)

        # Stop Button (QPushButton) - Added back for control
        self.stop_button = QPushButton("Stop", self)
        self.stop_button.setFont(QFont("Arial", 12))
        self.stop_button.setStyleSheet(
            "background-color: #FF6347; color: white; border: none; "
            "padding: 5px 15px; border-radius: 15px;"
        )
        self.stop_button.clicked.connect(self.stop_automation)
        self.stop_button.setEnabled(False) # Initially disabled
        main_layout.addWidget(self.stop_button, alignment=Qt.AlignCenter)

        # Screenshot Display Area (QLabel)
        self.screenshot_label = QLabel(self)
        self.screenshot_label.setAlignment(Qt.AlignCenter)
        self.screenshot_label.setStyleSheet("background-color: lightgray; border: 1px solid #ccc; border-radius: 15px;")
        self.screenshot_label.setFixedSize(300, 400) # Fixed size for consistency with previous Tkinter
        main_layout.addWidget(self.screenshot_label, alignment=Qt.AlignCenter)

        # Logs area (QTextEdit)
        self.log_area = QTextEdit(self)
        self.log_area.setReadOnly(True)
        self.log_area.setFont(QFont("Arial", 10))
        self.log_area.setStyleSheet(
            "background-color: #B4DC9F; color: black; border: none; "
            "padding: 20px; border-radius: 25px;" # Rounded corners, padding
        )
        self.log_area.setText("Logs go here")
        # Set size policy to expand and fill available space
        self.log_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        main_layout.addWidget(self.log_area)

    def _handle_text_change(self, text):
        """Handles text changes in the QLineEdit for placeholder behavior."""
        if text == self._placeholder_text:
            self.task_entry.setStyleSheet(
                "background-color: #64B446; color: white; border: none; "
                "padding: 15px 20px; border-radius: 25px;"
            )
        else:
            self.task_entry.setStyleSheet(
                "background-color: #64B446; color: black; border: none; "
                "padding: 15px 20px; border-radius: 25px;"
            )

    def display_initial_instructions(self):
        """Displays initial setup instructions in the log area."""
        self.log_message("\nWelcome to the AI-powered Android Controller GUI!")
        self.log_message("IMPORTANT PREREQUISITES:")
        self.log_message("1. ADB (Android Debug Bridge) must be installed on your system and in your PATH.")
        self.log_message("2. Your Android device must be connected via USB.")
        self.log_message("3. USB Debugging must be enabled in your device's Developer Options.")
        self.log_message("4. You may need to authorize your computer on your phone the first time you connect.")
        self.log_message("5. Install PyQt5 and Pillow: pip install PyQt5 Pillow")
        self.log_message("\nRemember to set your Gemini API Key in the script's API_KEY variable!")
        self.log_message("\nEnter your overall task above and click 'Do'.")

    def log_message(self, message):
        """Appends a message to the scrolled text area."""
        # Use append to add text and automatically scroll to end
        # Ensure this is called on the main thread if from a worker thread
        if self.log_area.toPlainText().strip() == "Logs go here":
            self.log_area.clear()
        self.log_area.append(message)

    def update_screenshot_display(self, qpixmap):
        """Updates the QLabel with the given QPixmap."""
        self.current_screenshot_pixmap = qpixmap # Store reference to prevent garbage collection
        self.screenshot_label.setPixmap(self.current_screenshot_pixmap.scaled(
            self.screenshot_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        ))

    def start_automation(self):
        """Initiates the automation process."""
        if self.running_task:
            return

        if not API_KEY: # Check for API Key
            QMessageBox.critical(self, "API Key Missing", "Please set your Gemini API Key in the script's API_KEY variable before running.")
            self.log_message("ERROR: Gemini API Key is missing. Please update the API_KEY variable in the script.")
            return

        overall_task = self.task_entry.text().strip()
        if not overall_task or overall_task == self._placeholder_text:
            QMessageBox.warning(self, "Input Error", "Please enter an overall task.")
            return

        self.running_task = True
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.log_area.clear() # Clear previous logs
        self.log_message(f"\nStarting task: '{overall_task}'")
        self.log_message("The AI will now attempt to complete this task step-by-step.")

        # Create a QThread and Worker to run automation in background
        self.automation_thread = QThread()
        self.worker = AutomationWorker(overall_task)
        self.worker.moveToThread(self.automation_thread)

        # Connect signals from worker to GUI slots
        self.worker.log_message_signal.connect(self.log_message)
        self.worker.update_screenshot_signal.connect(self.update_screenshot_display)
        self.worker.automation_finished_signal.connect(self._automation_finished)
        self.worker.show_error_signal.connect(lambda title, msg: QMessageBox.critical(self, title, msg))


        # Connect thread started/finished signals
        self.automation_thread.started.connect(self.worker.run)
        self.automation_thread.finished.connect(self.automation_thread.deleteLater) # Clean up thread

        # Start the thread
        self.automation_thread.start()

    def stop_automation(self):
        """Requests the automation worker to stop."""
        if self.worker:
            self.worker.stop()
        self.log_message("Stopping automation requested by user...")
        # Button states will be reset by _automation_finished

    def _automation_finished(self):
        """Slot connected to worker's automation_finished_signal."""
        self.running_task = False
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        # The log_message about session ending is already handled by the worker's finally block


if __name__ == "__main__":
    app = QApplication([])
    window = AndroidAutomationApp()
    window.show()
    app.exec_()

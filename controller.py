import os
import subprocess
import json
import requests # For making HTTP requests to Gemini API
import base64 # For handling base64 encoding/decoding
import time # For potential delays

# --- Gemini API Configuration ---
# IMPORTANT: In a real application, you would load this from environment variables
# or a secure configuration system. For this example, it's left as an empty string.
# The Canvas environment will automatically provide the API key for gemini-2.0-flash.
API_KEY = "AIzaSyC0iXmXyUU_rMXFLCF8T63_mUDIgzCl8Io" # Leave this as an empty string. Canvas will inject the key.
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

def get_adb_commands_from_gemini(prompt_text: str, base64_image_data: str = None) -> str:
    """
    Sends a natural language prompt (and optionally image data) to the Gemini API
    and requests ADB commands.

    Args:
        prompt_text: The natural language command from the user.
        base64_image_data: Optional base64 encoded string of a screenshot.

    Returns:
        A string containing the generated ADB commands, or an error message.
    """
    # System instruction to guide Gemini's response
    # This instruction is crucial for Gemini to understand the desired output format.
    system_instruction = (
        "You are an assistant that translates natural language commands into Android Debug Bridge (ADB) shell commands. "
        "Provide only the ADB command(s) as output, one command per line. "
        "Do not include any explanations, greetings, or extra text. "
        "If a command requires text input, use `input text 'your text'` (e.g., `input text 'hello world'`). "
        "For opening specific applications, use `am start -n package.name/activity.name`. "
        "For opening web URLs, use `am start -a android.intent.action.VIEW -d http://example.com`. "
        "For simulating key presses, use `input keyevent KEYCODE_EVENT` (e.g., `input keyevent KEYCODE_HOME`). "
        "For tapping at screen coordinates, use `input tap X Y`. "
        "For swiping, use `input swipe X1 Y1 X2 Y2 [duration_ms]`. "
        "Assume the user's intent is to control the Android device via ADB. "
        "If an image is provided, use it to understand the current screen context and generate more accurate commands. "
        "For example, if the image shows a button, and the user says 'tap that button', you might infer its coordinates "
        "or suggest a way to navigate to it if direct tapping isn't feasible. "
        "Prioritize commands that directly interact with visible elements if the image provides enough context."
        "\n\n"
        "Here are some examples of expected outputs:\n"
        "User: 'Open settings'\n"
        "Output: `am start -n com.android.settings/.Settings`\n"
        "User: 'Go to google.com'\n"
        "Output: `am start -a android.intent.action.VIEW -d https://google.com`\n"
        "User: 'Type hello world into the current field'\n"
        "Output: `input text 'hello world'`\n"
        "User: 'Tap at coordinates 100, 200'\n"
        "Output: `input tap 100 200`\n"
        "User: 'Press the home button'\n"
        "Output: `input keyevent KEYCODE_HOME`\n"
        "User: 'Scroll down'\n"
        "Output: `input swipe 500 1500 500 500`\n" # Example swipe down
        "User: 'Take a screenshot'\n"
        "Output: `screencap -p /sdcard/screenshot.png`\n`pull /sdcard/screenshot.png`" # Example for multiple commands
    )

    # Build the parts for the content payload
    content_parts = [{ "text": system_instruction + "\n" + prompt_text }]

    # If image data is provided, add it to the content parts
    if base64_image_data:
        content_parts.append({
            "inlineData": {
                "mimeType": "image/png", # Assuming PNG format for screenshots
                "data": base64_image_data
            }
        })

    payload = {
        "contents": [
            {"role": "user", "parts": content_parts}
        ],
        "generationConfig": {
            "temperature": 0.1, # Keep temperature low for more deterministic and precise output
            "topK": 1,
            "topP": 1,
        }
    }

    headers = {
        'Content-Type': 'application/json'
    }

    # Construct the API URL with the API key. Canvas will inject the key at runtime.
    api_url_with_key = f"{GEMINI_API_URL}?key={API_KEY}"

    try:
        # Make the POST request to the Gemini API
        response = requests.post(api_url_with_key, headers=headers, data=json.dumps(payload))
        response.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)
        result = response.json()

        # Extract the generated text from the API response
        if result.get("candidates") and result["candidates"][0].get("content") and result["candidates"][0]["content"].get("parts"):
            generated_text = result["candidates"][0]["content"]["parts"][0]["text"].strip()
            return generated_text
        else:
            # Handle cases where the response structure is unexpected or content is missing
            return f"Error: No content generated by Gemini. Response: {json.dumps(result, indent=2)}"
    except requests.exceptions.RequestException as e:
        # Catch network-related errors or bad HTTP responses
        return f"Error communicating with Gemini API: {e}"
    except json.JSONDecodeError:
        # Catch errors if the response is not valid JSON
        return f"Error decoding JSON response from Gemini: {response.text}"
    except Exception as e:
        # Catch any other unexpected errors
        return f"An unexpected error occurred: {e}"

def main():
    """
    Main function to run the AI-powered Android Controller script.
    It prompts the user for commands, gets ADB commands from Gemini, and prints them.
    """
    print("Welcome to the AI-powered Android Controller!")
    print("This script generates ADB commands based on your natural language prompts using the Gemini API.")
    print("\nIMPORTANT NOTE:")
    print("This script is designed to run on your LOCAL machine, where ADB is installed and your Android device is connected.")
    print("The screenshot capture and transfer steps MUST be executed locally.")
    print("The generated commands will be printed for you to execute manually in your local terminal.")
    print("Type 'exit' to quit.")
    print("\nExample prompts:")
    print("- 'Open Chrome and go to https://www.google.com'")
    print("- 'Type hello world into the current input field'")
    print("- 'Tap the screen at coordinates 500, 1200'")
    print("- 'Press the back button'")
    print("- 'Scroll down the current page'")
    print("\n--- Screenshot Integration (Local Execution Required) ---")
    print("Before each command, the script will attempt to get a screenshot from your device.")
    print("This requires ADB setup and permissions on your local machine.")

    while True:
        current_screenshot_base64 = None
        screenshot_filename = "current_screenshot.png" # Temporary file for screenshot

        print("\nAttempting to capture screenshot from device via ADB...")
        print("--- Local ADB Commands to Execute ---")
        print(f"1. `adb shell screencap -p /sdcard/{screenshot_filename}`")
        print(f"2. `adb pull /sdcard/{screenshot_filename} .`")
        print("-------------------------------------")
        print("Please execute these two commands in your LOCAL terminal.")
        print("Press Enter after you have pulled the screenshot to continue.")
        input() # Wait for user to confirm screenshot is pulled

        # --- THIS SECTION SIMULATES LOCAL SCREENSHOT CAPTURE AND BASE64 ENCODING ---
        # In a real local application, you would replace the following lines
        # with actual subprocess calls and file operations.
        print(f"Assuming '{screenshot_filename}' is now in your current directory.")
        try:
            # Simulate reading a local file. In a real scenario, you'd read the actual file.
            # For this environment, we'll ask the user to paste it if they want to test.
            print("To proceed with image analysis, you MUST paste the base64 string of your screenshot.")
            print("Use this Python command in your LOCAL terminal to get the base64 string:")
            print(f"`import base64; with open('{screenshot_filename}', 'rb') as f: print(base64.b64encode(f.read()).decode('utf-8'))`")
            current_screenshot_base64 = input("Paste Base64 encoded image data here (or leave empty to skip image context for this command):\n> ").strip()
            if not current_screenshot_base64:
                print("No screenshot provided for AI context.")
        except FileNotFoundError:
            print(f"Error: Could not find '{screenshot_filename}'. Make sure you pulled it successfully.")
        except Exception as e:
            print(f"An error occurred during local screenshot processing simulation: {e}")
        # --- END OF LOCAL SIMULATION SECTION ---

        user_prompt = input("\nEnter your command for the Android phone:\n> ").strip()

        if user_prompt.lower() == 'exit':
            print("Exiting application. Goodbye!")
            break

        print("\nThinking... (Generating ADB commands with Gemini AI)")
        # Call Gemini to get the ADB commands, passing the screenshot if available
        adb_commands_raw = get_adb_commands_from_gemini(user_prompt, current_screenshot_base64)

        if adb_commands_raw.startswith("Error:"):
            print(adb_commands_raw) # Print any errors from Gemini API call
            continue

        print("\n--- Generated ADB Commands ---")
        print("Please execute these commands in your local terminal:")
        print("------------------------------")
        # Split the generated commands by newline, as Gemini might return multiple commands
        commands_to_execute = adb_commands_raw.split('\n')
        for cmd in commands_to_execute:
            if cmd.strip(): # Ensure the command is not empty after stripping whitespace
                print(f"'{cmd.strip()}'") # Print each generated command

        print("------------------------------")
        print("\nTo run these, open your terminal and type 'adb shell <command>' for most commands.")
        print("For commands like 'pull' or 'install', just use 'adb <command>'.")
        print("For example, if the generated command is 'am start -n com.android.chrome/com.google.android.apps.chrome.Main',")
        print("you would type in your terminal: 'adb shell am start -n com.android.chrome/com.google.android.apps.chrome.Main'")
        print("Make sure your device is connected and recognized by ADB (run 'adb devices' to check).")

# This ensures that main() is called only when the script is executed directly
if __name__ == "__main__":
    main()

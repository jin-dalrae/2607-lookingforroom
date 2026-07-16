#!/usr/bin/env python3
"""Interactive setup script for Looking for Room.

This script prompts the user for search/profile conditions, creates profile.yaml,
initializes the SQLite database, starts the local servers, and opens the UI in the browser.
"""

import sys
import os
import shutil
import subprocess
import webbrowser
from pathlib import Path

# Try to import yaml. If not available, ask the user to install requirements first.
try:
    import yaml
except ImportError:
    print("Error: PyYAML is not installed.")
    print("Please run: pip install -r requirements.txt")
    sys.exit(1)

def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")

def prompt_input(prompt_text, default_val):
    placeholder = f" [{default_val}]" if default_val is not None else ""
    try:
        user_val = input(f"{prompt_text}{placeholder}: ").strip()
        if not user_val and default_val is not None:
            return default_val
        return user_val
    except (KeyboardInterrupt, EOFError):
        print("\nSetup cancelled.")
        sys.exit(0)

def main():
    clear_screen()
    print("==================================================")
    print("      Welcome to Looking for Room Setup!       ")
    print("==================================================")
    print("Let's configure your room-hunting profile and launch")
    print("the local server so you can view listings.\n")

    # Determine default values from existing profile.yaml, profile.example.yaml, or fallback
    profile_path = Path("profile.yaml")
    example_path = Path("profile.example.yaml")
    
    current_profile = {}
    if profile_path.exists():
        try:
            with open(profile_path, "r", encoding="utf-8") as f:
                current_profile = yaml.safe_load(f) or {}
        except Exception:
            pass
    elif example_path.exists():
        try:
            with open(example_path, "r", encoding="utf-8") as f:
                current_profile = yaml.safe_load(f) or {}
        except Exception:
            pass

    # Prompt user for conditions
    name = prompt_input("1. Your Full Name", current_profile.get("name", "Your Name"))
    email = prompt_input("2. Your Email Address", current_profile.get("email", "you@example.com"))
    phone = prompt_input("3. Your Phone Number (for WhatsApp/Texts)", current_profile.get("phone", "555-555-5555"))
    move_in = prompt_input("4. Target Move-in Window", current_profile.get("move_in", "late July through August 18, 2026"))
    
    # Budget must be integer
    while True:
        budget_str = prompt_input("5. Maximum Monthly Budget ($)", str(current_profile.get("budget", 1300)))
        try:
            budget = int(budget_str)
            break
        except ValueError:
            print("Please enter a valid integer for budget.")

    email_subject = prompt_input("6. Email Subject Line", current_profile.get("email_subject", "Room Rental Inquiry"))

    # Gmail App Password (required for drafts + reply monitoring)
    print("\nGmail App Password is required (not your normal Gmail password).")
    print("  1. Enable 2-Step Verification: https://myaccount.google.com/security")
    print("  2. Create App Password: https://myaccount.google.com/apppasswords")
    print("  3. App = Mail → copy the 16-character code")
    existing_pwd = ""
    env_path_pre = Path(".env")
    if env_path_pre.exists():
        for line in env_path_pre.read_text(encoding="utf-8").splitlines():
            if line.startswith("GMAIL_PASSWORD=") or line.startswith("GMAIL_APP_PASSWORD="):
                existing_pwd = line.split("=", 1)[-1].strip().strip('"').strip("'")
                break
    gmail_password = prompt_input(
        "7. Gmail App Password (16 chars; leave blank to keep existing)",
        existing_pwd or "",
    )
    if not (gmail_password or existing_pwd):
        print("Warning: without GMAIL_PASSWORD, Gmail drafts and mail monitoring will not work.")
    
    # Message templates
    print("\nDrafting your outreach templates...")
    
    # Base templates to inject variables
    default_msg_tmpl = (
        "Hi! I'm interested in your room listing.\n\n"
        f"My name is {name}, and I'm currently looking for a private room with a 12-month lease.\n\n"
        "I'm clean, quiet, respectful, and a non-smoker. I have sufficient funds to comfortably support myself, "
        "and I'm happy to provide proof of funds, references, or any other documentation if needed.\n\n"
        "On weekdays, I'm usually busy working/studying, keeping shared spaces clean, and being considerate of housemates. "
        "I value a peaceful and friendly living environment.\n\n"
        "Is the room still available? I'd love to schedule a viewing.\n\n"
        f"You can reach me at {phone} via call or text.\n\n"
        "Thank you, and I look forward to hearing from you!"
    )
    
    default_followup_tmpl = (
        f"Hi! I wanted to follow up on my room inquiry. I'm still very interested — my move-in window is {move_in}.\n\n"
        "Is the room still available? I'd love to schedule a viewing if possible.\n\n"
        "Thank you!\n"
        f"{name}\n"
        f"{phone}"
    )

    message_template = current_profile.get("message_template", default_msg_tmpl)
    follow_up_template = current_profile.get("follow_up_template", default_followup_tmpl)

    # Let the user review and confirm template generation
    print("\nStandard outreach message template generated.")
    print("-" * 50)
    print(default_msg_tmpl[:200] + "...\n[Truncated for display]")
    print("-" * 50)
    
    confirm_template = prompt_input("Use this generated message template? (y/n)", "y").lower()
    if confirm_template != "y":
        print("\nNo problem! We'll use the template from profile.example.yaml, and you can edit profile.yaml later.")
        message_template = current_profile.get("message_template", "[Your intro, move-in window, and contact info.]")
        follow_up_template = current_profile.get("follow_up_template", "Hi! I wanted to follow up on my room inquiry.")

    # Save to profile.yaml
    profile_data = {
        "name": name,
        "email": email,
        "email_subject": email_subject,
        "phone": phone,
        "move_in": move_in,
        "budget": budget,
        "message_template": message_template,
        "append_hold_question": current_profile.get("append_hold_question", True),
        "follow_up_template": follow_up_template
    }

    with open(profile_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(profile_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
    
    print(f"\nSaved profile details to: {profile_path.resolve()}")

    # Always ensure .env has Gmail address + app password (required)
    env_path = Path(".env")
    env_example_path = Path(".env.example")
    if not env_path.exists():
        if env_example_path.exists():
            shutil.copy(env_example_path, env_path)
        else:
            env_path.write_text("", encoding="utf-8")

    def _upsert_env(path: Path, key: str, value: str) -> None:
        lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        out: list[str] = []
        found = False
        for line in lines:
            if line.startswith(f"{key}="):
                out.append(f"{key}={value}")
                found = True
            else:
                out.append(line)
        if not found:
            out.append(f"{key}={value}")
        path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")

    _upsert_env(env_path, "GMAIL_ADDRESS", email)
    pwd_to_write = (gmail_password or existing_pwd).replace(" ", "")
    if pwd_to_write:
        _upsert_env(env_path, "GMAIL_PASSWORD", pwd_to_write)
        print(f"Updated {env_path.resolve()} with GMAIL_ADDRESS and GMAIL_PASSWORD.")
    else:
        _upsert_env(env_path, "GMAIL_PASSWORD", "")
        print(f"Updated {env_path.resolve()} with GMAIL_ADDRESS (password still empty).")

    # Initialize SQLite DB tables
    print("\nInitializing database tables...")
    try:
        subprocess.run(
            [sys.executable, "-c", "from lfr.db import init_pipeline_tables; init_pipeline_tables()"],
            check=True,
            capture_output=True,
            text=True
        )
        print("Database initialized successfully.")
    except Exception as e:
        print(f"Warning: Could not initialize database tables: {e}")

    # Run queue export to create site/data.json
    print("Generating initial apply queue data...")
    try:
        subprocess.run(
            [sys.executable, "listings_page.py"],
            check=True,
            capture_output=True,
            text=True
        )
        print("Apply queue data exported to site/data.json.")
    except Exception as e:
        print(f"Warning: Initial queue export failed: {e}")

    # Start the detached background workers
    print("Starting background workers (UI and API servers)...")
    try:
        subprocess.run(["bash", "scripts/workers.sh", "start"], check=True)
    except Exception as e:
        print(f"Error starting background workers: {e}")
        print("Please try starting them manually: scripts/workers.sh start")
        sys.exit(1)

    # Open local server in the user's browser
    server_url = "http://127.0.0.1:8765/"
    print(f"\nSuccess! Opening {server_url} in your browser...")
    try:
        webbrowser.open_new_tab(server_url)
    except Exception as e:
        print(f"Could not open browser automatically: {e}")
        print(f"Please open this link manually: {server_url}")

    print("\n==================================================")
    print("              Setup Complete!                    ")
    print("==================================================")
    print(f"Your Apply Queue is running at: {server_url}")
    print("To stop the servers later, run:")
    print("  scripts/workers.sh stop")
    print("==================================================\n")

if __name__ == "__main__":
    main()

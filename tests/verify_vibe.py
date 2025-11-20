import logging
from finder.vibe import VibeChecker

# Configure logging to see VibeChecker output
logging.basicConfig(level=logging.INFO)

def test_vibe():
    print("Initializing VibeChecker...")
    checker = VibeChecker()
    
    transcript = "This is a test transcript about Python programming. It is very structured and educational. We will learn about lists and loops."
    profile_summary = "Interests: Python, Programming. Level: B1."
    
    print("Running check...")
    score = checker.check(transcript, profile_summary)
    print(f"Vibe Check Score: {score}")
    
    if score > 0:
        print("SUCCESS: VibeChecker returned a valid score.")
    else:
        print("FAILURE: VibeChecker returned 0 or failed.")

if __name__ == "__main__":
    test_vibe()

import sys
import io
from pathlib import Path

if sys.platform.startswith("win"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.append(str(Path(__file__).resolve().parent))

from src.crawler import collect_hot_candidates
from src.storage import add_posts_to_storage


def run_automated_pipeline():
    print("=" * 60)
    print(" X Content Workbench - Hot candidate collection ")
    print("=" * 60)

    print("\n[*] Collecting up to 200 hot/popular titles + links...")
    all_posts = collect_hot_candidates(limit=200)

    if not all_posts:
        print("\n[!] No candidates were collected.")
        return

    print("\n" + "=" * 60)
    print(" Saving metadata index...")
    print("=" * 60)

    added_count = add_posts_to_storage(all_posts)

    print("\n" + "=" * 60)
    print(f" Done! collected={len(all_posts)}, added={added_count}")
    print("=" * 60)


if __name__ == "__main__":
    run_automated_pipeline()

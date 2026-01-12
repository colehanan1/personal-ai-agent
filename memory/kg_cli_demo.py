"""
Demo script for Knowledge Graph CLI tools.

This script demonstrates all CLI commands with example usage.
Run from project root: python -m memory.kg_cli_demo
"""

import subprocess
import sys
from pathlib import Path


def run_command(cmd: list[str], description: str) -> None:
    """Run a CLI command and display results."""
    print("\n" + "=" * 80)
    print(f"📋 {description}")
    print("-" * 80)
    print(f"$ {' '.join(cmd)}")
    print("-" * 80)
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.stdout:
        print(result.stdout)
    
    if result.returncode != 0:
        print(f"❌ Command failed with exit code {result.returncode}", file=sys.stderr)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
    else:
        print("✅ Command completed successfully")


def main():
    """Run all demo commands."""
    print("=" * 80)
    print("Knowledge Graph CLI Demo")
    print("=" * 80)
    print("\nThis demo shows all available KG CLI commands.")
    print("Prerequisites: Some memories should be stored in the system.")
    
    # Command 1: Stats
    run_command(
        ["python", "-m", "memory.kg_cli", "--stats"],
        "Show Knowledge Graph statistics"
    )
    
    # Command 2: Search entities
    run_command(
        ["python", "-m", "memory.kg_cli", "--search", "python"],
        "Search for entities containing 'python'"
    )
    
    # Command 3: Search with type filter
    run_command(
        ["python", "-m", "memory.kg_cli", "--search", "python", "--type", "tool", "--limit", "5"],
        "Search for tool entities containing 'python' (limit 5)"
    )
    
    # Command 4: Show neighbors of user entity
    run_command(
        ["python", "-m", "memory.kg_cli", "--neighbors", "entity:user:primary", "--limit", "5"],
        "Show outgoing relationships from user (limit 5)"
    )
    
    # Command 5: Show incoming neighbors
    run_command(
        ["python", "-m", "memory.kg_cli", "--neighbors", "entity:user:primary", 
         "--direction", "incoming", "--limit", "3"],
        "Show incoming relationships to user (limit 3)"
    )
    
    # Command 6: Export to file
    export_path = "/tmp/kg_export_demo.json"
    run_command(
        ["python", "-m", "memory.kg_cli", "--export", export_path],
        f"Export Knowledge Graph to {export_path}"
    )
    
    # Command 7: Show export file stats
    if Path(export_path).exists():
        print("\n" + "=" * 80)
        print("📊 Export file contents")
        print("-" * 80)
        with open(export_path) as f:
            import json
            data = json.load(f)
            print(f"Version: {data.get('version')}")
            print(f"Exported at: {data.get('exported_at')}")
            print(f"Entities: {len(data.get('entities', []))}")
            print(f"Edges: {len(data.get('edges', []))}")
            
            # Show first entity
            if data.get('entities'):
                print(f"\nFirst entity:")
                print(json.dumps(data['entities'][0], indent=2))
            
            # Show first edge
            if data.get('edges'):
                print(f"\nFirst edge:")
                print(json.dumps(data['edges'][0], indent=2))
        print("✅ Export file is valid JSON")
    
    # Command 8: Rebuild dry-run
    run_command(
        ["python", "-m", "memory.kg_cli", "--rebuild-from-memory", "--dry-run"],
        "Simulate rebuilding KG from memories (dry-run)"
    )
    
    # Summary
    print("\n" + "=" * 80)
    print("📚 CLI Command Reference")
    print("=" * 80)
    print("""
Available commands:
  --stats                    Show entity/edge counts and statistics
  --search "term"            Search for entities by name
  --search "term" --type T   Search with type filter
  --neighbors "entity"       Show entity relationships
  --export <path>            Export KG to JSON
  --import <path>            Import KG from JSON
  --import <path> --merge    Import and merge with existing KG
  --rebuild-from-memory      Rebuild KG from stored memories
  --rebuild-from-memory --dry-run  Simulate rebuild

Options:
  --limit N                  Limit results (default: 20)
  --direction DIR            Edge direction: outgoing, incoming, both
  --db-path PATH             Custom database path
  -v, --verbose              Verbose logging

Environment:
  STATE_DIR or MILTON_STATE_DIR  KG database directory
  
For more info: python -m memory.kg_cli --help
    """)
    
    print("=" * 80)
    print("✨ Demo Complete!")
    print("=" * 80)


if __name__ == "__main__":
    main()

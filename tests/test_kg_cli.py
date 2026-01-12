"""Tests for Knowledge Graph CLI"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from memory.kg_cli import (
    cmd_stats,
    cmd_search,
    cmd_neighbors,
    cmd_export,
    cmd_import,
    cmd_rebuild_from_memory,
)
from memory.kg.schema import Entity, Edge
from memory.kg.store import KnowledgeGraphStore


@pytest.fixture
def temp_kg_db():
    """Create a temporary KG database"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_kg.sqlite"
        store = KnowledgeGraphStore(db_path=db_path)
        
        # Add test data
        user_entity = store.upsert_entity(
            name="Primary User",
            entity_type="user",
        )
        
        python_entity = store.upsert_entity(
            name="Python",
            entity_type="tool",
        )
        
        project_entity = store.upsert_entity(
            name="Meshalyzer",
            entity_type="project",
        )
        
        store.upsert_edge(
            subject_id=user_entity.id,
            predicate="prefers",
            object_id=python_entity.id,
            weight=1.0,
            evidence={"memory_id": "mem_test", "src": "deterministic"},
        )
        
        store.upsert_edge(
            subject_id=user_entity.id,
            predicate="works_on",
            object_id=project_entity.id,
            weight=0.9,
            evidence={"memory_id": "mem_test2", "src": "deterministic"},
        )
        
        yield db_path


class TestCmdStats:
    """Test --stats command"""
    
    def test_stats_on_empty_db(self, capsys):
        """Should handle empty database gracefully"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "empty.sqlite"
            cmd_stats(db_path=db_path)
            
            captured = capsys.readouterr()
            assert "Total Entities: 0" in captured.out
            assert "Total Edges: 0" in captured.out
    
    def test_stats_with_data(self, temp_kg_db, capsys):
        """Should show entity and edge counts"""
        cmd_stats(db_path=temp_kg_db)
        
        captured = capsys.readouterr()
        assert "Total Entities: 3" in captured.out
        assert "Total Edges: 2" in captured.out
        assert "user" in captured.out
        assert "tool" in captured.out
        assert "project" in captured.out
        assert "prefers" in captured.out
        assert "works_on" in captured.out


class TestCmdSearch:
    """Test --search command"""
    
    def test_search_finds_entity(self, temp_kg_db, capsys):
        """Should find entities by name"""
        cmd_search(term="Python", db_path=temp_kg_db)
        
        captured = capsys.readouterr()
        assert "Python" in captured.out
        assert "[tool]" in captured.out
    
    def test_search_with_type_filter(self, temp_kg_db, capsys):
        """Should filter by entity type"""
        cmd_search(term="Python", entity_type="tool", db_path=temp_kg_db)
        
        captured = capsys.readouterr()
        assert "Python" in captured.out
        assert "[tool]" in captured.out
    
    def test_search_no_results(self, temp_kg_db, capsys):
        """Should handle no results gracefully"""
        cmd_search(term="NonexistentEntity", db_path=temp_kg_db)
        
        captured = capsys.readouterr()
        assert "No matching entities found" in captured.out


class TestCmdNeighbors:
    """Test --neighbors command"""
    
    def test_neighbors_by_id(self, temp_kg_db, capsys):
        """Should show neighbors by entity ID"""
        # Get user entity ID
        store = KnowledgeGraphStore(db_path=temp_kg_db)
        entities = store.search_entities(name="Primary User", limit=1)
        user_id = entities[0].id
        
        cmd_neighbors(entity_ref=user_id, direction="outgoing", db_path=temp_kg_db)
        
        captured = capsys.readouterr()
        assert "prefers" in captured.out
        assert "works_on" in captured.out
        assert "Python" in captured.out
        assert "Meshalyzer" in captured.out
    
    def test_neighbors_by_name(self, temp_kg_db, capsys):
        """Should resolve entity by name and show neighbors"""
        cmd_neighbors(entity_ref="Primary User", direction="outgoing", db_path=temp_kg_db)
        
        captured = capsys.readouterr()
        assert "Found entity:" in captured.out
        assert "prefers" in captured.out or "works_on" in captured.out
    
    def test_neighbors_not_found(self, temp_kg_db, capsys):
        """Should handle entity not found"""
        cmd_neighbors(entity_ref="NonexistentEntity", db_path=temp_kg_db)
        
        captured = capsys.readouterr()
        assert "No entity found" in captured.out


class TestCmdExportImport:
    """Test --export and --import commands"""
    
    def test_export_creates_file(self, temp_kg_db):
        """Should export KG to JSON file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "export.json"
            cmd_export(output_path=str(output_path), db_path=temp_kg_db)
            
            assert output_path.exists()
            
            # Verify JSON structure
            with open(output_path) as f:
                data = json.load(f)
            
            assert "entities" in data
            assert "edges" in data
            assert len(data["entities"]) == 3
            assert len(data["edges"]) == 2
    
    def test_import_from_file(self, temp_kg_db):
        """Should import KG from JSON file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Export first
            export_path = Path(tmpdir) / "export.json"
            cmd_export(output_path=str(export_path), db_path=temp_kg_db)
            
            # Create new empty database
            import_db_path = Path(tmpdir) / "import.sqlite"
            
            # Import
            cmd_import(input_path=str(export_path), db_path=import_db_path)
            
            # Verify import
            store = KnowledgeGraphStore(db_path=import_db_path)
            entities = store.search_entities(name="Python", limit=10)
            assert len(entities) == 1
            assert entities[0].name == "Python"


class TestCmdRebuildFromMemory:
    """Test --rebuild-from-memory command"""
    
    @patch("memory.kg_cli.get_backend")
    @patch("memory.kg_cli.extract_entities_and_edges")
    def test_rebuild_dry_run(self, mock_extract, mock_get_backend, capsys):
        """Should simulate rebuild without modifying database"""
        # Mock backend and memories
        mock_backend = MagicMock()
        mock_memory = MagicMock()
        mock_memory.id = "mem_test"
        mock_memory.content = "I prefer Python"
        mock_memory.tags = []
        mock_backend.list_short_term.return_value = [mock_memory]
        mock_get_backend.return_value = mock_backend
        
        # Mock extraction
        user_entity = Entity(
            id="entity:user:primary",
            type="user",
            name="Primary User",
        )
        python_entity = Entity(
            id="entity:tool:python",
            type="tool",
            name="Python",
        )
        edge = Edge(
            id="edge:test",
            subject_id=user_entity.id,
            predicate="prefers",
            object_id=python_entity.id,
            weight=1.0,
        )
        mock_extract.return_value = ([user_entity, python_entity], [edge])
        
        # Run dry run
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "rebuild.sqlite"
            cmd_rebuild_from_memory(db_path=db_path, dry_run=True)
            
            captured = capsys.readouterr()
            assert "[DRY RUN]" in captured.out
            assert "2 entities" in captured.out
            assert "1 edges" in captured.out
    
    @patch("memory.kg_cli.get_backend")
    @patch("memory.kg_cli.extract_entities_and_edges")
    def test_rebuild_actual(self, mock_extract, mock_get_backend):
        """Should rebuild KG from memories"""
        # Mock backend and memories
        mock_backend = MagicMock()
        mock_memory = MagicMock()
        mock_memory.id = "mem_test"
        mock_memory.content = "I prefer Python"
        mock_memory.tags = []
        mock_backend.list_short_term.return_value = [mock_memory]
        mock_get_backend.return_value = mock_backend
        
        # Mock extraction
        user_entity = Entity(
            id="entity:user:primary",
            type="user",
            name="Primary User",
        )
        python_entity = Entity(
            id="entity:tool:python",
            type="tool",
            name="Python",
        )
        edge = Edge(
            id="edge:test",
            subject_id=user_entity.id,
            predicate="prefers",
            object_id=python_entity.id,
            weight=1.0,
        )
        mock_extract.return_value = ([user_entity, python_entity], [edge])
        
        # Run rebuild
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "rebuild.sqlite"
            cmd_rebuild_from_memory(db_path=db_path, dry_run=False)
            
            # Verify entities were created
            store = KnowledgeGraphStore(db_path=db_path)
            entities = store.search_entities(name="Python", limit=10)
            assert len(entities) == 1
            assert entities[0].name == "Python"


class TestCLIModuleLevel:
    """Test CLI module-level functionality"""
    
    def test_cli_module_imports(self):
        """Should import CLI module without errors"""
        import memory.kg_cli
        assert hasattr(memory.kg_cli, "main")
        assert hasattr(memory.kg_cli, "cmd_stats")
        assert hasattr(memory.kg_cli, "cmd_search")
        assert hasattr(memory.kg_cli, "cmd_neighbors")
        assert hasattr(memory.kg_cli, "cmd_export")
        assert hasattr(memory.kg_cli, "cmd_import")
        assert hasattr(memory.kg_cli, "cmd_rebuild_from_memory")

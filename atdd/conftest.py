"""
Root conftest for unified test reporting across all test categories.
"""
import pytest


def pytest_configure(config):
    """Add custom metadata and markers."""
    # ATDD lifecycle markers
    config.addinivalue_line("markers", "planner: Planning phase validation tests")
    config.addinivalue_line("markers", "tester: Testing phase validation tests (contracts-as-code)")
    config.addinivalue_line("markers", "coder: Coding phase validation tests")

    # Legacy/component markers
    config.addinivalue_line("markers", "platform: Platform validation tests")
    config.addinivalue_line("markers", "backend: Backend Python tests")
    config.addinivalue_line("markers", "frontend: Frontend Preact/TypeScript tests")
    config.addinivalue_line("markers", "agents: Agent behavior tests")
    config.addinivalue_line("markers", "schemas: Schema validation tests")
    config.addinivalue_line("markers", "utils: Utility and runtime tests")
    config.addinivalue_line("markers", "contracts: Contract tests")
    config.addinivalue_line("markers", "telemetry: Telemetry tests")
    
    # Custom metadata for HTML report
    if hasattr(config, '_metadata'):
        config._metadata.update({
            "Project": "Wagons Platform",
            "Test Categories": "Platform, Backend, Agents, Schemas, Utils",
            "Environment": "Development",
        })


def pytest_collection_modifyitems(items):
    """Auto-assign category markers based on file path."""
    for item in items:
        # Get test file path
        test_path = str(item.fspath)

        # Assign ATDD lifecycle markers
        if "atdd/planner/" in test_path:
            item.add_marker(pytest.mark.planner)
        elif "atdd/tester/" in test_path:
            item.add_marker(pytest.mark.tester)
        elif "atdd/coder/" in test_path:
            item.add_marker(pytest.mark.coder)

        # Assign legacy/component markers
        elif "platform_validation" in test_path:
            item.add_marker(pytest.mark.platform)
        elif "python/" in test_path:
            item.add_marker(pytest.mark.backend)
        elif ".claude/agents/" in test_path:
            item.add_marker(pytest.mark.agents)
        elif ".claude/schemas/" in test_path:
            item.add_marker(pytest.mark.schemas)
        elif ".claude/utils/" in test_path:
            item.add_marker(pytest.mark.utils)
        elif "contracts/" in test_path:
            item.add_marker(pytest.mark.contracts)
        elif "telemetry/" in test_path:
            item.add_marker(pytest.mark.telemetry)
        elif "web/" in test_path:
            item.add_marker(pytest.mark.frontend)


def pytest_html_report_title(report):
    """Customize HTML report title."""
    report.title = "Wagons Platform - Comprehensive Test Report"


def pytest_html_results_table_header(cells):
    """Add category column to results table."""
    cells.insert(1, '<th>Category</th>')


def pytest_html_results_table_row(report, cells):
    """Add category to each test row."""
    category = "Unknown"

    if hasattr(report, 'nodeid'):
        path = report.nodeid

        # ATDD lifecycle categories
        if 'atdd/planner/' in path:
            category = '📋 Planner'
        elif 'atdd/tester/' in path:
            category = '🧪 Tester'
        elif 'atdd/coder/' in path:
            category = '⚙️ Coder'
        # Legacy categories
        elif 'platform_validation' in path:
            category = '🗺️ Platform'
        elif 'python/' in path:
            category = '🐍 Backend'
        elif '.claude/agents/' in path:
            category = '🤖 Agents'
        elif '.claude/schemas/' in path:
            category = '📋 Schemas'
        elif '.claude/utils/' in path:
            category = '🔧 Utils'
        elif 'contracts/' in path:
            category = '📄 Contracts'
        elif 'telemetry/' in path:
            category = '📊 Telemetry'
        elif 'web/' in path:
            category = '💙 Frontend'

    cells.insert(1, f'<td>{category}</td>')


def pytest_html_results_summary(prefix, summary, postfix):
    """Add custom summary header."""
    prefix.extend([
        '<div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); '
        'padding: 30px; border-radius: 10px; color: white; margin: 20px 0; text-align: center;">'
        '<h1 style="margin: 0 0 15px 0; font-size: 32px;">🚀 Wagons Platform Test Suite</h1>'
        '<p style="margin: 0; opacity: 0.9; font-size: 18px;">Comprehensive validation across all components</p>'
        '<div style="margin-top: 20px; display: flex; gap: 15px; justify-content: center; flex-wrap: wrap;">'
        '<span style="background: rgba(255,255,255,0.2); padding: 8px 16px; border-radius: 20px;">🗺️ Platform</span>'
        '<span style="background: rgba(255,255,255,0.2); padding: 8px 16px; border-radius: 20px;">🐍 Backend</span>'
        '<span style="background: rgba(255,255,255,0.2); padding: 8px 16px; border-radius: 20px;">🤖 Agents</span>'
        '<span style="background: rgba(255,255,255,0.2); padding: 8px 16px; border-radius: 20px;">📋 Schemas</span>'
        '<span style="background: rgba(255,255,255,0.2); padding: 8px 16px; border-radius: 20px;">🔧 Utils</span>'
        '</div>'
        '</div>'
    ])
